# -*- coding: utf-8 -*-
"""端到端冒烟测试：覆盖数据、模型、Agent 的安全分支与 Web 接口。

运行：
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.agent import WorkOrderAgent
from src.config import DATA_DIR, MODEL_DIR
from src.tools import KnowledgeBase
from src.webapp import app


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = WorkOrderAgent()

    def test_data_files_and_labels(self):
        df = pd.read_csv(DATA_DIR / "tickets.csv")
        self.assertEqual(len(df), 1395)
        self.assertEqual(set(df["label"]), {"homework", "system", "exam", "admin", "other"})

    def test_model_artifact(self):
        self.assertTrue((MODEL_DIR / "classifier.joblib").exists())
        r = self.agent.process("学习通打不开，一直显示 502", persist=False, log_trace=False)
        self.assertEqual(r.label, "system")
        self.assertGreater(r.confidence, 0.5)

    def test_normal_ticket_has_trace_and_reply(self):
        r = self.agent.process("老师，作业第 3 题的卷积没听懂", persist=False, log_trace=False)
        self.assertEqual(r.label, "homework")
        self.assertGreaterEqual(len(r.steps), 6)
        self.assertTrue(r.reply)
        self.assertIn("自动答复仅供参考", r.reply)

    def test_empty_input_is_rejected(self):
        r = self.agent.process("   ", persist=False, log_trace=False)
        self.assertEqual(r.resolution, "rejected")
        self.assertEqual(r.error, "输入为空")
        self.assertTrue(r.reply)

    def test_noise_input_is_rejected(self):
        r = self.agent.process("啊啊啊啊啊啊啊啊", persist=False, log_trace=False)
        self.assertEqual(r.resolution, "rejected")

    def test_high_impact_needs_human_review(self):
        r = self.agent.process("老师，我作业没写完能不能延期", persist=False, log_trace=False)
        self.assertTrue(r.needs_review)
        self.assertEqual(r.resolution, "pending_review")
        self.assertIn("人工", r.reply)

    def test_knowledge_base_hit(self):
        kb = KnowledgeBase()
        hits = kb.search("学习通打不开", category="system")
        self.assertTrue(hits)
        self.assertEqual(hits[0].faq_id, "K006")
        self.assertGreater(hits[0].score, 0.3)

    def test_web_endpoints(self):
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        resp = client.post("/api/process", json={"text": "考试可以带计算器吗"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])
        self.assertEqual(client.get("/api/stats").status_code, 200)


if __name__ == "__main__":
    unittest.main()
