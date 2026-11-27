# -*- coding: utf-8 -*-
"""生成报告与演示所需图表（全部基于真实实验结果）。

用法：python -m src.make_figures
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from sklearn.metrics import confusion_matrix

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_DIR, LABEL_CN, LABELS, OUTPUT_DIR

FONT_CANDIDATES = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]


def setup_font() -> None:
    from matplotlib import font_manager
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


SHORT = {"homework": "作业", "system": "系统", "exam": "考试", "admin": "行政", "other": "其他"}


def fig_class_distribution() -> None:
    df = pd.read_csv(DATA_DIR / "tickets.csv")
    counts = df["label"].value_counts().reindex(LABELS)
    plt.figure(figsize=(6.4, 3.6))
    bars = plt.bar([SHORT[l] for l in LABELS], counts.values, color="#4C78A8")
    for b, v in zip(bars, counts.values):
        plt.text(b.get_x() + b.get_width() / 2, v + 4, str(v), ha="center", fontsize=9)
    plt.ylabel("样本数")
    plt.title("工单类别分布（含195条边界难例）")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "fig_class_distribution.png", dpi=160)
    plt.close()


def fig_confusion() -> None:
    res = pd.read_csv(OUTPUT_DIR / "agent_test_results.csv")
    cm = confusion_matrix(res["true"], res["pred"], labels=LABELS)
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(LABELS)), [SHORT[l] for l in LABELS])
    ax.set_yticks(range(len(LABELS)), [SHORT[l] for l in LABELS])
    ax.set_xlabel("预测类别")
    ax.set_ylabel("真实类别")
    for i in range(len(LABELS)):
        for j in range(len(LABELS)):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "#222", fontsize=10)
    ax.set_title("测试集混淆矩阵（n=%d）" % len(res))
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "fig_confusion_matrix.png", dpi=160)
    plt.close()


def fig_threshold() -> None:
    curve = pd.read_csv(OUTPUT_DIR / "threshold_curve.csv")
    fig, ax1 = plt.subplots(figsize=(6.4, 3.8))
    ax1.plot(curve["threshold"], curve["auto_error_rate"] * 100, "o-", color="#D55E00", label="自动处理错误率")
    ax1.set_xlabel("置信度阈值")
    ax1.set_ylabel("自动处理错误率 (%)", color="#D55E00")
    ax1.tick_params(axis="y", labelcolor="#D55E00")
    ax2 = ax1.twinx()
    ax2.plot(curve["threshold"], curve["auto_coverage"] * 100, "s-", color="#0072B2", label="自动处理覆盖率")
    ax2.set_ylabel("自动处理覆盖率 (%)", color="#0072B2")
    ax2.tick_params(axis="y", labelcolor="#0072B2")
    meta = json.loads((OUTPUT_DIR / "metrics.json").read_text(encoding="utf-8"))
    chosen = meta["confidence_threshold"]
    ax1.axvline(chosen, color="gray", ls="--", lw=1)
    ax1.text(chosen + 0.01, ax1.get_ylim()[1] * 0.9, f"选用阈值={chosen}", fontsize=9, color="#444")
    plt.title("开发集上的置信度阈值权衡")
    fig.tight_layout()
    plt.savefig(OUTPUT_DIR / "fig_threshold.png", dpi=160)
    plt.close()


def fig_model_comparison() -> None:
    meta = json.loads((OUTPUT_DIR / "metrics.json").read_text(encoding="utf-8"))
    comp = pd.read_csv(OUTPUT_DIR / "model_comparison.csv")
    comp = comp[comp["model"].isin(["关键词规则基线", "ComplementNB", "LinearSVC(calibrated)", "LogisticRegression"])]
    labels = ["规则基线", "朴素贝叶斯", "线性SVM", "逻辑回归"]
    x = np.arange(len(labels))
    acc = comp["accuracy"].values * 100
    f1 = comp["macro_f1"].values * 100
    plt.figure(figsize=(6.4, 3.6))
    plt.bar(x - 0.2, acc, width=0.38, label="准确率", color="#4C78A8")
    plt.bar(x + 0.2, f1, width=0.38, label="Macro-F1", color="#F58518")
    for i, (a, f) in enumerate(zip(acc, f1)):
        plt.text(i - 0.2, a + 0.6, f"{a:.1f}", ha="center", fontsize=8)
        plt.text(i + 0.2, f + 0.6, f"{f:.1f}", ha="center", fontsize=8)
    plt.xticks(x, labels)
    plt.ylim(70, 100)
    plt.ylabel("百分比 (%)")
    plt.title("规则基线 vs 机器学习模型（含难例测试集）")
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "fig_model_comparison.png", dpi=160)
    plt.close()


def fig_ablation() -> None:
    ab = pd.read_csv(OUTPUT_DIR / "ablation.csv")
    labels = ["完整Agent", "去复核", "纯规则", "无知识库"]
    x = np.arange(len(ab))
    fig, ax1 = plt.subplots(figsize=(6.6, 3.8))
    ax1.bar(x - 0.2, ab["auto_answer_rate"] * 100, width=0.38, color="#54A24B", label="自动答复率")
    ax1.set_ylabel("自动答复率 (%)")
    ax1.set_ylim(0, 110)
    ax2 = ax1.twinx()
    ax2.bar(x + 0.2, ab["escaped_error_rate"] * 100, width=0.38, color="#E45756", label="自动答复错误率")
    ax2.set_ylabel("自动答复错误率 (%)")
    ax1.set_xticks(x, labels)
    fig.suptitle("消融实验：复核策略与知识库的作用")
    fig.tight_layout()
    plt.savefig(OUTPUT_DIR / "fig_ablation.png", dpi=160)
    plt.close()


def fig_workflow() -> None:
    steps = [
        ("用户输入\n（学生问题）", "#DCE9F7"),
        ("① 输入校验\n空 / 过短 / 噪声 / 超长", "#DCE9F7"),
        ("② 文本清洗\n全角转半角、压缩空白", "#DCE9F7"),
        ("③ ML 分类\nTF-IDF + ComplementNB\n输出类别与置信度", "#FCE3D2"),
        ("④ 决策\n低置信度/歧义/高影响\n→ 人工复核", "#FFF2CC"),
        ("⑤ 知识库检索\n类别过滤 + 关键词 + 余弦相似度", "#E2EFDA"),
        ("⑥ 路由与落库\n责任方 + SQLite 工单", "#E2EFDA"),
        ("⑦ 生成答复\n仅用有出处的知识", "#E2EFDA"),
    ]
    fig, ax = plt.subplots(figsize=(5.2, 8.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(steps) * 1.28 + 1)
    ax.axis("off")
    y = len(steps) * 1.28
    boxes = []
    for text, color in steps:
        box = FancyBboxPatch((1.0, y - 0.95), 7.0, 0.85, boxstyle="round,pad=0.06,rounding_size=0.15",
                             linewidth=0.8, edgecolor="#666", facecolor=color)
        ax.add_patch(box)
        ax.text(4.5, y - 0.52, text, ha="center", va="center", fontsize=9.5)
        boxes.append((y, y - 0.95))
        y -= 1.28
    for i in range(len(boxes) - 1):
        ax.add_patch(FancyArrowPatch((4.5, boxes[i][1] - 0.02), (4.5, boxes[i + 1][0]),
                                     arrowstyle="-|>", mutation_scale=12, color="#555", lw=1.0))
    # 侧边：复核队列
    ax.add_patch(FancyBboxPatch((8.1, boxes[4][0] - 1.6), 1.75, 1.0, boxstyle="round,pad=0.05",
                                facecolor="#F4CCCC", edgecolor="#999"))
    ax.text(8.97, boxes[4][0] - 1.1, "人工复核\n队列", ha="center", va="center", fontsize=9)
    ax.add_patch(FancyArrowPatch((7.05, boxes[4][1] + 0.4), (8.1, boxes[4][1] + 0.2),
                                 arrowstyle="-|>", mutation_scale=10, color="#B45F06", lw=1.2,
                                 connectionstyle="arc3,rad=-0.2"))
    ax.text(5.0, len(steps) * 1.28 + 0.55, "课程工单 Agent 工作流", ha="center", fontsize=12, weight="bold")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "fig_workflow.png", dpi=170, bbox_inches="tight")
    plt.close()


def main() -> None:
    setup_font()
    fig_class_distribution()
    fig_confusion()
    fig_threshold()
    fig_model_comparison()
    fig_ablation()
    fig_workflow()
    print("图表已生成：", [p.name for p in OUTPUT_DIR.glob("fig_*.png")])


if __name__ == "__main__":
    main()
