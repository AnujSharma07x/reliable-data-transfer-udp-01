#!/usr/bin/env python3
"""
gbn_packet_tests.py - packet-level verification of Go-Back-N.

A fake peer speaks our wire format and talks to the real binaries:
  * FakeReceiver  <-> ./server --proto gbn   (checks the SENDER rules)
  * FakeSender    <-> ./client --proto gbn   (checks the RECEIVER rules)
Every packet is inspected, so these tests prove the algorithm, not just
"the file eventually arrived".

Run from the repo root after `make`:  python3 tests/gbn_packet_tests.py
"""
import os, random, socket, struct, subprocess, sys, time

HELLO, DATA, ACK = 1, 2, 3
PAYLOAD = 1024
results = []


# ---------- wire format (must match src/packet.c) ----------
def csum(b):
    if len(b) % 2:
        b += b"\0"
    s = sum(struct.unpack("!%dH" % (len(b) // 2), b))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF

def encode(t, seq, payload=b"", corrupt=False):
    h = struct.pack("!BBIHH", t, 0, seq, len(payload), 0)
    c = csum(h + payload)
    pkt = bytearray(struct.pack("!BBIHH", t, 0, seq, len(payload), c) + payload)
    if corrupt:
        pkt[-1] ^= 0xFF
    return bytes(pkt)

def decode(b):
    t, _, seq, ln, c = struct.unpack("!BBIHH", b[:10])
    ok = csum(b[:8] + b"\0\0" + b[10:]) == c and len(b) == 10 + ln
    return t, seq, b[10:], ok


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if detail else ""))


# ---------- fake receiver: tests the GBN SENDER ----------
class FakeReceiver:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.srv = ("127.0.0.1", port)
        self.t0 = time.monotonic()
        self.log = []                 # (t_ms, seq, payload)
        self.max_ack = -1             # highest ACK we have sent
        self.ack_log = []             # (t_ms, k) of every ACK we sent

    def now(self):
        return (time.monotonic() - self.t0) * 1000

    def hello(self):
        self.s.sendto(encode(HELLO, 0), self.srv)

    def ack(self, k):
        self.max_ack = max(self.max_ack, k)
        self.ack_log.append((self.now(), k))
        self.s.sendto(encode(ACK, k), self.srv)

    def collect(self, ms):
        """Receive DATA for `ms` milliseconds; return [(t, seq)]."""
        out, end = [], time.monotonic() + ms / 1000
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return out
            self.s.settimeout(left)
            try:
                b, _ = self.s.recvfrom(2048)
            except socket.timeout:
                return out
            t, seq, pl, ok = decode(b)
            if ok and t == DATA:
                rec = (self.now(), seq, pl)
                self.log.append(rec)
                out.append(rec)


def sender_tests(port, W=4):
    data = random.Random(42).randbytes(20000)       # seq 0..19 data + seq 20 EOF
    path = f"tests/tmp/pk_send_{port}.bin"
    open(path, "wb").write(data)
    srv = subprocess.Popen(["./server", str(port), path, "--proto", "gbn",
                            "--window", str(W)], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True)
    time.sleep(0.2)
    r = FakeReceiver(port)
    seqs = lambda pk: [p[1] for p in pk]

    # 1. No ACKs: only the first W packets go out (next <= base + W).
    r.hello()
    first = r.collect(120)
    check("S1 initial burst = exactly [0, W)", seqs(first) == list(range(W)), seqs(first))

    # 2. Timeout (initial RTO 200 ms) resends exactly [base, next) = [0, W).
    burst = r.collect(250)
    check("S2 timeout retransmits exactly [base,next)", seqs(burst) == list(range(W)), seqs(burst))
    check("S3 first timeout fires at initial RTO (~200 ms)",
          burst and 170 <= burst[0][0] - first[0][0] <= 260,
          f"{burst[0][0] - first[0][0]:.0f} ms" if burst else "none")

    # 3. Cumulative ACK 1 acknowledges 0 and 1 -> base = 2, next = 6.
    t_ack = r.now(); r.ack(1)
    new = r.collect(60)
    check("S4 ACK 1 is cumulative: base->2, sends exactly [W, W+2)",
          seqs(new) == [W, W + 1], seqs(new))

    # 4. Duplicate ACK 1, old ACK 0, and a future ACK 50 must not move the window.
    r.ack(1); r.ack(0); r.s.sendto(encode(ACK, 50), r.srv)
    quiet = r.collect(60)
    check("S5 duplicate/old/future ACKs do not move the window", seqs(quiet) == [], seqs(quiet))

    # 5. Next timeout: resend [2, 6); 0 and 1 (ACKed) must NOT be resent.
    burst2 = r.collect(400)
    check("S6 second timeout resends [2,6), never ACKed 0/1",
          seqs(burst2) == [2, 3, 4, 5], seqs(burst2))
    # Karn: ACK 1 covered a RETRANSMITTED packet -> no RTT sample, backoff
    # cleared -> RTO back to the initial 200 ms. A wrong sample would give
    # >= 375 ms (sample from retransmission) or ~1350 ms (from first send).
    gap = burst2[0][0] - t_ack if burst2 else -1
    check("S7 Karn: no sample from retransmitted packet (timer = 200 ms)",
          170 <= gap <= 260, f"{gap:.0f} ms")

    # 6. Valid samples: ACK every packet 60 ms after it arrives, seq 2..15.
    pending, expected = [], 2
    end = time.monotonic() + 3
    while expected <= 15 and time.monotonic() < end:
        r.collect(5)
        seen = {}
        for (t, seq, _) in r.log:               # includes packets seen earlier
            seen.setdefault(seq, t)
        while expected in seen and expected <= 15:
            pending.append((max(seen[expected], r.now()) + 60, expected)); expected += 1
        while pending and pending[0][0] <= r.now():
            r.ack(pending.pop(0)[1])
    while pending:
        time.sleep(max(0, (pending[0][0] - r.now()) / 1000)); r.ack(pending.pop(0)[1])
    # Now withhold ACK 16: the timeout interval shows the adapted RTO.
    pk = r.collect(400)
    # One timer, for base: it restarts at our LAST ACK (15), so the RTO is
    # (first retransmission after that ACK) - (time of that ACK).
    last_ack_t = r.ack_log[-1][0]
    sends16 = [t for (t, s, _) in r.log if s == 16]
    rto_seen = sends16[1] - last_ack_t if len(sends16) >= 2 else -1
    check("S8 adaptive RTO learned from valid samples (60 ms RTT -> RTO ~70-110)",
          60 <= rto_seen < 130, f"RTO {rto_seen:.0f} ms")

    # 7. EOF: ACK up to 19 but withhold the EOF ACK (seq 20).
    got, expected, deadline = {}, 16, time.monotonic() + 5
    for (_, s, pl) in r.log:
        got.setdefault(s, pl)
    while expected <= 19 and time.monotonic() < deadline:
        for (_, s, pl) in r.collect(20):
            got.setdefault(s, pl)
        while expected in got and expected <= 19:
            r.ack(expected); expected += 1
    r.collect(300)
    eof_sends = [t for (t, s, _) in r.log if s == 20]
    check("S9 sender keeps retransmitting EOF and does not exit without its ACK",
          srv.poll() is None and len(eof_sends) >= 2, f"EOF sent {len(eof_sends)}x, alive={srv.poll() is None}")

    r.ack(20)
    try:
        out, _ = srv.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        srv.kill(); out = ""
    check("S10 sender exits 0 with RESULT only after EOF ACK",
          srv.returncode == 0 and out.startswith("RESULT"), out.strip()[:60])
    rebuilt = b"".join(got.get(i, b"") for i in range(20))
    check("S11 payloads seen by receiver reassemble to the file", rebuilt == data)

    # Invariant over the WHOLE run: when the sender emits seq s, its base is at
    # most (highest ACK we had sent so far) + 1, so s < that + 1 + W.
    viol = []
    for (t, sq, _) in r.log:
        hi = max([k for (ta, k) in r.ack_log if ta <= t and k <= 20] + [-1])
        if sq >= hi + 1 + W:
            viol.append((round(t), sq, hi))
    check("S12 next never exceeds base + W (all %d packets checked)" % len(r.log),
          not viol, viol[:3])


# ---------- fake sender: tests the GBN RECEIVER ----------
def receiver_tests(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    out = f"tests/tmp/pk_recv_{port}.bin"
    cli = subprocess.Popen(["./client", "127.0.0.1", str(port), out, "--proto", "gbn",
                            "--window", "4"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True)
    s.settimeout(3)
    _, client = s.recvfrom(2048)                       # HELLO
    pl = [bytes([65 + i]) * (PAYLOAD if i < 3 else 100) for i in range(4)]

    def send(seq, corrupt=False):
        s.sendto(encode(DATA, seq, pl[seq] if seq < 4 else b"", corrupt), client)

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

    send(1)
    check("R1 out-of-order before anything received: discarded, no ACK", acks() == [])
    send(0); a = acks()
    check("R2 in-order seq 0 -> ACK 0", a == [0], a)
    send(2); send(3); a = acks()
    check("R3 out-of-order 2,3 discarded -> duplicate cumulative ACK 0,0", a == [0, 0], a)
    send(1); a = acks()
    check("R4 missing seq 1 arrives -> ACK 1 (2,3 were NOT buffered)", a == [1], a)
    send(2); a = acks()
    check("R5 seq 2 -> ACK 2", a == [2], a)
    send(1); a = acks()
    check("R6 duplicate seq 1 -> re-ACK expected-1 = 2, not rewritten", a == [2], a)
    send(3, corrupt=True); a = acks()
    check("R7 corrupted seq 3 dropped silently, no ACK", a == [], a)
    send(3); send(4); a = acks()
    check("R8 seq 3 + EOF 4 -> ACK 3, ACK 4", a == [3, 4], a)

    # final ACK "lost": sender retries EOF 1.5 s later, then a stale packet 2 s later
    time.sleep(1.5); send(4); a1 = acks(150)
    time.sleep(1.85); send(3); a2 = acks(150)
    check("R9 linger re-ACKs EOF retry after 1.5 s", a1 == [4], a1)
    check("R10 linger was extended by the retry (still answers 3.5 s after EOF)", a2 == [3], a2)
    t_last = time.monotonic()
    try:
        stdout, _ = cli.communicate(timeout=6)
    except subprocess.TimeoutExpired:
        cli.kill(); stdout = ""
    quiet = time.monotonic() - t_last
    check("R11 receiver exits 0 after ~2.5 s of quiet", cli.returncode == 0 and 2.2 <= quiet <= 3.5,
          f"exit={cli.returncode}, quiet {quiet:.1f}s")
    written = open(out, "rb").read()
    check("R12 each payload written exactly once, in order",
          written == b"".join(pl), f"{len(written)} bytes")


if __name__ == "__main__":
    os.makedirs("tests/tmp", exist_ok=True)
    base = int(os.environ.get("BASE_PORT", "9700"))
    print("== GBN sender (fake receiver <-> ./server) ==")
    sender_tests(base + 1)
    print("== GBN receiver (fake sender <-> ./client) ==")
    receiver_tests(base + 2)
    bad = [n for n, ok, _ in results if not ok]
    print(f"\npacket-level: {len(results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)
