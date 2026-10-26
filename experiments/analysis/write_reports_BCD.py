#!/usr/bin/env python3
"""Write evidence-based Markdown explanations for Experiments B, C and D."""
import csv, os, statistics
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "experiments", "results")
LABEL = {"saw": "Stop-and-Wait", "gbn": "Go-Back-N", "sr": "Selective Repeat"}

def load(name):
    with open(os.path.join(RES, f"experiment_{name}_raw.csv"), newline="") as f:
        return list(csv.DictReader(f))

def good(r):
    return r.get("status") == "ok" and r.get("hash_match") == "1" and r.get("exit_code") == "0"

def fnum(x, d=1):
    return "—" if x in (None, "") else f"{float(x):.{d}f}"

def pct(x): return f"{float(x)*100:g}%"

def seed_note(rows):
    bases=sorted({int(r['seed']) for r in rows})
    data=sorted({int(r['data_seed']) for r in rows}) if rows and 'data_seed' in rows[0] else []
    ack=sorted({int(r['ack_seed']) for r in rows}) if rows and 'ack_seed' in rows[0] else []
    if data and ack:
        return f"Three repetitions per configuration used base seeds {', '.join(map(str,bases))}; DATA seeds were {', '.join(map(str,data))} and ACK seeds were {', '.join(map(str,ack))} across the batch."
    return f"Recorded base seeds: {', '.join(map(str,bases))}."

def stats(rows, metric):
    vals=[float(r[metric]) for r in rows if good(r) and r.get(metric, '') not in ('', None)]
    return (statistics.mean(vals), statistics.stdev(vals) if len(vals)>1 else 0.0, min(vals), max(vals)) if vals else None

def groups(rows, fields):
    out={}
    for r in rows: out.setdefault(tuple(r[f] for f in fields), []).append(r)
    return out

