# Project Handoff — Reliable Data Transfer over UDP

This document describes the **current integrated project**. Older engineering notes below were replaced because they described pre-integration placeholders.

## Current architecture

- `src/server.c` and `src/client.c`: command-line handling, sockets, transfer setup, whole-file SHA-256 reporting.
- `src/packet.c` / `src/packet.h`: 10-byte packet header, network-byte-order fields, checksum, and packet-field validation.
- `src/saw.c`, `src/gbn.c`, `src/sr.c`: Stop-and-Wait, Go-Back-N and Selective Repeat ARQ.
- `src/rto.c`: adaptive RTT/RTO estimation, Karn's rule support and timeout backoff.
- `src/channel.c`: seeded loss, duplication, reordering, corruption, delay and jitter emulator. Delay uses a delivery queue and thread.
- `src/options.c`: shared command-line option parsing and numeric validation.
- `src/hash.c`: SHA-256 via OpenSSL EVP.

## Packet format

The header is 10 bytes: type (1 byte), reserved (1 byte), sequence number (4 bytes), payload length (2 bytes), checksum (2 bytes), followed by 0–1024 payload bytes. Multi-byte values use network byte order. HELLO and ACK packets have no payload; DATA can contain up to 1024 bytes. A zero-length DATA packet signals EOF. Unknown packet types, nonzero reserved bytes, illegal packet-type/length combinations, invalid lengths and checksum failures are rejected by the packet decoder.

## Run and test

```bash
make clean
make -j2
make test
```

Example transfer:

```bash
./server 9000 input.bin --proto saw
./client 127.0.0.1 9000 output.bin --proto saw
```

Supported protocol names are `saw`, `gbn`, and `sr`. Use `--window N` for windowed protocols, `--rto adaptive|MS`, and channel options shown by `./server` or `./client` usage output. For end-to-end integrity verification, provide the expected source SHA-256 to the receiver using `--expect-sha256 HEX`.

## Experiments

The four required experiment definitions, runners, raw datasets, summaries, plots and explanations are under `experiments/`. The recorded datasets have been validated internally; a dataset audit is not the same as rerunning every network experiment from scratch. Preserve that distinction in the final report.

## Known limitations / final review

- The channel emulator checks queue allocation, condition-variable/thread initialization, invalid arguments, queue overflow, and immediate `sendto()` errors. Later asynchronous send failures are counted in `CHANNEL ... send_errors=...` because the original call has already returned; they cannot be synchronously propagated back to the ARQ sender.
- Rare OS/resource failures are not exhaustively tested. The full success-path and impairment suite passes, but that does not prove recovery from every resource exhaustion or network-stack failure.
- Packet encoder/decoder, CLI numeric/port parsing, and protocol file read/write/flush paths have been hardened and covered by tests.
- Packaged A–D CSVs are historical three-repetition measurements. Their per-run logs are not included in this ZIP; fresh one-repetition A–D validation is stored separately under `verification/` when complete.
- The team must review `AI-USE.md` and confirm its accuracy for all four members before submission.
- Each member should understand the code they contributed and use truthful Git commit history. No repository push is performed by this handoff.
