#!/usr/bin/env python3
"""Read-only validation of packaged A-D raw experiment data and per-run logs."""
import csv
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "experiments", "results")
INPUT = os.path.join(ROOT, "experiments", "data", "input_1048576.bin")
EXPECTED_ROWS = {"A": 45, "B": 36, "C": 36, "D": 63}

with open(INPUT, "rb") as f:
    input_sha = hashlib.sha256(f.read()).hexdigest()
print(f"Input: 1048576 bytes; SHA-256={input_sha}")
all_errors = []
all_rows = 0

for batch, expected_count in EXPECTED_ROWS.items():
    path = os.path.join(RES, f"experiment_{batch}_raw.csv")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    errors = []
    logs_found = 0
    for line_no, row in enumerate(rows, start=2):
        checks = {
            "status": row.get("status") == "ok",
            "hash_match": row.get("hash_match") == "1",
            "exit_code": row.get("exit_code") == "0",
            "server_exit": row.get("server_exit") == "0",
            "client_exit": row.get("client_exit") == "0",
            "bytes": row.get("file_bytes") == row.get("file_bytes_received") == "1048576",
            "data_seed": row.get("data_seed") == row.get("seed"),
            "ack_seed": int(row.get("ack_seed", "-1")) == int(row.get("seed", "0")) + 1000003,
        }
        try:
            calculated = int(row["file_bytes"]) * 8 / float(row["time_ms"])
            checks["goodput_rounding"] = abs(float(row["goodput_kbps"]) - calculated) <= 0.2
        except (KeyError, ValueError, ZeroDivisionError):
            checks["goodput_rounding"] = False
        prefix = os.path.join(ROOT, row.get("log_prefix", ""))
        try:
            with open(prefix + ".server.log", encoding="utf-8", errors="replace") as f:
                server_log = f.read()
            with open(prefix + ".client.log", encoding="utf-8", errors="replace") as f:
                client_log = f.read()
            sm = re.search(r"^RESULT .*source_sha256=([0-9a-f]{64})", server_log, re.M)
            cm = re.search(r"^RECV .*received_sha256=([0-9a-f]{64})", client_log, re.M)
            checks["logs_and_hashes"] = bool(sm and cm and sm.group(1) == input_sha and cm.group(1) == input_sha)
            logs_found += 1
        except OSError:
            checks.pop("logs_and_hashes", None)
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            errors.append((line_no, failed))
    count_ok = len(rows) == expected_count
    status_ok = not errors and count_ok
    all_rows += len(rows)
    print(f"{batch}: rows={len(rows)}/{expected_count}; invalid CSV rows={len(errors)}; logs verified={logs_found}/{len(rows)}; CSV status={'PASS' if status_ok else 'FAIL'}")
    for error in errors[:10]:
        print(f"  line {error[0]}: {', '.join(error[1])}")
    if not status_ok:
        all_errors.append((batch, errors, count_ok))

print(f"Total rows: {all_rows}/180")
print("CSV DATA AUDIT: " + ("PASS" if all_rows == 180 and not all_errors else "FAIL"))
print("PER-RUN LOG AUDIT: " + ("PASS" if all_rows == 180 and all(os.path.exists(os.path.join(ROOT, row.get("log_prefix", "")) + suffix) for batch in EXPECTED_ROWS for row in csv.DictReader(open(os.path.join(RES, f"experiment_{batch}_raw.csv"), newline="", encoding="utf-8")) for suffix in (".server.log", ".client.log")) else "NOT AVAILABLE (per-run logs are not packaged)"))
sys.exit(0 if all_rows == 180 and not all_errors else 1)
