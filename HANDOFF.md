# Engineer 1 Handoff — Common Foundation, Stop-and-Wait, Adaptive RTO

## 1. What's done

| Area | Status | File |
|---|---|---|
| Common packet format + checksum | Done, frozen | `src/packet.[ch]` |
| UDP socket layer | Done | `src/net.[ch]` |
| Channel emulator (Engineer 4 scope) | Done: loss, dup, reorder, corrupt, delay, jitter, seed | `src/channel.[ch]` |
| Adaptive RTO (Jacobson/Karels + Karn + backoff), fixed-RTO mode | Done | `src/rto.[ch]` |
| ARQ plug-in interface + shared helpers | Done, frozen | `src/arq.[ch]` |
| Stop-and-Wait | Done, tested | `src/saw.c` |
| Go-Back-N (Engineer 2 scope) | Done, tested with windows 1/4/8/16/32 | `src/gbn.c` |
| Selective Repeat (Engineer 3 scope) | Done, tested with windows 1/2/4/8/16/32 | `src/sr.c` |

## 2. Architecture

```
server.c / client.c          (parse options, open socket, pick protocol)
        │
   arq_find("saw"|"gbn"|"sr") → proto->send() / proto->recv()
        │
   saw.c   gbn.c   sr.c       (ARQ logic only)
        │
   net_send_pkt / net_recv_pkt   (encode/decode + checksum)
        │
   channel_send()             ← Engineer 4's emulator lives here
        │
     sendto()
```

Connection start: the client sends HELLO every 300 ms until the first DATA
packet arrives. The server waits for one valid HELLO and remembers the client.

End of file: a DATA packet with `len = 0`. After ACKing it, the receiver keeps
re-ACKing for 1 s (`arq_recv_linger`) in case its last ACK was lost.

## 3. Packet format (10-byte header)

| Offset | Field | Size | Meaning |
|---|---|---|---|
| 0 | type | 1 | 1 = HELLO, 2 = DATA, 3 = ACK |
| 1 | reserved | 1 | always 0 |
| 2 | seq | 4 | DATA: packet number from 0. ACK: number being ACKed |
| 6 | len | 2 | payload bytes, 0–1024 (0 = end of file) |
| 8 | checksum | 2 | Internet checksum over header + payload |
| 10 | payload | len | file data |

All multi-byte fields are in network byte order (`htonl`/`htons`), so the
format is portable. Sequence numbers are 32-bit and never wrap for our file
sizes, so SAW, GBN and SR all use the same numbering.

## 4. Checksum

16-bit one's-complement Internet checksum (the same idea as UDP/TCP/IP):
add 16-bit words, fold the carries back in, then invert.
The sender computes it with the checksum field set to 0. The receiver zeroes
that field, recomputes, and compares. On a mismatch, `net_recv_pkt()` returns
`NET_CORRUPT` and the packet is never used as data. The protocol recovers
normally because no ACK goes back, so the sender's timer resends.

## 5. Adaptive RTO (`rto.c`)

```
first sample:  SRTT = RTT,  RTTVAR = RTT/2
later:         RTTVAR = 3/4·RTTVAR + 1/4·|SRTT − RTT|
               SRTT   = 7/8·SRTT   + 1/8·RTT
RTO = SRTT + max(10 ms, 4·RTTVAR), clamped to [20 ms, 2000 ms], initial 200 ms
                (the 10 ms floor is RFC 6298's G term: without it a constant RTT
                 drives RTTVAR→0, RTO≈RTT, and causes spurious retransmissions)
timeout:       backoff ×2        (effective timeout = RTO × backoff)
new data ACKed: backoff = 1      (rto_on_progress)
```

**Why the backoff reset exists:** without it, GBN got stuck. After a timeout,
every in-flight packet is a retransmission, so Karn discards every RTT sample.
The doubled RTO then stays at the 2 s cap forever, and a 1 MB transfer with 10%
loss didn't finish in 120 s. Clearing the backoff when an ACK confirms new data
(Linux TCP does the same) fixed it, and the same run now takes about 9 s.
Karn's rule is unchanged: retransmitted packets still never give RTT samples.

Plain-English version: SRTT is the average RTT and RTTVAR is how much it jumps
around, so RTO is "average plus a safety margin".

**Karn's algorithm:** call `rto_on_sample()` only for packets that were sent
exactly once. If a packet was retransmitted, we can't tell which copy the ACK
is for, so that sample is thrown away. See `saw.c`: `if (tries == 1)`.

**Fixed RTO** (`--rto 100`) ignores samples and timeouts, and is capped at 2000 ms. This is for
Engineer 4's RTO-sensitivity experiment.

