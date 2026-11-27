# -*- coding: utf-8 -*-
"""数据预处理：清洗、分词、文本规范化。

注意：训练与推理必须使用同一套清洗逻辑，否则会造成特征漂移。
"""
from __future__ import annotations

import re
import unicodedata

import jieba

# 这些词在多个类别中都会出现（如"提交""老师"），保留但由模型自行学习权重
JIEBA_USER_WORDS = ["学习通", "雨课堂", "教务系统", "课程回放", "作业延期", "成绩复核", "免修", "缓考", "补考"]


def clean_text(text: str) -> str:
    """全角转半角、去控制字符、压缩空白。保留标点（字符 n-gram 需要）。"""
    if text is None:
        return ""
    text = str(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def jieba_tokenize(text: str) -> list[str]:
    for w in JIEBA_USER_WORDS:
        jieba.add_word(w)
    tokens = [t.strip() for t in jieba.lcut(clean_text(text)) if t.strip()]
    # 去掉纯标点和单字空白，保留数字/英文（如 502、PDF 对系统类很有区分度）
    return [t for t in tokens if re.search(r"[\w\u4e00-\u9fff]", t)]
