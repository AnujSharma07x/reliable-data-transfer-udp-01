/*
 * channel.h - network emulator. Every outgoing packet passes through here:
 *
 *   net_send_pkt() -> channel_send() -> [loss/corrupt/dup/delay/reorder] -> sendto()
 *
 * Owner: Engineer 4. channel_send() and channel_init() are the frozen
 * interface; ARQ code never calls sendto() directly, so SAW/GBN/SR stay
 * independent of the emulator.
 *
 * Applied independently on each side (server DATA path, client ACK path),
 * so e.g. delay 20 ms gives an RTT of about 40 ms.
 */
#ifndef CHANNEL_H
#define CHANNEL_H

#include <sys/socket.h>
#include <stdint.h>

typedef struct {
    /* probabilities, 0.0 .. 1.0 */
    double   loss;           /* silently drop the packet                */
    double   dup;            /* deliver the packet twice                */
    double   reorder;        /* hold it back 5-25 ms so later ones pass */
    double   corrupt;        /* flip one random bit (checksum fails)    */
    int      delay_ms;       /* one-way delay                           */
    int      jitter_ms;      /* delay varies uniformly in +/- jitter    */
    unsigned long seed;      /* same seed + config -> same decisions    */

    /* deterministic test hooks (kept for the exact-value regression tests) */
    int drop_every;          /* drop every Nth packet (0 = off)         */
    int corrupt_every;       /* corrupt every Nth packet (0 = off)      */
} channel_cfg_t;

typedef struct {
    long sent, dropped, corrupted, duplicated, reordered, queue_full;
    long send_errors, init_errors;
} channel_stats_t;

void channel_init(const channel_cfg_t *cfg);

/* Same contract as sendto(): returns len (even if intentionally dropped or
 * queued for delayed delivery), or -1 for immediate validation/socket/queue
 * errors. Errors that occur later in the delivery thread are counted in
 * send_errors because the originating call has already returned. Never blocks. */
int channel_send(int sock, const uint8_t *buf, int len,
                 const struct sockaddr *to, socklen_t tolen);

/* Counters since channel_init(). Also printed to stderr at exit as a
 * "CHANNEL ..." line when any impairment is configured. */
void channel_get_stats(channel_stats_t *out);

#endif
