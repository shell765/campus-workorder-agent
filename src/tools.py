# -*- coding: utf-8 -*-
"""Agent 可调用的工具层：知识库检索、工单落库、责任方目录。

设计原则：
- 工具失败必须抛出明确异常，由 Agent 捕获并降级（转人工/给出安全提示），
  不允许静默失败后编造答案；
- 知识库只返回有出处的条目，并给出相似度，低相似度由 Agent 判定为"无可靠答案"。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import DATA_DIR, KB_MIN_SCORE, ROUTING
from src.preprocess import clean_text, jieba_tokenize


class ToolError(RuntimeError):
    """工具执行失败（数据缺失、IO 异常等）。"""


@dataclass
class KBHit:
    faq_id: str
    question: str
    answer: str
    category: str
    owner: str
    source: str
    score: float
    method: str = "vector"

    def as_dict(self) -> dict:
        return {
            "faq_id": self.faq_id, "question": self.question, "answer": self.answer,
            "category": self.category, "owner": self.owner, "source": self.source,
            "score": round(self.score, 4), "method": self.method,
        }


# 意图关键词 -> FAQ 条目。用于弥补短查询与长问题之间 TF-IDF 相似度偏低的问题，
# 属于"规则 + 向量"的混合检索；命中后仍需通过类别过滤，避免跨类误配。
INTENT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("开卷", "闭卷", "考试形式"), "K013"),
    (("范围", "章节", "重点", "复习"), "K014"),
    (("补考", "报名"), "K015"),
    (("缓考", "材料", "证明"), "K016"),
    (("计算器", "带纸", "带资料", "开卷"), "K017"),
    (("占比", "平时分", "总评", "分数怎么算", "分数"), "K018"),
    (("补考成绩", "成绩什么时候", "成绩公布", "成绩出来"), "K019"),
    (("复核", "成绩不对", "成绩有异议"), "K020"),
    (("调课", "换班", "换组", "课程冲突"), "K021"),
    (("延期", "迟交", "补交", "没写完"), "K022"),
    (("在读证明", "成绩单", "盖章"), "K023"),
    (("学生证", "补办"), "K024"),
    (("免修", "免听"), "K025"),
    (("转专业", "辅修", "学分认定"), "K026"),
    (("二手", "队友", "教材"), "K027"),
    (("二维码", "加群", "群"), "K028"),
    (("格式", "pdf", "docx", "命名"), "K001"),
    (("迟交", "扣分"), "K002"),
    (("重新提交", "再提交", "覆盖"), "K003"),
    (("分组", "小组"), "K004"),
    (("答案", "参考", "示例"), "K005"),
    (("打不开", "502", "白屏", "网页", "进不去"), "K006"),
    (("附件", "上传", "大小", "超过"), "K007"),
    (("登录", "登陆", "账号", "密码"), "K008"),
    (("验证码", "收不到"), "K009"),
    (("回放", "声音", "音频"), "K010"),
    (("已提交", "文件为空", "提交后"), "K011"),
    (("课件", "乱码", "下载"), "K012"),
]


class KnowledgeBase:
    """混合检索工具：类别过滤 + 关键词意图匹配 + TF-IDF 余弦相似度。

    只用问题文本建索引（答案文本较长，会稀释短查询的相似度）。
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "kb_faq.csv")
        if not self.path.exists():
            raise ToolError(f"知识库文件不存在: {self.path}")
        try:
            self.df = pd.read_csv(self.path).fillna("")
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"知识库读取失败: {e}") from e
        if self.df.empty:
            raise ToolError("知识库为空")
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True
        )
        docs = self.df["question"].tolist()
        self.matrix = self.vectorizer.fit_transform(docs)
        self.by_id = {str(r["faq_id"]): i for i, r in self.df.iterrows()}

    def _rule_ids(self, query: str, category: str | None) -> list[tuple[str, str]]:
        q = clean_text(query).lower()
        out = []
        for words, faq_id in INTENT_RULES:
            if any(w.lower() in q for w in words):
                idx = self.by_id.get(faq_id)
                if idx is None:
                    continue
                if category and str(self.df.iloc[idx]["category"]) != category:
                    continue  # 类别不一致的规则命中直接丢弃
                out.append((faq_id, words[0]))
        return out

    def search(self, query: str, category: str | None = None,
               top_k: int = 3, min_score: float = KB_MIN_SCORE) -> list[KBHit]:
        q = clean_text(query)
        if not q:
            return []
        try:
            vec = self.vectorizer.transform([q])
            sims = cosine_similarity(vec, self.matrix)[0]
            cand_idx = np.arange(len(sims))
            if category:
                mask = self.df["category"].to_numpy() == category
                cand_idx = np.where(mask)[0]

            rule_hits = self._rule_ids(q, category)
            scores: dict[int, tuple[float, str]] = {}
            for faq_id, _ in rule_hits:
                i = self.by_id[faq_id]
                scores[i] = (max(float(sims[i]), 0.55), "keyword+vector")

            for i in cand_idx:
                if sims[i] >= min_score:
                    scores.setdefault(int(i), (float(sims[i]), "vector"))

            ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)[:top_k]
            hits = []
            for i, (score, method) in ranked:
                row = self.df.iloc[i]
                hits.append(KBHit(
                    faq_id=str(row["faq_id"]), question=str(row["question"]),
                    answer=str(row["answer"]), category=str(row["category"]),
                    owner=str(row["owner"]), source=str(row["source"]),
                    score=score, method=method,
                ))
            return hits
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"知识库检索失败: {e}") from e


class TicketStore:
    """SQLite 工单库：记录每次处理结果，并维护人工复核队列。"""

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "agent_tickets.db")
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        try:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    label TEXT,
                    label_cn TEXT,
                    confidence REAL,
                    route_to TEXT,
                    priority TEXT,
                    status TEXT,
                    needs_review INTEGER,
                    review_reason TEXT,
                    reply TEXT,
                    trace_json TEXT
                )
            """)
            self.conn.commit()
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"工单库初始化失败: {e}") from e

    def create(self, record: dict) -> int:
        try:
            cur = self.conn.execute("""
                INSERT INTO tickets (created_at, raw_text, label, label_cn, confidence,
                                     route_to, priority, status, needs_review, review_reason, reply, trace_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.now().isoformat(timespec="seconds"), record["raw_text"], record["label"],
                record["label_cn"], record["confidence"], record["route_to"], record["priority"],
                record["status"], int(record["needs_review"]), record.get("review_reason", ""),
                record.get("reply", ""), record.get("trace_json", ""),
            ))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"工单写入失败: {e}") from e

    def list_reviews(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM tickets WHERE needs_review=1 AND status='pending_review' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve(self, ticket_id: int, status: str, note: str = "") -> None:
        self.conn.execute(
            "UPDATE tickets SET status=?, review_reason=? WHERE id=?", (status, note, ticket_id)
        )
        self.conn.commit()

    def stats(self) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"
        ).fetchall()
        stats = {r["status"]: r["n"] for r in rows}
        stats["total"] = sum(stats.values())
        return stats

    def close(self) -> None:
        self.conn.close()


def route_for(label: str) -> tuple[str, str]:
    """返回 (责任方中文名, 责任方代码)，未知类别转助教。"""
    return ROUTING.get(label, ROUTING["other"])
