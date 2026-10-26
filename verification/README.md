# Verification Record

This release was updated after the earlier audit. Historical logs in this folder refer to earlier revisions unless explicitly named `fresh_*_2026-10-24`. The embedded Git history is intentionally not included; experiment metadata records the source revision used for the packaged CSVs.

## Fresh checks on this revision

- Clean build: rerun with `make clean && make -j2`; GCC flags include `-Wall -Wextra`.
- Unit tests: rerun with `./test_units`.
- Channel tests: rerun with `./test_channel`; includes an invalid-socket test proving immediate UDP send errors are returned and counted.
- Full suite: `fresh_make_test_2026-10-24.log` and `.exit` show a fresh complete `make test` run; exit code `0`, 93 end-to-end cases passed, GBN 24/24, SR 27/27, hash-integrity 48/48.
- Port parsing: `abc`, `12abc`, `65536`, and `0` are rejected by both server and client.

## Packaged experiment data audit

The packaged A–D raw CSVs contain 180 rows total (A 45, B 36, C 36, D 63), three repetitions per configuration. Their CSV fields pass checks for successful recorded status, zero recorded process exit codes, `hash_match=1`, byte counts, directional seed relation, and goodput consistency. The per-run `results/logs/` files are excluded from the ZIP by `.gitignore`, so this package cannot independently re-read the old run logs or verify the hashes against them. The CSVs are historical measurements from the earlier audit working copy, not fresh results from the latest source revision. See `experiment_data_audit.txt` for the current scope and outcome.

Fresh one-repetition validations of batches A–D passed: 15 + 12 + 12 + 21 = 60 runs, all with successful status, zero process exits, hash match, matching source/received SHA-256 in the actual logs, correct directional seeds and goodput consistency. CSVs and metadata are `verification/fresh_[A-D]_raw.csv` / `.meta.txt`; per-run logs are under `experiments/results/logs/fresh_[A-D]_raw/`. The earlier three-repetition datasets remain separate and are still the source for the report statistics.

## Current hardening scope

- Packet encoder/decoder validates packet types, reserved fields, payload lengths, and packet-specific payload constraints.
- CLI numeric options and positional ports use strict range/full-string parsing.
- Protocol file reads/writes/flushes check errors.
- Channel emulator checks queue allocation, condition-variable and thread initialization, invalid sends, and queue overflow; immediate UDP send errors are returned, and asynchronous send errors are counted in channel statistics.
- Rare OS/resource-failure behaviour cannot be exhaustively proven by ordinary success-path tests.
