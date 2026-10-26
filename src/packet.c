/* packet.c - encode/decode + checksum. See packet.h for the wire format. */
#include "packet.h"
#include <string.h>
#include <arpa/inet.h>

/*
 * Internet checksum:
 *   1. Add the data as 16-bit words (odd last byte is padded with 0).
 *   2. Fold any carry above 16 bits back into the low 16 bits.
 *   3. Take the one's complement (~).
 * Any single-bit error changes the result, so corruption is detected.
 */
uint16_t checksum16(const uint8_t *data, size_t n)
{
    uint32_t sum = 0;
    size_t i;
    for (i = 0; i + 1 < n; i += 2)
        sum += (uint32_t)((data[i] << 8) | data[i + 1]);
    if (n & 1)
        sum += (uint32_t)data[n - 1] << 8;
    while (sum >> 16)
        sum = (sum & 0xFFFF) + (sum >> 16);
    return (uint16_t)~sum;
}

int packet_encode(const packet_t *p, uint8_t *buf)
{
    uint32_t seq = htonl(p->seq);
    uint16_t len = htons(p->len);
    int total = PKT_HEADER_SIZE + p->len;

    buf[0] = p->type;
    buf[1] = 0;
    memcpy(buf + 2, &seq, 4);
    memcpy(buf + 6, &len, 2);
    buf[8] = buf[9] = 0;                       /* checksum = 0 while computing */
    memcpy(buf + PKT_HEADER_SIZE, p->payload, p->len);

    uint16_t c = htons(checksum16(buf, (size_t)total));
    memcpy(buf + 8, &c, 2);
    return total;
}

int packet_decode(const uint8_t *buf, int n, packet_t *p)
{
    uint32_t seq;
    uint16_t len, csum;
    uint8_t tmp[PKT_MAX_SIZE];

    if (n < PKT_HEADER_SIZE)
        return PKT_ERR_LENGTH;
    memcpy(&seq, buf + 2, 4);
    memcpy(&len, buf + 6, 2);
    memcpy(&csum, buf + 8, 2);
    len = ntohs(len);
    if (len > MAX_PAYLOAD || PKT_HEADER_SIZE + len != n)
        return PKT_ERR_LENGTH;

    /* Recompute the checksum with the checksum field zeroed, then compare. */
    memcpy(tmp, buf, (size_t)n);
    tmp[8] = tmp[9] = 0;
    if (checksum16(tmp, (size_t)n) != ntohs(csum))
        return PKT_ERR_CHECKSUM;

    p->type = buf[0];
    p->seq = ntohl(seq);
    p->len = len;
    memcpy(p->payload, buf + PKT_HEADER_SIZE, len);
    return PKT_OK;
}
