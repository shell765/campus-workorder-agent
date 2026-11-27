# -*- coding: utf-8 -*-
"""端到端评估与消融实验。

1. 用训练好的 Agent 逐条处理测试集，统计分类、自动处理、复核、逃逸错误、时延；
2. 与"无置信度复核""纯规则""无知识库""单通道特征"等简化版本对照；
3. 测试异常输入（空、噪声、超长、工具不可用），验证降级行为；
4. 导出错误案例，供报告做误差分析。

用法：python -m src.evaluate
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import WorkOrderAgent
from src.baseline import rule_classify
from src.config import DATA_DIR, LABELS, MODEL_DIR, OUTPUT_DIR
from src.preprocess import jieba_tokenize
from src.train import build_features

THRESHOLD = json.loads((OUTPUT_DIR / "metrics.json").read_text(encoding="utf-8"))["confidence_threshold"]


def feature_pipeline(kind: str, clf) -> Pipeline:
    if kind == "char":
        feats = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2,
                                sublinear_tf=True, max_features=60000)
    elif kind == "word":
        feats = TfidfVectorizer(tokenizer=jieba_tokenize, token_pattern=None, lowercase=False,
                                ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=30000)
    else:
        feats = build_features()
    return Pipeline([("features", feats), ("clf", clf)])


def main() -> None:
    df = pd.read_csv(DATA_DIR / "tickets.csv")
    base = df[df["is_hard"] == 0]
    metrics = json.loads((OUTPUT_DIR / "metrics.json").read_text(encoding="utf-8"))
    # 复现 train.py 的划分（相同 random_state）
    from sklearn.model_selection import train_test_split
    train_df, temp_df = train_test_split(base, test_size=0.25, random_state=42, stratify=base["label"])
    dev_base_df, test_base_df = train_test_split(temp_df, test_size=0.5, random_state=42, stratify=temp_df["label"])
    hard = df[df["is_hard"] == 1]
    hard_dev, hard_test = train_test_split(hard, test_size=0.6, random_state=42, stratify=hard["label"])
    test_df = pd.concat([test_base_df, hard_test], ignore_index=True)

    agent = WorkOrderAgent(threshold=THRESHOLD)

    rows, latencies = [], []
    for _, row in test_df.iterrows():
        t0 = time.perf_counter()
        r = agent.process(row["text"], persist=False, log_trace=True)
        latencies.append((time.perf_counter() - t0) * 1000)
        rows.append({
            "ticket_id": row["ticket_id"], "text": row["text"], "true": row["label"],
            "pred": r.label, "confidence": r.confidence, "needs_review": r.needs_review,
            "review_reason": r.review_reason, "priority": r.priority,
            "resolution": r.resolution,
            "route_to": r.route_to, "kb_hits": len(r.sources),
            "kb_top_score": r.sources[0]["score"] if r.sources else 0.0,
            "degraded": r.degraded, "reply_len": len(r.reply),
        })

    res = pd.DataFrame(rows)
    res["correct"] = (res["true"] == res["pred"]).astype(int)
    res["auto_answered"] = res["resolution"].isin(["auto_answered", "auto_closed"]).astype(int)
    res.to_csv(OUTPUT_DIR / "agent_test_results.csv", index=False, encoding="utf-8-sig")

    n = len(res)
    err = res[res["correct"] == 0]
    auto = res[res["auto_answered"] == 1]
    substantive = res[res["resolution"] == "auto_answered"]
    routed = res[res["resolution"] == "routed"]
    reviewed = res[res["needs_review"] == 1]
    escaped = auto[auto["correct"] == 0]
    captured = reviewed[reviewed["correct"] == 0]

    summary = {
        "n_test": n,
        "classification": {
            "accuracy": float(accuracy_score(res["true"], res["pred"])),
            "macro_f1": float(f1_score(res["true"], res["pred"], labels=LABELS, average="macro")),
        },
        "agent_policy": {
            "auto_answer_rate": float(len(auto) / n),
            "substantive_answer_rate": float(len(substantive) / n),
            "routed_rate": float(len(routed) / n),
            "review_rate": float(len(reviewed) / n),
            "auto_answer_accuracy": float(auto["correct"].mean()) if len(auto) else None,
            "escaped_errors": int(len(escaped)),
            "escaped_error_rate": float(len(escaped) / len(auto)) if len(auto) else None,
            "total_errors": int(len(err)),
            "error_capture_rate": float(len(captured) / len(err)) if len(err) else None,
        },
        "kb": {
            "hit_rate": float((res["kb_hits"] > 0).mean()),
            "mean_top_score": float(res.loc[res["kb_hits"] > 0, "kb_top_score"].mean()) if (res["kb_hits"] > 0).any() else 0.0,
        },
        "latency": {
            "mean_ms": float(np.mean(latencies)),
            "p95_ms": float(sorted(latencies)[min(len(latencies) - 1, int(0.95 * len(latencies)))]),
        },
        "degraded_count": int(res["degraded"].sum()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # ---- 消融：同一测试集上的策略对照 ----------------------------------
    rule_pred = np.array([rule_classify(t) for t in res["text"]])
    ablations = [
        {
            "variant": "完整 Agent（ML + 置信度复核 + KB）",
            "auto_answer_rate": summary["agent_policy"]["auto_answer_rate"],
            "escaped_error_rate": summary["agent_policy"]["escaped_error_rate"],
            "macro_f1": summary["classification"]["macro_f1"],
            "kb_evidence_rate": summary["kb"]["hit_rate"],
        },
        {
            "variant": "去掉置信度复核（全自动）",
            "auto_answer_rate": 1.0,
            "escaped_error_rate": float((res["true"] != res["pred"]).mean()),
            "macro_f1": summary["classification"]["macro_f1"],
            "kb_evidence_rate": float((res["kb_hits"] > 0).mean()),
        },
        {
            "variant": "纯关键词规则（全自动）",
            "auto_answer_rate": 1.0,
            "escaped_error_rate": float((res["true"] != rule_pred).mean()),
            "macro_f1": float(f1_score(res["true"], rule_pred, labels=LABELS, average="macro")),
            "kb_evidence_rate": float((res["kb_hits"] > 0).mean()),
        },
        {
            "variant": "无知识库（只分类路由）",
            "auto_answer_rate": float((res["resolution"].isin(["auto_closed"])).mean()),
            "escaped_error_rate": summary["agent_policy"]["escaped_error_rate"],
            "macro_f1": summary["classification"]["macro_f1"],
            "kb_evidence_rate": 0.0,
        },
    ]
    ab_df = pd.DataFrame(ablations)
    ab_df.to_csv(OUTPUT_DIR / "ablation.csv", index=False, encoding="utf-8-sig")
    print("\n=== 消融实验 ===")
    print(ab_df.to_string(index=False))

    # ---- 特征通道消融 --------------------------------------------------
    train_all = pd.concat([train_df, dev_base_df, hard_dev])
    feat_rows = []
    for kind in ["char", "word", "union"]:
        if kind == "union":
            model = joblib.load(MODEL_DIR / "classifier.joblib")
        else:
            model = feature_pipeline(kind, ComplementNB(alpha=0.4))
            model.fit(train_all["text"], train_all["label"])
        pred = model.predict(test_df["text"])
        feat_rows.append({
            "features": {"char": "字符 2-4 gram", "word": "jieba 词 1-2 gram", "union": "字符 + 词（最终）"}[kind],
            "accuracy": float(accuracy_score(test_df["label"], pred)),
            "macro_f1": float(f1_score(test_df["label"], pred, labels=LABELS, average="macro")),
        })
    feat_df = pd.DataFrame(feat_rows)
    feat_df.to_csv(OUTPUT_DIR / "feature_ablation.csv", index=False, encoding="utf-8-sig")
    print("\n=== 特征通道消融 ===")
    print(feat_df.to_string(index=False))

    # ---- 错误案例 ------------------------------------------------------
    err_out = res[res["correct"] == 0].copy()
    err_out["true_cn"] = err_out["true"].map(metrics["label_cn"])
    err_out["pred_cn"] = err_out["pred"].map(metrics["label_cn"])
    err_out = err_out.sort_values("confidence", ascending=False)
    err_out[["ticket_id", "text", "true_cn", "pred_cn", "confidence", "needs_review", "review_reason"]] \
        .head(20).to_csv(OUTPUT_DIR / "error_cases.csv", index=False, encoding="utf-8-sig")

    # ---- 异常输入与降级测试 --------------------------------------------
    failure_tests = []
    cases = [
        ("空输入", ""),
        ("单字符", "？"),
        ("重复噪声", "啊啊啊啊啊啊啊啊"),
        ("超长文本", "作业不会做。" * 300),
        ("纯英文", "help me please"),
    ]
    for name, text in cases:
        r = agent.process(text, persist=False, log_trace=False)
        failure_tests.append({
            "case": name, "input_len": len(text), "error": r.error,
            "reply": r.reply[:80], "steps": len(r.steps),
            "handled": bool(r.reply) and not r.degraded,
        })
    ft = pd.DataFrame(failure_tests)
    ft.to_csv(OUTPUT_DIR / "failure_handling.csv", index=False, encoding="utf-8-sig")
    print("\n=== 异常输入处理 ===")
    print(ft[["case", "error", "handled"]].to_string(index=False))

    (OUTPUT_DIR / "agent_eval.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    agent.close()
    print(f"\n结果已保存到 {OUTPUT_DIR}")


if __name__ == "__main__":
    main()


