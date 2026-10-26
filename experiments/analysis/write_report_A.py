#!/usr/bin/env python3
"""Write an evidence-based Markdown explanation for Experiment A."""
import csv, os, statistics
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES=os.path.join(ROOT,'experiments','results')
LABEL={'saw':'Stop-and-Wait','gbn':'Go-Back-N','sr':'Selective Repeat'}
with open(os.path.join(RES,'experiment_A_raw.csv'),newline='') as f: rows=list(csv.DictReader(f))
with open(os.path.join(RES,'experiment_A_summary.csv'),newline='') as f: summary=list(csv.DictReader(f))
def good(r): return r.get('status')=='ok' and r.get('hash_match')=='1' and r.get('exit_code')=='0'
def fmt(x,d=1): return '—' if x in ('',None) else f'{float(x):.{d}f}'
def stat(rs,field):
 v=[float(r[field]) for r in rs if good(r) and r.get(field,'') not in ('',None)]
 return (statistics.mean(v),statistics.stdev(v) if len(v)>1 else 0.0,min(v),max(v)) if v else None
failed=[r for r in rows if not good(r)]
configs={(r['protocol'],r['loss']):[] for r in rows}
for r in rows: configs.setdefault((r['protocol'],r['loss']),[]).append(r)
seeds=sorted({int(r['seed']) for r in rows}); ds=sorted({int(r['data_seed']) for r in rows}); aks=sorted({int(r['ack_seed']) for r in rows})
lines=["# Experiment A — Goodput vs Packet-Loss Probability", "", "## Hypothesis", "Increasing packet loss should reduce goodput because lost DATA or ACK packets trigger retransmission and additional waiting. Windowed protocols should generally use the link more efficiently than Stop-and-Wait, while GBN and SR may differ in retransmission overhead.", "", "## Setup and controls", "- Input: deterministic 1 MiB file (1,048,576 bytes).", "- Protocols: Stop-and-Wait (window 1), Go-Back-N (window 8), Selective Repeat (window 8).", "- Loss probabilities: 0%, 2%, 5%, 10%, 15% on both DATA and ACK directions; no reordering, corruption, or duplication.", "- One-way delay: 10 ms per direction; jitter 0; adaptive RTO.", f"- Configurations: 15 × 3 repetitions = {len(rows)} raw rows; {len(rows)-len(failed)} successful and {len(failed)} failed.", f"- Base seeds: {', '.join(map(str,seeds))}; DATA seeds: {', '.join(map(str,ds))}; ACK seeds: {', '.join(map(str,aks))}.", "- Every successful row requires `hash_match=1`, matching file size, and zero process exit codes.", "", "## Metric", "Goodput is read from the sender's RESULT line, calculated as `file_bytes × 8 / time_ms`, reported in kbps. Retransmissions are the sender's measured retransmission count. The raw CSV preserves each run; summary statistics exclude only failed rows.", "", "## Results", "| Protocol | Loss | Successful runs | Mean goodput (kbps) | SD | Min–max (kbps) | Mean retransmissions |", "|---|---:|---:|---:|---:|---:|---:|"]
for proto in ('saw','gbn','sr'):
 for loss in sorted({float(r['loss']) for r in rows}):
  rr=configs.get((proto,str(loss)),[])
  if not rr: rr=[r for r in rows if r['protocol']==proto and float(r['loss'])==loss]
  gp=stat(rr,'goodput_kbps'); rt=stat(rr,'retransmissions')
  lines.append(f"| {LABEL[proto]} | {loss*100:g}% | {sum(good(r) for r in rr)}/{len(rr)} | {fmt(gp[0] if gp else '')} | {fmt(gp[1] if gp else '')} | {fmt(gp[2] if gp else '')}–{fmt(gp[3] if gp else '')} | {fmt(rt[0] if rt else '')} |")
lines += ["", "## Observations", ""]
for proto in ('saw','gbn','sr'):
 zero=stat([r for r in rows if r['protocol']==proto and float(r['loss'])==0],'goodput_kbps')
 high=stat([r for r in rows if r['protocol']==proto and float(r['loss'])==0.15],'goodput_kbps')
 if zero and high:
  lines.append(f"- {LABEL[proto]} mean goodput changed from {zero[0]:.1f} kbps at 0% loss to {high[0]:.1f} kbps at 15% loss ({high[0]-zero[0]:+.1f} kbps).")
for loss in sorted({float(r['loss']) for r in rows}):
 vals=[]
 for proto in ('saw','gbn','sr'):
  s=stat([r for r in rows if r['protocol']==proto and float(r['loss'])==loss],'goodput_kbps')
  if s: vals.append((proto,s[0]))
 if vals:
  winner=max(vals,key=lambda x:x[1])
  lines.append(f"- At {loss*100:g}% loss, the highest measured mean goodput was {LABEL[winner[0]]} at {winner[1]:.1f} kbps.")
for proto in ('gbn','sr'):
 s=stat([r for r in rows if r['protocol']==proto and float(r['loss'])==0.15],'retransmissions')
 if s: lines.append(f"- At 15% loss, {LABEL[proto]} averaged {s[0]:.1f} retransmissions (SD {s[1]:.1f}).")
lines += ["", "## Limitations", "- Only three repetitions were run per configuration; small differences between GBN and SR should not be described as statistically significant.", "- Results use localhost with emulated 10 ms one-way delay and no bandwidth cap. Operating-system scheduling can cause occasional spurious timeouts even at 0% loss.", "- DATA and ACK channels use separate deterministic seeds, recorded in the raw CSV and metadata. Real-time timeout behaviour can still vary because the number and timing of transmitted packets are runtime-dependent.", "- No failed run was removed silently; check the raw CSV for the exact status and exit codes.", ""]
open(os.path.join(RES,'experiment_A.md'),'w').write('\n'.join(lines))
print('Wrote experiments/results/experiment_A.md')
