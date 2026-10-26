/*
 * sr.c - Selective Repeat ARQ.  Owner: Engineer 3.
 *
 * SENDER (window of N packets, slot = seq % N)
 *   - send while next < base + N
 *   - every unACKed packet has ITS OWN timer: its deadline is fixed when
 *     it is sent (expires_at = send time + RTO at that moment). A later
 *     backoff never stretches timers that are already running.
 *     On expiry only THAT packet is resent.
 *   - ACK k is SELECTIVE: it acknowledges packet k only.
 *   - base slides forward only over consecutive ACKed packets.
 *   - Karn: RTT sample only from a packet that was sent once.
 *   No threads: the loop sleeps until the EARLIEST packet timer.
 *
 * RECEIVER (window of N, buffer slot = seq % N)
 *   - rcv_base <= s < rcv_base+N : ACK s, buffer it (if new), then deliver
 *                                  every consecutive buffered packet.
 *   - s < rcv_base               : already delivered -> duplicate, re-ACK s
 *                                  (our first ACK may have been lost).
 *   - s >= rcv_base+N            : outside window -> ignore, no ACK.
 *   Out-of-order data is only buffered, never written early.
 *
 * EOF = DATA with len 0. It is buffered and delivered like any packet,
 * so the receiver stops only when everything before it is written.
 */
#include "arq.h"
#include "util.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define MAX_STALLS 50   /* timeout wake-ups in a row with no new ACK */

typedef struct {
    packet_t pkt;
    double   sent_at;        /* last send time (for RTT samples) */
    double   expires_at;     /* this packet's own timer deadline */
    int      retransmitted;  /* Karn: never take an RTT sample if set */
    int      acked;
} sslot_t;

static void send_slot(arq_ctx_t *ctx, sslot_t *s)
{
    s->sent_at = now_ms();
    s->expires_at = s->sent_at + rto_get_ms(&ctx->rto);   /* start its timer */
    net_send_pkt(ctx->conn, &s->pkt);
    ctx->stats.packets_sent++;
}

int sr_send(arq_ctx_t *ctx, FILE *in)
{
    int N = ctx->window;
    sslot_t *win = calloc((size_t)N, sizeof(sslot_t));
    uint32_t base = 0, next = 0, s;
    int eof_queued = 0, stalls = 0;
    uint32_t eof_seq = 0;
    packet_t ack;

    if (!win) return -1;
    ctx->stats.start_ms = now_ms();

    for (;;) {
        /* 1. Fill the window with new packets. */
        while (!eof_queued && next < base + (uint32_t)N) {
            sslot_t *sl = &win[next % N];
            memset(sl, 0, sizeof(*sl));
            sl->pkt.type = PKT_DATA;
            sl->pkt.seq = next;
            sl->pkt.len = (uint16_t)fread(sl->pkt.payload, 1, MAX_PAYLOAD, in);
            if (sl->pkt.len == 0 && ferror(in)) { perror("read input"); free(win); return -1; }
            if (sl->pkt.len == 0) { eof_queued = 1; eof_seq = next; }
            ctx->stats.file_bytes += sl->pkt.len;
            send_slot(ctx, sl);
            next++;
        }

        /* 2. Sleep until the earliest timer of an unACKed packet. */
        double earliest = -1;
        for (s = base; s < next; s++) {
            sslot_t *sl = &win[s % N];
            if (!sl->acked && (earliest < 0 || sl->expires_at < earliest))
                earliest = sl->expires_at;
        }
        int left = (int)ceil(earliest - now_ms());   /* never wake up early */
        int r = (left > 0) ? arq_wait(ctx, &ack, left) : NET_TIMEOUT;

        if (r == NET_OK) {
            if (ack.type != PKT_ACK || ack.seq < base || ack.seq >= next)
                continue;                       /* old / future ACK: ignore */
            sslot_t *sl = &win[ack.seq % N];
            if (sl->acked)
                continue;                       /* duplicate ACK: ignore */

            sl->acked = 1;                      /* selective: only packet k */
            if (!sl->retransmitted)             /* Karn */
                rto_on_sample(&ctx->rto, now_ms() - sl->sent_at);
            rto_on_progress(&ctx->rto);
            ctx->stats.acks_received++;
            stalls = 0;

            while (base < next && win[base % N].acked)
                base++;                         /* slide over ACKed packets */
            if (eof_queued && base > eof_seq)
                break;                          /* EOF ACKed: done */

        } else if (r == NET_TIMEOUT) {
            /* 3. Resend ONLY the packets whose own timer expired.
             *    Timers due within the next 1 ms (packets sent in one burst)
             *    count as ONE loss event: back off once, then resend them
             *    with the backed-off RTO. */
            double now = now_ms();
            int expired = 0;
            for (s = base; s < next; s++)
                if (!win[s % N].acked && win[s % N].expires_at <= now + 1.0)
                    expired++;
            if (expired) {
                rto_on_timeout(&ctx->rto);
                for (s = base; s < next; s++) {
                    sslot_t *sl = &win[s % N];
                    if (!sl->acked && sl->expires_at <= now + 1.0) {
                        sl->retransmitted = 1;
                        send_slot(ctx, sl);
                        ctx->stats.retransmissions++;
                        ctx->stats.timeouts++;
                    }
                }
                if (++stalls > MAX_STALLS) {
                    fprintf(stderr, "sr: no progress after %d timeouts\n", MAX_STALLS);
                    free(win);
                    return -1;
                }
            }
        } else {
            free(win);
            return -1;
        }
    }

    ctx->stats.end_ms = now_ms();
    free(win);
    return 0;
}

typedef struct {
    int      have;
    uint16_t len;
    uint8_t  data[MAX_PAYLOAD];
} rslot_t;

int sr_recv(arq_ctx_t *ctx, FILE *out)
{
    int N = ctx->window;
    rslot_t *buf = calloc((size_t)N, sizeof(rslot_t));
    uint32_t rcv_base = 0;
    int started = 0, done = 0;
    packet_t p;

    if (!buf) return -1;

    while (!done) {
        if (arq_recv_next(ctx, &p, &started) != 0) {
            free(buf);
            return -1;
        }

        if (p.seq < rcv_base) {                 /* already delivered */
            ctx->stats.duplicates++;
            arq_send_ack(ctx, p.seq);
            continue;
        }
        if (p.seq >= rcv_base + (uint32_t)N)    /* outside receive window */
            continue;

        arq_send_ack(ctx, p.seq);               /* individual ACK */
        rslot_t *sl = &buf[p.seq % N];
        if (sl->have) {                         /* already buffered */
            ctx->stats.duplicates++;
            continue;
        }
        sl->have = 1;
        sl->len = p.len;
        memcpy(sl->data, p.payload, p.len);

        /* Deliver every consecutive packet starting at rcv_base. */
        while (buf[rcv_base % N].have) {
            rslot_t *d = &buf[rcv_base % N];
            if (d->len == 0) {                  /* EOF, everything before it written */
                done = 1;
                d->have = 0;
                rcv_base++;
                break;
            }
            if (fwrite(d->data, 1, d->len, out) != d->len) { perror("write output"); free(buf); return -1; }
            ctx->stats.file_bytes += d->len;
            d->have = 0;
            rcv_base++;
        }
    }

    ctx->stats.end_ms = now_ms();
    if (fflush(out) != 0) { perror("flush output"); free(buf); return -1; }
    free(buf);
    arq_recv_linger(ctx);
    return 0;
}
