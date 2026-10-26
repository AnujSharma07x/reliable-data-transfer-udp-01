/* util.h - small time helpers. */
#ifndef UTIL_H
#define UTIL_H

#include <time.h>

/* Monotonic time in milliseconds (not affected by clock changes). */
static inline double now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static inline void sleep_ms(int ms)
{
    struct timespec ts = { ms / 1000, (long)(ms % 1000) * 1000000L };
    nanosleep(&ts, NULL);
}

#endif
