# Reliable Data Transfer over UDP (P3)

CS-30003 · CSE 33 · Team: Anuj Sharma, Bhuvika Naulani, Divyanshi Agrawal, Dhruv Singh Laishram

A command-line file-transfer application over UDP with a pluggable reliability layer. Reliability is added on top of UDP with sequence numbers, Internet checksums, acknowledgements, retransmission timers, adaptive RTO, and whole-file SHA-256 verification, supporting three ARQ protocols: Stop-and-Wait (`saw`), Go-Back-N (`gbn`), and Selective Repeat (`sr`).

## Build

```bash
make            # builds ./server ./client ./test_units ./test_channel
make -j2        # parallel build with -std=gnu11 -Wall -Wextra -O2
```

**Prerequisites:** GCC, POSIX socket support (Linux/WSL/macOS), pthreads, and OpenSSL `libcrypto` for SHA-256 (Ubuntu/Debian: `sudo apt install libssl-dev`). Python 3 is required for the packet-level tests and experiment runners.

## Run

```bash
# Terminal 1 (Sender / Server)
./server 9000 input.bin --proto saw

# Terminal 2 (Receiver / Client)
./client 127.0.0.1 9000 output.bin --proto saw

# Verify integrity
cmp input.bin output.bin && echo "files identical"

# Receiver with automatic source SHA-256 verification
./client 127.0.0.1 9000 output.bin --proto saw --expect-sha256 $(sha256sum input.bin | cut -d' ' -f1)
```

### CLI Options

* Both sides: `--proto saw|gbn|sr`, `--window N` (window size for GBN/SR; SAW defaults to 1).
* Sender: `--rto adaptive` (default Jacobson/Karels) or `--rto MS` (fixed timeout in ms).
* Channel emulator (pass matching impairment parameters to both sides):
  * `--loss P`: packet drop probability (0.0 to 1.0 or 0% to 100%)
  * `--dup P`: packet duplication probability
  * `--reorder P`: packet reordering probability
  * `--corrupt P`: packet checksum corruption probability
  * `--delay MS`: base one-way transmission delay in milliseconds
  * `--jitter MS`: random delay variation (+/- ms)
  * `--seed N`: deterministic pseudo-random number generator seed
* Receiver: `--expect-sha256 HEX` (exits 0 on match, 2 on hash mismatch, 1 on transfer failure).

The server outputs a machine-readable `RESULT` line; the client outputs a matching `RECV` line:

```
RESULT protocol=sr window=8 rto=adaptive file_bytes=1048576 packets_sent=1315 retransmissions=290 timeouts=290 corrupted=133 time_ms=4041.7 goodput_kbps=2075.5 source_sha256=90483e6b...
RECV protocol=sr file_bytes=1048576 duplicates=133 corrupted=157 time_ms=4041.6 received_sha256=90483e6b... hash_match=1
```

## Repository Structure & Module Ownership

* **Anuj Sharma (Engineer 1 — Core Foundation & Integration):**
  * `src/packet.[ch]`: 10-byte wire header, network-byte-order packing, Internet checksum.
  * `src/net.[ch]`: UDP socket layer, connect/bind, address resolution, timeout handling.
  * `src/rto.[ch]`: Jacobson/Karels adaptive RTT/RTO estimator, Karn's rule, exponential backoff.
  * `src/arq.[ch]`: Pluggable ARQ interface, protocol registry, and shared helpers.
  * `src/options.[ch]`: Command-line options parsing and numerical validation.
  * `src/hash.[ch]`: SHA-256 file hashing via OpenSSL EVP.
  * `src/server.c`, `src/client.c`: Sender and receiver main entry points and error cleanup.
  * `AI-USE.md`, `HANDOFF.md`: AI disclosure and architecture handoff documentation.

* **Bhuvika Naulani (Engineer 2 — ARQ Protocols & Packet Tests):**
  * `src/saw.c`: Stop-and-Wait ARQ sender/receiver implementation.
  * `src/gbn.c`: Go-Back-N ARQ sliding-window sender with cumulative ACKs and receiver.
  * `src/sr.c`: Selective Repeat ARQ sender with per-packet timers and receiver buffering.
  * `tests/gbn_packet_tests.py`: Wire-format packet tests for Go-Back-N protocol logic (24 cases).
  * `tests/sr_packet_tests.py`: Wire-format packet tests for Selective Repeat protocol logic (27 cases).

* **Divyanshi Agrawal (Engineer 3 — Channel Emulator & Test Suites):**
  * `src/channel.[ch]`: Multi-threaded channel emulator with loss, dup, corrupt, reorder, delay, jitter.
  * `tests/test_units.c`: Unit test suite for packet encoding, checksum, RTO, and hash functions.
  * `tests/test_channel.c`: Verification tests for emulator accuracy, delay queues, and error counters.
  * `tests/run_tests.sh`: End-to-end integration test runner across protocols and impairments.

* **Dhruv Singh Laishram (Engineer 4 — Experiments, Verification & Reporting):**
  * `experiments/run_experiments.py`: Automated multi-run experiment harness.
  * `experiments/analysis/`: Data aggregation, statistical summary, and plot generators.
  * `experiments/results/`: Datasets (`.csv`), summaries, metadata, and generated figures.
  * `verification/`: Independent audit scripts, build logs, and test evidence files.
  * `REPORT.md`, `REPORT.pdf`: Final comprehensive technical project report.
  * `TEST-RESULTS.md`: Detailed test matrix and reproducibility documentation.
  * `SUBMISSION-CHECKLIST.md`: Academic submission compliance checklist.

## Verification & Testing

Run individual test suites:

```bash
./test_units                        # Unit tests (packet, RTO, SHA-256)
./test_channel                      # Channel emulator mechanics and error handling
python3 tests/gbn_packet_tests.py   # Go-Back-N wire-format packet tests
python3 tests/sr_packet_tests.py    # Selective Repeat wire-format packet tests
bash tests/hash_tests.sh            # SHA-256 file integrity and corruption tests
bash tests/run_tests.sh             # 93-case end-to-end integration suite
```

Or run the full test suite via Makefile:

```bash
make test
```

## Experiments (A–D)

The `experiments/` directory includes the automated experiment runner, configuration definitions, and analysis tooling for the four required studies:
* **Experiment A:** Goodput vs packet loss probability (0% to 15%) across protocols.
* **Experiment B:** Goodput vs sender window size (1 to 32) for GBN and SR.
* **Experiment C:** Retransmissions vs packet reordering probability (0% to 20%).
* **Experiment D:** Retransmission timeout (RTO) sensitivity (adaptive vs fixed RTO 20–640 ms).

To inspect the experiment runner CLI options:

```bash
python3 experiments/run_experiments.py --help
```

Packaged datasets and report figures in `experiments/results/` reflect controlled three-repetition benchmarks. Independent single-repetition verification evidence and audit logs are retained in `verification/`.
