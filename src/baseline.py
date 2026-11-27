# -*- coding: utf-8 -*-
"""关键词规则基线：模拟"助教人工按关键词分流"的现有做法。

用于回答一个关键问题：引入机器学习分类器到底带来了多少提升？
规则按优先级匹配，越靠前的类别越"强"。
"""
from __future__ import annotations

from src.preprocess import clean_text

SYSTEM_WORDS = [
    "打不开", "502", "报错", "错误", "失败", "卡住", "卡死", "闪退", "白屏", "转圈",
    "登不上", "登录", "登陆", "账号", "密码", "验证码", "上传", "附件", "下载",
    "网络", "连不上", "没声音", "乱码", "崩", "加载", "提交不了", "无法提交",
    "进不去", "中断", "识别失败", "收不到", "过期", "解压失败",
]
ADMIN_WORDS = [
    "申请", "调课", "延期", "复核", "证明", "补办", "免修", "免听", "换班", "换组",
    "转专业", "学分", "休学", "申诉", "盖章", "成绩单", "辅修", "修改", "更正",
    "缓考申请", "补考申请", "提前毕业",
]
EXAM_WORDS = [
    "考试", "补考", "缓考", "考场", "成绩", "分数", "开卷", "闭卷", "题型",
    "复习范围", "平时分", "总评", "查重", "答题卡", "笔试", "机考", "期末", "期中",
]
HOMEWORK_WORDS = [
    "作业", "习题", "实验报告", "小组", "提交", "截止", "ddl", "题", "代码", "编程",
    "参考文献", "课程设计", "报告", "评分标准",
]


def rule_classify(text: str) -> str:
    """返回五类之一。规则命中顺序 = 人工分流的优先级。"""
    t = clean_text(text).lower()
    for label, words in (
        ("system", SYSTEM_WORDS),
        ("admin", ADMIN_WORDS),
        ("exam", EXAM_WORDS),
        ("homework", HOMEWORK_WORDS),
    ):
        if any(w.lower() in t for w in words):
            return label
    return "other"


def rule_confidence(text: str) -> float:
    """规则法没有概率，用"命中词数"做一个粗粒度置信度，便于阈值对比。"""
    t = clean_text(text).lower()
    hits = 0
    for words in (SYSTEM_WORDS, ADMIN_WORDS, EXAM_WORDS, HOMEWORK_WORDS):
        hits += sum(1 for w in words if w.lower() in t)
    if hits <= 0:
        return 0.3
    return min(0.5 + 0.12 * hits, 0.95)
