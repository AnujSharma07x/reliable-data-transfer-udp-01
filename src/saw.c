/*
 * saw.c - Stop-and-Wait ARQ. Owner: Engineer 1.
 *
 * Sender:   send packet N -> wait for ACK N -> send N+1.
 *           No ACK before RTO expires -> resend N (and back off the RTO).
 *           Only ONE packet is outstanding at any time.
 *
 * Receiver: packet N == expected  -> write it, ACK N, expected++
 *           packet N <  expected  -> duplicate (our ACK was lost/late):
 *                                    don't write, just ACK N again
 *           corrupted packet      -> dropped by the checksum, no ACK;
 *                                    the sender's timer will resend it.
 */
#include "arq.h"
#include "util.h"
#include <string.h>

#define MAX_TRIES 50   /* give up on a packet after this many sends */

int saw_send(arq_ctx_t *ctx, FILE *in)
{
    packet_t pkt, ack;
    uint32_t seq = 0;

    ctx->window = 1;
    ctx->stats.start_ms = now_ms();

    for (;;) {
        memset(&pkt, 0, sizeof(pkt));
        pkt.type = PKT_DATA;
        pkt.seq = seq;
        pkt.len = (uint16_t)fread(pkt.payload, 1, MAX_PAYLOAD, in);
        if (pkt.len == 0 && ferror(in)) { perror("read input"); return -1; }
        /* len == 0 means end of file: send it like a normal packet */

        int tries = 0, acked = 0;
        while (!acked) {
            if (tries >= MAX_TRIES) {
                fprintf(stderr, "saw: packet %u not ACKed after %d tries\n",
                        seq, MAX_TRIES);
                return -1;
            }
            double sent_at = now_ms();
            net_send_pkt(ctx->conn, &pkt);
            ctx->stats.packets_sent++;
            if (tries > 0)
                ctx->stats.retransmissions++;
            tries++;

            /* wait for ACK seq until the timer expires */
            double deadline = sent_at + rto_get_ms(&ctx->rto);
            for (;;) {
                int left = (int)(deadline - now_ms());
                if (left <= 0 || arq_wait(ctx, &ack, left) != NET_OK)
                    break;                          /* timeout */
                if (ack.type == PKT_ACK && ack.seq == seq) {
                    acked = 1;
                    break;
                }
                /* old/duplicate ACK or stray HELLO: ignore, keep waiting */
            }

            if (acked) {
                ctx->stats.acks_received++;
                if (tries == 1)                     /* Karn: only clean samples */
                    rto_on_sample(&ctx->rto, now_ms() - sent_at);
                rto_on_progress(&ctx->rto);         /* clear backoff */
            } else {
                ctx->stats.timeouts++;
                rto_on_timeout(&ctx->rto);
            }
        }

        if (pkt.len == 0)
            break;                                  /* EOF acknowledged: done */
        ctx->stats.file_bytes += pkt.len;
        seq++;
    }

    ctx->stats.end_ms = now_ms();
    return 0;
}

int saw_recv(arq_ctx_t *ctx, FILE *out)
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
                break;                              /* EOF */
        } else if (p.seq < expected) {
            ctx->stats.duplicates++;
            arq_send_ack(ctx, p.seq);               /* re-ACK, don't write */
        }
        /* p.seq > expected can't happen in SAW: ignore */
    }

    ctx->stats.end_ms = now_ms();
    if (fflush(out) != 0) { perror("flush output"); return -1; }
    arq_recv_linger(ctx);
    return 0;
}
