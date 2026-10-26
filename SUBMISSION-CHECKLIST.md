# Submission Checklist

## Project evidence prepared

- [x] Core source, Makefile and test scripts included.
- [x] Clean build completed with `-Wall -Wextra` and no visible compiler warnings.
- [x] Fresh `make test` completed successfully on the integrated source tree (exit code 0); full output and exit code are retained in `verification/final_integrated_make_test_2026-10-24.log` and `final_integrated_make_test_2026-10-24.exit`.
- [x] Experiments A–D include raw CSVs, metadata, three repetitions per configuration, summaries, plots and written explanations.
- [x] Existing A–D CSVs pass the numeric/data-field audit (180/180 rows); their per-run server/client logs are not packaged, so old source/destination hashes cannot be independently checked from logs in this ZIP. Re-run A–D for fresh results if time permits.
- [x] One-page proposal, report, handoff notes and AI-use disclosure draft included.

## Team actions still required before submission

- [ ] Every member reviews `AI-USE.md` and adds all relevant AI use from the original implementation and other sessions. Do not submit until accurate.
- [ ] Review `PROPOSAL.pdf` and confirm its planned work split matches the original proposal; it is not proof of actual contributions.
- [ ] Confirm every team member can explain the protocol code, test changes, experiments and measured results for the viva.
- [ ] Initialize a fresh Git history in the team repository only after the team verifies the final package; the archive omits the old embedded `.git` directory because it does not establish all four members' contributions.
- [ ] Have each member commit their genuine work under their own Git identity; do not manufacture commits or attribute work inaccurately.
- [x] Retain the exit code and complete output from the fresh `make test` run on this integrated source revision.
- [ ] Check the course portal for any required report/proposal file naming or upload format.

## Known limitations

The channel emulator now checks allocation/condition-variable/thread initialization, validates queued packets, returns immediate `sendto()` failures, counts asynchronous delivery errors, and rejects queue overflow. Asynchronous send errors are recorded because the original `channel_send()` call has already returned. Packet validation, numeric option validation, file I/O checks, and positional port parsing are hardened. Stretch goals were not added because Core evidence took priority.

## Follow-up after robustness fixes

- [ ] Complete `AI-USE.md` based on every member's actual AI use.
- [x] Review channel thread/condition-variable initialization and `sendto()` error reporting; immediate errors, asynchronous error counting and queue overflow are covered by channel tests.
- [x] Positional port parsing in `server.c` and `client.c` now rejects malformed and out-of-range ports.
- [x] Fresh one-repetition runs for A–D completed and audited: 60/60 successful, with source/destination hashes verified from real logs. Historical three-repetition datasets remain the source for the report statistics.
- [ ] Confirm proposal names/work split and official submission requirements.
