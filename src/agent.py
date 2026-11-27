# -*- coding: utf-8 -*-
"""课程工单智能分类 Agent 的核心工作流。

流程（每一步都写入 trace，便于报告展示与排障）：
  1. 输入校验：空文本 / 超长 / 无意义重复 / 乱码
  2. 文本清洗与规范化
  3. 机器学习分类：TF-IDF + 线性模型，输出类别与置信度
  4. 决策：低置信度、类别边界模糊、高影响申请 → 转人工复核
  5. 知识库检索：TF-IDF 余弦相似度，低于阈值视为"无可靠答案"
  6. 路由与落库：按类别分配责任方，写入 SQLite，维护复核队列
  7. 生成答复：只用知识库中有出处的信息，不编造政策

用法（单条）：
    python -m src.agent --text "作业提交不了，一直转圈"
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import (
    DATA_DIR, DEFAULT_CONFIDENCE_THRESHOLD, HIGH_IMPACT_INTENTS, KB_MIN_SCORE,
    LABEL_CN, MODEL_DIR, OUTPUT_DIR,
)
from src.preprocess import clean_text
from src.tools import KnowledgeBase, TicketStore, ToolError, route_for

import jieba
jieba.setLogLevel(logging.ERROR)

MAX_INPUT_LEN = 500
MIN_INPUT_LEN = 2
AMBIGUITY_MARGIN = 0.06

HIGH_PRIORITY_HINTS = ["全班", "所有人", "大家都", "马上", "开考", "今天截止", "明天截止", "紧急"]


@dataclass
class Step:
    name: str
    status: str
    detail: str
    elapsed_ms: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentResult:
    raw_text: str
    label: str = "other"
    label_cn: str = ""
    confidence: float = 0.0
    route_to: str = ""
    route_code: str = ""
    priority: str = "低"
    needs_review: bool = False
    review_reason: str = ""
    resolution: str = ""  # auto_answered / auto_closed / routed / pending_review / rejected
    reply: str = ""
    sources: list[dict] = field(default_factory=list)
    ticket_id: int | None = None
    steps: list[dict] = field(default_factory=list)
    degraded: bool = False
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "raw_text": self.raw_text, "label": self.label, "label_cn": self.label_cn,
            "confidence": round(self.confidence, 4), "route_to": self.route_to,
            "route_code": self.route_code, "priority": self.priority,
            "needs_review": self.needs_review, "review_reason": self.review_reason,
            "resolution": self.resolution,
            "reply": self.reply, "sources": self.sources, "ticket_id": self.ticket_id,
            "steps": self.steps, "degraded": self.degraded, "error": self.error,
        }


class WorkOrderAgent:
    def __init__(self, model_path: Path | None = None, threshold: float | None = None):
        self.model_path = model_path or (MODEL_DIR / "classifier.joblib")
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"未找到模型 {self.model_path}，请先运行: python -m src.train"
            )
        self.model = joblib.load(self.model_path)
        self.classes = list(self.model.named_steps["clf"].classes_)
        meta_path = MODEL_DIR / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        self.threshold = float(threshold if threshold is not None else
                               meta.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD))

        self.kb_error = ""
        try:
            self.kb: KnowledgeBase | None = KnowledgeBase()
        except ToolError as e:
            self.kb, self.kb_error = None, str(e)

        self.store_error = ""
        try:
            self.store: TicketStore | None = TicketStore()
        except ToolError as e:
            self.store, self.store_error = None, str(e)

        self.trace_path = OUTPUT_DIR / "agent_trace.jsonl"

    # ------------------------------------------------------------------ #
    def _proba(self, text: str) -> tuple[np.ndarray, np.ndarray]:
        proba = self.model.predict_proba([text])[0]
        return proba, np.asarray(self.classes)

    def process(self, text: str, persist: bool = True, log_trace: bool = True) -> AgentResult:
        r = AgentResult(raw_text=text or "")
        t0 = time.perf_counter()
        steps: list[Step] = []

        def add(name: str, status: str, detail: str, start: float) -> None:
            steps.append(Step(name, status, detail, int((time.perf_counter() - start) * 1000)))

        # 1. 输入校验 ------------------------------------------------------
        s = time.perf_counter()
        raw = clean_text(text or "")
        if not raw:
            r.error = "输入为空"
            r.resolution = "rejected"
            add("输入校验", "error", "输入为空，已拒绝处理", s)
            r.steps = [x.as_dict() for x in steps]
            r.reply = "没有收到有效内容，请描述你遇到的问题（例如：作业第 3 题不会做 / 学习通打不开）。"
            return r
        if len(raw) < MIN_INPUT_LEN:
            r.error = "输入过短"
            r.resolution = "rejected"
            add("输入校验", "error", f"输入长度 {len(raw)} < {MIN_INPUT_LEN}", s)
            r.steps = [x.as_dict() for x in steps]
            r.reply = "信息太少，无法判断问题类型，请补充具体课程、平台或操作步骤。"
            return r
        truncated = False
        if len(raw) > MAX_INPUT_LEN:
            raw = raw[:MAX_INPUT_LEN]
            truncated = True
        if len(set(raw)) <= 2 and len(raw) > 5:  # "啊啊啊啊啊啊"
            r.error = "无意义重复输入"
            r.resolution = "rejected"
            add("输入校验", "error", "检测到重复字符噪声", s)
            r.steps = [x.as_dict() for x in steps]
            r.reply = "没有识别到有效问题，请用一句话描述具体困难。"
            return r
        add("输入校验", "ok", f"长度={len(raw)}" + ("，已截断到500字" if truncated else ""), s)

        # 2. 预处理 --------------------------------------------------------
        s = time.perf_counter()
        add("文本清洗", "ok", "全角转半角、压缩空白、保留数字/英文/标点", s)

        # 3. 机器学习分类 ---------------------------------------------------
        s = time.perf_counter()
        try:
            proba, classes = self._proba(raw)
            idx = int(proba.argmax())
            label = str(classes[idx])
            conf = float(proba[idx])
            margin = float(proba[idx] - np.partition(proba, -2)[-2]) if len(proba) > 1 else 1.0
            add("机器学习分类", "ok",
                f"TF-IDF(char 2-4 + word 1-2) + {type(self.model.named_steps['clf']).__name__} → "
                f"{LABEL_CN.get(label, label)}，置信度={conf:.3f}，与次优类别差距={margin:.3f}", s)
        except Exception as e:  # noqa: BLE001
            r.error = f"分类失败: {e}"
            r.degraded = True
            r.resolution = "rejected"
            add("机器学习分类", "error", r.error, s)
            r.steps = [x.as_dict() for x in steps]
            r.reply = "分类服务暂时不可用，已记录问题并转人工处理。"
            self._persist(r, steps, None, log_trace, persist)
            return r

        r.label, r.label_cn, r.confidence = label, LABEL_CN.get(label, label), conf
        r.route_to, r.route_code = route_for(label)
        proba_map = {str(c): round(float(p), 4) for c, p in zip(classes, proba)}

        # 4. 决策：复核 / 优先级 --------------------------------------------
        s = time.perf_counter()
        reasons = []
        if conf < self.threshold:
            reasons.append(f"置信度 {conf:.2f} 低于阈值 {self.threshold:.2f}")
        if margin < AMBIGUITY_MARGIN:
            reasons.append(f"前两类概率差距仅 {margin:.2f}，存在类别歧义")
        if len(raw) < 6:
            reasons.append("输入过短，语义不完整")
        hit_intents = [k for k in HIGH_IMPACT_INTENTS if k in raw]
        if hit_intents:
            reasons.append("涉及高影响申请（" + "、".join(hit_intents) + "），需人工确认后答复")
        r.needs_review = bool(reasons)
        r.review_reason = "；".join(reasons)

        if label == "system" and any(h in raw for h in HIGH_PRIORITY_HINTS):
            r.priority = "高"
        elif hit_intents or label == "system":
            r.priority = "中"
        else:
            r.priority = "低"
        add("决策", "review" if r.needs_review else "ok",
            (r.review_reason if r.needs_review else "置信度足够，可自动处理") + f"；优先级={r.priority}", s)

        # 5. 知识库检索 -----------------------------------------------------
        s = time.perf_counter()
        hits: list[dict] = []
        if self.kb is None:
            r.degraded = True
            add("知识库检索", "error", f"知识库不可用：{self.kb_error}", s)
        else:
            try:
                found = self.kb.search(raw, category=label, top_k=3)
                hits = [h.as_dict() for h in found]
                if hits:
                    add("知识库检索", "ok",
                        f"命中 {len(hits)} 条，最高相似度={hits[0]['score']:.3f}（{hits[0]['faq_id']}）", s)
                else:
                    add("知识库检索", "ok", f"无相似度≥{KB_MIN_SCORE}的条目，判定为无可靠答案", s)
            except ToolError as e:
                r.degraded = True
                add("知识库检索", "error", f"检索失败：{e}", s)
        r.sources = [h for h in hits[:2]]

        # 6. 路由与落库 -----------------------------------------------------
        s = time.perf_counter()
        add("路由", "ok", f"{r.label_cn} → {r.route_to}（{r.route_code}）", s)

        # 7. 生成答复 -------------------------------------------------------
        s = time.perf_counter()
        r.reply = self._compose_reply(r, hits, proba_map)
        add("生成答复", "ok", f"基于知识库证据生成 {len(r.reply)} 字答复，未调用通用大模型", s)

        # 处理结论：能答才答，答不了就转人工，不编造
        if r.error:
            r.resolution = "rejected"
        elif r.needs_review:
            r.resolution = "pending_review"
        elif label == "other":
            r.resolution = "auto_closed"
        elif hits:
            r.resolution = "auto_answered"
        else:
            r.resolution = "routed"
        add("结论", "ok",
            {"auto_answered": "已基于知识库自动答复",
             "auto_closed": "非工单，自动归档",
             "routed": "已分类并路由，等待人工答复",
             "pending_review": "进入人工复核队列",
             "rejected": "输入无效，已拒绝"}[r.resolution], s)

        r.steps = [x.as_dict() for x in steps]
        # 8. 持久化 ---------------------------------------------------------
        self._persist(r, steps, proba_map, log_trace, persist)
        return r

    # ------------------------------------------------------------------ #
    def _compose_reply(self, r: AgentResult, hits: list[dict], proba_map: dict) -> str:
        header = f"【自动处理】{r.label_cn}\n"
        if r.label == "other":
            return (header + "这条消息更像课程群里的日常交流，不属于需要跟进的工单，"
                    "已归入“其他”分类，不会打扰助教。如确实需要办理事务，请补充具体诉求。")

        if r.needs_review:
            body = (f"已登记你的问题，并转交{r.route_to}人工确认。\n"
                    f"原因：{r.review_reason}。\n"
                    "在人工确认前，系统不会替你做出调课、延期、成绩处理等决定，请留意后续回复。")
            return header + body

        if hits:
            top = hits[0]
            body = (f"参考答复：{top['answer']}\n"
                    f"依据：{top['source']}（{top['owner']}，条目 {top['faq_id']}，相似度 {top['score']:.2f}）。\n"
                    f"下一步：工单已路由给{r.route_to}，如仍有疑问可直接在工单下追问。")
        else:
            body = (f"暂未在知识库中找到可信度足够的标准答案，为避免误导，已转交{r.route_to}人工回复。\n"
                    f"你可以补充课程名称、平台报错截图或具体题号，帮助助教更快定位。")

        body += "\n（自动答复仅供参考，最终以课程/教务的正式通知为准。）"
        return header + body

    # ------------------------------------------------------------------ #
    def _persist(self, r: AgentResult, steps: list[Step], proba_map: dict | None, log_trace: bool, persist: bool = True) -> None:
        record = {
            "raw_text": r.raw_text, "label": r.label, "label_cn": r.label_cn,
            "confidence": round(r.confidence, 4), "route_to": r.route_to,
            "priority": r.priority,
            "status": r.resolution or ("pending_review" if r.needs_review else "routed"),
            "needs_review": r.needs_review, "review_reason": r.review_reason,
            "reply": r.reply, "trace_json": json.dumps([x.as_dict() for x in steps], ensure_ascii=False),
        }
        if persist and self.store is not None:
            try:
                r.ticket_id = self.store.create(record)
            except ToolError as e:
                r.degraded = True
                r.error = (r.error + "；" if r.error else "") + f"工单落库失败：{e}"
        elif persist and self.store is None:
            r.degraded = True
            r.error = (r.error + "；" if r.error else "") + f"工单库不可用：{self.store_error}"

        if log_trace:
            try:
                payload = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "input": r.raw_text, "result": r.as_dict(), "proba": proba_map,
                }
                with self.trace_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        if self.store:
            self.store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="课程工单 Agent 单条演示")
    parser.add_argument("--text", required=True)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    agent = WorkOrderAgent()
    result = agent.process(args.text, persist=not args.no_persist)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    print("\n--- 处理轨迹 ---")
    for i, step in enumerate(result.steps, 1):
        print(f"{i}. [{step['status']}] {step['name']} ({step['elapsed_ms']}ms): {step['detail']}")


if __name__ == "__main__":
    main()

