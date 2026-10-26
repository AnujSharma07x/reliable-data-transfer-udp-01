/*
 * arq.h - THE INTERFACE every ARQ protocol plugs into. Owner: Engineer 1.
 *
 * To add a protocol (Engineer 2: GBN, Engineer 3: SR):
 *   1. Implement   int xxx_send(arq_ctx_t *ctx, FILE *in);
 *                  int xxx_recv(arq_ctx_t *ctx, FILE *out);
 *      in your own file (gbn.c / sr.c - stubs already exist).
 *   2. That's it. They are already registered in arq.c, so
 *      ./server ... --proto gbn  /  ./client ... --proto gbn  just works.
 *
 * Rules for every protocol:
 *   - send/receive ONLY with net_send_pkt() / net_recv_pkt()
 *     (or the arq_* helpers below) so the emulator sees every packet;
 *   - use ctx->rto for timeouts; follow Karn (see rto.h);
 *   - update ctx->stats so the RESULT line is correct;
 *   - EOF = DATA packet with len 0; sender returns 0 once it is ACKed.
 *   - return 0 on success, -1 on failure.
 */
#ifndef ARQ_H
#define ARQ_H

#include <stdio.h>
#include "net.h"
#include "rto.h"

typedef struct {
    long packets_sent;     /* every DATA packet sent, including retransmissions */
    long retransmissions;  /* DATA packets sent more than once */
    long timeouts;         /* timer expiries */
    long acks_received;    /* valid ACKs received (sender) */
    long corrupted;        /* packets dropped due to bad checksum */
    long duplicates;       /* duplicate DATA packets received (receiver) */
    long file_bytes;       /* useful file bytes sent / written */
    double start_ms, end_ms;
} stats_t;

typedef struct {
    conn_t *conn;
    rto_t   rto;
    int     window;        /* window size (SAW ignores it, always 1) */
    stats_t stats;
} arq_ctx_t;

typedef int (*arq_send_fn)(arq_ctx_t *ctx, FILE *in);
typedef int (*arq_recv_fn)(arq_ctx_t *ctx, FILE *out);

typedef struct {
    const char *name;
    arq_send_fn send;
    arq_recv_fn recv;
} arq_protocol_t;

/* "saw", "gbn", "sr" -> protocol, or NULL. */
const arq_protocol_t *arq_find(const char *name);

/* ---- Protocol entry points ---- */
int saw_send(arq_ctx_t *ctx, FILE *in);   /* Engineer 1 */
int saw_recv(arq_ctx_t *ctx, FILE *out);
int gbn_send(arq_ctx_t *ctx, FILE *in);   /* Engineer 2 */
int gbn_recv(arq_ctx_t *ctx, FILE *out);
int sr_send(arq_ctx_t *ctx, FILE *in);    /* Engineer 3 */
int sr_recv(arq_ctx_t *ctx, FILE *out);

/* ---- Shared helpers ---- */

/* Sender: wait up to timeout_ms for a valid packet. Counts corrupted ones.
 * Returns NET_OK or NET_TIMEOUT (or NET_ERROR). */
int arq_wait(arq_ctx_t *ctx, packet_t *p, int timeout_ms);

/* Receiver: get the next valid DATA packet. Sends HELLO until the transfer
 * starts. Returns 0, or -1 if the sender went silent for too long. */
int arq_recv_next(arq_ctx_t *ctx, packet_t *p, int *started);

/* Receiver: send ACK for seq. */
void arq_send_ack(arq_ctx_t *ctx, uint32_t seq);

/* Receiver: after the EOF was ACKed, keep re-ACKing for a short while in
 * case our last ACK was lost (otherwise the sender would never finish). */
void arq_recv_linger(arq_ctx_t *ctx);

/* Print the one-line machine-readable result (Engineer 4 parses this).
 * extra: optional "key=value ..." fields appended to the same line, or NULL. */
void arq_print_result(const char *proto, const arq_ctx_t *ctx, int is_sender,
                      const char *extra);

#endif