def write_B(rows):
    g=groups(rows,['protocol','window'])
    order={'gbn':0,'sr':1}
    keys=sorted(g, key=lambda k:(order.get(k[0],9),int(k[1])))
    lines=["# Experiment B — Goodput vs Window Size", "", "## Hypothesis", "Increasing the sender window should improve goodput because more packets can be in flight before acknowledgements arrive. The gain may level off or vary due to loss recovery and host scheduling.", "", "## Setup and controls", "- Input: deterministic 1 MiB file.", "- Protocols: Go-Back-N and Selective Repeat; windows 1, 2, 4, 8, 16, 32.", "- Loss: 2% independently configured on each direction; no reordering or corruption.", "- One-way delay: 10 ms; jitter: 0; adaptive RTO.", f"- Repetitions: {len(rows)//len(g) if g else 0} per configuration. {seed_note(rows)}", "- Integrity: each successful row requires `hash_match=1` and zero process exit codes.", "", "## Metric", "Goodput is taken from the sender's RESULT line: `file_bytes × 8 / time_ms`, expressed as kbps (bits/ms). Failed rows remain in the raw CSV and are excluded from successful-run statistics.", "", "## Results", "| Protocol | Window | Successful runs | Mean goodput (kbps) | SD | Min–max (kbps) | Mean retransmissions |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k in keys:
        rr=g[k]; gp=stats(rr,'goodput_kbps'); rt=stats(rr,'retransmissions'); okn=sum(good(r) for r in rr)
        lines.append(f"| {LABEL[k[0]]} | {k[1]} | {okn}/{len(rr)} | {fnum(gp[0] if gp else '')} | {fnum(gp[1] if gp else '')} | {fnum(gp[2] if gp else '')}–{fnum(gp[3] if gp else '')} | {fnum(rt[0] if rt else '')} |")
    lines += ["", "## Observations", ""]
    for proto in ('gbn','sr'):
        available=[(int(k[1]),stats(v,'goodput_kbps')) for k,v in g.items() if k[0]==proto and stats(v,'goodput_kbps')]
        if available:
            best=max(available,key=lambda x:x[1][0]); first=next((v for w,v in available if w==1),None)
            text=f"- {LABEL[proto]} had its highest measured mean goodput at window {best[0]} ({best[1][0]:.1f} kbps)."
            if first and first[0]>0: text += f" Window 1 measured {first[0]:.1f} kbps; the observed change to the best window was {best[1][0]-first[0]:+.1f} kbps."
            lines.append(text)
    lines += ["", "## Limitations", "Results are from localhost with emulated delay and no bandwidth cap. Three repetitions give a useful comparison but do not establish statistical significance; timing and OS scheduling can affect goodput. Consult the raw CSV, metadata, and per-run logs when interpreting any outlier.", ""]
    open(os.path.join(RES,'experiment_B.md'),'w').write('\n'.join(lines))

def write_C(rows):
    g=groups(rows,['protocol','reorder'])
    order={'saw':0,'gbn':1,'sr':2}
    keys=sorted(g,key=lambda k:(order.get(k[0],9),float(k[1])))
    lines=["# Experiment C — Retransmissions vs Reordering Probability", "", "## Hypothesis", "Increasing reordering can create gaps at the receiver and duplicate acknowledgements, potentially increasing retransmissions. Go-Back-N may resend more already-received packets than Selective Repeat because it retransmits a suffix of its window after a timeout.", "", "## Setup and controls", "- Input: deterministic 1 MiB file.", "- Protocols: Stop-and-Wait (window 1), Go-Back-N (window 8), Selective Repeat (window 8).", "- Reordering probabilities: 0%, 5%, 10%, 20% on both directional channels.", "- Loss and corruption: 0%; one-way delay 10 ms; jitter 0; adaptive RTO.", f"- Repetitions: {len(rows)//len(g) if g else 0} per configuration. {seed_note(rows)}", "- Integrity: each successful row requires `hash_match=1` and zero process exit codes.", "", "## Metric", "Retransmission count is read from the sender's RESULT line. The table reports the mean and standard deviation across successful runs; raw per-run counts remain in the CSV.", "", "## Results", "| Protocol | Reordering | Successful runs | Mean retransmissions | SD | Min–max | Mean goodput (kbps) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k in keys:
        rr=g[k]; rt=stats(rr,'retransmissions'); gp=stats(rr,'goodput_kbps'); okn=sum(good(r) for r in rr)
        lines.append(f"| {LABEL[k[0]]} | {pct(k[1])} | {okn}/{len(rr)} | {fnum(rt[0] if rt else '')} | {fnum(rt[1] if rt else '')} | {fnum(rt[2] if rt else '')}–{fnum(rt[3] if rt else '')} | {fnum(gp[0] if gp else '')} |")
    lines += ["", "## Observations", ""]
    for proto in ('saw','gbn','sr'):
        a=stats(g.get((proto,'0.0'),g.get((proto,'0'),[])),'retransmissions')
        b=stats(g.get((proto,'0.2'),g.get((proto,'0.20'),[])),'retransmissions')
        if a and b:
            lines.append(f"- {LABEL[proto]} mean retransmissions changed from {a[0]:.1f} at 0% reordering to {b[0]:.1f} at 20% ({b[0]-a[0]:+.1f} packets).")
    gb=stats(g.get(('gbn','0.2'),g.get(('gbn','0.20'),[])),'retransmissions')
    sr=stats(g.get(('sr','0.2'),g.get(('sr','0.20'),[])),'retransmissions')
    if gb and sr: lines.append(f"- At 20% reordering, GBN averaged {gb[0]:.1f} retransmissions and SR averaged {sr[0]:.1f}; the observed difference was {gb[0]-sr[0]:.1f} packets.")
    lines += ["", "## Limitations", "The emulator applies reordering on both DATA and ACK directions. Retransmissions can also depend on timeout scheduling, so use the spread and individual logs rather than treating a small mean difference as conclusive. Results are localhost measurements with no bandwidth cap.", ""]
    open(os.path.join(RES,'experiment_C.md'),'w').write('\n'.join(lines))

def write_D(rows):
    g=groups(rows,['protocol','rto'])
    rto_order={'adaptive':0,'20':1,'40':2,'80':3,'160':4,'320':5,'640':6}
    keys=sorted(g,key=lambda k:({'saw':0,'gbn':1,'sr':2}.get(k[0],9),rto_order.get(k[1],99)))
    lines=["# Experiment D — Sensitivity to RTO Tuning", "", "## Hypothesis", "An RTO that is too short can trigger unnecessary retransmissions before an ACK arrives; an overly long RTO can make recovery from real loss slow. Adaptive RTO should respond to measured RTT, while fixed RTO settings expose this trade-off.", "", "## Setup and controls", "- Input: deterministic 1 MiB file.", "- Protocols: Stop-and-Wait (window 1), Go-Back-N (window 8), Selective Repeat (window 8).", "- RTO settings: adaptive, fixed 20, 40, 80, 160, 320, and 640 ms.", "- Loss: 5% independently configured on each direction; no reordering or corruption.", "- One-way delay: 10 ms; jitter: 0.", f"- Repetitions: {len(rows)//len(g) if g else 0} per configuration. {seed_note(rows)}", "- Integrity: each successful row requires `hash_match=1` and zero process exit codes.", "", "## Metrics", "Retransmissions and transfer time come from the sender's RESULT line. Goodput is reported by the sender as `file_bytes × 8 / time_ms` in kbps. Failed rows remain in the raw CSV and are excluded from successful-run means.", "", "## Results", "| Protocol | RTO setting | Successful runs | Mean retransmissions | Mean time (s) | Mean goodput (kbps) |", "|---|---|---:|---:|---:|---:|"]
    for k in keys:
        rr=g[k]; rt=stats(rr,'retransmissions'); tm=stats(rr,'time_ms'); gp=stats(rr,'goodput_kbps'); okn=sum(good(r) for r in rr)
        lines.append(f"| {LABEL[k[0]]} | {k[1]} | {okn}/{len(rr)} | {fnum(rt[0] if rt else '')} | {fnum(tm[0]/1000 if tm else '')} | {fnum(gp[0] if gp else '')} |")
    lines += ["", "## Observations", ""]
    for proto in ('saw','gbn','sr'):
        available=[(k[1],stats(v,'goodput_kbps'),stats(v,'retransmissions'),stats(v,'time_ms')) for k,v in g.items() if k[0]==proto and stats(v,'goodput_kbps')]
        if available:
            best=max(available,key=lambda x:x[1][0]); adapt=next((x for x in available if x[0]=='adaptive'),None); slow=next((x for x in available if x[0]=='640'),None)
            text=f"- {LABEL[proto]} had its highest measured mean goodput at RTO {best[0]} ms ({best[1][0]:.1f} kbps)."
            if adapt: text += f" Adaptive RTO measured {adapt[1][0]:.1f} kbps, {adapt[2][0]:.1f} retransmissions on average, and {adapt[3][0]/1000:.2f} s mean transfer time."
            if slow: text += f" Fixed 640 ms measured {slow[1][0]:.1f} kbps and {slow[3][0]/1000:.2f} s mean transfer time."
            lines.append(text)
    lines += ["", "## Limitations", "Fixed RTO disables estimation/backoff by design in this experiment; it is a comparison mode, not a recommended production setting. The results depend on the emulated 20 ms base RTT, the 5% loss probability on each direction, and host scheduling. Three repetitions do not prove statistical significance. See the raw CSV and metadata for all seeds and outcomes.", ""]
    open(os.path.join(RES,'experiment_D.md'),'w').write('\n'.join(lines))

def main():
    b=load('B'); c=load('C'); d=load('D')
    write_B(b); write_C(c); write_D(d)
    print('Wrote experiment_B.md, experiment_C.md, experiment_D.md')
if __name__=='__main__': main()
