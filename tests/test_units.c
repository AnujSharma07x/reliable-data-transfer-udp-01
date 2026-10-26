/* test_units.c - unit tests for the packet layer, the RTO estimator and SHA-256. */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <arpa/inet.h>
#include "packet.h"
#include "rto.h"
#include "hash.h"

static int failures = 0;
#define CHECK(cond, msg) do { \
    if (cond) printf("  PASS  %s\n", msg); \
    else { printf("  FAIL  %s\n", msg); failures++; } } while (0)

static void test_packet(void)
{
    packet_t a, b;
    uint8_t buf[PKT_MAX_SIZE];
    int i, n;

    printf("[packet]\n");
    memset(&a, 0, sizeof(a));
    a.type = PKT_DATA; a.seq = 123456; a.len = 500;
    for (i = 0; i < a.len; i++) a.payload[i] = (uint8_t)(i * 7);

    n = packet_encode(&a, buf);
    CHECK(n == PKT_HEADER_SIZE + 500, "encoded size = header + payload");
    CHECK(packet_decode(buf, n, &b) == PKT_OK, "valid packet decodes");
    CHECK(b.type == a.type && b.seq == a.seq && b.len == a.len &&
          memcmp(a.payload, b.payload, a.len) == 0, "fields survive round trip");

    buf[PKT_HEADER_SIZE + 10] ^= 0x01;
    CHECK(packet_decode(buf, n, &b) == PKT_ERR_CHECKSUM, "1-bit payload error detected");
    buf[PKT_HEADER_SIZE + 10] ^= 0x01;

    buf[3] ^= 0x80;
    CHECK(packet_decode(buf, n, &b) == PKT_ERR_CHECKSUM, "corrupted seq number detected");
    buf[3] ^= 0x80;

    CHECK(packet_decode(buf, n - 1, &b) == PKT_ERR_LENGTH, "truncated packet rejected");

    memset(&a, 0, sizeof(a));
    a.type = PKT_ACK; a.seq = 7;
    n = packet_encode(&a, buf);
    CHECK(n == PKT_HEADER_SIZE && packet_decode(buf, n, &b) == PKT_OK &&
          b.type == PKT_ACK && b.seq == 7, "empty ACK packet round trip");

#ifdef PKT_ERR_FIELD
    buf[0] = 99;
    /* Recompute checksum so this specifically tests field validation. */
    buf[8] = buf[9] = 0;
    uint16_t c = htons(checksum16(buf, (size_t)n));
    memcpy(buf + 8, &c, sizeof(c));
    CHECK(packet_decode(buf, n, &b) == PKT_ERR_FIELD, "unknown packet type rejected");

    a.type = PKT_ACK; a.len = 1;
    CHECK(packet_encode(&a, buf) == -1, "ACK with payload rejected by encoder");
    a.type = PKT_DATA; a.len = MAX_PAYLOAD + 1;
    CHECK(packet_encode(&a, buf) == -1, "oversized payload rejected by encoder");

    memset(&a, 0, sizeof(a)); a.type = PKT_DATA; a.len = 1;
    n = packet_encode(&a, buf);
    buf[1] = 1;
    buf[8] = buf[9] = 0;
    c = htons(checksum16(buf, (size_t)n));
    memcpy(buf + 8, &c, sizeof(c));
    CHECK(packet_decode(buf, n, &b) == PKT_ERR_FIELD, "nonzero reserved byte rejected");
#endif
}

static void test_rto(void)
{
    rto_t r;
    int i;

    printf("[rto]\n");
    rto_init(&r, 0);
    CHECK(rto_get_ms(&r) == (int)RTO_INITIAL_MS, "initial RTO before any sample");

    rto_on_sample(&r, 100);              /* SRTT=100, RTTVAR=50 -> RTO=300 */
    CHECK(fabs(r.srtt - 100) < 1e-9 && fabs(r.rttvar - 50) < 1e-9 &&
          rto_get_ms(&r) == 300, "first sample: SRTT=RTT, RTTVAR=RTT/2, RTO=300");

    rto_on_sample(&r, 100);              /* RTTVAR=0.75*50+0=37.5 SRTT=100 RTO=250 */
    CHECK(rto_get_ms(&r) == 250, "second sample follows Jacobson/Karels");

    for (i = 0; i < 100; i++) rto_on_sample(&r, 100);
    CHECK(rto_get_ms(&r) == 110,
          "stable RTT -> RTO converges to RTT + G (RFC 6298 margin)");

    int before = rto_get_ms(&r);
    rto_on_timeout(&r);
    CHECK(rto_get_ms(&r) == 2 * before, "timeout doubles RTO (backoff)");
    for (i = 0; i < 20; i++) rto_on_timeout(&r);
    CHECK(rto_get_ms(&r) == (int)RTO_MAX_MS, "backoff is capped at RTO_MAX");

    rto_init(&r, 0);
    rto_on_sample(&r, 100);              /* RTO = 300 */
    rto_on_timeout(&r); rto_on_timeout(&r);
    CHECK(rto_get_ms(&r) == 1200, "two timeouts -> 4x RTO");
    rto_on_progress(&r);
    CHECK(rto_get_ms(&r) == 300, "ACK of new data clears backoff (no Karn sample needed)");

    rto_init(&r, 0);
    rto_on_sample(&r, 0.05);
    CHECK(rto_get_ms(&r) == (int)RTO_MIN_MS, "tiny RTT clamps to RTO_MIN");

    rto_init(&r, 75);
    rto_on_sample(&r, 500);
    rto_on_timeout(&r);
    CHECK(rto_get_ms(&r) == 75, "fixed RTO ignores samples and timeouts");
}

/* write n bytes of data (or n x 'a') to path */
static void write_file(const char *path, const char *data, size_t n, int repeat_a)
{
    FILE *f = fopen(path, "wb");
    size_t i;
    if (repeat_a) for (i = 0; i < n; i++) fputc('a', f);
    else          fwrite(data, 1, n, f);
    fclose(f);
}

static void test_hash(void)
{
    char hex[SHA256_HEX_LEN + 1];
    const char *p = "test_units_hash.tmp";

    printf("[hash]\n");
    /* Official FIPS 180-2 / NIST test vectors */
    write_file(p, "", 0, 0);
    CHECK(sha256_file(p, hex) == 0 &&
          !strcmp(hex, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
          "SHA-256(empty file) = NIST vector");
    write_file(p, "abc", 3, 0);
    CHECK(sha256_file(p, hex) == 0 &&
          !strcmp(hex, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
          "SHA-256(\"abc\") = NIST vector");
    write_file(p, "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", 56, 0);
    CHECK(sha256_file(p, hex) == 0 &&
          !strcmp(hex, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
          "SHA-256(448-bit message) = NIST vector");
    write_file(p, NULL, 1000000, 1);   /* > 64 KiB: exercises the chunked read loop */
    CHECK(sha256_file(p, hex) == 0 &&
          !strcmp(hex, "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
          "SHA-256(one million 'a') = NIST vector (multi-chunk read)");
    remove(p);
    CHECK(sha256_file("no/such/file", hex) == -1, "missing file returns -1");
}

int main(void)
{
    test_packet();
    test_rto();
    test_hash();
    printf(failures ? "\n%d unit test(s) FAILED\n" : "\nall unit tests passed\n",
           failures);
    return failures ? 1 : 0;
}
