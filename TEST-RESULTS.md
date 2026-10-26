# Test Results — Reliable Data Transfer over UDP

Environment: Linux x86-64, GCC 14.2.0, Python 3.13.5.

## Latest source revision (2026-10-24)

- `make clean && make -j2`: **PASS**, clean build with `-Wall -Wextra` and no compiler warnings visible.
- `./test_units`: **PASS** after packet validation, RTO and SHA-256 checks.
- `./test_channel`: **PASS** after adding immediate and asynchronous UDP send-error coverage plus queue-overflow coverage; the test verifies invalid socket errors are returned or counted and a full queue returns `-1`.
- Port parser smoke checks: both client and server reject `abc`, `12abc`, `65536`, and `0`.
- Full `make test`: **PASS**, exit code 0. Fresh output and exit code are retained in `verification/fresh_make_test_2026-10-24.log` and `verification/fresh_make_test_2026-10-24.exit`.

## Packaged experiment data

- Existing A–D CSVs contain 180 rows: A 45, B 36, C 36, D 63, three repetitions per configuration.
- The CSV data-field audit passes all 180 rows for recorded status, process exit codes, file sizes, hash-match field, directional seeds and goodput calculation.
- Per-run server/client logs for those historical CSVs are not included in this ZIP, so their original SHA-256 lines cannot be independently rechecked from this package.
- Fresh A–D one-repetition validation: **PASS, 60/60 runs**. `verification/audit_fresh_experiments.py` checked every row against its real server/client logs and SHA-256 values. These one-repetition checks do not replace the historical three-repetition datasets used for report statistics.

## Known limitations

- Asynchronous UDP send failures occur after `channel_send()` has returned; these are counted in `CHANNEL ... send_errors=...`, but cannot be synchronously returned to the original protocol call.
- Rare operating-system resource failures cannot be exhaustively verified with ordinary success-path tests.
- The report's experiment measurements are localhost emulator results and are from the earlier audit working copy. The team should not describe them as fresh measurements from this exact source revision.
