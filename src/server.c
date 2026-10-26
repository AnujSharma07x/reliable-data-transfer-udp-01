/*
 * server.c - SENDER. Waits for a client's HELLO, then sends the file
 * using the chosen ARQ protocol and prints a RESULT line.
 *
 * Integrity: the SHA-256 of the source file is computed BEFORE the transfer
 * (so it is not counted in time_ms) and reported as source_sha256=<hex>.
 *
 *   ./server <port> <file> [--proto saw|gbn|sr] [--window N] [--rto adaptive|MS]
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
    packet_t p;
    char src_hash[SHA256_HEX_LEN + 1];
    char extra[32 + SHA256_HEX_LEN];
    int port;

    if (argc < 3 || opts_parse(argc, argv, 3, &opt) != 0) {
        fprintf(stderr, "usage: %s <port> <file> [options]\n", argv[0]);
        opts_usage();
        return 1;
    }
    if (parse_port(argv[1], &port) != 0) { fprintf(stderr, "invalid port: %s\n", argv[1]); return 1; }
    const arq_protocol_t *proto = arq_find(opt.proto);
    if (!proto) { fprintf(stderr, "unknown protocol %s\n", opt.proto); return 1; }

    if (sha256_file(argv[2], src_hash) != 0) { perror(argv[2]); return 1; }
    FILE *in = fopen(argv[2], "rb");
    if (!in) { perror(argv[2]); return 1; }

    channel_init(&opt.chan);
    if (net_server_open(&conn, port) != 0) {
        fclose(in);
        return 1;
    }

    fprintf(stderr, "server: waiting for client on port %s ...\n", argv[1]);
    while (!(net_recv_pkt(&conn, &p, -1) == NET_OK && p.type == PKT_HELLO))
        ;   /* ignore anything else until a valid HELLO arrives */
    fprintf(stderr, "server: client connected, sending %s with %s\n",
            argv[2], proto->name);

    memset(&ctx, 0, sizeof(ctx));
    ctx.conn = &conn;
    ctx.window = opt.window;
    rto_init(&ctx.rto, opt.fixed_rto);

    int rc = proto->send(&ctx, in);
    if (rc == 0) {
        snprintf(extra, sizeof(extra), "source_sha256=%s", src_hash);
        arq_print_result(proto->name, &ctx, 1, extra);
    } else {
        fprintf(stderr, "server: transfer FAILED\n");
    }

    fclose(in);
    net_close(&conn);
    return rc == 0 ? 0 : 1;
}
