/*
 * channel.c - network emulator behind channel_send(). Owner: Engineer 4.
 *
 * For every packet, in this order (exactly 7 random numbers are drawn per
 * packet whatever happens, so packet k always gets the same decisions for a
 * given seed):
 *   1. loss     : drop it, return as if sent
 *   2. corrupt  : flip one random bit in a COPY -> receiver checksum fails
 *   3. dup      : deliver two copies
 *   4. delay    : due = now + delay + jitter * uniform(-1, 1), but never
 *                 earlier than the previous in-order packet (FIFO, like a
 *                 real link): jitter varies timing, it does NOT reorder
 *   5. reorder  : hold an extra 5-25 ms, so packets sent later overtake it
 *                 (the ONLY way packets get reordered)
 *
 * Non-blocking delay: channel_send() only puts the packet in a queue and
 * returns. One delivery thread sleeps until the earliest due time and sends.
 * (The ARQ code waits in poll() and never calls back into the channel, so a
 * thread is the only way to release delayed packets on time.)
 * With no delay/jitter/reorder configured, packets are sent immediately.
 */
#include "channel.h"
#include "packet.h"
#include "util.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <time.h>

#define QUEUE_CAP       4096
#define REORDER_MIN_MS  5.0
#define REORDER_MAX_MS  25.0

typedef struct {
    double   due;                  /* delivery time (now_ms clock)  */
    unsigned long order;           /* FIFO tie-break for equal due  */
    int      sock, len;
    socklen_t tolen;
    struct sockaddr_storage to;
    uint8_t  buf[PKT_MAX_SIZE];
} entry_t;

static channel_cfg_t   g_cfg;
static channel_stats_t g_st;
static uint64_t        g_rng;
static long            g_count;
static int             g_use_queue;
static double          g_last_due;      /* FIFO: due time of last in-order packet */

static entry_t        *g_q;
static int             g_qn;
static unsigned long   g_order;
static int             g_thread_up;
static int             g_cond_ready;
static int             g_init_error;
static pthread_t       g_thr;
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  g_cv;

