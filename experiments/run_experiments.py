#!/usr/bin/env python3
"""
run_experiments.py - experiment runner for the RDT-over-UDP project.

Runs ./server and ./client (unchanged) for many configurations and writes one
CSV row per transfer. All metrics come from the programs' own RESULT / RECV /
CHANNEL lines; nothing is re-timed or invented. A failed run is still written
as a row (status != ok) and makes the runner exit non-zero.

Usage (from the repository root, after `make`):
  python3 experiments/run_experiments.py list                # show batches
  python3 experiments/run_experiments.py smoke               # quick check
  python3 experiments/run_experiments.py A                   # one batch
  python3 experiments/run_experiments.py all                 # A + B + C + D
  python3 experiments/run_experiments.py one --proto sr --window 8 --loss 0.05
  python3 experiments/run_experiments.py A --dry-run         # print plan only
"""
import argparse, csv, datetime, hashlib, os, platform, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(ROOT, "experiments")
DATA = os.path.join(EXP, "data")
RESULTS = os.path.join(EXP, "results")

# ---------------------------------------------------------------- defaults
DEFAULTS = dict(
    file_size=1048576,   # 1 MiB input file (same file for every run)
    delay=10,            # one-way delay per direction, ms -> base RTT ~20 ms
    jitter=0,
    seed=42,             # base seed; DATA and ACK paths use distinct derived seeds
    window=8,            # GBN/SR window when not the variable under study
    rto="adaptive",
    reps=1,
)

CSV_COLUMNS = [
    # required columns, in the requested order
    "experiment", "protocol", "window", "file_bytes", "loss", "reorder",
    "corruption", "delay_ms", "jitter_ms", "seed", "data_seed", "ack_seed", "sent_packets",
    "retransmissions", "file_bytes_received", "time_ms", "goodput_kbps",
    "hash_match", "exit_code",
    # extra columns (all from existing program output)
    "rep", "dup", "rto", "status", "server_exit", "client_exit",
    "timeouts", "sender_corrupted_acks", "receiver_corrupted", "receiver_duplicates",
    "data_dropped", "data_corrupted", "data_duplicated", "data_reordered",
    "ack_dropped", "ack_corrupted", "ack_duplicated", "ack_reordered",
    "log_prefix",
]


# ---------------------------------------------------------------- batches
def cfg(experiment, proto, **kw):
    c = dict(experiment=experiment, proto=proto, window=1 if proto == "saw" else DEFAULTS["window"],
             loss=0.0, reorder=0.0, corrupt=0.0, dup=0.0,
             delay=DEFAULTS["delay"], jitter=DEFAULTS["jitter"], seed=DEFAULTS["seed"],
             rto=DEFAULTS["rto"])
    c.update(kw)
    return c

def batch(name):
    P = ["saw", "gbn", "sr"]
    if name == "smoke":
        return [cfg("smoke", p) for p in P] + [
            cfg("smoke", "sr", loss=0.05),
            cfg("smoke", "gbn", reorder=0.10)]
    if name == "A":      # goodput vs loss
        return [cfg("A_goodput_vs_loss", p, loss=l)
                for p in P for l in (0.0, 0.02, 0.05, 0.10, 0.15)]
    if name == "B":      # goodput vs window (loss fixed at 2%)
        return [cfg("B_goodput_vs_window", p, window=w, loss=0.02)
                for p in ("gbn", "sr") for w in (1, 2, 4, 8, 16, 32)]
    if name == "C":      # retransmissions vs reordering (no loss)
        return [cfg("C_retx_vs_reorder", p, reorder=r)
                for p in P for r in (0.0, 0.05, 0.10, 0.20)]
    if name == "D":      # RTO sensitivity (loss fixed at 5%)
        return [cfg("D_rto_sensitivity", p, loss=0.05, rto=r)
                for p in P for r in ("adaptive", "20", "40", "80", "160", "320", "640")]
    if name == "all":
        return batch("A") + batch("B") + batch("C") + batch("D")
    raise SystemExit(f"unknown batch {name!r}")


