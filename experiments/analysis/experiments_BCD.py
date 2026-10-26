#!/usr/bin/env python3
"""Summarise and plot raw results for mandatory Experiments B, C and D.

Raw CSVs are not edited. Failed runs are retained in summaries and excluded
from metric calculations. Run after run_experiments.py has produced B/C/D data.
"""
import csv, os, statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "experiments", "results")
COLORS = {"saw": "#2a78d6", "gbn": "#eb6834", "sr": "#1baf7a"}
MARKERS = {"saw": "o", "gbn": "s", "sr": "^"}
LABELS = {"saw": "Stop-and-Wait", "gbn": "Go-Back-N", "sr": "Selective Repeat"}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def load(name):
    path = os.path.join(RES, f"experiment_{name}_raw.csv")
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"No rows in {path}")
    return rows


def ok(row):
    return row.get("status") == "ok" and row.get("hash_match") == "1" and row.get("exit_code") == "0"


def stat(values):
    return {
        "mean": statistics.mean(values) if values else "",
        "median": statistics.median(values) if values else "",
        "sd": statistics.stdev(values) if len(values) > 1 else (0.0 if values else ""),
        "min": min(values) if values else "",
        "max": max(values) if values else "",
    }


def summarise(name, rows, group_fields, metrics):
    groups = {}
    for row in rows:
        key = tuple(row[field] for field in group_fields)
        groups.setdefault(key, []).append(row)
    out = []
    for key, group in sorted(groups.items(), key=lambda kv: tuple(kv[0])):
        good = [r for r in group if ok(r)]
        item = {field: value for field, value in zip(group_fields, key)}
        item.update(n_runs=len(group), n_ok=len(good), seeds=" ".join(r.get("seed", "") for r in group))
        for metric in metrics:
            vals = [float(r[metric]) for r in good if r.get(metric, "") not in (None, "")]
            st = stat(vals)
            for suffix, value in st.items():
                item[f"{metric}_{suffix}"] = value
        out.append(item)
    path = os.path.join(RES, f"experiment_{name}_summary.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    return out, path


def base_ax(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED)


def plot_B(summary):
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=150)
    fig.patch.set_facecolor(SURFACE); base_ax(ax)
    windows = sorted({int(r["window"]) for r in summary})
    for proto in ("gbn", "sr"):
        rows = sorted((r for r in summary if r["protocol"] == proto), key=lambda r: int(r["window"]))
        xs = [int(r["window"]) for r in rows]
        means = [float(r["goodput_kbps_mean"]) for r in rows]
        low = [m - float(r["goodput_kbps_min"]) for m, r in zip(means, rows)]
        high = [float(r["goodput_kbps_max"]) - m for m, r in zip(means, rows)]
        ax.errorbar(xs, means, yerr=[low, high], color=COLORS[proto], marker=MARKERS[proto],
                    linewidth=2, capsize=4, label=LABELS[proto])
    ax.set_xticks(windows); ax.set_xlabel("Sender window size", color=INK)
    ax.set_ylabel("Goodput (kbps)", color=INK)
    ax.set_title("Experiment B: Goodput vs Window Size", loc="left", color=INK, pad=28)
    ax.text(0, 1.02, "Mean across successful runs; bars show min–max. 1 MiB file, 2% loss per direction, 10 ms one-way delay.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")
    ax.legend(frameon=False, labelcolor=INK)
    fig.tight_layout()
    path = os.path.join(RES, "experiment_B_goodput_vs_window.png")
    fig.savefig(path, facecolor=SURFACE); plt.close(fig)
    return path


