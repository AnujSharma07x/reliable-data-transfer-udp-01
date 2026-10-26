# Experiment runner

`run_experiments.py` runs the unchanged `./server` and `./client` for many
configurations and writes **one CSV row per transfer**. Every metric comes
from the programs' own `RESULT` (sender), `RECV` (receiver) and `CHANNEL`
(emulator) lines. Nothing is re-timed or estimated by the runner.

```
make                                                   # build first
python3 experiments/run_experiments.py list            # batches + sizes
python3 experiments/run_experiments.py smoke           # 5 runs, ~1 min
python3 experiments/run_experiments.py A               # one batch
python3 experiments/run_experiments.py all             # A, B, C, D in one CSV
python3 experiments/run_experiments.py A --dry-run     # print the plan only
python3 experiments/run_experiments.py one --proto sr --window 8 --loss 0.05 --rto 80
```

Useful options: `--reps N`, `--rep-seed vary|fixed`, `--seed N`, `--delay MS`, `--jitter MS`,
`--file-size BYTES`, `--timeout S` (per run, default 300) and `--out PATH`.

## Results and analysis

| Experiment | Raw data | Analysis | Graph | Explanation |
|---|---|---|---|---|
| A goodput vs loss | `results/experiment_A_raw.csv` | `analysis/experiment_A.py` → `results/experiment_A_summary.csv` | `results/experiment_A_goodput_vs_loss.png` | `results/experiment_A.md` |
| B goodput vs window | `results/experiment_B_raw.csv` | `analysis/experiments_BCD.py` → `results/experiment_B_summary.csv` | `results/experiment_B_goodput_vs_window.png` | `results/experiment_B.md` |
| C retransmissions vs reordering | `results/experiment_C_raw.csv` | `analysis/experiments_BCD.py` → `results/experiment_C_summary.csv` | `results/experiment_C_retransmissions_vs_reordering.png` | `results/experiment_C.md` |
| D RTO sensitivity | `results/experiment_D_raw.csv` | `analysis/experiments_BCD.py` → `results/experiment_D_summary.csv` | `results/experiment_D_rto_sensitivity.png` | `results/experiment_D.md` |

To reproduce the packaged three-repetition raw CSVs, run each batch separately from the repository root (choose free port ranges):

```bash
python3 experiments/run_experiments.py A --reps 3 --out experiments/results/experiment_A_raw.csv --port 30000
python3 experiments/run_experiments.py B --reps 3 --out experiments/results/experiment_B_raw.csv --port 30100
python3 experiments/run_experiments.py C --reps 3 --out experiments/results/experiment_C_raw.csv --port 30200
python3 experiments/run_experiments.py D --reps 3 --out experiments/results/experiment_D_raw.csv --port 30300
```

After generating all batches, run `python3 experiments/analysis/experiment_A.py` and `python3 experiments/analysis/experiments_BCD.py`, then `python3 experiments/analysis/write_report_A.py`, `python3 experiments/analysis/write_reports_BCD.py`, and `python3 experiments/analysis/write_final_report.py` to refresh summaries, plots, and written explanations from the raw CSVs.

## What one run does

1. **Input file.** The same 1 MiB file (`data/input_1048576.bin`) is used for
   every run. It is generated deterministically with SHA-256 in counter mode,
   with no random generator: sha256 `a67ed882dee03ab8...`.
2. **Expected hash.** Computed with Python's `hashlib`, then cross-checked
   against the server's `source_sha256`.
3. **Server.** Started, and the runner waits until it prints "waiting for
   client".
4. **Client.** Started with `--expect-sha256 <expected>`. Emulator probabilities
   are configured on both outgoing paths: the server's channel affects DATA and
   the client's channel affects ACKs. The paths use distinct deterministic seeds;
   the CSV records `seed`, `data_seed`, and `ack_seed`.
5. **Wait.** The runner waits for both processes. Past `--timeout` it kills
   them and records `status=timeout`.
6. **Row written.** The row is flushed immediately, so a crash keeps earlier
   rows. Logs are kept in `results/logs/<batch>/`.

## The four experiments (fixed parameters)

All batches share these settings:
- 1 MiB file
- one-way delay **10 ms** each direction (base RTT ≈ 20 ms), jitter 0
- base seed **42**; each repetition increments the base seed when `--rep-seed vary` is used
- DATA-direction seed = base seed; ACK-direction seed = base seed + **1,000,003**
- adaptive RTO, unless D varies it
- GBN/SR window **8**, unless B varies it; SAW is always window 1
- 3 repetitions per configuration for the packaged evidence

