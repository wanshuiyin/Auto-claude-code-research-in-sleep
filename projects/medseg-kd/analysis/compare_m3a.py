# -*- coding: utf-8 -*-
"""m3a queue (R013/R014a/R014b) comparison: tables + convergence figure."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUNS = {
    "R013 no-KD (baseline)": "r013_noKD_dualdomain.results.json",
    "R014a KD-logit skin": "r014a_kd_logit_skin.results.json",
    "R014b KD-logit polyp": "r014b_kd_logit_polyp.results.json",
}
DATA = {k: json.load(open(v, encoding="utf-8")) for k, v in RUNS.items()}

# ---------- summary table ----------
print("run                 | best(val)  ep  sel    | val@400 isic/kvasir | kvasir TEST dice/iou/hd95")
for k, d in DATA.items():
    t = d["test"]
    h = d["history"][-1]
    print(f"{k:20s} | {d['best_dice']:.4f}  {d['best_epoch']:3d}  {d['select']:6s} | "
          f"{h['isic']['dice']:.4f} / {h['kvasir']['dice']:.4f}   | "
          f"{t['dice']:.4f} / {t['iou']:.4f} / {t['hd95']:.2f}")

base = DATA["R013 no-KD (baseline)"]
print("\nKD gain (dice) vs R013:")
for k in ["R014a KD-logit skin", "R014b KD-logit polyp"]:
    d = DATA[k]
    h = d["history"][-1]
    print(f"  {k:20s}: isic val {h['isic']['dice']-base['history'][-1]['isic']['dice']:+.4f} | "
          f"kvasir val {h['kvasir']['dice']-base['history'][-1]['kvasir']['dice']:+.4f} | "
          f"kvasir test {d['test']['dice']-base['test']['dice']:+.4f}")

# ---------- convergence figure ----------
COLORS = {"R013 no-KD (baseline)": "#444444", "R014a KD-logit skin": "#2a7bb8", "R014b KD-logit polyp": "#c0392b"}
STYLE = {"R013 no-KD (baseline)": "--", "R014a KD-logit skin": "-", "R014b KD-logit polyp": "-"}

fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), constrained_layout=True)
for dom, ax, title in [("isic", axes[0], "ISIC (val dice)"), ("kvasir", axes[1], "Kvasir (val dice)")]:
    for k, d in DATA.items():
        xs = [p["epoch"] for p in d["history"]]
        ys = [p[dom]["dice"] for p in d["history"]]
        ax.plot(xs, ys, STYLE[k], color=COLORS[k], label=k, linewidth=1.8)
    ax.set_xlabel("epoch")
    ax.set_ylabel("Dice")
    ax.set_title(title)
    ax.grid(alpha=0.3)
axes[1].legend(fontsize=8, frameon=False)
fig.savefig("m3a_convergence.png", dpi=200)
fig.savefig("m3a_convergence.svg")
print("\nsaved m3a_convergence.png / .svg")
