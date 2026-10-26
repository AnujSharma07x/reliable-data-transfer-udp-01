/* hash.c - SHA-256 of a whole file using OpenSSL's EVP API (libcrypto). */
#include "hash.h"
#include <stdio.h>
#include <openssl/evp.h>

int sha256_file(const char *path, char hex[SHA256_HEX_LEN + 1])
{
    static const char digits[] = "0123456789abcdef";
    unsigned char buf[65536], md[EVP_MAX_MD_SIZE];
    unsigned int mdlen = 0, i;
    size_t n;
    int ok;

    FILE *f = fopen(path, "rb");
    if (!f)
        return -1;

    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    ok = ctx != NULL && EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) == 1;
    while (ok && (n = fread(buf, 1, sizeof(buf), f)) > 0)
        ok = EVP_DigestUpdate(ctx, buf, n) == 1;            /* file bytes only */
    ok = ok && !ferror(f) && EVP_DigestFinal_ex(ctx, md, &mdlen) == 1 && mdlen == 32;

    EVP_MD_CTX_free(ctx);
    fclose(f);
    if (!ok)
        return -1;

    for (i = 0; i < mdlen; i++) {
        hex[2 * i]     = digits[md[i] >> 4];
        hex[2 * i + 1] = digits[md[i] & 0x0F];
    }
    hex[SHA256_HEX_LEN] = '\0';
    return 0;
}