| Batch | Varies | Fixed | Runs |
|---|---|---|---|
| **A** goodput vs loss | loss 0, 2, 5, 10, 15 % × SAW/GBN/SR | reorder 0, corrupt 0 | 45 (15 configs × 3 reps) |
| **B** goodput vs window | window 1, 2, 4, 8, 16, 32 × GBN/SR | loss 2 % | 36 (12 configs × 3 reps) |
| **C** retransmissions vs reordering | reorder 0, 5, 10, 20 % × SAW/GBN/SR | loss 0 | 36 (12 configs × 3 reps) |
| **D** RTO sensitivity | RTO adaptive, 20, 40, 80, 160, 320, 640 ms × SAW/GBN/SR | loss 5 % | 63 (21 configs × 3 reps) |

**Why a 10 ms delay?** On bare localhost the RTT is about 0.05 ms, so window
size and RTO barely matter and timing noise dominates. A 20 ms RTT makes the
classic effects measurable. For example, SAW needs about 1025 × 20 ms ≈ 21 s,
while GBN/SR with window 8 need about 2.6 s.

**RTO in experiment D:** this uses the existing `--rto MS` flag, which gives a
fixed RTO with no estimation and no backoff (`rto.c` is unchanged). Values are
clamped by the code to 20–2000 ms. The `rto` CSV column shows what the server
actually used.

**Approximate wall time for the packaged three-repetition batches:** smoke ~1 min;
A ~15 min; B ~8 min; C ~8 min; D ~20 min (SAW with fixed RTO 640 ms is among
the slowest settings). Actual runtime depends on host load and retransmissions.
Each run also has a ~2.5 s client linger, which is **not** included in `time_ms`.

## CSV columns

| Column | Source |
|---|---|
| experiment, protocol, window, loss, reorder, corruption, dup, delay_ms, jitter_ms, seed, data_seed, ack_seed, rep | the configuration and directional PRNG seeds |
| file_bytes | size of the input file |
| sent_packets, retransmissions, timeouts, time_ms, goodput_kbps, rto | server `RESULT` (`time_ms` runs from first send to the EOF ACK; SHA-256 time is excluded) |
| sender_corrupted_acks | server `RESULT corrupted` (bad-checksum ACKs) |
| file_bytes_received, hash_match, receiver_corrupted, receiver_duplicates | client `RECV` |
| data_* / ack_* (dropped, corrupted, duplicated, reordered) | emulator `CHANNEL` line of the server (DATA path) and the client (ACK path) |
| server_exit, client_exit | process exit codes (−9 = killed on timeout) |
| status | `ok`, `transfer_failed`, `hash_mismatch`, `timeout`, `parse_error`, `source_hash_differs` or `size_mismatch` |
| exit_code | 0 = ok; 1 = transfer failed; 2 = hash mismatch; 124 = timeout; 3 = runner-detected inconsistency |
| log_prefix | where the server/client logs for that run are |

A metric that is not available, for example because the run failed, is left
**empty**. The runner exits non-zero if any run failed or if the number of rows
differs from the plan.

## Reproducibility

- Each batch writes `results/<batch>.meta.txt` with:
  - date and git commit (flagged if the tree is dirty)
  - OS, CPU and compiler
  - input size and SHA-256
  - repetitions and number of runs
- A fixed directional seed and configuration make the emulator's random draws
  reproducible for the same sequence of send calls. DATA and ACK use separate
  seeds to avoid reusing the same PRNG stream across directions. Retransmission
  counts can still vary because timeout scheduling is tied to real time.
- **Measured timing noise** on a 2-vCPU VM, no impairment, delay 10 ms. An
  occasional OS scheduling delay of 10 ms or more pushes an ACK past the
  adaptive RTO (SRTT + 10 ms when the RTT is steady):

  | Protocol | Runs with spurious retransmissions | Values seen |
  |---|---|---|
  | GBN | 1 of 8 | 48 (one burst of 6 window timeouts) |
  | SAW | 2 of 8 | 1 and 2 |
  | SR | 0 of 8 | none |

- **Configurations dominated by channel events reproduced exactly** across
  3 runs: SR at 5 % loss gave 1165 sent / 140 retx every time, and GBN at
  10 % reorder gave 1769 / 744 every time.
- `time_ms` and `goodput_kbps` vary by about 1 % between identical runs.
- **For the report, use repetitions.**
  - `--reps 3` (seed + k) averages over channel realisations.
  - `--reps 3 --rep-seed fixed` isolates the timing noise.
- Report the mean or median, and mention the spread.

## Known limitations

- **If the client's HELLO never arrives** (loss 100 %), the server waits
  forever. This is existing behaviour. The runner's `--timeout` kills it and
  records `status=timeout`.
- **Everything runs on localhost.** The 10 ms delay comes from the emulator,
  not a real network, and results depend somewhat on machine load. Run batches
  on an idle machine and record the meta file.
- **Ports from `--port` (default 10000) upward must be free.** Run one batch
  at a time.
