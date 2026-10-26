/* arq.c - protocol registry + helpers shared by all ARQ protocols. */
#include "arq.h"
#include "util.h"
#include <string.h>

#define HELLO_INTERVAL_MS 300
#define IDLE_TIMEOUT_MS   10000
#define LINGER_MS         (RTO_MAX_MS + 500)  /* quiet time > any RTO */

static const arq_protocol_t PROTOCOLS[] = {
    { "saw", saw_send, saw_recv },
    { "gbn", gbn_send, gbn_recv },
    { "sr",  sr_send,  sr_recv  },
};

const arq_protocol_t *arq_find(const char *name)
{
    size_t i;
    for (i = 0; i < sizeof(PROTOCOLS) / sizeof(PROTOCOLS[0]); i++)
        if (strcmp(PROTOCOLS[i].name, name) == 0)
            return &PROTOCOLS[i];
    return NULL;
}

int arq_wait(arq_ctx_t *ctx, packet_t *p, int timeout_ms)
{
    double deadline = now_ms() + timeout_ms;
    for (;;) {
        int left = (int)(deadline - now_ms());
        if (left <= 0)
            return NET_TIMEOUT;
        int r = net_recv_pkt(ctx->conn, p, left);
        if (r == NET_CORRUPT) { ctx->stats.corrupted++; continue; }
        return r;
    }
}

int arq_recv_next(arq_ctx_t *ctx, packet_t *p, int *started)
{
    double last_activity = now_ms();
    for (;;) {
        if (!*started) {
            packet_t hello;
            memset(&hello, 0, sizeof(hello));
            hello.type = PKT_HELLO;
            net_send_pkt(ctx->conn, &hello);
        }
        int r = net_recv_pkt(ctx->conn, p, HELLO_INTERVAL_MS);
        if (r == NET_OK && p->type == PKT_DATA) {
            if (!*started) {
                *started = 1;
                ctx->stats.start_ms = now_ms();
            }
            return 0;
        }
        if (r == NET_CORRUPT) {
            ctx->stats.corrupted++;
            last_activity = now_ms();
        }
        if (r == NET_ERROR)
            return -1;
        if (now_ms() - last_activity > IDLE_TIMEOUT_MS) {
            fprintf(stderr, "receiver: sender silent for %d ms, giving up\n",
                    IDLE_TIMEOUT_MS);
            return -1;
        }
    }
}

void arq_send_ack(arq_ctx_t *ctx, uint32_t seq)
{
    packet_t ack;
    memset(&ack, 0, sizeof(ack));
    ack.type = PKT_ACK;
    ack.seq = seq;
    net_send_pkt(ctx->conn, &ack);
}

void arq_recv_linger(arq_ctx_t *ctx)
{
    double end = now_ms() + LINGER_MS;
    packet_t p;
    for (;;) {
        int left = (int)(end - now_ms());
        if (left <= 0)
            break;
        int r = net_recv_pkt(ctx->conn, &p, left);
        if (r == NET_OK && p.type == PKT_DATA) {
            arq_send_ack(ctx, p.seq);   /* everything is received: ACK anything */
            end = now_ms() + LINGER_MS; /* sender still retrying: stay longer */
        }
    }
}

void arq_print_result(const char *proto, const arq_ctx_t *ctx, int is_sender,
                      const char *extra)
{
    const char *sep = extra ? " " : "";

    if (!extra)
        extra = "";
    const stats_t *s = &ctx->stats;
    double t = s->end_ms - s->start_ms;
    double goodput_kbps = t > 0 ? (s->file_bytes * 8.0) / t : 0.0; /* bits/ms = kbit/s */

    if (is_sender) {
        char rto_desc[32];
        if (ctx->rto.fixed)
            snprintf(rto_desc, sizeof(rto_desc), "%d", rto_get_ms(&ctx->rto));
        else
            snprintf(rto_desc, sizeof(rto_desc), "adaptive");
        printf("RESULT protocol=%s window=%d rto=%s file_bytes=%ld "
               "packets_sent=%ld retransmissions=%ld timeouts=%ld "
               "corrupted=%ld time_ms=%.1f goodput_kbps=%.1f%s%s\n",
               proto, ctx->window, rto_desc, s->file_bytes,
               s->packets_sent, s->retransmissions, s->timeouts,
               s->corrupted, t, goodput_kbps, sep, extra);
    } else {
        printf("RECV protocol=%s file_bytes=%ld duplicates=%ld corrupted=%ld "
               "time_ms=%.1f%s%s\n",
               proto, s->file_bytes, s->duplicates, s->corrupted, t, sep, extra);
    }
    fflush(stdout);
}
