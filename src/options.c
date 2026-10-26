/* options.c */
#include "options.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

void opts_usage(void)
{
    fprintf(stderr,
        "options:\n"
        "  --proto saw|gbn|sr     ARQ protocol (default saw)\n"
        "  --window N             window size for gbn/sr (default 1)\n"
        "  --rto adaptive|MS      adaptive RTO or fixed RTO in ms (sender)\n"
        "  --expect-sha256 HEX    receiver: compare the received file's SHA-256\n"
        "                         with HEX (exit code 2 if it differs)\n"
        "  channel emulator (applies to packets THIS side sends):\n"
        "  --loss P               drop probability, 0..1 or e.g. 10%%\n"
        "  --dup P                duplication probability\n"
        "  --reorder P            reordering probability (held back 5-25 ms)\n"
        "  --corrupt P            corruption probability (one bit flipped)\n"
        "  --delay MS             one-way delay (non-blocking)\n"
        "  --jitter MS            delay varies uniformly by +/- MS\n"
        "  --seed N               random seed (default 1)\n"
        "  deterministic test hooks:\n"
        "  --drop-every N         drop every Nth packet\n"
        "  --corrupt-every N      corrupt every Nth packet\n"
        "  --delay-ms N           same as --delay\n");
}

/* "0.1" -> 0.1, "10%" -> 0.1. Returns -1 if outside 0..1. */
static double prob(const char *v)
{
    size_t n = strlen(v);
    double p = atof(v);
    if (n > 0 && v[n - 1] == '%')
        p /= 100.0;
    return (p < 0.0 || p > 1.0) ? -1.0 : p;
}

int opts_parse(int argc, char **argv, int first, opts_t *o)
{
    int i;
    memset(o, 0, sizeof(*o));
    o->proto = "saw";
    o->window = 1;
    o->chan.seed = 1;

    for (i = first; i < argc; i++) {
        const char *a = argv[i];
        const char *v = (i + 1 < argc) ? argv[i + 1] : NULL;
        double *pp = NULL;
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return -1; }

        if      (!strcmp(a, "--proto"))         o->proto = v;
        else if (!strcmp(a, "--window"))        o->window = atoi(v);
        else if (!strcmp(a, "--rto"))           o->fixed_rto = strcmp(v, "adaptive") ? atoi(v) : 0;
        else if (!strcmp(a, "--loss"))          pp = &o->chan.loss;
        else if (!strcmp(a, "--dup"))           pp = &o->chan.dup;
        else if (!strcmp(a, "--reorder"))       pp = &o->chan.reorder;
        else if (!strcmp(a, "--corrupt"))       pp = &o->chan.corrupt;
        else if (!strcmp(a, "--delay") ||
                 !strcmp(a, "--delay-ms"))      o->chan.delay_ms = atoi(v);
        else if (!strcmp(a, "--jitter"))        o->chan.jitter_ms = atoi(v);
        else if (!strcmp(a, "--seed"))          o->chan.seed = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--expect-sha256")) {
            int k;
            if (strlen(v) != SHA256_HEX_LEN) {
                fprintf(stderr, "--expect-sha256 needs %d hex characters\n", SHA256_HEX_LEN);
                return -1;
            }
            for (k = 0; k < SHA256_HEX_LEN; k++) {
                if (!isxdigit((unsigned char)v[k])) {
                    fprintf(stderr, "--expect-sha256: not a hex string\n");
                    return -1;
                }
                o->expect_sha256[k] = (char)tolower((unsigned char)v[k]);
            }
            o->expect_sha256[SHA256_HEX_LEN] = '\0';
        }
        else if (!strcmp(a, "--drop-every"))    o->chan.drop_every = atoi(v);
        else if (!strcmp(a, "--corrupt-every")) o->chan.corrupt_every = atoi(v);
        else { fprintf(stderr, "unknown option %s\n", a); return -1; }

        if (pp && (*pp = prob(v)) < 0) {
            fprintf(stderr, "%s must be between 0 and 1 (or 0%%..100%%)\n", a);
            return -1;
        }
        i++;
    }
    if (o->window < 1) o->window = 1;
    if (o->chan.delay_ms < 0 || o->chan.jitter_ms < 0) {
        fprintf(stderr, "--delay and --jitter must be >= 0\n");
        return -1;
    }
    return 0;
}
