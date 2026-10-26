# Experiment C — Retransmissions vs Reordering Probability

## Hypothesis
Increasing reordering can create gaps at the receiver and duplicate acknowledgements, potentially increasing retransmissions. Go-Back-N may resend more already-received packets than Selective Repeat because it retransmits a suffix of its window after a timeout.

## Setup and controls
- Input: deterministic 1 MiB file.
- Protocols: Stop-and-Wait (window 1), Go-Back-N (window 8), Selective Repeat (window 8).
- Reordering probabilities: 0%, 5%, 10%, 20% on both directional channels.
- Loss and corruption: 0%; one-way delay 10 ms; jitter 0; adaptive RTO.
- Repetitions: 3 per configuration. Three repetitions per configuration used base seeds 42, 43, 44; DATA seeds were 42, 43, 44 and ACK seeds were 1000045, 1000046, 1000047 across the batch.
- Integrity: each successful row requires `hash_match=1` and zero process exit codes.

## Metric
Retransmission count is read from the sender's RESULT line. The table reports the mean and standard deviation across successful runs; raw per-run counts remain in the CSV.

## Results
| Protocol | Reordering | Successful runs | Mean retransmissions | SD | Min–max | Mean goodput (kbps) |
|---|---:|---:|---:|---:|---:|---:|
| Stop-and-Wait | 0% | 3/3 | 2.0 | 2.6 | 0.0–5.0 | 394.1 |
| Stop-and-Wait | 5% | 3/3 | 91.3 | 2.3 | 90.0–94.0 | 366.6 |
| Stop-and-Wait | 10% | 3/3 | 162.3 | 18.6 | 147.0–183.0 | 340.7 |
| Stop-and-Wait | 20% | 3/3 | 265.3 | 26.1 | 236.0–286.0 | 306.4 |
| Go-Back-N | 0% | 3/3 | 2.7 | 4.6 | 0.0–8.0 | 3139.9 |
| Go-Back-N | 5% | 3/3 | 450.7 | 44.1 | 400.0–480.0 | 1284.6 |
| Go-Back-N | 10% | 3/3 | 827.7 | 91.1 | 731.0–912.0 | 791.5 |
| Go-Back-N | 20% | 3/3 | 1591.0 | 60.7 | 1522.0–1636.0 | 422.7 |
| Selective Repeat | 0% | 3/3 | 2.7 | 4.6 | 0.0–8.0 | 3114.1 |
| Selective Repeat | 5% | 3/3 | 75.7 | 8.7 | 66.0–83.0 | 2510.5 |
| Selective Repeat | 10% | 3/3 | 136.7 | 26.8 | 107.0–159.0 | 2191.4 |
| Selective Repeat | 20% | 3/3 | 48.7 | 15.5 | 31.0–60.0 | 1877.3 |

## Observations

- Stop-and-Wait mean retransmissions changed from 2.0 at 0% reordering to 265.3 at 20% (+263.3 packets).
- Go-Back-N mean retransmissions changed from 2.7 at 0% reordering to 1591.0 at 20% (+1588.3 packets).
- Selective Repeat mean retransmissions changed from 2.7 at 0% reordering to 48.7 at 20% (+46.0 packets).
- At 20% reordering, GBN averaged 1591.0 retransmissions and SR averaged 48.7; the observed difference was 1542.3 packets.

## Limitations
The emulator applies reordering on both DATA and ACK directions. Retransmissions can also depend on timeout scheduling, so use the spread and individual logs rather than treating a small mean difference as conclusive. Results are localhost measurements with no bandwidth cap.