## 6. Stop-and-Wait (`saw.c`)

- **Sender:** send N, wait for ACK N until the RTO expires. On timeout, back
  off and resend N. Give up after 50 tries.
- **Receiver:** if `seq == expected`, write it, ACK it, then `expected++`.
  If `seq < expected`, it's a duplicate: re-ACK it but don't write it.
  Corrupted packets are dropped by the checksum.

## 6b. Go-Back-N (`gbn.c`)

- **Sender:** keeps `base` (oldest unACKed) and `next` (next new seq), and
  sends while `next < base + window`. There is **one timer**, for `base`.
  ACK k is **cumulative**, so `base = k + 1`. On timeout it resends
  **everything** from `base` to `next − 1`.
- **Receiver:** accepts only `seq == expected`. Anything else is discarded,
  and it re-ACKs `expected − 1`. There is no buffer.
- The window buffer is `window` slots, indexed by `seq % window`.

## 6c. Selective Repeat (`sr.c`)

- **Sender:** window `[base, base + W)`, slot `seq % W`.
  - **Own timer per packet:** each unACKed packet's timer is fixed when it is
    sent (`expires_at = send time + RTO`). A later backoff never stretches
    timers that are already running.
  - **One thread:** the loop sleeps until the earliest deadline (rounded *up*,
    so it never wakes early). It resends **only** the expired packets. Timers
    due within the same 1 ms burst count as one loss event, so the RTO backs
    off once.
  - **ACK k is selective:** it marks packet k only. `base` slides over
    consecutive ACKed packets.
  - **Karn:** a sample is taken only from a packet sent once.
- **Receiver:** buffer of W slots.
  - **In window:** ACK it, buffer it if new, then deliver consecutive buffered
    packets from `rcv_base`.
  - **Below `rcv_base`:** already delivered, so re-ACK it (counted as a
    duplicate).
  - **Beyond the window:** ignored.
  - **EOF:** buffered like any other packet. The transfer finishes only when
    everything before it has been written.
- **Viva point:** at 10% loss, GBN sent 5073 packets and SR sent **1138**. A
  single loss costs SR 1 retransmission at any window size; GBN pays 1/4/7 for
  w = 1/4/8.

## 6d. Channel emulator (`channel.c`)

Every send goes `net_send_pkt → channel_send → sendto`, on both sides. The
server's DATA and the client's ACKs are impaired independently, so
`--delay 20` gives an RTT of about 40 ms.

| Option (both sides) | Effect |
|---|---|
| `--loss P` | drop silently (P = 0..1 or `10%`) |
| `--corrupt P` | flip one random bit in a copy, so the receiver's checksum fails |
| `--dup P` | deliver two real copies |
| `--reorder P` | hold the packet an extra 5–25 ms, so later packets overtake it |
| `--delay MS` / `--jitter MS` | one-way delay ± uniform jitter, **FIFO** (jitter never reorders) |
| `--seed N` | default 1. Exactly 7 random draws per packet (splitmix64, not `rand()`) |

- **Delay is non-blocking.** `channel_send()` queues the packet and returns,
  and one delivery thread sends at the due time. This is needed because the
  ARQ code waits in `poll()` and never calls back into the channel.
- **No delay, jitter or reorder configured:** packets are sent inline, so
  there is no thread on that path.
- **Stats line:** each process prints
  `CHANNEL sent=.. dropped=.. corrupted=.. duplicated=.. reordered=..` to
  stderr at exit.
- **Old test hooks:** `--drop-every` and `--corrupt-every` still work, for the
  exact-value tests.

**Why jitter is FIFO:** with independent jitter, a back-to-back GBN window
arrived out of order. With 20 ± 5 ms and no loss, GBN made 988
retransmissions in 21 s, and after the fix it makes 0 retransmissions in
1.08 s. Reordering is a separate knob, so experiments can vary it on its own.

**Reproducibility:** the same seed and configuration give identical channel
decisions. Measured end to end, three repeated runs of each protocol gave
identical packets_sent and retransmissions, including the combined
loss + dup + reorder + corrupt + delay + jitter configuration.

## 6e. File integrity: SHA-256 (`hash.c`, `server.c`, `client.c`)

The assignment says integrity is verified by hash comparison of the source
and received file. The packet checksum protects each packet on the wire. The
hash proves the **whole file** is identical, so the two are independent.

- **Algorithm:** SHA-256 through OpenSSL's EVP API (`libcrypto`). It is
  computed over the file's bytes only, never over headers, sequence numbers
  or retransmissions.
