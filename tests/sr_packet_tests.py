#!/usr/bin/env python3
"""
sr_packet_tests.py - packet-level verification of Selective Repeat.

Same fake-peer approach as gbn_packet_tests.py (helpers imported from it):
  * FakeReceiver <-> ./server --proto sr   (SENDER rules)
  * fake sender  <-> ./client --proto sr   (RECEIVER rules)

Run from the repo root after `make`:  python3 tests/sr_packet_tests.py
"""
import os, random, socket, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gbn_packet_tests import encode, decode, FakeReceiver, check, results, HELLO, DATA, ACK

W = 4


def sender_tests(port):
    data = random.Random(43).randbytes(20000)        # seq 0..19 data + seq 20 EOF
    path = f"tests/tmp/sr_send_{port}.bin"
    open(path, "wb").write(data)
    srv = subprocess.Popen(["./server", str(port), path, "--proto", "sr", "--window", str(W)],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    time.sleep(0.2)
    r = FakeReceiver(port)
    seqs = lambda pk: [p[1] for p in pk]

    r.hello()
    first = r.collect(120)
    check("S1 initial burst = exactly [0, W)", seqs(first) == [0, 1, 2, 3], seqs(first))

    # ACK 1,2,3 but not 0: selective, yet base must stay at 0 -> nothing new.
    for k in (1, 2, 3): r.ack(k)
    q = r.collect(50)
    check("S2 ACKs 1-3 without 0: base stays 0, no new packets", seqs(q) == [], seqs(q))

    burst = r.collect(300)
    check("S3 timeout resends ONLY the unACKed packet 0 (not 1-3)", seqs(burst) == [0], seqs(burst))
    # Packet 0's timer started when it was SENT, with the initial 200 ms RTO.
    # (ACKs 1-3 are valid samples and change the RTO, but not a running timer.)
    g0 = burst[0][0] - first[0][0] if burst else -1
    check("S4 packet 0's own timer started at send with initial RTO (~200 ms)",
          170 <= g0 <= 240, f"{g0:.0f} ms")

    r.ack(0)
    new = r.collect(60)
    check("S5 ACK 0 slides base over 0..3 -> sends exactly [4, 8)", seqs(new) == [4, 5, 6, 7], seqs(new))

    # No ACKs: each of 4..7 expires on its own timer. ACK 0 was for a
    # RETRANSMITTED packet, so Karn gives no sample: RTO stays 200 ms.
    t_new = {s: t for (t, s, _) in new}
    exp = r.collect(350)
    gaps = [round(t - t_new[s]) for (t, s, _) in exp if s in t_new]
    # ACKs 1-3 were 3 valid ~120 ms samples -> RTO = 120 + 4*33.75 = ~255 ms.
    # Karn: ACK 0 covered a RETRANSMITTED packet -> no sample, RTO stays ~255.
    # 4..7 were sent together, so they all expire together after that RTO.
    check("S6 Karn + per-packet timers: 4..7 all expire together at learned RTO (~255)",
          seqs(exp) == [4, 5, 6, 7] and gaps and all(220 <= g <= 300 for g in gaps)
          and max(gaps) - min(gaps) <= 5, f"{seqs(exp)} gaps {gaps}")

    # ACK 4, 6, 7 (not 5): base -> 5 only; window [5, 9) -> exactly one new packet, 8.
    for k in (4, 6, 7): r.ack(k)
    q = r.collect(50)
    check("S7 base stops at first unACKed (5): sends only 8", seqs(q) == [8], seqs(q))
    r.ack(8)

    r.ack(6); r.ack(1); r.s.sendto(encode(ACK, 50), r.srv)
    q = r.collect(40)
    check("S8 duplicate / old / future ACKs change nothing", seqs(q) == [], seqs(q))

    # Withhold 5: only 5 is resent. Its last two gaps have no ACK in between,
    # so the second must be exactly double the first (backoff).
    q = r.collect(2300)
    t5 = [t for (t, s, _) in r.log if s == 5]
    others = [s for (_, s, _) in q if s != 5]
    ratio = (t5[-1] - t5[-2]) / (t5[-2] - t5[-3]) if len(t5) >= 3 else 0
    check("S9 repeated timeout: only seq 5 resent, interval doubles",
          not others and len(t5) >= 3 and 1.6 <= ratio <= 2.4,
          f"{len(t5) - 1} resends of 5, ratio {ratio:.2f}, others {others}")

    # Finish: ACK in order up to 19, withhold EOF (20).
    r.ack(5)
    got = {}
    for (_, s, pl) in r.log:
        got.setdefault(s, pl)
    deadline = time.monotonic() + 5
    while not all(k in got for k in range(21)) and time.monotonic() < deadline:
        for (_, s, pl) in r.collect(20):
            got.setdefault(s, pl)
            if s < 20:
                r.ack(s)
    r.collect(500)
    eof_sends = [t for (t, s, _) in r.log if s == 20]
    check("S10 EOF resent until ACKed; sender does not exit early",
          srv.poll() is None and len(eof_sends) >= 2, f"EOF sent {len(eof_sends)}x")
    r.ack(20)
    try:
        out, _ = srv.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        srv.kill(); out = ""
    check("S11 sender exits 0 with RESULT after EOF ACK",
          srv.returncode == 0 and out.startswith("RESULT"), out.strip()[:50])
    check("S12 payloads reassemble to the file", b"".join(got.get(i, b"") for i in range(20)) == data)

    # Whole-run invariants, from our own ACK history:
    #   our_base = lowest seq we had NOT ACKed yet -> every send must be < our_base + W
    #   a seq we ACKed (>5 ms earlier) must never be sent again
    viol_w, viol_r = [], []
    for (t, sq, _) in r.log:
        acked = {k for (ta, k) in r.ack_log if ta <= t}
        ob = 0
        while ob in acked:
            ob += 1
        if sq >= ob + W:
            viol_w.append((round(t), sq, ob))
        if any(k == sq and ta < t - 5 for (ta, k) in r.ack_log):
            viol_r.append((round(t), sq))
    check("S13 next never exceeds base + W (%d packets)" % len(r.log), not viol_w, viol_w[:3])
    check("S14 an ACKed packet is never retransmitted", not viol_r, viol_r[:3])


def receiver_tests(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    out = f"tests/tmp/sr_recv_{port}.bin"
    cli = subprocess.Popen(["./client", "127.0.0.1", str(port), out, "--proto", "sr",
                            "--window", str(W)], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True)
    s.settimeout(3)
    _, client = s.recvfrom(2048)                         # HELLO
    pl = [bytes([65 + i]) * (1024 if i < 5 else 300) for i in range(6)]   # seq 6 = EOF

    def send(seq, corrupt=False):
        s.sendto(encode(DATA, seq, pl[seq] if seq < 6 else b"", corrupt), client)

    def acks(ms=80):
        res, end = [], time.monotonic() + ms / 1000
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return res
            s.settimeout(left)
            try:
                b, _ = s.recvfrom(2048)
            except socket.timeout:
                return res
            t, seq, _, ok = decode(b)
            if ok and t == ACK:
                res.append(seq)

    send(1); a = acks()
    check("R1 out-of-order 1 (in window) is buffered and ACKed individually", a == [1], a)
    send(3); send(2); a = acks()
    check("R2 out-of-order 3, 2 -> individual ACKs 3, 2", a == [3, 2], a)
    send(0); a = acks()
    check("R3 missing 0 arrives -> ACK 0 (0..3 delivered)", a == [0], a)
    send(1); a = acks()
    check("R4 duplicate below window (1) is re-ACKed", a == [1], a)
    send(9); a = acks()
    check("R5 packet beyond window [4,8) is ignored, no ACK", a == [], a)
    send(4, corrupt=True); a = acks()
    check("R6 corrupted 4 dropped, no ACK", a == [], a)
    send(5); send(5); a = acks()
    check("R7 in-window duplicate 5 is re-ACKed", a == [5, 5], a)
    send(6); a = acks(); time.sleep(0.2)
    check("R8 early EOF is ACKed + buffered; receiver does not finish yet",
          a == [6] and cli.poll() is None, f"{a}, alive={cli.poll() is None}")
    send(4); a = acks()
    check("R9 missing 4 -> ACK 4, then 4, 5, EOF delivered", a == [4], a)
    time.sleep(1.5); send(6); a = acks(150)
    check("R10 final ACK lost: linger re-ACKs EOF retry", a == [6], a)
    t_last = time.monotonic()
    try:
        stdout, _ = cli.communicate(timeout=6)
    except subprocess.TimeoutExpired:
        cli.kill(); stdout = ""
    quiet = time.monotonic() - t_last
    check("R11 receiver exits 0 after ~2.5 s of quiet",
          cli.returncode == 0 and 2.2 <= quiet <= 3.5, f"exit={cli.returncode}, quiet {quiet:.1f}s")
    written = open(out, "rb").read()
    check("R12 file = 0..5 in order, each written once", written == b"".join(pl), f"{len(written)} B")
    check("R13 stats: duplicates=2 (R4, R7), corrupted=1 (R6)",
          "duplicates=2" in stdout and "corrupted=1" in stdout, stdout.strip())


if __name__ == "__main__":
    os.makedirs("tests/tmp", exist_ok=True)
    base = int(os.environ.get("BASE_PORT", "9750"))
    print("== SR sender (fake receiver <-> ./server) ==")
    sender_tests(base + 1)
    print("== SR receiver (fake sender <-> ./client) ==")
    receiver_tests(base + 2)
    bad = [n for n, ok, _ in results if not ok]
    print(f"\nSR packet-level: {len(results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)
