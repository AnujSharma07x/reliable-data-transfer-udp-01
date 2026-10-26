/*
 * client.c - RECEIVER. Sends HELLO to the server, receives the file with the
 * chosen ARQ protocol and writes it to <outfile>.
 *
 *   ./client <host> <port> <outfile> [--proto saw|gbn|sr] [--window N]
 *            [--expect-sha256 HEX]
 *
 * Integrity: AFTER the protocol has delivered EOF and the file is closed,
 * the SHA-256 of the received file is computed and reported as
 * received_sha256=<hex>. With --expect-sha256 (the source file's hash,
 * obtained out-of-band) it also reports hash_match=1|0 and exits with
 * code 2 if the hashes differ.
 *
 * Exit codes: 0 = complete (and hash matches, if checked),
 *             1 = transfer failed, 2 = complete but hash mismatch.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include "arq.h"
#include "options.h"
#include "hash.h"

static int parse_port(const char *text, int *port)
{
    char *end;
    long value;
    errno = 0;
    value = strtol(text, &end, 10);
    if (errno || end == text || *end != '\0' || value < 1 || value > 65535)
        return -1;
    *port = (int)value;
    return 0;
}

int main(int argc, char **argv)
{
    opts_t opt;
    conn_t conn;
    arq_ctx_t ctx;
    char got[SHA256_HEX_LEN + 1];
    char extra[64 + SHA256_HEX_LEN];
    int match = 1;
    int port;

    if (argc < 4 || opts_parse(argc, argv, 4, &opt) != 0) {
        fprintf(stderr, "usage: %s <host> <port> <outfile> [options]\n", argv[0]);
        opts_usage();
        return 1;
    }
    if (parse_port(argv[2], &port) != 0) { fprintf(stderr, "invalid port: %s\n", argv[2]); return 1; }
    const arq_protocol_t *proto = arq_find(opt.proto);
    if (!proto) { fprintf(stderr, "unknown protocol %s\n", opt.proto); return 1; }

    FILE *out = fopen(argv[3], "wb");
    if (!out) { perror(argv[3]); return 1; }

    channel_init(&opt.chan);
    if (net_client_open(&conn, argv[1], port) != 0) {
        fclose(out);
        return 1;
    }

    memset(&ctx, 0, sizeof(ctx));
    ctx.conn = &conn;
    ctx.window = opt.window;
    rto_init(&ctx.rto, opt.fixed_rto);

    int rc = proto->recv(&ctx, out);
    if (fclose(out) != 0)
        rc = -1;                          /* data may not have reached disk */
    net_close(&conn);
    if (rc != 0) {
        fprintf(stderr, "client: transfer FAILED\n");
        return 1;
    }

    /* Whole file received, written and closed: now hash it. */
    if (sha256_file(argv[3], got) != 0) {
        perror(argv[3]);
        return 1;
    }
    if (opt.expect_sha256[0]) {
        match = strcmp(got, opt.expect_sha256) == 0;
        snprintf(extra, sizeof(extra), "received_sha256=%s hash_match=%d", got, match);
        fprintf(stderr, "File Integrity: %s\n", match ? "PASSED" : "FAILED");
    } else {
        snprintf(extra, sizeof(extra), "received_sha256=%s", got);
    }
    arq_print_result(proto->name, &ctx, 0, extra);
    return match ? 0 : 2;
}