- **Sender:** `sha256_file(source)` runs before the transfer, so it isn't
  counted in `time_ms`. RESULT gets `source_sha256=<hex>` appended.
- **Receiver:** the hash is computed only after recv has returned (EOF
  delivered, linger done) and `fclose()` has succeeded. RECV gets
  `received_sha256=<hex>`.
- **Comparison:** happens at the receiver. With the packet format frozen,
  nothing can carry the receiver's hash back to the sender. So the receiver
  gets the expected (source) hash out-of-band with `--expect-sha256 HEX`, the
  same way a download page publishes a checksum. RECV then gets
  `hash_match=1|0`, stderr shows `File Integrity: PASSED/FAILED`, and a
  mismatch exits with code **2**.
- **Experiment scripts:** to determine integrity, pass `--expect-sha256`
  and read `hash_match` from the client's RECV line (or compare
  `source_sha256` with `received_sha256`). Everything else stays in RESULT.

## 7. Compile and run

```
make
./server 9000 input.bin --proto saw [--rto adaptive|MS]
./client 127.0.0.1 9000 output.bin --proto saw
make test
```

## 8. Tests performed

- **Unit tests** (`./test_units`, 15/15 pass): packet round trip, 1-bit
  payload error detected, corrupted seq detected, truncated packet rejected,
  RTO first and second sample match the formulas, convergence, backoff
  doubling and cap, min clamp, fixed mode.
- **End-to-end** (`tests/run_tests.sh`, 8/8 pass). Every test checks
  `cmp` + SHA-256 of the received file.

| # | Test | Packets sent | Retx | Result |
|---|---|---|---|---|
| 1 | Normal transfer, 1 MB | 1025 | 0 | identical |
| 2 | Lost DATA (every 10th) | 1138 | 113 | identical |
| 3 | Corrupted DATA (every 7th) | 1195 | 170 | identical, 170 caught by checksum |
| 4 | Lost ACK (every 8th) | 1171 | 146 | identical, 146 duplicates not re-written |
| 5 | Corrupted ACK (every 9th) | 1153 | 128 | identical |
| 6 | Delayed ACK 20 ms, adaptive RTO | 22 | 1 | identical, spurious retx → duplicate handled |
| 7 | Delayed ACK 25 ms, fixed RTO 100 | 21 | 0 | identical |
| 8 | Loss + corruption combined | 1296 | 271 | identical |

**Go-Back-N** (1 MB file = 1025 packets):

| Test | Window | Packets sent | Retx | Timeouts | Result |
|---|---|---|---|---|---|
| Normal | 1, 4, 8, 16, 32 | 1025 | 0 | 0 | identical (all 5) |
| Lost DATA (every 10th) | 8 | 5073 | 4048 | 507 | identical |
| Lost DATA (every 10th) | 32 | 5067 | 4042 | 129 | identical |
| Corrupted DATA (every 7th) | 8 | 2385 | 1360 | 171 | identical |
| Lost ACK (every 8th) | 8 | 1025 | **0** | 0 | identical. The next cumulative ACK covers the lost one |
| Corrupted ACK (every 9th) | 8 | 1026 | 1 | 1 | identical |
| Delayed ACK 20 ms | 8 | 21 | 0 | 0 | identical (20 KB file) |
| Loss + corruption combined | 16 | 4629 | 3604 | 227 | identical |

GBN resends the whole window for one loss: about 4 retransmissions per lost
packet at 10% loss. This is the waste Selective Repeat avoids, so it is
evidence for our claim.

Note: the drop pattern is "every Nth packet", which lines up with GBN's resend
bursts and exaggerates the cost. E4's random, seeded emulator gives the real
numbers for the report.

## 8b. Verification suite (`make test`, ~10 min)

| Suite | Count | What it proves |
|---|---|---|
| `test_channel` | 24 | emulator alone over real UDP: loss 0/10/100 %, dup, reorder (and FIFO control), corruption, non-blocking delay, jitter, seed determinism, combined |
| `test_units` | 22 | checksum, encode/decode, Jacobson/Karels formulas, backoff, G margin, fixed mode, SHA-256 against NIST vectors |
| `tests/run_tests.sh` | 93 |  (incl. 24 emulator transfers: SAW/GBN/SR × none, loss 5/10 %, corrupt, reorder, dup, delay+jitter, combined) end-to-end SAW + GBN. Both processes exit 0 and the file is identical. T1–T8 assert **exact** counts (e.g. one loss → retx 1/4/7 for w = 1/4/8) |
| `tests/gbn_packet_tests.py` | 24 | packet-level: a fake peer checks every GBN rule (window bound, [base,next) resend, cumulative/dup ACKs, Karn, EOF, linger) |
| `tests/hash_tests.sh` | 48 | SHA-256 end to end: 43 transfers (sizes 0 B–8 MB × SAW/GBN/SR; loss, corruption, combined; 3× determinism), wrong-hash detection, byte-for-byte |
| `tests/sr_packet_tests.py` | 27 | packet-level SR: only the lost packet is resent, base waits for its oldest packet, per-packet timers, backoff ×2, buffering, early EOF, duplicates |

