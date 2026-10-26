/* rto.c - Jacobson/Karels RTO estimation. See rto.h for the formulas. */
#include "rto.h"
#include <math.h>
#include <string.h>

#define ALPHA 0.125   /* weight of a new RTT in SRTT   (1/8) */
#define BETA  0.25    /* weight of a new error in RTTVAR (1/4) */
#define RTO_G_MS 10.0 /* minimum safety margin above SRTT */

static double clamp(double v)
{
    if (v < RTO_MIN_MS) return RTO_MIN_MS;
    if (v > RTO_MAX_MS) return RTO_MAX_MS;
    return v;
}

void rto_init(rto_t *r, int fixed_ms)
{
    memset(r, 0, sizeof(*r));
    r->backoff = 1;
    if (fixed_ms > 0) {
        r->fixed = 1;
        r->rto = clamp(fixed_ms);       /* keep below receiver linger */
    } else {
        r->rto = RTO_INITIAL_MS;
    }
}

void rto_on_sample(rto_t *r, double rtt_ms)
{
    if (r->fixed)
        return;
    if (!r->has_sample) {
        r->srtt = rtt_ms;
        r->rttvar = rtt_ms / 2.0;
        r->has_sample = 1;
    } else {
        /* update RTTVAR first: it uses the OLD srtt */
        r->rttvar = (1.0 - BETA) * r->rttvar + BETA * fabs(r->srtt - rtt_ms);
        r->srtt   = (1.0 - ALPHA) * r->srtt + ALPHA * rtt_ms;
    }
    r->rto = clamp(r->srtt + fmax(RTO_G_MS, 4.0 * r->rttvar));  /* RFC 6298 */
    r->backoff = 1;                 /* fresh estimate: no backoff needed */
}

void rto_on_timeout(rto_t *r)
{
    if (r->fixed)
        return;
    if (r->rto * r->backoff < RTO_MAX_MS)
        r->backoff *= 2;            /* exponential backoff */
}

void rto_on_progress(rto_t *r)
{
    r->backoff = 1;                 /* new data ACKed: network works again */
}

int rto_get_ms(const rto_t *r)
{
    return (int)(clamp(r->rto * r->backoff) + 0.5);
}
