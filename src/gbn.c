/*
 * gbn.c - Go-Back-N ARQ.  Owner: Engineer 2.
 *
 * Sender keeps a window of up to N unacknowledged packets:
 *
 *        base                  next
 *         |                     |
 *   ... [ 5 ][ 6 ][ 7 ][ 8 ] [ 9 ] ...
 *         sent, not ACKed     can send
 *
 *   - send while next < base + N
 *   - ACK k is CUMULATIVE: "I have everything up to k" -> base = k + 1
 *   - ONE timer, for the oldest unACKed packet (base)
 *   - timeout -> resend EVERYTHING from base to next-1 ("go back N")
 *
 * Receiver accepts packets ONLY in order:
 *   - seq == expected -> write it, ACK it, expected++
 *   - anything else   -> discard, re-ACK the last in-order packet (expected-1)
 *   No buffering: out-of-order packets are simply resent by the sender.
 *
 * Karn: an RTT sample is taken only from a packet that was sent once.
 */
#include "arq.h"
#include "util.h"
#include <stdlib.h>
#include <string.h>

#define MAX_TIMEOUTS_IN_A_ROW 50

typedef struct {
    packet_t pkt;
    double   sent_at;      /* time of the most recent send */
    int      retransmitted;
} slot_t;

int gbn_send(arq_ctx_t *ctx, FILE *in)
{
    int N = ctx->window;
    slot_t *win = calloc((size_t)N, sizeof(slot_t));  /* slot = seq % N */
    uint32_t base = 0, next = 0;
    int eof_queued = 0;        /* EOF packet (len 0) is in the window */
    uint32_t eof_seq = 0;
    double timer_start = 0;
    int timeouts_in_a_row = 0;
    packet_t ack;

    if (!win) return -1;
    ctx->stats.start_ms = now_ms();

    for (;;) {
        /* 1. Fill the window. */
        while (!eof_queued && next < base + (uint32_t)N) {
            slot_t *s = &win[next % N];
            memset(s, 0, sizeof(*s));
            s->pkt.type = PKT_DATA;
            s->pkt.seq = next;
            s->pkt.len = (uint16_t)fread(s->pkt.payload, 1, MAX_PAYLOAD, in);
            if (s->pkt.len == 0 && ferror(in)) { perror("read input"); free(win); return -1; }
            if (s->pkt.len == 0) { eof_queued = 1; eof_seq = next; }
            ctx->stats.file_bytes += s->pkt.len;

            s->sent_at = now_ms();
            net_send_pkt(ctx->conn, &s->pkt);
            ctx->stats.packets_sent++;
            if (next == base)
                timer_start = s->sent_at;        /* timer runs for base */
            next++;
        }

        /* 2. Wait for an ACK until the timer for base expires. */
        int left = (int)(timer_start + rto_get_ms(&ctx->rto) - now_ms());
        int r = (left > 0) ? arq_wait(ctx, &ack, left) : NET_TIMEOUT;

        if (r == NET_OK) {
            if (ack.type != PKT_ACK || ack.seq < base || ack.seq >= next)
                continue;                        /* old/duplicate ACK: ignore */

            /* Cumulative ACK: everything up to ack.seq is received. */
            slot_t *acked = &win[ack.seq % N];
            if (!acked->retransmitted)           /* Karn */
                rto_on_sample(&ctx->rto, now_ms() - acked->sent_at);
            rto_on_progress(&ctx->rto);          /* new data ACKed: clear backoff */
            ctx->stats.acks_received++;
            timeouts_in_a_row = 0;

            base = ack.seq + 1;                  /* slide the window */
            if (eof_queued && base > eof_seq)
                break;                           /* EOF ACKed: done */
            timer_start = now_ms();              /* restart timer for new base */

        } else if (r == NET_TIMEOUT) {
            /* 3. Timeout: go back and resend base .. next-1. */
            ctx->stats.timeouts++;
            rto_on_timeout(&ctx->rto);
            if (++timeouts_in_a_row > MAX_TIMEOUTS_IN_A_ROW) {
                fprintf(stderr, "gbn: no progress after %d timeouts\n",
                        MAX_TIMEOUTS_IN_A_ROW);
                free(win);
                return -1;
            }
            uint32_t s;
            for (s = base; s < next; s++) {
                slot_t *sl = &win[s % N];
                sl->retransmitted = 1;
                sl->sent_at = now_ms();
                net_send_pkt(ctx->conn, &sl->pkt);
                ctx->stats.packets_sent++;
                ctx->stats.retransmissions++;
            }
            timer_start = now_ms();
        } else {
            free(win);
            return -1;
        }
    }

    ctx->stats.end_ms = now_ms();
    free(win);
    return 0;
}

int gbn_recv(arq_ctx_t *ctx, FILE *out)
{
    packet_t p;
    uint32_t expected = 0;
    int started = 0;

    for (;;) {
        if (arq_recv_next(ctx, &p, &started) != 0)
            return -1;

        if (p.seq == expected) {
            if (p.len > 0) {
                if (fwrite(p.payload, 1, p.len, out) != p.len) { perror("write output"); return -1; }
                ctx->stats.file_bytes += p.len;
            }
            arq_send_ack(ctx, p.seq);
            expected++;
            if (p.len == 0)
                break;                           /* EOF */
        } else {
            if (p.seq < expected)
                ctx->stats.duplicates++;
            /* out of order or duplicate: discard, re-ACK last in-order packet */
            if (expected > 0)
                arq_send_ack(ctx, expected - 1);
        }
    }

    ctx->stats.end_ms = now_ms();
    if (fflush(out) != 0) { perror("flush output"); return -1; }
    arq_recv_linger(ctx);
    return 0;
}
