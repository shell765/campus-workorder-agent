# -*- coding: utf-8 -*-
"""训练与评估文本分类模型，并做置信度阈值搜索。

流程：
1. 读取合成工单数据；难例全部留作测试集，基础样本按 75/12.5/12.5 划分；
2. 在开发集上比较 ComplementNB / LinearSVC / LogisticRegression；
3. 用开发集搜索"自动处理 vs 转人工"的置信度阈值；
4. 最优模型在 train+dev 上重训，在含难例的测试集上报告最终指标；
5. 保存模型、指标、预测明细，供 Agent 与报告使用。

用法：python -m src.train
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.baseline import rule_classify
from src.config import DATA_DIR, LABELS, LABEL_CN, MODEL_DIR, OUTPUT_DIR
from src.preprocess import jieba_tokenize

RANDOM_STATE = 42


def build_features() -> FeatureUnion:
    """字符 n-gram + 分词词 n-gram 的双通道 TF-IDF。

    - 字符 n-gram 对中文错别字、口语缩写更稳健（如"做业""登不上"）；
    - 词 n-gram 提供可解释的关键词证据，便于向用户/助教说明分类依据。
    """
    return FeatureUnion([
        ("char", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), min_df=2,
            sublinear_tf=True, max_features=60000,
        )),
        ("word", TfidfVectorizer(
            tokenizer=jieba_tokenize, token_pattern=None, lowercase=False,
            ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=30000,
        )),
    ])


def build_model(name: str) -> Pipeline:
    if name == "nb":
        clf = ComplementNB(alpha=0.4)
    elif name == "svm":
        clf = CalibratedClassifierCV(LinearSVC(C=1.0, class_weight="balanced"), cv=3, method="sigmoid")
    elif name == "lr":
        clf = LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced", random_state=RANDOM_STATE)
    else:
        raise ValueError(name)
    return Pipeline([("features", build_features()), ("clf", clf)])


def metrics_dict(y_true, y_pred) -> dict:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted")),
    }


def predict_with_confidence(model: Pipeline, texts) -> tuple[np.ndarray, np.ndarray]:
    proba = model.predict_proba(texts)
    idx = proba.argmax(axis=1)
    classes = np.asarray(model.classes_)
    return classes[idx], proba.max(axis=1)


def main() -> None:
    df = pd.read_csv(DATA_DIR / "tickets.csv")
    base = df[df["is_hard"] == 0].copy()
    hard = df[df["is_hard"] == 1].copy()

    train_df, temp_df = train_test_split(
        base, test_size=0.25, random_state=RANDOM_STATE, stratify=base["label"]
    )
    dev_base_df, test_base_df = train_test_split(
        temp_df, test_size=0.5, random_state=RANDOM_STATE, stratify=temp_df["label"]
    )
    # 难例也要分一部分进开发集：否则阈值只在高置信度样本上调，会严重偏高覆盖、
    # 到真实模糊输入上错误率失控（第一版实验就踩了这个坑）。
    hard_dev, hard_test = train_test_split(
        hard, test_size=0.6, random_state=RANDOM_STATE, stratify=hard["label"]
    )
    dev_df = pd.concat([dev_base_df, hard_dev], ignore_index=True)
    test_df = pd.concat([test_base_df, hard_test], ignore_index=True)

    print(f"train={len(train_df)} dev={len(dev_df)} test={len(test_df)} "
          f"(其中难例 {len(hard_test)} 条，占 {len(hard_test)/len(test_df):.1%})")

    model_results = {}
    dev_scores = {}
    for name in ["nb", "svm", "lr"]:
        model = build_model(name)
        model.fit(train_df["text"], train_df["label"])
        pred = model.predict(dev_df["text"])
        m = metrics_dict(dev_df["label"], pred)
        dev_scores[name] = m["macro_f1"]
        model_results[name] = (model, m)
        print(f"[dev] {name:4s} acc={m['accuracy']:.4f} macroF1={m['macro_f1']:.4f}")

    best_name = max(dev_scores, key=dev_scores.get)
    print(f"开发集最优模型: {best_name}")

    # ---- 阈值搜索（用开发集，避免在测试集上调参）----
    model = model_results[best_name][0]
    pred_dev, conf_dev = predict_with_confidence(model, dev_df["text"])
    curve = []
    for t in np.round(np.arange(0.30, 0.91, 0.02), 2):
        auto = conf_dev >= t
        n_auto = int(auto.sum())
        if n_auto == 0:
            continue
        err = float((pred_dev[auto] != dev_df["label"].to_numpy()[auto]).mean())
        curve.append({
            "threshold": float(t),
            "auto_coverage": n_auto / len(dev_df),
            "auto_error_rate": err,
            "review_rate": 1 - n_auto / len(dev_df),
            "auto_accuracy": 1 - err,
        })
    curve_df = pd.DataFrame(curve)
    # 运行成本：每 100 条工单，错误自动答复记 4 分（需返工、影响信任），
    # 转人工复核记 1 分（助教确认成本）。取总成本最低的阈值。
    curve_df["cost_per_100"] = (
        4 * curve_df["auto_error_rate"] * curve_df["auto_coverage"] * 100
        + curve_df["review_rate"] * 100
    )
    curve_df.to_csv(OUTPUT_DIR / "threshold_curve.csv", index=False, encoding="utf-8-sig")

    threshold = float(curve_df.sort_values("cost_per_100").iloc[0]["threshold"])
    chosen = curve_df[curve_df["threshold"] == threshold].iloc[0]
    print(f"选定置信度阈值={threshold}（开发集成本最低：自动错误率={chosen['auto_error_rate']:.3f}，"
          f"自动覆盖率={chosen['auto_coverage']:.3f}）")

    # ---- 用 train+dev 重训最终模型，测试集只评一次 ----
    final = build_model(best_name)
    final.fit(pd.concat([train_df, dev_df])["text"], pd.concat([train_df, dev_df])["label"])
    test_pred, test_conf = predict_with_confidence(final, test_df["text"])

    y_true = test_df["label"].to_numpy()
    overall = metrics_dict(y_true, test_pred)
    per_class = classification_report(y_true, test_pred, labels=LABELS, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, test_pred, labels=LABELS)

    base_mask = test_df["is_hard"].to_numpy() == 0
    hard_mask = ~base_mask
    subset = {
        "base_test": metrics_dict(y_true[base_mask], test_pred[base_mask]),
        "hard_test": metrics_dict(y_true[hard_mask], test_pred[hard_mask]),
        "n_base": int(base_mask.sum()),
        "n_hard": int(hard_mask.sum()),
    }

    # 自动处理（不转人工）时的错误率
    auto_mask = test_conf >= threshold
    auto_metrics = {
        "coverage": float(auto_mask.mean()),
        "error_rate": float((test_pred[auto_mask] != y_true[auto_mask]).mean()) if auto_mask.any() else None,
        "review_rate": float(1 - auto_mask.mean()),
    }

    # 规则基线
    rule_pred = np.array([rule_classify(t) for t in test_df["text"]])
    rule_metrics = metrics_dict(y_true, rule_pred)
    rule_metrics["auto_error_rate(全部自动)"] = rule_metrics["accuracy"]  # 便于对照，见报告说明

    comparison = [
        {"model": "关键词规则基线", **rule_metrics},
        {"model": "ComplementNB", **model_results["nb"][1], "note": "dev"},
        {"model": "LinearSVC(calibrated)", **model_results["svm"][1], "note": "dev"},
        {"model": "LogisticRegression", **model_results["lr"][1], "note": "dev"},
        {"model": f"最终模型({best_name})", **overall, "note": "test"},
    ]
    comparison_df = pd.DataFrame(comparison)

    test_out = test_df[["ticket_id", "text", "label", "is_hard"]].copy()
    test_out["pred"] = test_pred
    test_out["confidence"] = np.round(test_conf, 4)
    test_out["correct"] = (test_out["label"] == test_out["pred"]).astype(int)
    test_out["auto_handled"] = (test_out["confidence"] >= threshold).astype(int)
    test_out.to_csv(OUTPUT_DIR / "test_predictions.csv", index=False, encoding="utf-8-sig")

    cm_df = pd.DataFrame(cm, index=[f"true_{l}" for l in LABELS], columns=[f"pred_{l}" for l in LABELS])
    cm_df.to_csv(OUTPUT_DIR / "confusion_matrix.csv", encoding="utf-8-sig")
    comparison_df.to_csv(OUTPUT_DIR / "model_comparison.csv", index=False, encoding="utf-8-sig")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, MODEL_DIR / "classifier.joblib")

    metrics = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "random_state": RANDOM_STATE,
        "best_model": best_name,
        "confidence_threshold": threshold,
        "data": {
            "train": len(train_df), "dev": len(dev_df),
            "test": len(test_df), "n_hard": int(len(hard)),
            "n_hard_dev": int(len(hard_dev)), "n_hard_test": int(hard_mask.sum()),
            "n_base_test": int(base_mask.sum()),
        },
        "threshold_policy": {
            "method": "在开发集上最小化运行成本（错误自动答复*4 + 人工复核*1）",
            "best": {
                "threshold": threshold,
                "auto_coverage": float(chosen["auto_coverage"]),
                "auto_error_rate": float(chosen["auto_error_rate"]),
                "cost_per_100": float(chosen["cost_per_100"]),
            },
        },
        "overall": overall,
        "per_class": {k: v for k, v in per_class.items() if k in LABELS},
        "macro_f1_no_other": float(f1_score(
            y_true[np.isin(y_true, [l for l in LABELS if l != "other"])],
            test_pred[np.isin(y_true, [l for l in LABELS if l != "other"])],
            average="macro", labels=[l for l in LABELS if l != "other"],
        )),
        "subset": subset,
        "auto_policy": auto_metrics,
        "rule_baseline": rule_metrics,
        "dev_scores": {k: float(v) for k, v in dev_scores.items()},
        "label_cn": LABEL_CN,
    }
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "model_name": best_name,
        "confidence_threshold": threshold,
        "classes": LABELS,
        "feature": "char(2-4)+jieba_word(1-2) TF-IDF",
        "trained_at": metrics["generated_at"],
        "train_size": len(train_df) + len(dev_df),
    }
    (MODEL_DIR / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 测试集（含难例）===")
    print(f"accuracy={overall['accuracy']:.4f} macroF1={overall['macro_f1']:.4f}")
    print(f"难例 macroF1={subset['hard_test']['macro_f1']:.4f} 基础样本 macroF1={subset['base_test']['macro_f1']:.4f}")
    print(f"自动处理覆盖率={auto_metrics['coverage']:.3f} 自动处理错误率={auto_metrics['error_rate']:.3f}")
    print(f"规则基线 accuracy={rule_metrics['accuracy']:.4f} macroF1={rule_metrics['macro_f1']:.4f}")
    print("\n各类别：")
    for l in LABELS:
        r = per_class[l]
        print(f"  {LABEL_CN[l]:6s} P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1-score']:.3f} n={int(r['support'])}")


if __name__ == "__main__":
    main()
