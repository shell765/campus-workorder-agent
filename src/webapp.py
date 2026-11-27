# -*- coding: utf-8 -*-
"""课程工单智能分类 Agent —— 本地 Web 应用（Flask）。

启动：
    python -m src.webapp
然后浏览器打开 http://127.0.0.1:8000

接口：
    POST /api/process           {"text": "..."} -> 结构化处理结果
    GET  /api/stats             工单统计
    GET  /api/reviews           待复核队列
    POST /api/reviews/<id>/resolve  {"status": "resolved"} 人工处理
"""
from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import WorkOrderAgent
from src.config import BASE_DIR, OUTPUT_DIR

WEB_DIR = BASE_DIR / "web"

app = Flask(
    __name__,
    template_folder=str(WEB_DIR),
    static_folder=str(WEB_DIR / "static"),
    static_url_path="/static",
)

_lock = threading.RLock()
_agent: WorkOrderAgent | None = None

SAMPLES = [
    "学习通打不开，一直显示 502 Bad Gateway，作业还没提交",
    "老师，作业第 3 讲的卷积公式没听懂，能不能给个例题",
    "我想申请调课，周四下午和实验课冲突了",
    "期末考试是闭卷还是开卷，可以带计算器吗",
    "老师你用的什么 IDE，看起来很好用",
    "作业提交不了，是不是系统坏了",
    "老师，我作业没写完能不能延期，最近发烧了",
    "验证码收不到，一直登不上教务系统",
    "补考什么时候报名，在哪里申请",
    "今天食堂排队好长，有人一起去吗",
]


def get_agent() -> WorkOrderAgent:
    global _agent
    if _agent is None:
        with _lock:
            if _agent is None:
                _agent = WorkOrderAgent()
    return _agent


@app.get("/")
def index():
    demo = request.args.get("demo")
    initial = None
    if demo:
        text = request.args.get("text") or SAMPLES[0]
        try:
            with _lock:
                initial = get_agent().process(text, persist=True, log_trace=True).as_dict()
        except Exception as e:  # noqa: BLE001
            initial = {"error": str(e)}
    return render_template("index.html", initial=initial)


@app.get("/api/samples")
def samples():
    return jsonify({"samples": SAMPLES})


@app.post("/api/process")
def process():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", ""))
    try:
        with _lock:
            result = get_agent().process(text, persist=True, log_trace=True)
        return jsonify({"ok": True, "result": result.as_dict()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


@app.get("/api/stats")
def stats():
    try:
        with _lock:
            s = get_agent().store.stats() if get_agent().store else {}
        return jsonify({"ok": True, "stats": s})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/reviews")
def reviews():
    try:
        with _lock:
            rows = get_agent().store.list_reviews() if get_agent().store else []
        return jsonify({"ok": True, "reviews": rows})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/reviews/<int:ticket_id>/resolve")
def resolve(ticket_id: int):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", "resolved"))
    if status not in {"resolved", "closed"}:
        return jsonify({"ok": False, "error": "status 必须是 resolved 或 closed"}), 400
    try:
        with _lock:
            store = get_agent().store
            if store is None:
                return jsonify({"ok": False, "error": "工单库不可用"}), 500
            store.resolve(ticket_id, status, note="Web 端人工复核完成")
        return jsonify({"ok": True})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": "TF-IDF + ComplementNB", "trace": str(OUTPUT_DIR / "agent_trace.jsonl")})


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"课程工单 Agent 已启动：{url}")
    if args.open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
