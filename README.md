# Reliable Data Transfer over UDP (P3)

CS-30003 · CSE 33 · Team: Anuj Sharma, Bhuvika Naulani, Divyanshi Agrawal, Dhruv Singh Laishram

A server sends a file to a client over UDP. Reliability is added on top with
sequence numbers, checksums, ACKs and retransmissions, using one of three ARQ
protocols: Stop-and-Wait (`saw`), Go-Back-N (`gbn`), Selective Repeat (`sr`).

## Build

```
make            # builds ./server ./client ./test_units ./test_channel
make test       # unit, channel, end-to-end, packet-level and hash tests
```

Needs gcc, Linux/macOS (POSIX sockets) and OpenSSL's libcrypto for SHA-256
(Ubuntu/Debian: `sudo apt install libssl-dev`). Python 3 is used only by the
test scripts.

## Run

```
# terminal 1 (sender)
./server 9000 input.bin --proto saw

# terminal 2 (receiver)
./client 127.0.0.1 9000 output.bin --proto saw

cmp input.bin output.bin && echo "files identical"

# with integrity check: give the receiver the source file's SHA-256
./client 127.0.0.1 9000 output.bin --proto saw --expect-sha256 $(sha256sum input.bin | cut -d' ' -f1)
```

Options (both sides): `--proto saw|gbn|sr`, `--window N`.
Sender only: `--rto adaptive` (default) or `--rto 100` (fixed 100 ms).
Channel emulator (pass the same flags to both sides): `--loss P`, `--dup P`,
`--reorder P`, `--corrupt P`, `--delay MS`, `--jitter MS`, `--seed N`.
Receiver only: `--expect-sha256 HEX`.

The server prints one machine-readable line at the end (the hash of the
source file is appended); the client prints a matching RECV line:

```
RESULT protocol=sr window=8 rto=adaptive file_bytes=1048576 packets_sent=1315 retransmissions=290 timeouts=290 corrupted=133 time_ms=4041.7 goodput_kbps=2075.5 source_sha256=90483e6b...
RECV protocol=sr file_bytes=1048576 duplicates=133 corrupted=157 time_ms=4041.6 received_sha256=90483e6b... hash_match=1
```

`hash_match` appears only when `--expect-sha256` is given. Client exit code:
0 = complete (and hash matches), 1 = transfer failed, 2 = hash mismatch.

## Layout

```
src/packet.[ch]   packet format + Internet checksum          (E1)
src/net.[ch]      UDP sockets, send/recv with timeout        (E1)
src/channel.[ch]  every send goes through here -> emulator    (E4 replaces .c)
src/rto.[ch]      Jacobson/Karels RTO + Karn                 (E1)
src/arq.[ch]      protocol interface, registry, helpers      (E1)
src/saw.c         Stop-and-Wait                              (E1)
src/gbn.c         Go-Back-N                                  (E2)
src/sr.c          Selective Repeat                           (E3)
src/hash.[ch]     SHA-256 of a file (OpenSSL EVP)            (E1)
src/server.c      sender main
src/client.c      receiver main
src/options.[ch]  command-line options
tests/            unit tests + end-to-end script
```

See `HANDOFF.md` for the design and integration notes.
