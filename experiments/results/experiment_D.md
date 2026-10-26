# Experiment D — Sensitivity to RTO Tuning

## Hypothesis
An RTO that is too short can trigger unnecessary retransmissions before an ACK arrives; an overly long RTO can make recovery from real loss slow. Adaptive RTO should respond to measured RTT, while fixed RTO settings expose this trade-off.

## Setup and controls
- Input: deterministic 1 MiB file.
- Protocols: Stop-and-Wait (window 1), Go-Back-N (window 8), Selective Repeat (window 8).
- RTO settings: adaptive, fixed 20, 40, 80, 160, 320, and 640 ms.
- Loss: 5% independently configured on each direction; no reordering or corruption.
- One-way delay: 10 ms; jitter: 0.
- Repetitions: 3 per configuration. Three repetitions per configuration used base seeds 42, 43, 44; DATA seeds were 42, 43, 44 and ACK seeds were 1000045, 1000046, 1000047 across the batch.
- Integrity: each successful row requires `hash_match=1` and zero process exit codes.

## Metrics
Retransmissions and transfer time come from the sender's RESULT line. Goodput is reported by the sender as `file_bytes × 8 / time_ms` in kbps. Failed rows remain in the raw CSV and are excluded from successful-run means.

## Results
| Protocol | RTO setting | Successful runs | Mean retransmissions | Mean time (s) | Mean goodput (kbps) |
|---|---|---:|---:|---:|---:|
| Stop-and-Wait | adaptive | 3/3 | 108.0 | 24.6 | 340.7 |
| Stop-and-Wait | 20 | 3/3 | 1138.3 | 23.1 | 363.2 |
| Stop-and-Wait | 40 | 3/3 | 108.3 | 25.5 | 328.6 |
| Stop-and-Wait | 80 | 3/3 | 107.3 | 29.8 | 282.1 |
| Stop-and-Wait | 160 | 3/3 | 107.3 | 38.3 | 219.7 |
| Stop-and-Wait | 320 | 3/3 | 107.3 | 55.4 | 152.1 |
| Stop-and-Wait | 640 | 3/3 | 107.3 | 89.7 | 94.2 |
| Go-Back-N | adaptive | 3/3 | 461.3 | 5.1 | 1670.1 |
| Go-Back-N | 20 | 3/3 | 1226.3 | 3.4 | 2493.7 |
| Go-Back-N | 40 | 3/3 | 464.0 | 5.5 | 1555.3 |
| Go-Back-N | 80 | 3/3 | 461.3 | 7.7 | 1114.7 |
| Go-Back-N | 160 | 3/3 | 461.3 | 12.4 | 702.6 |
| Go-Back-N | 320 | 3/3 | 461.3 | 21.6 | 404.5 |
| Go-Back-N | 640 | 3/3 | 461.3 | 40.1 | 219.8 |
| Selective Repeat | adaptive | 3/3 | 109.0 | 4.8 | 1781.9 |
| Selective Repeat | 20 | 3/3 | 1142.0 | 3.6 | 2310.2 |
| Selective Repeat | 40 | 3/3 | 107.3 | 5.0 | 1700.4 |
| Selective Repeat | 80 | 3/3 | 107.3 | 7.7 | 1099.2 |
| Selective Repeat | 160 | 3/3 | 107.3 | 13.1 | 647.7 |
| Selective Repeat | 320 | 3/3 | 107.3 | 23.9 | 355.2 |
| Selective Repeat | 640 | 3/3 | 107.3 | 45.6 | 186.8 |

## Observations

- Stop-and-Wait had its highest measured mean goodput at RTO 20 ms (363.2 kbps). Adaptive RTO measured 340.7 kbps, 108.0 retransmissions on average, and 24.63 s mean transfer time. Fixed 640 ms measured 94.2 kbps and 89.71 s mean transfer time.
- Go-Back-N had its highest measured mean goodput at RTO 20 ms (2493.7 kbps). Adaptive RTO measured 1670.1 kbps, 461.3 retransmissions on average, and 5.09 s mean transfer time. Fixed 640 ms measured 219.8 kbps and 40.08 s mean transfer time.
- Selective Repeat had its highest measured mean goodput at RTO 20 ms (2310.2 kbps). Adaptive RTO measured 1781.9 kbps, 109.0 retransmissions on average, and 4.76 s mean transfer time. Fixed 640 ms measured 186.8 kbps and 45.61 s mean transfer time.

## Limitations
Fixed RTO disables estimation/backoff by design in this experiment; it is a comparison mode, not a recommended production setting. The results depend on the emulated 20 ms base RTT, the 5% loss probability on each direction, and host scheduling. Three repetitions do not prove statistical significance. See the raw CSV and metadata for all seeds and outcomes.
