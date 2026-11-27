# -*- coding: utf-8 -*-
"""生成期末报告 docx（正文 3000—5000 字，图表来自真实实验结果）。

用法：
    python report/make_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import OUTPUT_DIR, REPORT_DIR

CN_FONT = "宋体"
EN_FONT = "Times New Roman"
HEAD_FONT = "黑体"


def set_run_font(run, size=11, bold=False, cn=CN_FONT, color=None):
    run.font.name = EN_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn)
    if color:
        run.font.color.rgb = color


def body(doc, text, size=11, first_indent=True, space_after=6, bold_lead=None):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(space_after)
    if first_indent:
        p.paragraph_format.first_line_indent = Pt(22)
    if bold_lead:
        r = p.add_run(bold_lead)
        set_run_font(r, size, bold=True)
    r = p.add_run(text)
    set_run_font(r, size)
    return p


def h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    set_run_font(r, 15, bold=True, cn=HEAD_FONT)
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(text)
    set_run_font(r, 12, bold=True, cn=HEAD_FONT)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.line_spacing = 1.4
    r = p.add_run(text)
    set_run_font(r, 10.5)
    return p


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    set_run_font(r, 9, color=RGBColor(0x55, 0x55, 0x55))


def table(doc, headers, rows, widths=None, font_size=9):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        set_run_font(r, font_size, bold=True)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(str(val))
            set_run_font(r, font_size)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


def add_image(doc, filename, cap, width_cm=15.6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(OUTPUT_DIR / filename), width=Cm(width_cm))
    caption(doc, cap)


def build():
    metrics = json.loads((OUTPUT_DIR / "metrics.json").read_text(encoding="utf-8"))
    agent = json.loads((OUTPUT_DIR / "agent_eval.json").read_text(encoding="utf-8"))

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.5)
    sec.top_margin = sec.bottom_margin = Cm(2.3)

    style = doc.styles["Normal"]
    style.font.name = EN_FONT
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)

    # ================= 封面 =================
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("《机器学习》课程期末项目报告")
    set_run_font(r, 16, bold=True, cn=HEAD_FONT)

    doc.add_paragraph()
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("课程工单智能分类 Agent")
    set_run_font(r, 26, bold=True, cn=HEAD_FONT)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("——基于文本分类、置信度复核与知识库检索的校园答疑工作流")
    set_run_font(r, 13, color=RGBColor(0x44, 0x44, 0x44))

    for _ in range(6):
        doc.add_paragraph()
    for label, value in [
        ("课程名称", "机器学习"),
        ("项目类型", "个人项目（可扩展为 2 人小组）"),
        ("姓名", "________________"),
        ("学号", "________________"),
        ("组员及分工", "________________"),
        ("日期", "2026 年 11 月 27 日"),
    ]:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(f"{label}：{value}")
        set_run_font(r, 12)

    doc.add_page_break()

    # ================= 摘要 =================
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("摘要")
    set_run_font(r, 14, bold=True, cn=HEAD_FONT)
    body(doc, "课程群和教学平台每天产生大量学生消息，助教需要人工判断类型并转发，重复劳动多、响应慢且难以统计。"
              "本文实现一个面向该场景的端到端 Agent：以 1395 条合成中文工单训练 TF-IDF + ComplementNB 五分类器，"
              "在含边界难例的开发集上搜索置信度阈值，并把分类、知识库检索、责任方路由、人工复核组织成可审计的 8 步工作流。"
              "在 267 条测试集（含 117 条难例）上，分类 Macro-F1 为 0.928，规则基线为 0.817；"
              "Agent 自动答复 48.7% 的工单且自动答复错误为 0，89.5% 的分类错误被复核或转人工拦截，平均处理耗时约 5.5 ms。"
              "结果表明，机器学习分类负责“分得准”，置信度复核与知识库证据负责“答得稳”，二者结合适合课程答疑这类低风险但高频的场景。")
    body(doc, "关键词：工单分类；TF-IDF；朴素贝叶斯；置信度校准；Agent 工作流；人工复核", first_indent=False)

    # ================= 一、需求与目标 =================
    h1(doc, "一、需求与目标")
    h2(doc, "1.1 场景与痛点")
    body(doc, "在“机器学习”“数据结构”等课程中，学生的问题分散在课程群、学习通讨论区、雨课堂私信和教务系统留言里。"
              "助教每天要逐条阅读几十到上百条消息，判断它属于作业、平台故障、考试安排还是行政申请，再转发给任课教师、"
              "平台技术支持或教务办公室。现有做法的不足有三点：其一，分类标准依赖个人经验，不同助教对同一条消息的判断不一致；"
              "其二，消息没有优先级和状态，群里刷屏后容易漏掉“作业提交失败”这类紧急问题；其三，处理过程无法统计，"
              "教师难以知道本周哪类问题最多、哪些 FAQ 需要补充。")
    body(doc, "我把目标收窄到一个可验证的边界：只处理“课程相关的一句话文本”，输出类别、置信度、责任方、优先级和答复依据；"
              "不自动执行调课、延期、成绩修改等操作，也不采集真实学生聊天记录。")

    h2(doc, "1.2 目标用户与成功标准")
    body(doc, "目标用户是课程助教（主要使用者）、任课教师（查看统计与复核）和平台技术支持（接收系统故障工单）。"
              "项目开始前设定四个可验证标准：（1）测试集 Macro-F1 不低于 0.85；（2）自动答复的错误率不高于 5%；"
              "（3）人工复核比例不高于 30%；（4）单条处理延迟低于 50 ms（本地 CPU）。"
              "此外，所有自动答复必须能给出知识库出处，答不出来时一律转人工，不允许“看起来很合理”的编造。")

    h2(doc, "1.3 为什么适合 Agent 化")
    body(doc, "这个任务不是一次文本分类就能完成：同一条“作业提交不了”既可能是作业问题，也可能是平台故障；"
              "“作业没写完能不能延期”即使分类正确，也不能由系统直接批准。Agent 需要先校验输入，再分类并判断置信度，"
              "然后检索有出处的答案，决定路由和优先级，遇到低置信度或高影响申请时暂停并请求人工确认。"
              "这种“模型判断 + 工具检索 + 规则约束 + 人在回路”的流程，正好对应课程要求中的 Agent 设计与机器学习组件。")

    # ================= 二、方案与系统设计 =================
    h1(doc, "二、方案与系统设计")
    h2(doc, "2.1 总体架构")
    body(doc, "系统采用浏览器/服务器结构：前端是原生 HTML/CSS/JS 页面，后端是 Flask 提供的 JSON API，"
              "核心是 WorkOrderAgent；它依赖两个工具——FAQ 知识库检索器与 SQLite 工单库，以及一个离线训练的分类模型。"
              "模型、工具、规则与人工复核的关系见图 1：模型只负责“类别与置信度”，知识库只负责“有出处的答案”，"
              "规则负责“什么时候必须停下来”，工单库负责“留下可审计的记录”。这种把模型视为更大系统中的一个组件、"
              "并用规则和人工兜住不确定性的做法，与 ML 系统技术债的讨论一致 [8]。")
    add_image(doc, "fig_workflow.png", "图 1  Agent 工作流：分类、复核、检索、路由与答复", width_cm=9.6)

    h2(doc, "2.2 八步工作流")
    body(doc, "（1）输入校验：拒绝空文本、单字符、重复噪声（如“啊啊啊啊”）和超长文本（超过 500 字截断），并给出可操作的提示；"
              "（2）文本清洗：全角转半角、去零宽字符、压缩空白，保留数字和英文（“502”“PDF”对系统类很有区分度）；"
              "（3）机器学习分类：双通道 TF-IDF + ComplementNB，输出五类概率；"
              "（4）决策：置信度低于阈值、前两类概率差小于 0.06、文本过短，或命中高影响意图（调课、延期、复核、免修等）时转人工；"
              "（5）知识库检索：先按预测类别过滤，再用意图关键词与字符 TF-IDF 余弦相似度混合排序，低于阈值视为“无可靠答案”"
              "（检索式问答的相关工作见 [2][9]）；"
              "（6）路由：按类别映射到助教、平台支持、任课教师或教务，并按“全班故障/临近截止”等线索定优先级；"
              "（7）生成答复：只用检索到的 FAQ 原文与固定模板，附条目编号、来源和相似度；"
              "（8）结论与落库：写入 SQLite，状态分为自动答复、自动归档、已路由、待复核、已拒绝五类。")

    h2(doc, "2.3 失败与安全处理")
    body(doc, "三类失败分别处理：模型或知识库不可用时，Agent 不降级为“自由生成”，而是返回“服务暂不可用，已登记转人工”；"
              "分类置信度不足或类别歧义时，工单进入复核队列，答复只说明“已转交”，不给出结论；"
              "涉及调课、延期、成绩复核、免修等申请时，即使分类置信度很高也强制人工确认，因为这类操作的影响不可逆。"
              "网页端提供复核队列，助教可以标记“已答复”或“关闭”，所有状态变化都写入数据库。")

    h2(doc, "2.4 关键设计选择与备选方案")
    body(doc, "第一，为什么不用纯大模型？纯大模型接口在无密钥、无网络的教学环境中不可复现，且容易生成不存在的截止时间；"
              "本项目的答复必须逐条对应 FAQ 条目，便于核查。第二，为什么保留关键词规则？规则在“打不开”“验证码”等强信号上准确率高、"
              "延迟低，适合作为知识库检索的补充，但它单独分类的 Macro-F1 只有 0.817，说明它无法处理“作业没写完能不能延期”这类语义边界。"
              "第三，为什么阈值不设 0.5？开发集实验显示低阈值虽然覆盖率接近 100%，但自动答复错误率超过 15%；"
              "最终用“错误自动答复记 4 分、人工复核记 1 分”的成本函数选出 0.84，把风险留给人工而不是学生。")

    # ================= 三、机器学习方法 =================
    h1(doc, "三、机器学习方法")
    h2(doc, "3.1 数据构造与划分")
    body(doc, "数据由 src/data_gen.py 合成：以 26 组意图模板、课程名/平台名/周次/题号等槽位，加上“老师好”“急”“😭”等口语前后缀生成基础样本；"
              "另外手工编写 50 组边界难例（如“作业打不开”“成绩不对”“这门课可以免听吗”），每条再用不同前后缀扩展。"
              "共 1395 条，类别分布为作业 359、系统 323、考试 282、行政 244、其他 187。难例不参与训练，全部用于开发集与测试集，"
              "以避免“用简单样本调阈值、到真实模糊输入上失控”的问题。划分见表 1。")
    table(doc, ["数据集", "基础样本", "边界难例", "合计"],
          [["训练集", 900, 0, 900],
           ["开发集", 150, 78, 228],
           ["测试集", 150, 117, 267]],
          widths=[4, 4, 4, 4])
    caption(doc, "表 1  数据划分（难例仅进入开发集/测试集）")

    h2(doc, "3.2 特征与模型")
    body(doc, "中文短文本的字面变体多，单一词特征容易因错别字（“做业”“登陆”）失效，因此使用双通道 TF-IDF："
              "字符 n-gram（2–4，char_wb）捕捉局部字串，词 n-gram（jieba 分词后 1–2）提供可解释的关键词证据；"
              "两个通道都使用 sublinear TF 抑制高频词，最大特征数分别为 60000 和 30000。"
              "TF-IDF 与子线性词频的原理见 [2]，向量化实现见 [1][6]，中文分词使用 jieba [4]。")
    body(doc, "分类器比较了三种课程常见模型：ComplementNB（alpha=0.4）、线性 SVM（C=1.0，class_weight=balanced，用 3 折 sigmoid 校准输出概率）、"
              "逻辑回归（C=4.0，balanced）。选择 ComplementNB 的理由是：工单文本高维稀疏、类别先验不均，NB 在小样本上稳定且训练极快；"
              "线性 SVM 需要额外校准才能给出可信概率 [3][7]，逻辑回归虽然可解释但收敛更慢。开发集结果见表 2，NB 的 Macro-F1 最高。"
              "模型实现与评估指标见 [1]，朴素贝叶斯的教材推导见 [10]。")
    table(doc, ["模型", "开发集准确率", "开发集 Macro-F1"],
          [["ComplementNB", "0.8991", "0.9010"],
           ["LinearSVC（校准）", "0.8904", "0.8870"],
           ["LogisticRegression", "0.8947", "0.8913"]],
          widths=[6, 5, 5])
    caption(doc, "表 2  开发集模型对比（相同特征与划分，随机种子 42）")

    h2(doc, "3.3 置信度阈值")
    body(doc, "分类器输出概率并不等于“可以自动处理”的把握：NB 的概率偏极端，错分时也可能给出 0.9 以上。"
              "因此我在开发集上扫描 0.30–0.90 的阈值，计算每个阈值下的自动处理覆盖率与错误率，并用运行成本函数选点："
              "每 100 条工单中，错误自动答复计 4 分（要返工并损害信任），转人工复核计 1 分（助教确认成本）。"
              "最终阈值 0.84 对应开发集自动覆盖率 86.4%、自动错误率 5.6%，成本最低（图 2）。"
              "该阈值在测试集上把自动答复率压到 48.7%，但把自动答复错误压到 0。"
              "NB 概率偏极端、不能直接当作置信度的现象，与概率校准研究中的结论一致 [7]。")
    add_image(doc, "fig_threshold.png", "图 2  开发集上的置信度阈值与自动处理风险权衡", width_cm=14.5)

    h2(doc, "3.4 测试结果与特征消融")
    body(doc, "最终模型（train+dev 重训，测试集只评一次）的准确率 0.9288、Macro-F1 0.9275，明显高于规则基线的 0.8277 / 0.8174，"
              "提升约 11 个百分点。各类别指标见表 3，混淆矩阵见图 3：系统类召回最高（0.951），行政类精确率 1.000 但召回 0.843，"
              "说明“延期/复核”类申请容易被相邻的考试类吸走；作业与考试之间的边界错误最多（作业→考试 4 条、考试→作业 1 条）。"
              "难例子集 Macro-F1 为 0.8384，而基础子集为 1.000——后者说明模板分布高度重合，不能当作泛化证据，"
              "这也是本文只把难例子集作为主要分析对象的原因。")
    table(doc, ["类别", "Precision", "Recall", "F1", "支持数"],
          [["作业疑问", "0.952", "0.922", "0.937", 64],
           ["系统故障", "0.983", "0.951", "0.967", 61],
           ["考试咨询", "0.852", "0.945", "0.897", 55],
           ["行政申请", "1.000", "0.843", "0.915", 51],
           ["无关/灌水", "0.857", "1.000", "0.923", 36]],
          widths=[4.4, 3.4, 3.2, 3.2, 3])
    caption(doc, "表 3  测试集各类别指标（267 条，含 117 条难例）")
    add_image(doc, "fig_confusion_matrix.png", "图 3  测试集混淆矩阵：错误集中在作业/考试、行政/考试的语义边界", width_cm=12.2)

    body(doc, "特征通道消融显示了双通道的必要性：仅字符 2–4 gram 的 Macro-F1 为 0.9191，仅 jieba 词 1–2 gram 为 0.9209，"
              "两者合并为 0.9275。字符通道对错别字和无标点输入更稳，词通道则让“调课”“缓考”“验证码”等关键词获得更高权重；"
              "合并后的提升不大，但错误类型更集中，便于后续针对性补数据。")

    # ================= 四、Skills 与组件复用 =================
    h1(doc, "四、Skills 与组件复用")
    body(doc, "本项目复用了六个开源组件，均通过 pip 安装且未修改源码，清单见表 4。选择标准是：组件必须能解释输入输出、"
              "许可证允许教学使用、且在本机离线可运行。完整清单、来源链接与许可证见附录 B。")
    table(doc, ["组件", "版本", "许可证", "用途"],
          [["scikit-learn", "1.9.1", "BSD-3-Clause", "TF-IDF、NB/SVM/LR、评估指标"],
           ["jieba", "0.42.1", "MIT", "中文分词"],
           ["Flask", "3.1.3", "BSD-3-Clause", "Web API 与页面服务"],
           ["pandas / numpy", "3.1.1 / 2.5.5", "BSD-3-Clause", "数据处理与数值计算"],
           ["matplotlib", "3.11.2", "PSF/BSD", "实验图表"],
           ["python-docx", "1.2.0", "MIT", "报告生成"]],
          widths=[4, 3.2, 3.6, 5.6], font_size=8.5)
    caption(doc, "表 4  主要复用组件（版本以本机安装为准）")

    h2(doc, "4.1 深入分析：scikit-learn")
    body(doc, "它解决的是“文本向量化 + 概率分类 + 指标计算”这一子任务。输入是文本列表与标签列表，输出是类别、五维概率和 P/R/F1。"
              "限制有三点：TfidfVectorizer 的 tokenizer 必须可序列化，否则模型无法保存；LinearSVC 不直接输出概率，必须额外校准，训练成本约增加 3 倍；"
              "ComplementNB 的概率校准较差，必须单独做阈值实验。我的核验方式是：阅读官方文档确认 char_wb 与 sublinear_tf 的行为；"
              "在相同划分上重跑三个模型并记录开发集指标；把保存后的 Pipeline 重新加载，逐条比对预测结果；最后用混淆矩阵检查错误类型是否符合预期。")
    h2(doc, "4.2 集成工作：Flask 与前端")
    body(doc, "Flask 负责把 Agent 暴露成网页可调用的接口 [5]。集成中遇到两个实际问题：其一，服务层用普通 Lock 包住 Agent 初始化，"
              "而初始化内部又申请同一把锁，导致首次请求死锁、页面一直转圈；改为可重入锁 RLock 后恢复。其二，浏览器截图工具在页面加载完成时"
              "尚未等到前端 fetch 返回，截图是空的；于是增加服务端预跑模式（/?demo=1 直接渲染结果），同时把前端首次渲染改为同步执行，"
              "使无 JS 环境也能看到完整结果。接口层还统一了错误码：参数错误返回 400，工具/模型异常返回 500 且不泄露堆栈。")
    body(doc, "复用边界也需要说明：项目没有使用 LangChain、AutoGen 等 Agent 框架，工作流、状态机、trace 与复核队列都是自行实现的；"
              "没有调用通用大模型，答复只来自 FAQ 原文；没有使用真实学生数据。这样做的代价是表达自然度有限，好处是每个结论都能追溯到代码和条目。")

    # ================= 五、实验设计与结果 =================
    h1(doc, "五、实验设计与结果")
    h2(doc, "5.1 测试设计与指标")
    body(doc, "测试集 267 条，来源与训练集相同（模板 + 难例），但难例占比 43.8%，高于自然分布，目的是暴露边界错误而不是刷高准确率。"
              "评价指标包括：分类准确率与 Macro-F1；Agent 层面的自动答复率、复核率、自动答复错误率（逃逸错误/自动答复数）、"
              "错误捕获率（进入复核或转人工的错误/全部错误）、知识库命中率与平均时延。所有指标由 src/evaluate.py 一次运行生成，"
              "预测明细保存在 outputs/agent_test_results.csv，可逐条复核。")
    add_image(doc, "fig_model_comparison.png", "图 4  规则基线与三个机器学习模型在含难例测试集上的对比", width_cm=13.6)

    h2(doc, "5.2 Agent 端到端结果")
    body(doc, "分类准确率 0.9288、Macro-F1 0.9275；自动答复率 48.7%（其中实质答复 37.8%，其余为“无关灌水”自动归档），"
              "转人工路由 29.2%，人工复核 22.1%。自动答复的 130 条中错误为 0；全部 19 个分类错误中，17 个被复核或转人工拦截，"
              "错误捕获率 89.5%，剩余 2 个错误因“无匹配 FAQ”被路由到人工，也没有形成错误答复。"
              "知识库命中率 47.2%（126/267），命中时的平均最高相似度 0.582；单条平均处理耗时 5.5 ms（首次调用因加载 jieba 词典约 450–600 ms，已单独说明）。")

    h2(doc, "5.3 消融实验")
    body(doc, "表 5 在同一测试集上比较四个版本。完整 Agent 的自动答复错误率为 0，但只覆盖 48.7%；去掉置信度复核后覆盖率升到 100%，"
              "错误率升到 7.1%——这正是“多答多错”的代价；纯关键词规则全自动的错误率高达 17.2%，说明规则无法替代语义分类；"
              "去掉知识库后，只有“无关灌水”能被自动归档（10.9%），其余工单都只能转人工，说明检索工具是“能答”的必要条件。")
    table(doc, ["版本", "自动答复率", "自动答复错误率", "Macro-F1", "知识库命中率"],
          [["完整 Agent", "48.7%", "0.0%", "0.928", "47.2%"],
           ["去掉置信度复核", "100%", "7.1%", "0.928", "47.2%"],
           ["纯关键词规则", "100%", "17.2%", "0.817", "47.2%"],
           ["无知识库", "10.9%", "0.0%", "0.928", "0%"]],
          widths=[5.2, 3.4, 3.8, 3.2, 3.2], font_size=8.5)
    caption(doc, "表 5  消融实验：复核策略与知识库各自的贡献")
    add_image(doc, "fig_ablation.png", "图 5  消融实验：自动答复率与自动答复错误率的权衡", width_cm=13.8)

    h2(doc, "5.4 错误分析与失败处理")
    body(doc, "19 个错误里最典型的三类是：（1）“课程和考试冲突了怎么办”被分成考试咨询，真实标签是行政申请——句子同时含“课程”“考试”，"
              "但诉求是行政协调；（2）“这门课可以免听吗”被分成无关/灌水，因为“免听”在训练模板中出现少，且口语短句缺少“申请”这个强信号；"
              "（3）“作业在哪提交”被分成作业疑问，真实标签是系统故障（问的是平台入口）。这些错误的共同点是短、省略、双意图，"
              "单标签分类本身就有歧义。改进方向不是继续调模型，而是引入多标签/意图槽位，或在低置信度时直接要求用户补充信息。")
    body(doc, "异常输入测试覆盖空文本、单字符、重复噪声、超长文本和纯英文五类，Agent 均返回可理解的中文提示且不写坏数据（表 6）。"
              "另外，当知识库文件缺失或 SQLite 写入失败时，Agent 会把 degraded 标记写入结果并提示人工处理，而不是假装成功。")
    table(doc, ["输入", "处理结果", "是否安全降级"],
          [["空文本", "提示“没有收到有效内容”", "是"],
           ["单字符“？”", "提示“信息太少，无法判断”", "是"],
           ["重复噪声", "识别为无意义输入并拒绝", "是"],
           ["超长文本", "截断到 500 字后正常分类", "是"],
           ["纯英文", "分类并给出转人工提示", "是"]],
          widths=[4.5, 7.5, 3.5], font_size=8.5)
    caption(doc, "表 6  异常输入与降级行为")

    h2(doc, "5.5 完整运行演示")
    body(doc, "图 6 是网页原型的真实截图：输入“学习通打不开，一直显示 502 Bad Gateway，作业还没提交”，"
              "Agent 判定为系统故障（置信度 1.00），路由到平台技术支持，命中 FAQ K006 并给出三条排查建议，"
              "同时展示 8 步轨迹与结构化 JSON。图 7 是“作业没写完能不能延期”的处理：分类为行政申请（0.987），"
              "但因命中高影响意图“延期”，状态变为“待人工复核”，答复明确说明不会代替教师做决定。两张截图均可通过 "
              "`/?demo=1` 与 `/?demo=1&text=...` 复现。")
    doc.add_page_break()
    add_image(doc, "demo_web.png", "图 6  网页原型：系统故障工单的自动分类、检索与答复", width_cm=14.2)
    add_image(doc, "demo_web_review.png", "图 7  网页原型：高影响申请进入人工复核队列", width_cm=14.2)

    # ================= 六、讨论与改进 =================
    h1(doc, "六、讨论与改进")
    body(doc, "从真实使用价值看，这个 Agent 最直接的作用是把“读消息、贴标签、转给谁”这三步自动化，并用置信度把不确定的工单集中到一个小队列。"
              "对助教而言，22.1% 的复核量比逐条阅读全部消息更可控；对教师而言，类别分布和错误案例可以反哺 FAQ 与课程公告；"
              "对学生而言，系统故障、考试安排这类标准化问题能得到秒级回复。")
    body(doc, "但必须承认三个边界。第一，数据是合成的，模板重合使基础测试集达到 1.000，这个数字没有泛化意义；"
              "真正有价值的是 0.838 的难例 F1 和逐条错误分析，换到真实校园数据上必须重新标注、重新调阈值。"
              "第二，知识库只有 28 条，覆盖率 47.2%，大量具体问题仍需人工；这不是模型问题，而是内容运营问题。"
              "第三，置信度只来自 NB 概率，虽然阈值实验显示有效，但没有做温度缩放或保形预测，概率含义仍不严格。")
    body(doc, "后续改进按优先级排列：（1）与助教合作采集两周脱敏真实消息，做主动学习，优先标注低置信度样本；"
              "（2）把五分类扩展为“类别 + 意图槽位”的多任务输出，显式处理“作业 + 延期”这类双意图；"
              "（3）用保形预测（conformal prediction）替代手工阈值，给出有覆盖保证的复核集合；"
              "（4）在允许调用大模型的部署环境中，用检索增强生成改写答复，但强制每个断言附带 FAQ 编号，并保留模板作为兜底；"
              "（5）增加登录、角色权限、操作审计与脱敏日志，才可能从教学原型走向真实院系使用。")

    # ================= 参考文献 =================
    h1(doc, "参考文献")
    refs = [
        "[1] Pedregosa F, Varoquaux G, Gramfort A, et al. Scikit-learn: Machine Learning in Python[J]. Journal of Machine Learning Research, 2011, 12: 2825-2830. https://jmlr.org/papers/v12/pedregosa11a.html",
        "[2] Manning C D, Raghavan P, Schütze H. Introduction to Information Retrieval[M]. Cambridge University Press, 2008: ch.13. https://nlp.stanford.edu/IR-book/",
        "[3] Cortes C, Vapnik V. Support-vector networks[J]. Machine Learning, 1995, 20(3): 273-297. https://doi.org/10.1007/BF00994018",
        "[4] jieba 中文分词项目. https://github.com/fxsjy/jieba（MIT License，版本 0.42.1）",
        "[5] Flask Documentation. https://flask.palletsprojects.com/（BSD-3-Clause，版本 3.1.3）",
        "[6] scikit-learn developers. TfidfVectorizer 文档. https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html",
        "[7] Guo C, Pleiss G, Sun Y, Weinberger K Q. On Calibration of Modern Neural Networks[C]. ICML 2017. https://arxiv.org/abs/1706.04599",
        "[8] Sculley D, Holt G, Golovin D, et al. Hidden Technical Debt in Machine Learning Systems[C]. NeurIPS 2015. https://papers.nips.cc/paper/5656",
        "[9] Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks[C]. NeurIPS 2020. https://arxiv.org/abs/2005.11401",
        "[10] 周志华. 机器学习[M]. 北京: 清华大学出版社, 2016.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.3
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(ref)
        set_run_font(r, 9.5)

    # ================= 附录 =================
    h1(doc, "附录 A  代码仓库与运行说明（对应提交材料②）")
    body(doc, "代码仓库地址：https://github.com/shell765/campus-workorder-agent（公开仓库，含 README、依赖、运行步骤与测试）",
         first_indent=False, size=10)
    h2(doc, "A.1 仓库结构")
    body(doc, "README.md（项目说明、快速开始、接口、指标与隐私边界）；requirements.txt（固定版本依赖）；run_web.bat（Windows 一键启动）；"
              "src/（数据生成、预处理、训练、工具、Agent、评估、网页服务）；web/（原生 HTML/CSS/JS）；"
              "data/（合成工单、FAQ、12 条测试样例）；models/（训练好的 classifier.joblib）；outputs/（指标、图表、截图）；"
              "tests/（8 个冒烟测试）；docs/（验收对照表、演示说明、组件清单）；report/（报告 DOCX 与 PDF）。",
         first_indent=False, size=9.5)
    h2(doc, "A.2 依赖与版本")
    body(doc, "Python 3.10+（验证环境 3.12.6）。核心依赖：scikit-learn 1.9.1、jieba 0.42.1、Flask 3.1.3、pandas 3.1.1、numpy 2.5.5、"
              "matplotlib 3.11.2、python-docx 1.2.0、Pillow 13.0.0；完整清单与版本锁定见 requirements.txt。全部依赖可离线安装，无密钥、无外部 API。",
         first_indent=False, size=9.5)
    h2(doc, "A.3 运行步骤")
    body(doc, "pip install -r requirements.txt；python -m src.data_gen --seed 42（生成 1395 条数据与 FAQ）；"
              "python -m src.train（训练、选阈值、测试）；python -m src.evaluate（端到端评估与消融）；"
              "python -m src.make_figures（生成图表）；python -m src.webapp --open（启动网页，默认 http://127.0.0.1:8000）。"
              "Windows 也可直接双击 run_web.bat；仓库已附模型，只看演示可跳过数据生成与训练。",
         first_indent=False, size=9.5)
    h2(doc, "A.4 自检与预期结果")
    body(doc, "python -m unittest discover -s tests -v 应输出 8 个 OK（约 0.6 秒）；测试覆盖数据规模与标签、模型加载、正常工单轨迹、"
              "空输入/噪声拒绝、高影响申请复核、知识库命中与 Web 接口。评估完成后 outputs/metrics.json 中 Macro-F1 应为 0.9275，"
              "outputs/agent_eval.json 中自动答复错误数应为 0。",
         first_indent=False, size=9.5)

    h1(doc, "附录 B  演示材料（对应提交材料③）")
    body(doc, "本地演示地址：http://127.0.0.1:8000（启动 python -m src.webapp --open 后访问）。"
              "在线演示地址：____________________________________（如部署到 Hugging Face Spaces / Render，提交前填写）。"
              "以下截图均为本机真实运行结果，可用 /?demo=1 服务端预跑模式复现，不依赖浏览器异步请求。",
         first_indent=False, size=9.5)
    doc.add_page_break()
    h2(doc, "B.1 场景一：系统故障自动答复")
    body(doc, "输入“学习通打不开，一直显示 502 Bad Gateway，作业还没提交”。预期：类别系统故障、置信度高于 0.84、责任方平台技术支持、"
              "优先级高；答复引用 FAQ K006，并显示来源与相似度；8 步轨迹的结论状态为 auto_answered。",
         first_indent=False, size=9.5)
    add_image(doc, "demo_web.png", "图 B-1  系统故障工单：分类、知识库引用、8 步轨迹与结构化输出", width_cm=15.2)
    doc.add_page_break()
    h2(doc, "B.2 场景二：高影响申请强制人工复核")
    body(doc, "输入“老师，我作业没写完能不能延期，最近发烧了”。预期：即使分类置信度很高，也因命中高影响意图“延期”进入 pending_review；"
              "答复只说明已转交，不承诺结果；复核队列出现该工单，可标记已答复或关闭。",
         first_indent=False, size=9.5)
    add_image(doc, "demo_web_review.png", "图 B-2  延期申请：置信度 98.7% 仍进入人工复核，体现“人在回路”", width_cm=15.2)
    h2(doc, "B.3 演示讲解要点")
    bullet(doc, "模型只负责“类别 + 置信度”，不负责最终决定；")
    bullet(doc, "知识库只返回有出处的原文，检索不到就转人工，避免编造政策；")
    bullet(doc, "调课、延期、成绩复核等高影响申请，置信度再高也强制人工确认；")
    bullet(doc, "所有结论写入 SQLite，可在复核队列中追踪状态变化。")

    doc.add_page_break()
    h1(doc, "附录 C  复用组件清单与许可证/来源（对应提交材料④）")
    body(doc, "全部组件通过 pip 安装，未修改源码；许可证允许教学与开源使用。版本以本机安装为准，来源与核验记录同步保存在 docs/复用组件清单.md。",
         first_indent=False, size=9.5)
    table(doc, ["组件", "版本", "许可证", "来源", "用途与修改"],
          [["scikit-learn", "1.9.1", "BSD-3-Clause", "scikit-learn.org", "TF-IDF、NB/SVM/LR、评估；组合双通道特征"],
           ["jieba", "0.42.1", "MIT", "github.com/fxsjy/jieba", "中文分词；注册课程领域词"],
           ["Flask", "3.1.3", "BSD-3-Clause", "flask.palletsprojects.com", "Web 服务与 API；自建路由、RLock"],
           ["pandas", "3.1.1", "BSD-3-Clause", "pandas.pydata.org", "CSV 读取、分组统计、导出"],
           ["numpy", "2.5.5", "BSD-3-Clause", "numpy.org", "概率数组、阈值扫描、时延统计"],
           ["matplotlib", "3.11.2", "PSF/BSD", "matplotlib.org", "混淆矩阵、阈值曲线、消融图"],
           ["python-docx", "1.2.0", "MIT", "github.com/python-openxml/python-docx", "生成报告 DOCX"],
           ["Pillow", "13.0.0", "MIT-CMU", "python-pillow.org", "演示截图读取/保存"],
           ["Chrome headless", "本机版本", "专有（仅本机）", "本机安装", "仅渲染截图，不随项目分发"]],
          widths=[3.0, 2.1, 3.0, 4.6, 4.7], font_size=7.6)
    caption(doc, "表 C1  复用组件、版本、许可证与用途")
    body(doc, "来源链接：scikit-learn https://scikit-learn.org；jieba https://github.com/fxsjy/jieba；Flask https://flask.palletsprojects.com；"
              "pandas https://pandas.pydata.org；numpy https://numpy.org；matplotlib https://matplotlib.org；"
              "python-docx https://github.com/python-openxml/python-docx；Pillow https://python-pillow.org。",
         first_indent=False, size=8)
    body(doc, "行为核验：（1）在相同 train/dev 划分上重跑三个模型，记录开发集 Macro-F1（0.9010 / 0.8870 / 0.8913），确认模型选择不是偶然；"
              "（2）joblib 保存后重新加载，逐条比对预测结果一致；（3）Flask 接口用 curl 与 8 个冒烟测试核对状态码与 JSON 结构；"
              "（4）并发请求复测 RLock 修复，确认不再死锁；（5）逐项核对官网或仓库 LICENSE 文件，确认许可证与表中一致。",
         first_indent=False, size=9.2)

    doc.add_page_break()
    h1(doc, "附录 D  主要代码与测试样例")
    body(doc, "核心文件：src/agent.py（八步工作流、置信度决策、复核状态）、src/train.py（双通道特征、模型对比、阈值搜索）、"
              "src/tools.py（FAQ 混合检索、SQLite 工单库）、src/evaluate.py（端到端评估与消融）、src/webapp.py（Flask API 与预跑模式）、"
              "web/（原生前端）。",
         first_indent=False, size=9.5)
    table(doc, ["编号", "测试输入（节选）", "期望类别", "期望结论"],
          [["S01", "学习通打不开，一直显示 502", "system", "auto_answered"],
           ["S02", "作业第 3 题卷积没听懂，能给例题吗", "homework", "routed"],
           ["S03", "期末考试开卷还是闭卷，能带计算器吗", "exam", "auto_answered"],
           ["S04", "想申请调课，和实验课冲突", "admin", "pending_review"],
           ["S05", "作业没写完能不能延期", "admin", "pending_review"],
           ["S06", "老师你用的什么 IDE", "other", "auto_closed"],
           ["S07", "作业提交不了，一直转圈", "system", "routed"],
           ["S08", "验证码收不到，登不上教务系统", "system", "auto_answered"],
           ["S09", "啊啊啊啊啊啊啊啊", "other", "rejected"],
           ["S10", "（空输入）", "other", "rejected"],
           ["S11", "课程和考试冲突了怎么办", "exam", "routed"],
           ["S12", "这门课可以免听吗，有医院证明", "admin", "pending_review"]],
          widths=[2.0, 8.2, 3.0, 3.6], font_size=8.2)
    caption(doc, "表 D1  data/test_samples.csv 的 12 条测试样例（S11 为已知边界错误，靠转人工兜底）")
    body(doc, "完整样例与说明见 data/test_samples.csv；tests/test_smoke.py 另含 8 个自动化用例，覆盖数据规模、模型加载、正常轨迹、"
              "空输入/噪声拒绝、高影响复核、知识库命中与 Web 接口。运行 python -m unittest discover -s tests -v 可复现。",
         first_indent=False, size=9.5)

    out = REPORT_DIR / "2026-机器学习期末报告-课程工单智能分类Agent.docx"
    doc.save(out)

    # 统计中文字符数（仅正文段落）
    count = 0
    for p in doc.paragraphs:
        count += sum(1 for ch in p.text if "\u4e00" <= ch <= "\u9fff")
    print("report saved:", out)
    print("中文字符数（含标题/附录，不含图表内文字）：", count)


if __name__ == "__main__":
    build()