# ---------------------------------------------------------------- helpers
def make_input(size):
    """Deterministic input: SHA-256 in counter mode (no random generator)."""
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, f"input_{size}.bin")
    if not os.path.exists(path) or os.path.getsize(path) != size:
        out, i = bytearray(), 0
        while len(out) < size:
            out += hashlib.sha256(b"rdt-experiment-input" + i.to_bytes(8, "big")).digest()
            i += 1
        with open(path, "wb") as f:
            f.write(out[:size])
    return path

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()

def kv(line):
    """'RESULT a=1 b=x' -> {'a': '1', 'b': 'x'}"""
    return dict(re.findall(r"(\w+)=(\S+)", line or ""))

def first_line(text, prefix):
    for ln in text.splitlines():
        if ln.startswith(prefix):
            return ln
    return None

def emu_args(c, seed=None):
    # Each process emulates its own outgoing direction. Separate deterministic
    # seeds avoid reusing the same PRNG stream for DATA and ACK traffic.
    a = ["--seed", str(c["seed"] if seed is None else seed)]
    for flag, key in (("--loss", "loss"), ("--reorder", "reorder"),
                      ("--corrupt", "corrupt"), ("--dup", "dup")):
        if c[key] > 0:
            a += [flag, repr(c[key])]
    if c["delay"] > 0:
        a += ["--delay", str(c["delay"])]
    if c["jitter"] > 0:
        a += ["--jitter", str(c["jitter"])]
    return a


def run_one(c, rep, infile, expected, port, logdir, idx, timeout_s, vary_seed=True):
    seed = c["seed"] + (rep if vary_seed else 0)   # rep 0 always uses the configured seed
    data_seed = seed
    ack_seed = seed + 1000003
    cc = dict(c, seed=seed)
    win = ["--window", str(c["window"])]
    data_emu = emu_args(cc, data_seed)
    ack_emu = emu_args(cc, ack_seed)
    tag = f"{idx:03d}_{c['proto']}_w{c['window']}_l{c['loss']}_r{c['reorder']}_c{c['corrupt']}_rto{c['rto']}_ds{data_seed}_as{ack_seed}"
    prefix = os.path.join(logdir, tag)
    outfile = prefix + ".out.bin"

    srv_cmd = [os.path.join(ROOT, "server"), str(port), infile, "--proto", c["proto"],
               "--rto", c["rto"]] + win + data_emu
    cli_cmd = [os.path.join(ROOT, "client"), "127.0.0.1", str(port), outfile,
               "--proto", c["proto"], "--expect-sha256", expected] + win + ack_emu

    with open(prefix + ".server.log", "w") as so, open(prefix + ".client.log", "w") as co:
        so.write("$ " + " ".join(srv_cmd) + "\n"); so.flush()
        co.write("$ " + " ".join(cli_cmd) + "\n"); co.flush()
        srv = subprocess.Popen(srv_cmd, stdout=so, stderr=so)
        # wait until the server is listening (it prints this before blocking)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 5:
            with open(prefix + ".server.log") as f:
                if "waiting for client" in f.read():
                    break
            if srv.poll() is not None:
                break
            time.sleep(0.02)
        cli = subprocess.Popen(cli_cmd, stdout=co, stderr=co)
        timed_out = False
        deadline = time.monotonic() + timeout_s
        for p in (cli, srv):
            try:
                p.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
        if timed_out:
            for p in (cli, srv):
                if p.poll() is None:
                    p.kill(); p.wait()

    stext = open(prefix + ".server.log").read()
    ctext = open(prefix + ".client.log").read()
    res, recv = kv(first_line(stext, "RESULT")), kv(first_line(ctext, "RECV"))
    sch, cch = kv(first_line(stext, "CHANNEL")), kv(first_line(ctext, "CHANNEL"))
    se, ce = srv.returncode, cli.returncode

    # ---- verdict: every failure is explicit
    size = os.path.getsize(infile)
    if timed_out:
        status, code = "timeout", 124
    elif se != 0 or ce == 1:
        status, code = "transfer_failed", (se if se != 0 else ce)
    elif ce == 2 or recv.get("hash_match") != "1":
        status, code = "hash_mismatch", (ce if ce != 0 else 3)
    elif not res or not recv:
        status, code = "parse_error", 3
    elif res.get("source_sha256") != expected:
        status, code = "source_hash_differs", 3
    elif res.get("file_bytes") != str(size) or recv.get("file_bytes") != str(size):
        status, code = "size_mismatch", 3
    else:
        status, code = "ok", 0

    if os.path.exists(outfile):
        os.remove(outfile)          # keep logs, not 1 MiB copies

    return {
        "experiment": c["experiment"], "protocol": c["proto"], "window": c["window"],
        "file_bytes": size, "loss": c["loss"], "reorder": c["reorder"],
        "corruption": c["corrupt"], "delay_ms": c["delay"], "jitter_ms": c["jitter"],
        "seed": seed, "data_seed": data_seed, "ack_seed": ack_seed,
        "sent_packets": res.get("packets_sent", ""),
        "retransmissions": res.get("retransmissions", ""),
        "file_bytes_received": recv.get("file_bytes", ""),
        "time_ms": res.get("time_ms", ""), "goodput_kbps": res.get("goodput_kbps", ""),
        "hash_match": recv.get("hash_match", ""), "exit_code": code,
        "rep": rep, "dup": c["dup"], "rto": res.get("rto", c["rto"] if not res else ""),
        "status": status, "server_exit": se, "client_exit": ce,
        "timeouts": res.get("timeouts", ""), "sender_corrupted_acks": res.get("corrupted", ""),
        "receiver_corrupted": recv.get("corrupted", ""),
        "receiver_duplicates": recv.get("duplicates", ""),
        "data_dropped": sch.get("dropped", ""), "data_corrupted": sch.get("corrupted", ""),
        "data_duplicated": sch.get("duplicated", ""), "data_reordered": sch.get("reordered", ""),
        "ack_dropped": cch.get("dropped", ""), "ack_corrupted": cch.get("corrupted", ""),
        "ack_duplicated": cch.get("duplicated", ""), "ack_reordered": cch.get("reordered", ""),
        "log_prefix": os.path.relpath(prefix, ROOT),
    }


