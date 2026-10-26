# Experiment B — Goodput vs Window Size

## Hypothesis
Increasing the sender window should improve goodput because more packets can be in flight before acknowledgements arrive. The gain may level off or vary due to loss recovery and host scheduling.

## Setup and controls
- Input: deterministic 1 MiB file.
- Protocols: Go-Back-N and Selective Repeat; windows 1, 2, 4, 8, 16, 32.
- Loss: 2% independently configured on each direction; no reordering or corruption.
- One-way delay: 10 ms; jitter: 0; adaptive RTO.
- Repetitions: 3 per configuration. Three repetitions per configuration used base seeds 42, 43, 44; DATA seeds were 42, 43, 44 and ACK seeds were 1000045, 1000046, 1000047 across the batch.
- Integrity: each successful row requires `hash_match=1` and zero process exit codes.

## Metric
Goodput is taken from the sender's RESULT line: `file_bytes × 8 / time_ms`, expressed as kbps (bits/ms). Failed rows remain in the raw CSV and are excluded from successful-run statistics.

## Results
| Protocol | Window | Successful runs | Mean goodput (kbps) | SD | Min–max (kbps) | Mean retransmissions |
|---|---:|---:|---:|---:|---:|---:|
| Go-Back-N | 1 | 3/3 | 373.6 | 5.1 | 368.0–378.1 | 41.7 |
| Go-Back-N | 2 | 3/3 | 737.9 | 23.3 | 711.3–754.7 | 43.3 |
| Go-Back-N | 4 | 3/3 | 1367.9 | 79.8 | 1277.6–1428.6 | 85.3 |
| Go-Back-N | 8 | 3/3 | 2342.6 | 265.6 | 2036.3–2509.3 | 168.0 |
| Go-Back-N | 16 | 3/3 | 3987.2 | 837.5 | 3020.2–4474.3 | 320.3 |
| Go-Back-N | 32 | 3/3 | 6385.8 | 1667.9 | 4470.7–7519.9 | 578.3 |
| Selective Repeat | 1 | 3/3 | 372.9 | 3.8 | 370.0–377.2 | 40.7 |
| Selective Repeat | 2 | 3/3 | 716.9 | 22.7 | 694.9–740.2 | 42.0 |
| Selective Repeat | 4 | 3/3 | 1350.7 | 70.4 | 1282.0–1422.7 | 42.7 |
| Selective Repeat | 8 | 3/3 | 2376.5 | 112.1 | 2270.4–2493.8 | 40.7 |
| Selective Repeat | 16 | 3/3 | 3741.4 | 260.2 | 3516.2–4026.2 | 40.7 |
| Selective Repeat | 32 | 3/3 | 6417.7 | 571.7 | 5910.5–7037.3 | 40.7 |

## Observations

- Go-Back-N had its highest measured mean goodput at window 32 (6385.8 kbps). Window 1 measured 373.6 kbps; the observed change to the best window was +6012.2 kbps.
- Selective Repeat had its highest measured mean goodput at window 32 (6417.7 kbps). Window 1 measured 372.9 kbps; the observed change to the best window was +6044.8 kbps.

## Limitations
Results are from localhost with emulated delay and no bandwidth cap. Three repetitions give a useful comparison but do not establish statistical significance; timing and OS scheduling can affect goodput. Consult the raw CSV, metadata, and per-run logs when interpreting any outlier.