def plot_C(summary):
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=150)
    fig.patch.set_facecolor(SURFACE); base_ax(ax)
    reorders = sorted({float(r["reorder"]) for r in summary})
    dodge = {"saw": -0.5, "gbn": 0.0, "sr": 0.5}
    for proto in ("saw", "gbn", "sr"):
        rows = sorted((r for r in summary if r["protocol"] == proto), key=lambda r: float(r["reorder"]))
        xs = [float(r["reorder"]) * 100 + dodge[proto] for r in rows]
        means = [float(r["retransmissions_mean"]) for r in rows]
        low = [m - float(r["retransmissions_min"]) for m, r in zip(means, rows)]
        high = [float(r["retransmissions_max"]) - m for m, r in zip(means, rows)]
        ax.errorbar(xs, means, yerr=[low, high], color=COLORS[proto], marker=MARKERS[proto],
                    linewidth=2, capsize=4, label=LABELS[proto])
    ax.set_xticks([r * 100 for r in reorders]); ax.set_xlabel("Reordering probability per direction (%)", color=INK)
    ax.set_ylabel("Retransmissions (packets)", color=INK)
    ax.set_title("Experiment C: Retransmissions vs Reordering", loc="left", color=INK, pad=28)
    ax.text(0, 1.02, "Mean across successful runs; bars show min–max. Loss 0%, 1 MiB file, 10 ms one-way delay.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED, va="bottom")
    ax.legend(frameon=False, labelcolor=INK)
    fig.tight_layout()
    path = os.path.join(RES, "experiment_C_retransmissions_vs_reordering.png")
    fig.savefig(path, facecolor=SURFACE); plt.close(fig)
    return path


def plot_D(summary):
    order = {"adaptive": 0, "20": 1, "40": 2, "80": 3, "160": 4, "320": 5, "640": 6}
    labels = ["adaptive", "20", "40", "80", "160", "320", "640"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.3), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    metric_specs = [("retransmissions", "Retransmissions (packets)", False),
                    ("time_ms", "Transfer time (s)", True),
                    ("goodput_kbps", "Goodput (kbps)", True)]
    for ax, (metric, ylabel, logy) in zip(axes, metric_specs):
        base_ax(ax)
        for proto in ("saw", "gbn", "sr"):
            rows = sorted((r for r in summary if r["protocol"] == proto), key=lambda r: order[r["rto"]])
            xs = [order[r["rto"]] for r in rows]
            scale = 1000.0 if metric == "time_ms" else 1.0
            means = [float(r[f"{metric}_mean"]) / scale for r in rows]
            mins = [float(r[f"{metric}_min"]) / scale for r in rows]
            maxs = [float(r[f"{metric}_max"]) / scale for r in rows]
            lo = [m - v for m, v in zip(means, mins)]
            hi = [v - m for m, v in zip(means, maxs)]
            if logy:
                means = [max(v, 0.01) for v in means]
            ax.errorbar(xs, means, yerr=[lo, hi], color=COLORS[proto], marker=MARKERS[proto],
                        linewidth=1.8, capsize=3, label=LABELS[proto])
        if logy:
            ax.set_yscale("log")
        ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
        ax.set_xlabel("RTO setting (ms; adaptive or fixed)", color=INK)
        ax.set_ylabel(ylabel, color=INK)
    axes[0].legend(frameon=False, labelcolor=INK, fontsize=8)
    fig.suptitle("Experiment D: RTO Sensitivity", x=0.03, ha="left", color=INK, fontsize=14)
    fig.text(0.03, 0.91, "Mean across successful runs; bars show min–max. Fixed RTO disables estimation/backoff. 5% loss per direction, 1 MiB file, 10 ms one-way delay.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    path = os.path.join(RES, "experiment_D_rto_sensitivity.png")
    fig.savefig(path, facecolor=SURFACE); plt.close(fig)
    return path


def main():
    b = load("B")
    sb, pb = summarise("B", b, ["protocol", "window"], ["goodput_kbps", "retransmissions", "time_ms"])
    c = load("C")
    sc, pc = summarise("C", c, ["protocol", "reorder"], ["retransmissions", "goodput_kbps", "time_ms"])
    d = load("D")
    sd, pd = summarise("D", d, ["protocol", "rto"], ["retransmissions", "goodput_kbps", "time_ms"])
    plots = [plot_B(sb), plot_C(sc), plot_D(sd)]
    for name, rows in (("B", b), ("C", c), ("D", d)):
        failed = [r for r in rows if not ok(r)]
        print(f"Experiment {name}: {len(rows)} raw rows, {len(rows)-len(failed)} successful, {len(failed)} failed")
        for r in failed:
            print("  FAILED:", r.get("protocol"), r.get("window"), r.get("reorder"), r.get("rto"), r.get("seed"), r.get("status"), r.get("exit_code"))
    print("Summaries:", pb, pc, pd)
    print("Plots:", *plots, sep="\n  ")

if __name__ == "__main__":
    main()
