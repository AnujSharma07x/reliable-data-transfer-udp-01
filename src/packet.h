/*
 * packet.h - Common packet format used by ALL ARQ protocols (SAW, GBN, SR).
 * Owner: Engineer 1.  Other engineers: use this, do not change the wire format
 * without telling the whole team.
 *
 * Wire format (10-byte header, multi-byte fields in network byte order):
 *
 *   offset 0  type      1 byte   PKT_HELLO / PKT_DATA / PKT_ACK
 *   offset 1  reserved  1 byte   always 0 (kept for future use)
 *   offset 2  seq       4 bytes  DATA: packet number (0,1,2,...)
 *                                ACK : number being acknowledged
 *   offset 6  len       2 bytes  payload length, 0..MAX_PAYLOAD
 *   offset 8  checksum  2 bytes  16-bit Internet checksum over header+payload
 *   offset 10 payload   len bytes
 *
 * End of file is signalled by a DATA packet with len == 0.
 * Sequence numbers are 32-bit and never wrap for our file sizes, so
 * SAW, GBN and SR can all use the same numbering.
 */
#ifndef PACKET_H
#define PACKET_H

#include <stdint.h>
#include <stddef.h>

#define MAX_PAYLOAD     1024
#define PKT_HEADER_SIZE 10
#define PKT_MAX_SIZE    (PKT_HEADER_SIZE + MAX_PAYLOAD)

enum {
    PKT_HELLO = 1,  /* client -> server: "start sending me the file" */
    PKT_DATA  = 2,  /* server -> client: file data (len 0 = end of file) */
    PKT_ACK   = 3   /* client -> server: acknowledgement */
};

/* decode() results */
#define PKT_OK            0
#define PKT_ERR_LENGTH   -1  /* too short or length field doesn't match */
#define PKT_ERR_CHECKSUM -2  /* checksum mismatch -> corrupted */

typedef struct {
    uint8_t  type;
    uint32_t seq;
    uint16_t len;
    uint8_t  payload[MAX_PAYLOAD];
} packet_t;

/* 16-bit one's-complement Internet checksum (same idea as UDP/TCP/IP). */
uint16_t checksum16(const uint8_t *data, size_t n);

/* Packet -> bytes. Fills in the checksum. Returns number of bytes written. */
int packet_encode(const packet_t *p, uint8_t *buf);

/* Bytes -> packet. Verifies the checksum. Returns PKT_OK or a PKT_ERR_* code.
 * Corrupted packets must be DROPPED by the caller (never used as data). */
int packet_decode(const uint8_t *buf, int n, packet_t *p);

#endif
