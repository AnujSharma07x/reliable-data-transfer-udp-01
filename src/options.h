/* options.h - command-line options shared by server and client. */
#ifndef OPTIONS_H
#define OPTIONS_H

#include "channel.h"
#include "hash.h"

typedef struct {
    const char   *proto;      /* --proto saw|gbn|sr        (default saw)      */
    int           window;     /* --window N                (default 1)        */
    int           fixed_rto;  /* --rto adaptive|<ms>       (default adaptive) */
    channel_cfg_t chan;       /* emulator options (see opts_usage)             */
    char          expect_sha256[SHA256_HEX_LEN + 1];  /* --expect-sha256 HEX, "" = none */
} opts_t;

/* Parse argv[first..]. Returns 0 or -1 on a bad option. */
int opts_parse(int argc, char **argv, int first, opts_t *o);
void opts_usage(void);

#endif
