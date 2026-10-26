/*
 * hash.h - file-level integrity check (SHA-256 via OpenSSL libcrypto).
 *
 * This is NOT the packet checksum: the checksum protects each packet on the
 * wire; this hash proves the whole received FILE equals the source file.
 */
#ifndef HASH_H
#define HASH_H

#define SHA256_HEX_LEN 64

/* SHA-256 of the file's bytes, written as 64 lowercase hex chars + '\0'.
 * Returns 0 on success, -1 if the file cannot be read. */
int sha256_file(const char *path, char hex[SHA256_HEX_LEN + 1]);

#endif