/* ---- deterministic PRNG (splitmix64): same seed -> same sequence ---- */
static uint64_t rng_next(void)
{
    uint64_t z = (g_rng += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
static double rng_unit(void)            /* uniform in [0, 1) */
{
    return (double)(rng_next() >> 11) * (1.0 / 9007199254740992.0);
}

/* ---- delivery thread ---- */
static void *delivery_thread(void *arg)
{
    (void)arg;
    pthread_mutex_lock(&g_mu);
    for (;;) {
        if (g_qn == 0) {
            pthread_cond_wait(&g_cv, &g_mu);
            continue;
        }
        int i, best = 0;
        for (i = 1; i < g_qn; i++)
            if (g_q[i].due < g_q[best].due ||
                (g_q[i].due == g_q[best].due && g_q[i].order < g_q[best].order))
                best = i;

        if (g_q[best].due <= now_ms()) {
            entry_t e = g_q[best];
            g_q[best] = g_q[--g_qn];          /* remove (order kept by 'order') */
            pthread_mutex_unlock(&g_mu);
            ssize_t sent = sendto(e.sock, e.buf, (size_t)e.len, 0,
                                  (struct sockaddr *)&e.to, e.tolen);
            pthread_mutex_lock(&g_mu);
            if (sent != e.len)
                g_st.send_errors++;
            continue;
        }
        struct timespec ts;                   /* sleep until it is due */
        double due = g_q[best].due;
        ts.tv_sec = (time_t)(due / 1000.0);
        ts.tv_nsec = (long)((due - ts.tv_sec * 1000.0) * 1e6);
        if (ts.tv_nsec >= 1000000000L) { ts.tv_sec++; ts.tv_nsec -= 1000000000L; }
        pthread_cond_timedwait(&g_cv, &g_mu, &ts);
    }
    return NULL;
}

static void print_stats(void)
{
    pthread_mutex_lock(&g_mu);
    fprintf(stderr, "CHANNEL sent=%ld dropped=%ld corrupted=%ld duplicated=%ld "
            "reordered=%ld queue_full=%ld send_errors=%ld init_errors=%ld\n",
            g_st.sent, g_st.dropped, g_st.corrupted, g_st.duplicated,
            g_st.reordered, g_st.queue_full, g_st.send_errors, g_st.init_errors);
    pthread_mutex_unlock(&g_mu);
}

void channel_init(const channel_cfg_t *cfg)
{
    static int atexit_done = 0;
    int rc = 0;

    if (!cfg) {
        g_init_error = 1;
        g_st.init_errors++;
        return;
    }

    pthread_mutex_lock(&g_mu);
    g_cfg = *cfg;
    memset(&g_st, 0, sizeof(g_st));
    g_rng = (uint64_t)cfg->seed;
    g_count = 0;
    g_qn = 0;
    g_last_due = 0;
    g_init_error = 0;
    g_use_queue = cfg->delay_ms > 0 || cfg->jitter_ms > 0 || cfg->reorder > 0;
    if (g_use_queue && !g_q)
        g_q = calloc(QUEUE_CAP, sizeof(entry_t));
    if (g_use_queue && !g_q) {
        g_init_error = 1;
        g_st.init_errors++;
    }
    pthread_mutex_unlock(&g_mu);

    if (g_use_queue && g_q && !g_thread_up) {
        pthread_condattr_t ca;
        rc = pthread_condattr_init(&ca);
        if (rc == 0) {
            rc = pthread_condattr_setclock(&ca, CLOCK_MONOTONIC);
            if (rc == 0) {
                rc = pthread_cond_init(&g_cv, &ca);
                if (rc == 0) g_cond_ready = 1;
            }
            pthread_condattr_destroy(&ca);
        }
        if (rc == 0) {
            rc = pthread_create(&g_thr, NULL, delivery_thread, NULL);
            if (rc == 0) g_thread_up = 1;
        }
        if (rc != 0) {
            pthread_mutex_lock(&g_mu);
            g_init_error = 1;
            g_st.init_errors++;
            pthread_mutex_unlock(&g_mu);
            fprintf(stderr, "channel: unable to initialize delivery thread: %s\n", strerror(rc));
        }
    }
    if (g_use_queue && !g_cond_ready) {
        pthread_mutex_lock(&g_mu);
        g_init_error = 1;
        pthread_mutex_unlock(&g_mu);
    }
    if (!atexit_done && (cfg->loss > 0 || cfg->dup > 0 || cfg->reorder > 0 ||
                         cfg->corrupt > 0 || cfg->delay_ms > 0 || cfg->jitter_ms > 0 ||
                         cfg->drop_every > 0 || cfg->corrupt_every > 0)) {
        atexit(print_stats);
        atexit_done = 1;
    }
}

void channel_get_stats(channel_stats_t *out)
{
    pthread_mutex_lock(&g_mu);
    *out = g_st;
    pthread_mutex_unlock(&g_mu);
}

int channel_send(int sock, const uint8_t *buf, int len,
                 const struct sockaddr *to, socklen_t tolen)
{
    uint8_t tmp[PKT_MAX_SIZE];
    int copies, c;

    pthread_mutex_lock(&g_mu);
    if (g_init_error || (g_use_queue && (!g_q || !g_thread_up || !g_cond_ready))) {
        g_st.init_errors++;
        pthread_mutex_unlock(&g_mu);
        errno = ENOMEM;
        return -1;
    }
    if (!buf || len <= 0 || len > PKT_MAX_SIZE || !to || tolen > sizeof(struct sockaddr_storage)) {
        pthread_mutex_unlock(&g_mu);
        errno = EINVAL;
        return -1;
    }
    g_count++;
    g_st.sent++;

    /* Always draw the same 7 numbers per packet (keeps the stream aligned). */
    double   u_loss = rng_unit(), u_corrupt = rng_unit(), u_dup = rng_unit();
    double   u_reorder = rng_unit(), u_jitter = rng_unit(), u_hold = rng_unit();
    uint64_t u_bit = rng_next();

    /* 1. loss */
    if (u_loss < g_cfg.loss ||
        (g_cfg.drop_every > 0 && g_count % g_cfg.drop_every == 0)) {
        g_st.dropped++;
        pthread_mutex_unlock(&g_mu);
        return len;
    }

    /* 2. corruption: flip one bit of a copy (caller's buffer untouched) */
    memcpy(tmp, buf, (size_t)len);
    if (u_corrupt < g_cfg.corrupt ||
        (g_cfg.corrupt_every > 0 && g_count % g_cfg.corrupt_every == 0)) {
        tmp[u_bit % (uint64_t)len] ^= (uint8_t)(1u << ((u_bit >> 32) % 8));
        g_st.corrupted++;
    }

    /* 3. duplication */
    copies = (u_dup < g_cfg.dup) ? 2 : 1;
    if (copies == 2)
        g_st.duplicated++;

    if (!g_use_queue) {                       /* no delay configured: send now */
        int failed = 0;
        for (c = 0; c < copies; c++) {
            ssize_t sent = sendto(sock, tmp, (size_t)len, 0, to, tolen);
            if (sent != len) {
                g_st.send_errors++;
                failed = 1;
            }
        }
        pthread_mutex_unlock(&g_mu);
        if (failed) return -1;
        return len;
    }

    /* 4. delay + jitter, 5. reordering */
    double d = g_cfg.delay_ms + g_cfg.jitter_ms * (2.0 * u_jitter - 1.0);
    if (d < 0) d = 0;
    double due = now_ms() + d;
    if (u_reorder < g_cfg.reorder) {
        /* held back: later packets overtake it (does not move g_last_due) */
        due += REORDER_MIN_MS + u_hold * (REORDER_MAX_MS - REORDER_MIN_MS);
        g_st.reordered++;
    } else {
        if (due < g_last_due)
            due = g_last_due;               /* FIFO: never overtake */
        g_last_due = due;
    }

    for (c = 0; c < copies; c++) {
        if (g_qn >= QUEUE_CAP) {              /* like a full router queue */
            g_st.queue_full++;
            pthread_mutex_unlock(&g_mu);
            errno = ENOBUFS;
            return -1;
        }
        entry_t *e = &g_q[g_qn++];
        e->due = due;
        e->order = g_order++;
        e->sock = sock;
        e->len = len;
        e->tolen = tolen;
        memcpy(&e->to, to, tolen);
        memcpy(e->buf, tmp, (size_t)len);
    }
    pthread_cond_signal(&g_cv);
    pthread_mutex_unlock(&g_mu);
    return len;
}