def write_meta(path, name, configs, args, infile, expected):
    def cmd(c):
        try:
            return subprocess.run(c, capture_output=True, text=True, cwd=ROOT).stdout.strip()
        except OSError:
            return "?"
    commit = cmd(["git", "rev-parse", "--short", "HEAD"])
    git_status = cmd(["git", "status", "--porcelain"])
    if commit:
        commit_text = commit + (" (uncommitted changes)" if git_status else "")
    else:
        commit_text = "not available (release archive has no .git history)"
    cpu = ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except (OSError, StopIteration):
        cpu = platform.processor()
    with open(path, "w") as f:
        f.write(f"batch:        {name}\n")
        f.write(f"started:      {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"git commit:   {commit_text}\n")
        f.write(f"machine:      {platform.platform()} | {cpu} | {os.cpu_count()} CPUs\n")
        f.write(f"compiler:     {cmd(['gcc', '--version']).splitlines()[0] if cmd(['gcc', '--version']) else '?'}\n")
        f.write(f"input file:   {os.path.relpath(infile, ROOT)} ({os.path.getsize(infile)} bytes)\n")
        f.write(f"input sha256: {expected}\n")
        f.write(f"repetitions:  {args.reps} (" + ("rep k uses seed + k" if args.rep_seed == "vary" else "same seed every rep") + ")\n")
        f.write(f"configs:      {len(configs)} -> {len(configs) * args.reps} runs\n")
        f.write("emulator flags are applied to each sender's outgoing path (DATA on server, ACK on client);\n")
        f.write("loss/reorder/corruption are per-direction probabilities.\n")
        f.write("directional seeds: DATA=base seed; ACK=base seed + 1000003.\n")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch", help="smoke | A | B | C | D | all | one | list")
    ap.add_argument("--proto", default="sr", help="(one) saw | gbn | sr")
    ap.add_argument("--window", type=int, help="(one) window size")
    for k in ("loss", "reorder", "corrupt", "dup"):
        ap.add_argument(f"--{k}", type=float, default=0.0, help=f"(one) {k} probability 0..1")
    ap.add_argument("--rto", default=DEFAULTS["rto"], help="(one) adaptive | fixed ms")
    ap.add_argument("--delay", type=int, default=DEFAULTS["delay"], help="one-way delay ms (all batches)")
    ap.add_argument("--jitter", type=int, default=DEFAULTS["jitter"], help="jitter ms (all batches)")
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"], help="base seed (all batches)")
    ap.add_argument("--file-size", type=int, default=DEFAULTS["file_size"], help="input bytes")
    ap.add_argument("--reps", type=int, default=DEFAULTS["reps"], help="repetitions per config")
    ap.add_argument("--rep-seed", choices=("vary", "fixed"), default="vary",
                    help="vary: rep k uses seed+k (new channel realisation); "
                         "fixed: every rep uses the same seed (measures timing noise only)")
    ap.add_argument("--timeout", type=float, default=300, help="seconds per run before it is killed")
    ap.add_argument("--port", type=int, default=10000, help="first UDP port")
    ap.add_argument("--out", help="CSV path (default experiments/results/<batch>.csv)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = ap.parse_args()

    DEFAULTS.update(delay=args.delay, jitter=args.jitter, seed=args.seed)

    if args.batch == "list":
        for b in ("smoke", "A", "B", "C", "D"):
            print(f"{b:6s} {len(batch(b)):3d} configs")
        return 0
    if args.batch == "one":
        w = args.window if args.window else (1 if args.proto == "saw" else DEFAULTS["window"])
        configs = [cfg("one", args.proto, window=w, loss=args.loss, reorder=args.reorder,
                       corrupt=args.corrupt, dup=args.dup, rto=args.rto)]
    else:
        configs = batch(args.batch)

    if args.dry_run:
        for i, c in enumerate(configs):
            print(f"{i:3d} {c['experiment']:22s} {c['proto']:3s} w={c['window']:<2d} loss={c['loss']:<5} "
                  f"reorder={c['reorder']:<5} corrupt={c['corrupt']:<5} delay={c['delay']} "
                  f"jitter={c['jitter']} seed={c['seed']} rto={c['rto']}")
        print(f"{len(configs)} configs x {args.reps} reps = {len(configs) * args.reps} runs")
        return 0

    for b in ("server", "client"):
        if not os.access(os.path.join(ROOT, b), os.X_OK):
            sys.exit(f"./{b} not found: run `make` first")

    infile = make_input(args.file_size)
    expected = sha256_of(infile)
    os.makedirs(RESULTS, exist_ok=True)
    out = args.out or os.path.join(RESULTS, f"{args.batch}.csv")
    logdir = os.path.join(RESULTS, "logs", os.path.splitext(os.path.basename(out))[0])
    os.makedirs(logdir, exist_ok=True)
    write_meta(os.path.splitext(out)[0] + ".meta.txt", args.batch, configs, args, infile, expected)

    planned = len(configs) * args.reps
    rows, failed, port, idx = 0, 0, args.port, 0
    print(f"{args.batch}: {planned} runs, input {args.file_size} B sha256 {expected[:16]}..., CSV {os.path.relpath(out, ROOT)}")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader(); f.flush()
        for c in configs:
            for rep in range(args.reps):
                idx += 1; port += 1
                row = run_one(c, rep, infile, expected, port, logdir, idx, args.timeout,
                              vary_seed=(args.rep_seed == "vary"))
                w.writerow(row); f.flush(); rows += 1
                if row["status"] != "ok":
                    failed += 1
                print(f"[{idx:3d}/{planned}] {row['status']:15s} {c['proto']:3s} w={c['window']:<2} "
                      f"loss={c['loss']:<4} reorder={c['reorder']:<4} corrupt={c['corrupt']:<4} rto={c['rto']:<8} "
                      f"sent={row['sent_packets']:<5} retx={row['retransmissions']:<5} "
                      f"time_ms={row['time_ms']:<8} goodput_kbps={row['goodput_kbps']:<8} "
                      f"hash_match={row['hash_match']}", flush=True)

    # a missing row is an error, never silently ignored
    with open(out) as f:
        written = sum(1 for _ in csv.DictReader(f))
    print(f"\nrows written: {written}/{planned}   ok: {written - failed}   failed: {failed}")
    if written != planned:
        print("ERROR: missing rows"); return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
