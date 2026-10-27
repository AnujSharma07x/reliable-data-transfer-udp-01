# Reliable Data Transfer over UDP

**Course:** CS-30003: Computer Networks · Assignment 1 (Project P3)<br>
**Section:** CSE 33<br>
**Team:** Anuj Sharma, Bhuvika Naulani, Divyanshi Agrawal, Dhruv Singh Laishram

[![Build & Test](https://img.shields.io/badge/tests-227%20passed-brightgreen.svg)]()
[![C Standard](https://img.shields.io/badge/C-gnu11-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL2-orange.svg)]()
[![Integrity](https://img.shields.io/badge/hash-OpenSSL%20SHA--256-blueviolet.svg)]()

A high-performance command-line file-transfer suite over UDP implementing end-to-end reliability at the application layer. The system provides sequence numbers, 16-bit Internet checksums, acknowledgements, retransmission timers, adaptive RTO estimation, a multi-threaded channel emulator, and cryptographic SHA-256 verification, with support for three pluggable ARQ protocols: **Stop-and-Wait (`saw`)**, **Go-Back-N (`gbn`)**, and **Selective Repeat (`sr`)**.

---

## Table of Contents

- [Overview & The RDT Problem](#overview--the-rdt-problem)
- [Protocol Architecture](#protocol-architecture)
  - [Wire Format & Packet Header](#wire-format--packet-header)
  - [ARQ Protocol Implementations](#arq-protocol-implementations)
  - [Adaptive RTO Estimation](#adaptive-rto-estimation)
  - [Channel Emulator](#channel-emulator)
- [Technology Stack](#technology-stack)
- [Build Instructions](#build-instructions)
- [Usage & Execution](#usage--execution)
  - [Basic File Transfer](#basic-file-transfer)
  - [Command-Line Options](#command-line-options)
  - [Machine-Readable Output](#machine-readable-output)
- [Testing & Verification](#testing--verification)
- [Experimental Evaluation](#experimental-evaluation)
- [Known Limitations](#known-limitations)
- [Team Contributions & Module Ownership](#team-contributions--module-ownership)
- [Academic Integrity & AI Disclosure](#academic-integrity--ai-disclosure)

---

## Overview & The RDT Problem

User Datagram Protocol (UDP) is a connectionless, lightweight transport protocol that provides process-to-process communication via port numbers and basic corruption detection. However, standard UDP provides strictly **best-effort delivery**:
- **Packet Loss:** Router queues drop datagrams during network congestion.
- **Bit Corruption:** Electromagnetic interference, thermal noise, and physical layer impairments flip bits in transit.
- **Packet Duplication:** Network switches or retransmissions can deliver identical packets multiple times.
- **Packet Reordering:** Multi-path IP routing causes packets to arrive out of sequence.
- **Delay & Jitter:** Buffering variations along intermediate hops induce latency variance.

This project implements an application-layer Reliable Data Transfer (RDT) system on top of POSIX UDP sockets (`SOCK_DGRAM`) that guarantees **error-free, strictly in-order, and non-duplicated** delivery of files of arbitrary size, even across hostile network environments.

---

## Protocol Architecture

### Wire Format & Packet Header

All packets share a compact 10-byte fixed header followed by a variable payload (0 to 1024 bytes). Multi-byte integer fields are encoded in **Network Byte Order (Big-Endian)** using `htons()` and `htonl()`:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Type (1 B)   | Reserved (1 B)|      Sequence Number (4 B)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       (Seq No cont.)          |      Payload Length (2 B)     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      Checksum (2 B)           |      Payload (0–1024 B) ...   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **`type` (1 byte):** `1` = `DATA`, `2` = `ACK`, `3` = `HELLO`.
- **`reserved` (1 byte):** Must be `0`; non-zero values trigger packet rejection.
- **`seq_num` (4 bytes):** Packet sequence number for `DATA`; acknowledged sequence number for `ACK`.
- **`payload_len` (2 bytes):** Length of payload (0 for `HELLO`/`ACK`; 0 to 1024 for `DATA`). A `DATA` packet with `payload_len == 0` explicitly signals **End-of-File (EOF)**.
- **`checksum` (2 bytes):** 16-bit one's complement Internet Checksum (RFC 1071) computed over both the 10-byte header (with checksum zeroed) and the payload.

### ARQ Protocol Implementations

| Feature | Stop-and-Wait (`saw`) | Go-Back-N (`gbn`) | Selective Repeat (`sr`) |
|---|---|---|---|
| **Sender Window Size** | $W = 1$ | $W \ge 1$ (default 8) | $W \ge 1$ (default 8) |
| **Receiver Window Size** | 1 | 1 | $W$ |
| **Acknowledgements** | Individual ACK | Cumulative ACK | Individual (Selective) ACK |
| **Out-of-Order Handling** | Discarded | Discarded | Buffered in receiver window |
| **Retransmission Trigger** | Single timer timeout | Base timer timeout (retransmits full window) | Per-packet timer timeout (retransmits lost packet only) |
| **Complexity & Overhead** | Low memory, low goodput on high BDP | Moderate sender buffer, simple receiver | Per-packet timers and receiver buffering |

1. **Stop-and-Wait (`saw`):**
   The sender transmits a single packet and pauses until the corresponding ACK arrives or the timer expires. Upon timeout, the unacknowledged packet is retransmitted. Simple and resilient, but pipeline utilization is bounded by the Bandwidth-Delay Product (BDP).
2. **Go-Back-N (`gbn`):**
   The sender maintains a sliding window of up to $N$ outstanding packets. Acknowledgements are cumulative: `ACK(k)` confirms all packets up to and including $k$. The receiver accepts only strictly in-order packets, discarding any out-of-order arrivals. If the oldest unacknowledged packet times out, the sender retransmits all unacknowledged packets currently in the window.
3. **Selective Repeat (`sr`):**
   Both sender and receiver maintain independent sliding windows of size $N$ ($N \le 2^{31}-1$). Each valid packet is acknowledged individually. The receiver buffers out-of-order packets arriving within its window $[R_{\text{base}}, R_{\text{base}} + N - 1]$. When the in-order packet arrives, buffered consecutive packets are delivered to the file writer. The sender maintains dedicated per-packet retransmission timers, retransmitting only the specific packets that timed out.

### Adaptive RTO Estimation

To avoid spurious retransmissions and adapt to changing network latencies, the sender incorporates the **Jacobson/Karels algorithm** (RFC 6298):
$$\text{RTT}_{\text{sample}} = t_{\text{ack\_received}} - t_{\text{packet\_sent}}$$
$$\text{SRTT} \leftarrow (1 - \alpha) \cdot \text{SRTT} + \alpha \cdot \text{RTT}_{\text{sample}} \quad (\alpha = 0.125)$$
$$\text{RTTVAR} \leftarrow (1 - \beta) \cdot \text{RTTVAR} + \beta \cdot |\text{SRTT} - \text{RTT}_{\text{sample}}| \quad (\beta = 0.25)$$
$$\text{RTO} \leftarrow \text{clamp}(\text{SRTT} + 4 \cdot \text{RTTVAR}, \, \text{RTO}_{\text{min}}, \, \text{RTO}_{\text{max}})$$

- **Karn's Algorithm:** RTT samples are ignored for retransmitted packets to prevent ambiguous ACK association.
- **Exponential Backoff:** On consecutive retransmission timeouts, the current RTO is doubled: $\text{RTO} \leftarrow \min(2 \cdot \text{RTO}, \text{RTO}_{\text{max}})$.

### Channel Emulator

The channel emulator (`src/channel.[ch]`) intercepts packets between the transport layer and the UDP socket to simulate hostile network conditions deterministically:
- **Loss (`--loss P`):** Drops packets with probability $P$.
- **Duplication (`--dup P`):** Duplicates and injects extra packets with probability $P$.
- **Corruption (`--corrupt P`):** Inverts random payload bits with probability $P$ before transmission to test checksum detection.
- **Reordering (`--reorder P`):** Defers packets with probability $P$, delivering them after subsequent packets.
- **Delay & Jitter (`--delay MS --jitter MS`):** Enqueues packets into a background worker thread with simulated one-way latency $t_{\text{delay}} \pm \text{jitter}$.
- **Deterministic Seeding (`--seed N`):** Uses deterministic PRNG seeding to ensure exact experimental repeatability.

---

## Technology Stack

- **Implementation Language:** C (`-std=gnu11`, `-Wall -Wextra -O2`)
- **Networking:** POSIX BSD Sockets (`AF_INET`, `SOCK_DGRAM`, `IPPROTO_UDP`)
- **Concurrency & Synchronization:** POSIX Threads (`pthread_create`, `pthread_mutex_t`, `pthread_cond_t`)
- **Cryptographic Verification:** OpenSSL `libcrypto` (`EVP_DigestInit_ex`, `EVP_DigestUpdate`, `EVP_DigestFinal_ex` for SHA-256)
- **Testing & Tooling:** Python 3 (`socket`, `struct`, `unittest`), GNU Bash, GNU Make

---

## Build Instructions

### Prerequisites (Ubuntu / Debian / WSL)

Install the required build tools and OpenSSL development headers:

```bash
sudo apt update
sudo apt install -y build-essential libssl-dev python3
```

### Compilation

Build the complete project using the `Makefile`:

```bash
# Clean previous artifacts
make clean

# Compile all binaries in parallel (-O2, -Wall, -Wextra, -std=gnu11)
make -j2
```

This compiles four executables:
- `server`: The reliable file-transfer sender.
- `client`: The reliable file-transfer receiver.
- `test_units`: Unit test suite (packet parsing, checksum, RTO estimator, SHA-256).
- `test_channel`: Channel emulator verification suite.

---

## Usage & Execution

### Basic File Transfer

To transfer a file reliably over UDP:

```bash
# Terminal 1: Start sender (server) on port 9000
./server 9000 input.bin --proto gbn --window 8

# Terminal 2: Start receiver (client) connecting to localhost
./client 127.0.0.1 9000 output.bin --proto gbn --window 8

# Verify whole-file byte-level integrity
cmp input.bin output.bin && echo "SUCCESS: Files are byte-for-byte identical!"
```

### Command-Line Options

| Flag | Applicable To | Default | Description |
|---|---|---|---|
| `--proto <saw\|gbn\|sr>` | Both | `saw` | Selects ARQ protocol (`saw`, `gbn`, or `sr`). |
| `--window <N>` | Both | `1` (SAW), `8` (GBN/SR) | Sliding window size (packets). |
| `--rto adaptive` | Sender | `adaptive` | Uses Jacobson/Karels adaptive RTO with Karn's rule. |
| `--rto <MS>` | Sender | — | Sets a fixed retransmission timeout in milliseconds. |
| `--expect-sha256 <HEX>` | Receiver | — | Exits 0 if received SHA-256 matches `<HEX>`, exits 2 if mismatch. |
| `--loss <P>` | Both | `0.0` | Packet drop probability (0.0 to 1.0 or 0% to 100%). |
| `--dup <P>` | Both | `0.0` | Packet duplication probability. |
| `--corrupt <P>` | Both | `0.0` | Checksum/payload corruption probability. |
| `--reorder <P>` | Both | `0.0` | Packet reordering probability. |
| `--delay <MS>` | Both | `0` | Base one-way propagation delay in milliseconds. |
| `--jitter <MS>` | Both | `0` | Latency variance ($\pm$ ms uniform distribution). |
| `--seed <N>` | Both | `0` | Deterministic pseudo-random number generator seed. |

### Machine-Readable Output

Upon transfer completion, both binaries emit structured machine-parseable log lines:

```text
# Sender output
RESULT protocol=sr window=8 rto=adaptive file_bytes=1048576 packets_sent=1315 retransmissions=290 timeouts=290 corrupted=133 time_ms=4041.7 goodput_kbps=2075.5 source_sha256=90483e6b...

# Receiver output
RECV protocol=sr file_bytes=1048576 duplicates=133 corrupted=157 time_ms=4041.6 received_sha256=90483e6b... hash_match=1
```

---

## Testing & Verification

The repository includes a comprehensive 227-case automated test suite:

```bash
# Run the entire test suite via Makefile
make test
```

### Individual Test Suites

```bash
# 1. Unit tests (header encoding, checksum, RTO math, SHA-256)
./test_units                        # 22 tests

# 2. Channel emulator test suite (queues, delay, error paths)
./test_channel                      # 13 tests

# 3. Python wire-format tests for Go-Back-N protocol logic
python3 tests/gbn_packet_tests.py   # 24 tests

# 4. Python wire-format tests for Selective Repeat protocol logic
python3 tests/sr_packet_tests.py    # 27 tests

# 5. SHA-256 integrity, corruption detection, and repeat tests
bash tests/hash_tests.sh            # 48 tests

# 6. End-to-end integration test runner (SAW, GBN, SR + impairments)
bash tests/run_tests.sh             # 93 tests
```

---

## Experimental Evaluation

Automated experiment benchmarks and analysis tools are located in the `experiments/` directory:

- **Experiment A (Goodput vs Packet Loss):** Evaluates protocol throughput under packet loss rates from 0% to 15%. Selective Repeat maintains superior goodput compared to Go-Back-N and Stop-and-Wait under high loss.
- **Experiment B (Goodput vs Window Size):** Examines sliding window scaling ($W = 1, 2, 4, 8, 16, 32$) over channels with delay, demonstrating throughput saturation as the window matches the Bandwidth-Delay Product.
- **Experiment C (Retransmissions vs Reordering):** Demonstrates the catastrophic retransmission amplification in Go-Back-N under packet reordering versus Selective Repeat's out-of-order buffering resilience.
- **Experiment D (RTO Sensitivity):** Compares Jacobson/Karels adaptive RTO against fixed timeouts (20 ms to 640 ms), illustrating the trade-off between premature timeouts and delayed loss recovery.

Raw datasets, statistical summaries, and generated figures are archived under [`experiments/results/`](experiments/results/).

---

## Known Limitations

- **Asynchronous UDP Send Errors:** When packets are enqueued in the channel emulator for delayed delivery, `channel_send()` returns immediately to the caller. If a subsequent `sendto()` fails in the background worker thread, it is recorded in the channel emulator's `send_errors` counter, but cannot be synchronously returned to the ARQ protocol stack.
- **Localhost Loopback Environment:** Benchmark experiments were executed over local loopback (`127.0.0.1`) with software-emulated delays and no host bandwidth throttling. Results reflect protocol mechanics rather than physical wide-area network bottlenecks.
- **Fixed vs. Adaptive RTO:** Fixed RTO mode is intended strictly for sensitivity analysis in Experiment D; adaptive RTO with Karn's rule is the standard and recommended operational mode.

---

## Team Contributions & Module Ownership

This project was designed, implemented, and verified collaboratively by a team of four engineers:

- **Anuj Sharma (Engineer 1 — Core Foundation & Integration):**
  - Packet format specification, network byte order serialization, and 16-bit Internet checksum (`src/packet.[ch]`).
  - UDP socket layer, address resolution, socket option configuration, and error recovery (`src/net.[ch]`).
  - Jacobson/Karels adaptive RTO estimator, Karn's rule, and exponential backoff (`src/rto.[ch]`).
  - Pluggable ARQ interface, protocol dispatch table, and common protocol state helpers (`src/arq.[ch]`).
  - Command-line parsing and strict numeric validation (`src/options.[ch]`).
  - SHA-256 cryptographic hashing via OpenSSL EVP (`src/hash.[ch]`).
  - Sender (`src/server.c`) and receiver (`src/client.c`) entry points and transfer orchestration.

- **Bhuvika Naulani (Engineer 2 — ARQ Protocols & Packet Tests):**
  - Stop-and-Wait ARQ sender and receiver logic (`src/saw.c`).
  - Go-Back-N ARQ sliding-window sender with cumulative ACKs and receiver (`src/gbn.c`).
  - Selective Repeat ARQ sender with per-packet timers and receiver window buffering (`src/sr.c`).
  - Wire-format packet test suite for Go-Back-N protocol logic (`tests/gbn_packet_tests.py`, 24 cases).
  - Wire-format packet test suite for Selective Repeat protocol logic (`tests/sr_packet_tests.py`, 27 cases).
  - Final integration code review and sign-off.

- **Divyanshi Agrawal (Engineer 3 — Channel Emulator & Test Suites):**
  - Multi-threaded network channel emulator with loss, dup, corrupt, reorder, delay, and jitter (`src/channel.[ch]`).
  - Unit test suite for packet encoding, checksum, RTO, and hashing (`tests/test_units.c`, 22 cases).
  - Channel emulator verification test suite (`tests/test_channel.c`, 13 cases).
  - Automated end-to-end integration test runner across all protocols and impairments (`tests/run_tests.sh`, 93 cases).

- **Dhruv Singh Laishram (Engineer 4 — Experiments, Verification & Reporting):**
  - Automated multi-repetition experiment runner and harness (`experiments/run_experiments.py`).
  - Data aggregation, statistical summary computation, and plot generation (`experiments/analysis/`).
  - Benchmark datasets, summaries, and visualization figures (`experiments/results/`).
  - Independent audit scripts, build logs, and test evidence files (`verification/`).
  - Comprehensive technical project report (`REPORT.md`, `REPORT.pdf`).
  - Test matrix documentation and reproducibility guide (`TEST-RESULTS.md`).
  - Academic submission checklist and compliance verification (`SUBMISSION-CHECKLIST.md`).

---

## Academic Integrity & AI Disclosure

This project adheres strictly to the academic integrity policies of CS-30003. A comprehensive disclosure of all AI assistance used during development, debugging, testing, and documentation refinement is documented in [`AI-USE.md`](AI-USE.md).
