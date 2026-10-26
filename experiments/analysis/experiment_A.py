#!/usr/bin/env python3
"""
experiment_A.py - summary statistics + graph for Experiment A (goodput vs loss).

Reads the runner's raw CSV unchanged and writes, separately:
  experiments/results/experiment_A_summary.csv
  experiments/results/experiment_A_goodput_vs_loss.png

Every run is counted. Failed runs (status != ok) are kept in n_runs and listed,
and are excluded only from the goodput statistics, which need a completed run.

Usage: python3 experiments/analysis/experiment_A.py [raw.csv]
"""
import csv, os, statistics, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "experiments", "results")
RAW = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RES, "experiment_A_raw.csv")
SUMMARY = os.path.join(RES, "experiment_A_summary.csv")
PNG = os.path.join(RES, "experiment_A_goodput_vs_loss.png")

PROTOS = [("saw", "Stop-and-Wait"), ("gbn", "Go-Back-N (w=8)"), ("sr", "Selective Repeat (w=8)")]
# validated categorical palette (slots 1-3), fixed order; text uses ink tokens
COLOR = {"saw": "#2a78d6", "gbn": "#eb6834", "sr": "#1baf7a"}
MARKER = {"saw": "o", "gbn": "s", "sr": "^"}
DODGE = {"saw": 0.0, "gbn": -0.18, "sr": 0.18}     # small x-offset so GBN/SR error bars do not overlap
LABEL_DY = {"saw": 0, "gbn": -9, "sr": 9}          # end-label offsets (points) to avoid collision
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

rows = list(csv.DictReader(open(RAW)))
failed = [r for r in rows if r["status"] != "ok" or r["hash_match"] != "1" or r["exit_code"] != "0"]

groups = {}
for r in rows:
    groups.setdefault((r["protocol"], float(r["loss"])), []).append(r)
losses = sorted({k[1] for k in groups})

def stats(vals):
    if not vals:
        return dict(mean="", median="", sd="", lo="", hi="")
    return dict(mean=statistics.mean(vals), median=statistics.median(vals),
                sd=statistics.stdev(vals) if len(vals) > 1 else 0.0, lo=min(vals), hi=max(vals))

fmt = lambda v, d=1: "" if v == "" else f"{v:.{d}f}"
summary = []
for p, _ in PROTOS:
    for l in losses:
        g = groups.get((p, l), [])
        ok = [r for r in g if r not in failed]
        gp = stats([float(r["goodput_kbps"]) for r in ok])
        rt = stats([float(r["retransmissions"]) for r in ok])
        sent = stats([float(r["sent_packets"]) for r in ok])
        tm = stats([float(r["time_ms"]) for r in ok])
        summary.append({
            "protocol": p, "loss_pct": f"{l * 100:g}", "window": g[0]["window"] if g else "",
            "n_runs": len(g), "n_ok": len(ok), "seeds": " ".join(r["seed"] for r in g),
            "goodput_mean_kbps": fmt(gp["mean"]), "goodput_median_kbps": fmt(gp["median"]),
            "goodput_sd_kbps": fmt(gp["sd"]), "goodput_min_kbps": fmt(gp["lo"]),
            "goodput_max_kbps": fmt(gp["hi"]),
            "retx_mean": fmt(rt["mean"]), "retx_median": fmt(rt["median"]), "retx_sd": fmt(rt["sd"]),
            "sent_mean": fmt(sent["mean"]), "time_ms_mean": fmt(tm["mean"]),
            # packets on the wire per packet of the file (1025 = 1024 data + EOF)
            "sent_per_needed": fmt(sent["mean"] / 1025, 2) if sent["mean"] != "" else "",
        })

with open(SUMMARY, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
    w.writeheader(); w.writerows(summary)

# ------------------------------------------------------------------ graph
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
fig, ax = plt.subplots(figsize=(9, 5.6), dpi=150)
fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
xs = [l * 100 for l in losses]
for p, label in PROTOS:
    s = [r for r in summary if r["protocol"] == p]
    m = [float(r["goodput_mean_kbps"]) for r in s]
    lo = [float(r["goodput_mean_kbps"]) - float(r["goodput_min_kbps"]) for r in s]
    hi = [float(r["goodput_max_kbps"]) - float(r["goodput_mean_kbps"]) for r in s]
    xd = [x + DODGE[p] for x in xs]
    ax.errorbar(xd, m, yerr=[lo, hi], color=COLOR[p], marker=MARKER[p], markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=1.5, linewidth=2, capsize=4,
                elinewidth=1.2, label=label, zorder=3)
    ax.annotate(label.split(" (")[0], xy=(xd[-1], m[-1]), xytext=(10, LABEL_DY[p]), textcoords="offset points",
                va="center", fontsize=10, color=INK)          # direct label, ink colour
ax.set_xticks(xs); ax.set_xticklabels([f"{x:g}" for x in xs])
ax.set_xlim(-0.8, xs[-1] + 4.2)
ax.set_ylim(0, None)
ax.set_xlabel("Loss probability per direction (%)", color=INK)
ax.set_ylabel("Goodput (kbps)", color=INK)
ax.set_title("Experiment A: Goodput vs Loss Probability", loc="left", color=INK, fontsize=13, pad=38)
ax.text(0, 1.02, "Mean of 3 runs (seeds 42, 43, 44); bars show min–max; GBN/SR points nudged apart.\n"
        "1 MiB file, 10 ms one-way delay, adaptive RTO, loss applied on both DATA and ACK paths.",
        transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom", linespacing=1.4)
ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color(GRID)
ax.tick_params(colors=INK2)
ax.legend(frameon=False, loc="upper right", labelcolor=INK)
fig.tight_layout()
fig.savefig(PNG, facecolor=SURFACE)

# ------------------------------------------------------------------ console
print(f"raw rows: {len(rows)}   failed/invalid: {len(failed)}")
for r in failed:
    print("  FAILED:", r["protocol"], r["loss"], r["seed"], r["status"], r["exit_code"])
print(f"{'proto':5s} {'loss%':>5s} {'ok/n':>5s} {'mean':>8s} {'median':>8s} {'sd':>7s} {'min':>8s} {'max':>8s} {'retx':>7s} {'sent/needed':>11s}")
for r in summary:
    print(f"{r['protocol']:5s} {r['loss_pct']:>5s} {r['n_ok']}/{r['n_runs']:<3} {r['goodput_mean_kbps']:>8s} "
          f"{r['goodput_median_kbps']:>8s} {r['goodput_sd_kbps']:>7s} {r['goodput_min_kbps']:>8s} "
          f"{r['goodput_max_kbps']:>8s} {r['retx_mean']:>7s} {r['sent_per_needed']:>11s}")
print("wrote", os.path.relpath(SUMMARY, ROOT), "and", os.path.relpath(PNG, ROOT))
