# Experiment A — Goodput vs Packet-Loss Probability

## Hypothesis
Increasing packet loss should reduce goodput because lost DATA or ACK packets trigger retransmission and additional waiting. Windowed protocols should generally use the link more efficiently than Stop-and-Wait, while GBN and SR may differ in retransmission overhead.

## Setup and controls
- Input: deterministic 1 MiB file (1,048,576 bytes).
- Protocols: Stop-and-Wait (window 1), Go-Back-N (window 8), Selective Repeat (window 8).
- Loss probabilities: 0%, 2%, 5%, 10%, 15% on both DATA and ACK directions; no reordering, corruption, or duplication.
- One-way delay: 10 ms per direction; jitter 0; adaptive RTO.
- Configurations: 15 × 3 repetitions = 45 raw rows; 45 successful and 0 failed.
- Base seeds: 42, 43, 44; DATA seeds: 42, 43, 44; ACK seeds: 1000045, 1000046, 1000047.
- Every successful row requires `hash_match=1`, matching file size, and zero process exit codes.

## Metric
Goodput is read from the sender's RESULT line, calculated as `file_bytes × 8 / time_ms`, reported in kbps. Retransmissions are the sender's measured retransmission count. The raw CSV preserves each run; summary statistics exclude only failed rows.

## Results
| Protocol | Loss | Successful runs | Mean goodput (kbps) | SD | Min–max (kbps) | Mean retransmissions |
|---|---:|---:|---:|---:|---:|---:|
| Stop-and-Wait | 0% | 3/3 | 396.1 | 1.4 | 394.7–397.4 | 1.7 |
| Stop-and-Wait | 2% | 3/3 | 373.7 | 4.1 | 371.0–378.4 | 43.0 |
| Stop-and-Wait | 5% | 3/3 | 333.2 | 7.8 | 324.5–339.7 | 112.0 |
| Stop-and-Wait | 10% | 3/3 | 287.5 | 6.1 | 281.0–293.0 | 226.7 |
| Stop-and-Wait | 15% | 3/3 | 218.8 | 6.3 | 214.5–226.0 | 387.3 |
| Go-Back-N | 0% | 3/3 | 3161.4 | 8.8 | 3152.7–3170.3 | 0.0 |
| Go-Back-N | 2% | 3/3 | 2425.1 | 262.5 | 2122.5–2591.7 | 168.0 |
| Go-Back-N | 5% | 3/3 | 1656.4 | 233.4 | 1426.1–1892.7 | 461.3 |
| Go-Back-N | 10% | 3/3 | 1108.6 | 155.4 | 958.7–1269.0 | 901.0 |
| Go-Back-N | 15% | 3/3 | 737.6 | 63.7 | 671.3–798.3 | 1528.7 |
| Selective Repeat | 0% | 3/3 | 3169.9 | 2.1 | 3167.6–3171.6 | 0.0 |
| Selective Repeat | 2% | 3/3 | 2355.8 | 151.0 | 2198.5–2499.5 | 48.0 |
| Selective Repeat | 5% | 3/3 | 1744.4 | 164.5 | 1583.4–1912.1 | 114.3 |
| Selective Repeat | 10% | 3/3 | 1188.7 | 93.8 | 1095.9–1283.4 | 226.3 |
| Selective Repeat | 15% | 3/3 | 764.8 | 69.9 | 684.8–814.1 | 387.0 |

## Observations

- Stop-and-Wait mean goodput changed from 396.1 kbps at 0% loss to 218.8 kbps at 15% loss (-177.3 kbps).
- Go-Back-N mean goodput changed from 3161.4 kbps at 0% loss to 737.6 kbps at 15% loss (-2423.8 kbps).
- Selective Repeat mean goodput changed from 3169.9 kbps at 0% loss to 764.8 kbps at 15% loss (-2405.1 kbps).
- At 0% loss, the highest measured mean goodput was Selective Repeat at 3169.9 kbps.
- At 2% loss, the highest measured mean goodput was Go-Back-N at 2425.1 kbps.
- At 5% loss, the highest measured mean goodput was Selective Repeat at 1744.4 kbps.
- At 10% loss, the highest measured mean goodput was Selective Repeat at 1188.7 kbps.
- At 15% loss, the highest measured mean goodput was Selective Repeat at 764.8 kbps.
- At 15% loss, Go-Back-N averaged 1528.7 retransmissions (SD 133.7).
- At 15% loss, Selective Repeat averaged 387.0 retransmissions (SD 19.0).

## Limitations
- Only three repetitions were run per configuration; small differences between GBN and SR should not be described as statistically significant.
- Results use localhost with emulated 10 ms one-way delay and no bandwidth cap. Operating-system scheduling can cause occasional spurious timeouts even at 0% loss.
- DATA and ACK channels use separate deterministic seeds, recorded in the raw CSV and metadata. Real-time timeout behaviour can still vary because the number and timing of transmitted packets are runtime-dependent.
- No failed run was removed silently; check the raw CSV for the exact status and exit codes.
