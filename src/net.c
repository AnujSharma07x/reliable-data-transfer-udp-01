/* net.c - UDP sockets. All sends go through channel_send(). */
#include "net.h"
#include "channel.h"
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <poll.h>
#include <netdb.h>
#include <arpa/inet.h>
#include <sys/socket.h>

int net_server_open(conn_t *c, int port)
{
    struct sockaddr_in addr;
    memset(c, 0, sizeof(*c));
    c->sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (c->sock < 0) { perror("socket"); return -1; }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons((uint16_t)port);
    if (bind(c->sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(c->sock);
        return -1;
    }
    return 0;
}

int net_client_open(conn_t *c, const char *host, int port)
{
    struct addrinfo hints, *res;
    memset(c, 0, sizeof(*c));
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    if (getaddrinfo(host, NULL, &hints, &res) != 0) {
        fprintf(stderr, "cannot resolve host %s\n", host);
        return -1;
    }
    c->peer = *(struct sockaddr_in *)res->ai_addr;
    c->peer.sin_port = htons((uint16_t)port);
    c->have_peer = 1;
    freeaddrinfo(res);

    c->sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (c->sock < 0) { perror("socket"); return -1; }
    return 0;
}

void net_close(conn_t *c)
{
    if (c->sock >= 0)
        close(c->sock);
}

int net_send_pkt(conn_t *c, const packet_t *p)
{
    uint8_t buf[PKT_MAX_SIZE];
    int n = packet_encode(p, buf);
    return channel_send(c->sock, buf, n,
                        (struct sockaddr *)&c->peer, sizeof(c->peer));
}

int net_recv_pkt(conn_t *c, packet_t *p, int timeout_ms)
{
    uint8_t buf[PKT_MAX_SIZE + 64];
    struct sockaddr_in from;
    socklen_t fromlen = sizeof(from);
    struct pollfd pfd = { c->sock, POLLIN, 0 };

    int r = poll(&pfd, 1, timeout_ms);
    if (r == 0) return NET_TIMEOUT;
    if (r < 0) return errno == EINTR ? NET_TIMEOUT : NET_ERROR;

    ssize_t n = recvfrom(c->sock, buf, sizeof(buf), 0,
                         (struct sockaddr *)&from, &fromlen);
    if (n < 0) return NET_ERROR;

    if (packet_decode(buf, (int)n, p) != PKT_OK)
        return NET_CORRUPT;

    if (!c->have_peer) {          /* server: remember the client */
        c->peer = from;
        c->have_peer = 1;
    }
    return NET_OK;
}
