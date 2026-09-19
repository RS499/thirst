"""Render the two headline charts to results/.

divergence.png  - average basis: carbon vs water-withdrawal intensity over the
                  day, each min-max normalised, with the gap between their minima.
basis_flip.png  - water savings of a carbon-optimised schedule, average vs
                  marginal-empirical basis, from the vendored upstream simulation.

Reads only data/. Run: python3 make_charts.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "results"
SOURCE = "pjm-water-carbon @ 28aecf4 · PJM, 2025-09-17 to 2026-09-16"

INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"    # categorical slot 1
ORANGE = "#eb6834"  # categorical slot 2

plt.rcParams.update({
    "font.size": 16,
    "axes.edgecolor": INK_2,
    "axes.labelcolor": INK_2,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
})


def hourly_annual(path: Path) -> pd.DataFrame:
    """Collapse season x hour to hour: n_hours-weighted mean = annual mean."""
    d = pd.read_csv(path)
    cols = ["carbon_gco2_kwh", "withdrawal_gal_mwh"]
    num = d[cols].mul(d["n_hours"], axis=0).groupby(d["hour"]).sum()
    return num.div(d.groupby("hour")["n_hours"].sum(), axis=0)


def divergence() -> None:
    a = hourly_annual(DATA / "profile_hourly_average.csv")
    norm = (a - a.min()) / (a.max() - a.min())
    # (column, label, color, min-label alignment): labels splay outward from the gap.
    series = [("carbon_gco2_kwh", "Carbon", ORANGE, "right"),
              ("withdrawal_gal_mwh", "Water withdrawal", BLUE, "left")]

    fig, ax = plt.subplots(figsize=(12, 6.75))
    mins = {}
    for col, label, color, ha in series:
        ax.plot(norm.index, norm[col], color=color, lw=3)
        h = int(norm[col].idxmin())
        mins[col] = h
        ax.plot(h, 0, "o", ms=12, color=color, mec="white", mew=2, zorder=5)
        ax.annotate(f"{label} lowest\nhour {h}", (h, 0), xytext=(12 if ha == "right" else -12, -58),
                    textcoords="offset points", ha=ha, fontsize=15, color=INK)
        ax.text(24.4, norm[col].iloc[-1], label, color=INK, fontsize=16,
                va="center", fontweight="bold")

    h_c, h_w = mins["carbon_gco2_kwh"], mins["withdrawal_gal_mwh"]
    gap = abs(h_w - h_c)
    y = 0.14
    ax.annotate("", (h_c, y), (h_w, y),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=2, shrinkA=0, shrinkB=0))
    ax.text((h_c + h_w) / 2, y + 0.04, f"{gap} hours apart", ha="center",
            fontsize=20, fontweight="bold", color=INK)

    ax.set_xlim(0.5, 24.5)
    ax.set_ylim(-0.32, 1.05)
    ax.set_xticks([1, 6, 12, 18, 24])
    ax.set_xlabel("Hour of day (hour-ending, PJM local time)")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["daily\nlow", "daily\nhigh"])
    ax.spines["left"].set_bounds(0, 1)
    ax.yaxis.grid(True, color=GRID, lw=1)
    ax.set_axisbelow(True)

    fig.suptitle("The cleanest hour for carbon isn't the cleanest for water",
                 x=0.06, ha="left", fontsize=24, fontweight="bold", color=INK)
    ax.set_title("Average basis · annual mean by hour · each curve scaled to its own daily range",
                 loc="left", fontsize=15, color=INK_2, pad=14)
    fig.text(0.06, 0.02, f"Source: {SOURCE}. Withdrawal only; consumption is a separate metric.",
             fontsize=12, color=INK_2)
    fig.subplots_adjust(left=0.08, right=0.78, top=0.84, bottom=0.2)
    fig.savefig(OUT / "divergence.png", dpi=200)
    plt.close(fig)


def basis_flip() -> None:
    s = pd.read_csv(DATA / "savings_carbon_objective.csv", comment="#")
    slacks = sorted(s["slack_h"].unique())
    bases = [("average", "Average basis", ORANGE),
             ("marginal_empirical", "Marginal-empirical basis", BLUE)]
    metrics = [("withdrawal", "Water withdrawal"), ("consumption", "Water consumption")]
    lo = min(s["savings_pct"].min(), 0) - 1.2
    hi = s["savings_pct"].max() + 1

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), sharey=True)
    width = 0.38
    for ax, (metric, title) in zip(axes, metrics):
        for i, (basis, label, color) in enumerate(bases):
            v = (s[(s["basis"] == basis) & (s["metric"] == metric)]
                 .set_index("slack_h").loc[slacks, "savings_pct"])
            x = [k + (i - 0.5) * width for k in range(len(slacks))]
            ax.bar(x, v, width=width - 0.04, color=color, label=label)
        ax.axhline(0, color=INK, lw=2)
        ax.set_title(title, loc="left", fontsize=19, fontweight="bold", color=INK)
        ax.set_xticks(range(len(slacks)))
        ax.set_xticklabels([f"{h} h" for h in slacks])
        ax.set_xlabel("Slack: how long a job may wait")
        ax.set_ylim(lo, hi)
        ax.yaxis.grid(True, color=GRID, lw=1)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", length=0)
    axes[0].set_ylabel("Water saved vs run-on-arrival (%)\n← more water    less water →")
    axes[0].legend(loc="upper left", frameon=False, fontsize=15, labelcolor=INK)
    # One label in the right margin; the shared zero line runs through both panels.
    axes[1].annotate("no scheduling\nat all", (1, 0), xycoords=("axes fraction", "data"),
                     xytext=(12, 0), textcoords="offset points", ha="left", va="center",
                     fontsize=15, color=INK, fontstyle="italic", annotation_clip=False)

    fig.suptitle("Optimizing for carbon costs water on one basis and saves it on the other",
                 x=0.06, ha="left", fontsize=22, fontweight="bold", color=INK)
    fig.text(0.06, 0.885,
             "Jobs rescheduled to minimize carbon by the deadline-constrained job-scheduling "
             "simulation\n(not a lowest-carbon-hour rule). Baseline = each job runs on arrival.",
             fontsize=14, color=INK_2, va="top")
    fig.text(0.06, 0.02, f"Source: {SOURCE}, results/savings.csv (objective = carbon).",
             fontsize=12, color=INK_2)
    fig.subplots_adjust(left=0.1, right=0.87, top=0.76, bottom=0.15, wspace=0.08)
    fig.savefig(OUT / "basis_flip.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    divergence()
    basis_flip()
