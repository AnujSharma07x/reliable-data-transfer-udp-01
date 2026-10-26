# Reliable Data Transfer over UDP — Project Report

**Course:** CS-30003 — Coding Assignment 1  
**Project:** P3 — Reliable Data Transfer over UDP  
**Team:** Anuj Sharma, Bhuvika Naulani, Divyanshi, Dhruv  
**Section:** CSE 33

## 1. Overview

This project implements a file-transfer application over UDP with three selectable ARQ protocols: Stop-and-Wait, Go-Back-N, and Selective Repeat. The implementation adds sequence numbers, a packet checksum, acknowledgements, retransmission timers, adaptive RTO logic, a configurable channel emulator, and whole-file SHA-256 verification. The required experiments compare protocol goodput, window size, reordering and RTO settings.

## 2. Design summary

- **Transport:** real UDP sockets; one sender/server and one receiver/client per test run.
- **Packet format:** 10-byte header followed by 0–1024 bytes of payload. Header fields are type (1 byte), reserved (1 byte), sequence/ACK number (4 bytes), payload length (2 bytes), and Internet checksum (2 bytes). A zero-length DATA packet marks EOF.
- **Integrity:** Internet checksum detects packet corruption; SHA-256 comparison verifies the complete received file. These checks serve different purposes.
- **ARQ:** Stop-and-Wait retransmits one outstanding packet; GBN uses a sliding window and cumulative ACKs; SR uses per-packet ACK/timer state and buffers in-window out-of-order data.
- **RTO:** Jacobson/Karels SRTT/RTTVAR estimation, Karn sampling rules, timeout backoff, and a fixed-RTO mode for the sensitivity experiment.
- **Channel emulator:** configurable loss, duplication, reordering, corruption, delay and jitter. Experiment runs record a base seed and separate deterministic DATA/ACK seeds.

## 3. Verification results

| Suite | Result | Notes |
|---|---|---|
| Build (`make -j2`, `-Wall -Wextra`) | PASS | No visible compiler warnings in the checked build. |
| Unit tests | 22/22 PASS | Packet, checksum, RTO and SHA-256 cases. |
| Channel emulator tests | PASS | Timing assertions allow measured host-scheduler slack; deterministic per-packet random decisions are checked separately from delivery-order timing. |
| End-to-end tests | 93/93 PASS | `tests/run_tests.sh`, exit code 0; includes all three protocols and combined impairments. |
| GBN packet-level tests | 24/24 PASS | Packet-level GBN window, cumulative ACK, retransmission and EOF cases. |
| SR packet-level tests | 27/27 PASS | Packet-level SR selective ACK, buffering, per-packet timer and retransmission cases. |
| Hash-integrity suite | 48/48 PASS | Includes 43 transfer cases, wrong-hash detection and byte comparison. |

The end-to-end suite and targeted suites were executed separately; their complete logs are preserved under `verification/`. An independent audit validated all 180 experiment rows for status, sender/receiver exit codes, hash match, byte count, directional seeds and goodput within rounding tolerance.

## 4. Experimental method

Each experiment uses a deterministic 1 MiB input file, 10 ms one-way delay per direction, no jitter unless otherwise specified, and three repetitions per configuration. The experiment runner applies the same impairment probabilities to both directions while using DATA seed = base seed and ACK seed = base seed + 1,000,003. Raw CSVs include status, exit codes, file/hash verification, transfer metrics and both directional seeds. Failed runs, if any, remain in the raw CSV and are excluded from means.

Goodput is the sender-reported `file_bytes × 8 / time_ms`, in kbps. Retransmissions are the sender-reported count. The experiment-specific reports include configuration tables and per-setting statistics.

## 5. Results overview

### A. Goodput vs packet-loss probability

| Protocol | Mean goodput at 0% loss (kbps) | Mean goodput at 15% loss (kbps) | Mean retransmissions at 15% loss |
|---|---:|---:|---:|
| Stop-and-Wait | 396.1 | 218.8 | 387.3 |
| Go-Back-N | 3161.4 | 737.6 | 1528.7 |
| Selective Repeat | 3169.9 | 764.8 | 387.0 |

Raw rows: 45; successful: 45; failed: 0. See [`experiment_A.md`](experiments/results/experiment_A.md) and [`experiment_A_goodput_vs_loss.png`](experiments/results/experiment_A_goodput_vs_loss.png).

### B. Goodput vs window size

| Protocol | Best measured mean-goodput window | Mean goodput (kbps) |
|---|---:|---:|
| Go-Back-N | 32 | 6385.8 |
| Selective Repeat | 32 | 6417.7 |

Raw rows: 36; successful: 36; failed: 0. See [`experiment_B.md`](experiments/results/experiment_B.md) and [`experiment_B_goodput_vs_window.png`](experiments/results/experiment_B_goodput_vs_window.png).

### C. Retransmissions vs reordering probability

| Protocol | Mean retransmissions at 0% reordering | Mean retransmissions at 20% reordering |
|---|---:|---:|
| Stop-and-Wait | 2.0 | 265.3 |
| Go-Back-N | 2.7 | 1591.0 |
| Selective Repeat | 2.7 | 48.7 |

Raw rows: 36; successful: 36; failed: 0. See [`experiment_C.md`](experiments/results/experiment_C.md) and [`experiment_C_retransmissions_vs_reordering.png`](experiments/results/experiment_C_retransmissions_vs_reordering.png).

### D. RTO sensitivity

| Protocol | Adaptive mean goodput (kbps) | Best fixed RTO by measured mean goodput | Mean goodput (kbps) |
|---|---:|---:|---:|
| Stop-and-Wait | 340.7 | 20 ms | 363.2 |
| Go-Back-N | 1670.1 | 20 ms | 2493.7 |
| Selective Repeat | 1781.9 | 20 ms | 2310.2 |

Raw rows: 63; successful: 63; failed: 0. See [`experiment_D.md`](experiments/results/experiment_D.md) and [`experiment_D_rto_sensitivity.png`](experiments/results/experiment_D_rto_sensitivity.png).

## 6. Limitations and reproducibility notes

- Measurements use localhost with emulated delay and no bandwidth cap; they should not be treated as real-network throughput benchmarks.
- OS scheduling can trigger occasional spurious retransmissions when measured RTT is close to RTO. Three repetitions help expose variability but do not establish statistical significance.
- Fixed RTO is a comparison mode and is not the recommended operating mode.
- Source review identified some error-path hardening work still worth doing: checked allocation/thread-creation failures, file read/write/flush errors and strict malformed-packet validation. These were documented, not rewritten during this audit.
- The packaged project intentionally excludes the old embedded `.git` directory because its history does not prove all four members’ contributions. The team should create a fresh history in the empty GitHub repository and commit genuine work under each member’s own Git identity.
- Review `AI-USE.md` and complete it with all AI use by all team members before submission.

## 7. Files and reproduction

- Raw data + metadata: `experiments/results/experiment_[A-D]_raw.csv` and matching `.meta.txt` files.
- Summaries and plots: `experiments/results/experiment_[A-D]_summary.csv` and the experiment PNGs.
- Written explanations: `experiments/results/experiment_[A-D].md`.
- Commands: `README.md` and `experiments/README.md`.
- One-page proposal: `PROPOSAL.pdf` (editable source: `PROPOSAL.md`).
- Design details and test notes: `HANDOFF.md`.
- AI disclosure draft: `AI-USE.md` (must be completed and confirmed by all team members).
