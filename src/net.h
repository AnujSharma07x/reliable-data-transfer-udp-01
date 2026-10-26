/* net.h - UDP socket layer shared by all protocols. */
#ifndef NET_H
#define NET_H

#include <netinet/in.h>
#include "packet.h"

typedef struct {
    int sock;
    struct sockaddr_in peer;  /* who we talk to */
    int have_peer;            /* server learns the peer from the first valid packet */
} conn_t;

/* net_recv_pkt() results */
#define NET_OK       1
#define NET_TIMEOUT  0
#define NET_CORRUPT -1   /* bad checksum/length: already dropped, just count it */
#define NET_ERROR   -2

int net_server_open(conn_t *c, int port);
int net_client_open(conn_t *c, const char *host, int port);
void net_close(conn_t *c);

/* Encode + send through the channel (emulator). */
int net_send_pkt(conn_t *c, const packet_t *p);

/* Wait up to timeout_ms (-1 = forever) for one packet and decode it. */
int net_recv_pkt(conn_t *c, packet_t *p, int timeout_ms);

#endif
