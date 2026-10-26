#!/usr/bin/env python3
"""Audit fresh one-repetition A-D runs and their actual server/client logs."""
import csv, hashlib, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {"A": 15, "B": 12, "C": 12, "D": 21}
INPUT = os.path.join(ROOT, "experiments", "data", "input_1048576.bin")
with open(INPUT, "rb") as f:
    input_sha = hashlib.sha256(f.read()).hexdigest()
errors = []
total = 0
for batch, count in EXPECTED.items():
    path = os.path.join(ROOT, "verification", f"fresh_{batch}_raw.csv")
    if not os.path.exists(path):
        print(f"{batch}: missing CSV (batch may still be running)")
        errors.append((batch, 0, ["missing CSV"]))
        continue
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    bad = []
    for line, row in enumerate(rows, 2):
        fail = []
        for key, expected in (("status", "ok"), ("hash_match", "1"), ("exit_code", "0"),
                              ("server_exit", "0"), ("client_exit", "0"),
                              ("file_bytes", "1048576"), ("file_bytes_received", "1048576")):
            if row.get(key) != expected: fail.append(key)
        try:
            if int(row["data_seed"]) != int(row["seed"]): fail.append("data_seed")
            if int(row["ack_seed"]) != int(row["seed"]) + 1000003: fail.append("ack_seed")
            calc = int(row["file_bytes"]) * 8 / float(row["time_ms"])
            if abs(float(row["goodput_kbps"]) - calc) > 0.2: fail.append("goodput")
        except (KeyError, ValueError, ZeroDivisionError): fail.append("metrics")
        prefix = os.path.join(ROOT, row.get("log_prefix", ""))
        try:
            with open(prefix + ".server.log", encoding="utf-8", errors="replace") as f: sl = f.read()
            with open(prefix + ".client.log", encoding="utf-8", errors="replace") as f: cl = f.read()
            sm = re.search(r"^RESULT .*source_sha256=([0-9a-f]{64})", sl, re.M)
            cm = re.search(r"^RECV .*received_sha256=([0-9a-f]{64})", cl, re.M)
            if not (sm and cm and sm.group(1) == input_sha and cm.group(1) == input_sha): fail.append("logs/hash")
        except OSError: fail.append("missing logs")
        if fail: bad.append((line, fail))
    total += len(rows)
    ok = len(rows) == count and not bad
    print(f"{batch}: rows={len(rows)}/{count}, invalid={len(bad)}, status={'PASS' if ok else 'FAIL'}")
    for line, fields in bad[:10]: print(f"  line {line}: {', '.join(fields)}")
    if not ok: errors.append((batch, len(bad), ["row count or validation failure"]))
print(f"Total: {total}/60; fresh experiment audit: {'PASS' if total == 60 and not errors else 'INCOMPLETE/FAIL'}")
sys.exit(0 if total == 60 and not errors else 1)
