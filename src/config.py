# -*- coding: utf-8 -*-
"""全局配置：路径、类别定义、路由与复核规则。

所有模块共享此配置，避免类别名称和路由表在多处硬编码。
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
OUTPUT_DIR = BASE_DIR / "outputs"
REPORT_DIR = BASE_DIR / "report"

for _d in (DATA_DIR, MODEL_DIR, OUTPUT_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 五个工单类别（与课程模块表中的"新闻、评论或工单分类"对应）
LABELS = ["homework", "system", "exam", "admin", "other"]

LABEL_CN = {
    "homework": "作业疑问",
    "system": "系统故障",
    "exam": "考试咨询",
    "admin": "行政申请",
    "other": "无关/灌水",
}

# 类别 -> 责任方（路由表）
ROUTING = {
    "homework": ("课程助教", "teaching_assistant"),
    "system": ("平台技术支持", "it_support"),
    "exam": ("任课教师 / 教务", "course_teacher"),
    "admin": ("教务办公室", "academic_office"),
    "other": ("助教 / 群管理员", "group_admin"),
}

# 需要人工确认后才能对外答复或执行的高影响类别/子意图
HIGH_IMPACT_INTENTS = {
    "调课", "延期", "复核", "免修", "免听", "补考申请", "缓考申请",
    "换班", "换组", "提前毕业", "成绩修改", "成绩更正",
}

# 复核阈值（训练脚本会在验证集上做阈值搜索，并覆盖此默认值）
DEFAULT_CONFIDENCE_THRESHOLD = 0.55
# 知识库检索的最低相似度；低于该值视为"无可靠答案"，转人工
KB_MIN_SCORE = 0.32
