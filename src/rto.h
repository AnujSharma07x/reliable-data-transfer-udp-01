/*
 * rto.h - Retransmission timeout (Jacobson/Karels + Karn). Owner: Engineer 1.
 *
 * Every protocol (SAW, GBN, SR) uses ONE rto_t from the sender context.
 *
 *   RTT     = time from sending a packet to receiving its ACK
 *   SRTT    = smoothed (average) RTT
 *   RTTVAR  = how much RTT jumps around
 *   RTO     = SRTT + 4 * RTTVAR       ("average + safety margin")
 *
 * First sample:  SRTT = RTT,  RTTVAR = RTT / 2
 * Later samples: RTTVAR = 3/4 * RTTVAR + 1/4 * |SRTT - RTT|
 *                SRTT   = 7/8 * SRTT   + 1/8 * RTT
 *
 * KARN'S ALGORITHM (caller's job):
 *   Only call rto_on_sample() for a packet that was sent EXACTLY ONCE.
 *   If it was retransmitted we can't tell which copy the ACK belongs to,
 *   so the measurement is ambiguous and must be thrown away.
 *   On a timeout call rto_on_timeout(), which doubles the RTO (backoff).
 *
 * BACKOFF RESET:
 *   When an ACK confirms NEW data, call rto_on_progress(). This clears the
 *   backoff (like Linux TCP). Without it, GBN gets stuck: after a timeout
 *   every in-flight packet is a retransmission, Karn discards every sample,
 *   and the RTO would stay at its 2 s cap forever.
 *
 *   Effective timeout = RTO estimate x backoff, clamped to [MIN, MAX].
 *
 * Fixed mode (for Engineer 4's RTO-sensitivity experiment):
 *   rto_init(&r, 100) -> RTO stays 100 ms forever, no backoff.
 */
#ifndef RTO_H
#define RTO_H

#define RTO_INITIAL_MS 200.0
#define RTO_MIN_MS      20.0
#define RTO_MAX_MS    2000.0

typedef struct {
    double srtt;
    double rttvar;
    double rto;         /* estimate from SRTT/RTTVAR (no backoff) */
    int    backoff;     /* 1, 2, 4, ... doubled on each timeout   */
    int    has_sample;
    int    fixed;       /* 1 = fixed RTO, ignore samples/timeouts */
} rto_t;

/* fixed_ms > 0 : fixed RTO of that many ms.   fixed_ms <= 0 : adaptive. */
void rto_init(rto_t *r, int fixed_ms);
void rto_on_sample(rto_t *r, double rtt_ms);
void rto_on_timeout(rto_t *r);
void rto_on_progress(rto_t *r);
int  rto_get_ms(const rto_t *r);

#endif