## 9. Known issues / limitations

0a. Emulator limitations:
    - Two packets due within a fraction of a millisecond can occasionally
      swap order between runs, because real-time scheduling decides which
      leaves first. Decisions themselves never change.
    - FIFO jitter biases mean latency upward when packets are closer together
      than the jitter span (mean 34 ms for 30 ± 10 ms at 5 ms spacing).
    - The reorder hold is a fixed 5–25 ms.
    - The queue holds at most 4096 packets; overflow is counted as
      `queue_full`.
    - Delivery can be late by scheduler latency (a few ms under load), but
      never early.
0. Receiver linger is quiet-based: after the EOF it keeps re-ACKing and exits
   only after 2.5 s (RTO_MAX + 500 ms) with no packets. Each run's client
   therefore exits about 2.5 s after the server prints RESULT. Experiment
   scripts should read RESULT from the server.

1. The placeholder `--delay-ms` is a **blocking sleep**. With a fixed RTO
   smaller than the delay, duplicates pile up at the receiver and the
   transfer fails. Real delay needs a non-blocking delay queue, which is
   Engineer 4's emulator.
2. The placeholder channel is counter-based (every Nth packet), not
   probabilistic and seeded. Engineer 4 replaces it.
3. No file hash is printed yet (Engineer 3 owns hashing). The test script
   checks SHA-256 externally.
4. One client per server run (enough for this project).

## 10. Integration instructions

### Engineer 2 (GBN)

GBN is implemented and tested. Please review `src/gbn.c` so you can explain
it in the viva, and own any changes to it from here on.

### Engineer 3 (SR)

- Edit **only** `src/sr.c`. It is already registered in `arq.c` and
  selectable with `--proto sr`. The window comes in `ctx->window`.
  `gbn.c` is the closest example (window buffer `seq % window`, Karn,
  `rto_on_progress`).
- The textbook SR rule "window ≤ half the sequence space" is satisfied
  automatically: sequence numbers are 32-bit and never wrap for our file
  sizes. Mention this in the viva.
- Use `net_send_pkt()`, `arq_wait()` (sender), `arq_recv_next()`,
  `arq_send_ack()` and `arq_recv_linger()` (receiver). Never call `sendto()`
  directly, or the emulator won't see your packets.
- Use `ctx->rto` with Karn's rule: `rto_on_sample()` only for packets sent
  once, `rto_on_timeout()` on expiry, and `rto_on_progress()` whenever an ACK
  confirms new data. One shared timer on the oldest packet is
  fine for GBN. SR needs per-packet send times, but all can use the same
  `rto_get_ms()`.
- ACK meaning: GBN uses ACK N = "everything up to N received" (cumulative).
  SR uses ACK N = "packet N received" (individual). The header is the same.
- Fill in `ctx->stats` (`packets_sent`, `retransmissions`, `timeouts`,
  `file_bytes`, `start_ms`/`end_ms`) so the RESULT line is right.
- Copy `tests/run_tests.sh`, change `saw` to your protocol, and add
  `--window` values.

### Engineer 4 (emulator + experiments)

- Replace **`src/channel.c` only**. Keep the `channel_send()` signature.
  Extend `channel_cfg_t` and the options in `options.c` (loss rate, dup,
  reorder, corrupt, delay, jitter, seed).
- Apply the emulator on **both** sides (client ACKs pass through
  `channel_send()` too).
- For delay and reordering, don't block. Hold packets in a queue and release
  them later (for example, flush due packets on each `channel_send()` call and
  also before `net_recv_pkt()` polls).
- Parse the `RESULT ...` line for CSV. Use `--rto MS` for Experiment 4.

## 11. Commits

```
feat: add common packet structure and checksum
feat: add UDP socket layer and channel hook
feat: add adaptive RTO (Jacobson/Karels + Karn)
feat: add ARQ interface and stop-and-wait
test: add unit and end-to-end SAW tests
docs: add README and engineer 1 handoff
fix: clear RTO backoff when new data is ACKed
feat: implement go-back-n
test: add go-back-n end-to-end tests
docs: update handoff for go-back-n
```
