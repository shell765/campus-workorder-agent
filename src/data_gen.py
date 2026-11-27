# -*- coding: utf-8 -*-
"""构造课程工单数据集与 FAQ 知识库（纯合成数据）。

设计说明：
1. 基础样本由"意图模板 + 槽位填充 + 口语前后缀"生成，覆盖 5 个类别；
2. 额外构造一批"边界难例"（如"作业打不开""作业没写完能不能延期"），
   全部放入测试集，用于检验系统在真实模糊输入上的表现；
3. 不采集任何真实学生信息，因此可公开复现；
4. 少量随机错别字/无标点输入，模拟聊天窗口里的真实输入习惯。

用法：
    python -m src.data_gen --seed 42
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from src.config import DATA_DIR, LABEL_CN, LABELS

COURSES = ["机器学习", "数据结构", "计算机网络", "操作系统", "概率论", "大学英语", "体育", "数据库原理"]
PLATFORMS = ["学习通", "雨课堂", "中国大学MOOC", "教务系统", "课程网站", "学校VPN", "云盘"]
LANGS = ["Python", "C++", "Java", "MATLAB"]
PARTS = ["数据分析", "实验结论", "需求分析", "模型评估", "参考文献", "结果讨论"]
CONCEPTS = ["动态规划", "卷积", "梯度下降", "快速排序", "死锁", "TCP 三次握手", "特征选择", "交叉验证"]

PREFIXES = ["", "", "", "老师好，", "助教你好，", "打扰一下，", "请问", "想问下", "救命！", "老师，"]
SUFFIXES = ["", "", "", "，谢谢！", "，急！", "😭", "，在线等", "，麻烦了", "！"]

BASE_TEMPLATES = {
    "homework": [
        "《{course}》第{week}周的作业第{num}题不会做，能不能提示一下思路",
        "{course}作业要求用{lang}提交还是手写拍照",
        "作业截止时间是不是第{week}周周五晚上，我记不清了",
        "实验报告里的{part}部分要写多少字",
        "小组作业的分工表在哪里下载",
        "上次作业少交了一道题会不会扣分",
        "编程题{num}提交后显示编译错误，但本地能跑",
        "{course}的课后习题第{num}题，{concept}那块没听懂",
        "作业提交成 PDF 还是 docx，命名格式有要求吗",
        "老师，作业迟交一天扣多少分",
        "论文报告的参考文献格式用 APA 还是 GB/T 7714",
        "这道{concept}的题我推导不出来，能给个示例吗",
        "作业里要求画流程图，用 Visio 还是 ProcessOn",
        "第{num}题的实验数据在哪里下载",
        "作业评分标准里{part}占多少分",
        "老师，作业提交后还可以重新提交吗",
        "课程设计选题可以选{concept}方向吗",
        "作业的代码需要写注释吗",
        "习题第{num}题，为什么{concept}的结果是这样",
        "{course}作业的第{num}题，题目里的数据单位是 MB 还是 GB",
        "老师，小组作业的提交入口在哪",
        "实验报告需要附上源代码吗",
        "作业要求里说的{concept}实验，具体要做几组对比",
        "老师，这次作业的难度是不是比上次高很多",
        "编程作业的输入输出格式有没有样例",
        "作业里的{part}需要画图吗",
    ],
    "system": [
        "{platform}打不开，一直显示 502 Bad Gateway",
        "上传作业附件失败，提示文件超过大小限制",
        "{platform}的视频卡住不动，换了浏览器也不行",
        "登录{platform}提示账号不存在，学号是2023xxxx",
        "提交作业按钮点了没反应，页面一直在转圈",
        "手机 APP 收不到课程通知，权限都开了",
        "在线考试人脸识别一直失败，提示活体检测不通过",
        "课程回放没有声音，其他视频正常",
        "{platform}验证码收不到，手机号是联通",
        "课件下载下来是乱码，PDF 打不开",
        "选课系统进不去，提示会话已过期",
        "云盘里的实验数据压缩包解压失败",
        "课程群二维码过期了，扫不进去",
        "直播课听不到老师声音，但我这边麦克风正常",
        "提交的作业显示已提交，但文件列表是空的",
        "校园网连不上，{platform}一直转圈",
        "{platform}突然白屏，刷新也没用",
        "作业附件上传到一半就中断，试了三次",
        "登录时提示密码错误，但我没改过密码",
        "成绩查询页面显示暂无数据",
        "{platform}的讨论区发帖一直失败",
        "老师，课程直播进不去，提示房间不存在",
        "在{platform}看视频时进度条不能拖动",
        "作业文件下载后打不开，提示文件已损坏",
        "手机端{platform}闪退，重装也没用",
        "教务系统查成绩时页面一直加载中",
    ],
    "exam": [
        "期末考试是闭卷还是开卷",
        "期中考试范围包括第几章",
        "补考什么时候报名，在哪里申请",
        "考试可以带计算器吗",
        "期末成绩占比多少，平时分怎么算",
        "考场安排在哪个教学楼",
        "缓考需要提交什么材料",
        "考试时间和另一门课冲突了怎么办",
        "期末考试题型有哪些，有没有选择题",
        "平时测验缺考一次会影响总评吗",
        "{course}的考试重点能不能划一下",
        "补考成绩什么时候公布",
        "开卷考试可以带打印资料吗",
        "考试地点在哪，几点开始",
        "期末总评不及格是不是直接重修",
        "查重报告需要在考试前提交吗",
        "期中考试成绩在哪里查",
        "考试可以申请线上吗",
        "缓考申请截止到什么时候",
        "补考难度和正考一样吗",
        "老师，期末考试的答题卡要涂学号吗",
        "平时分包括哪些部分",
        "考试可以提前交卷吗",
        "期末考试的复习范围是全部章节吗",
        "{course}的考试有编程题吗",
        "总评成绩什么时候能在系统里查到",
    ],
    "admin": [
        "我想申请调课，周四下午和实验课冲突",
        "需要开在读证明，去哪里办，多久能拿到",
        "可以申请作业延期吗，我生病住院了",
        "想换到另一个班，还有名额吗",
        "成绩有异议，想申请复核",
        "补考/重修流程是什么，要交费吗",
        "学生证丢了怎么补办",
        "想申请体育免修，有医院证明",
        "小组作业队友不干活，能不能申请换组",
        "想申请缓考，需要哪些手续",
        "学分认定怎么申请，交换课程能转学分吗",
        "想申请课程免听，直接参加考试可以吗",
        "教室申请怎么借，社团活动要用",
        "想开成绩单，保研要用，盖章找谁",
        "辅修报名什么时候开始",
        "申请休学需要什么材料",
        "想改培养方案里的选修课，找谁签字",
        "考试违纪申诉流程是什么",
        "想申请提前毕业，条件是什么",
        "课程冲突需要填哪张表",
        "老师，我想申请转专业，流程是什么",
        "想申请创新创业学分，需要什么证明",
        "交换生学分转换找哪个部门",
        "想申请助学金，材料交给谁",
        "学籍信息有误，怎么修改",
        "想申请课程替代，之前修过的课能抵吗",
    ],
    "other": [
        "老师你用的什么 IDE，看起来很好用",
        "这门课有意思吗，值得选吗",
        "求推荐机器学习的入门书",
        "群里有二手教材卖吗",
        "今天食堂排队好长",
        "老师辛苦了，教师节快乐",
        "有没有课程群二维码",
        "想找队友一起做项目，有人吗",
        "老师，你觉得{concept}以后工作用得上吗",
        "推荐一下上海周末能去的地方",
        "这套 PPT 模板挺好看的，哪里下的",
        "有人一起打球吗",
        "今天下雨，大家记得带伞",
        "这个课的给分高不高",
        "求个课程表模板",
        "老师声音好好听",
        "有人出二手显示器吗",
        "图书馆座位怎么预约",
        "最近有什么比赛可以参加",
        "想转专业，有经验的同学吗",
        "老师，你平时用什么笔记软件",
        "大家寒假都回家吗",
        "食堂哪个窗口好吃",
        "有没有人拼单买咖啡",
        "这门课作业多不多，想摸个底",
        "老师，您上课的 PPT 会发群里吗",
    ],
}

# 边界难例：短文本、双意图、口语省略。全部进入测试集。
HARD_CASES = [
    ("作业打不开", "system"),
    ("作业提交不了", "system"),
    ("作业提交不了，是不是系统坏了", "system"),
    ("附件传不上去", "system"),
    ("验证码收不到，登不上", "system"),
    ("账号被锁了", "system"),
    ("系统崩了", "system"),
    ("卡死了", "system"),
    ("视频看不了", "system"),
    ("PPT 在哪下载", "system"),
    ("作业在哪提交", "system"),
    ("提交的作业老师收到了吗", "homework"),
    ("作业评分标准是什么", "homework"),
    ("作业答案在哪", "homework"),
    ("老师这道题不会", "homework"),
    ("小组作业怎么分组", "homework"),
    ("小组作业队友联系不上", "homework"),
    ("作业交错了怎么办", "homework"),
    ("作业可以用中文写吗", "homework"),
    ("ddl 是几号", "homework"),
    ("作业是周五交吗", "homework"),
    ("考试时间能改吗", "admin"),
    ("成绩什么时候出", "exam"),
    ("补考成绩什么时候公布", "exam"),
    ("期末考什么", "exam"),
    ("分数怎么算", "exam"),
    ("考试难不难", "exam"),
    ("有没有题库", "exam"),
    ("考试能带纸吗", "exam"),
    ("机考还是笔试", "exam"),
    ("缓考算挂科吗", "exam"),
    ("补考在哪报名", "exam"),
    ("补考安排在哪看", "exam"),
    ("老师，我作业没写完能不能延期", "admin"),
    ("作业迟交了还能补交吗", "admin"),
    ("老师，我病了", "admin"),
    ("老师我想换组", "admin"),
    ("课程和考试冲突了怎么办", "admin"),
    ("成绩不对", "admin"),
    ("重修怎么报名", "admin"),
    ("转专业需要什么条件", "admin"),
    ("保研成绩单怎么开", "admin"),
    ("这门课可以免听吗", "admin"),
    ("论文查重没过怎么办", "admin"),
    ("老师这个怎么弄", "other"),
    ("有人出二手鼠标吗", "other"),
    ("求推荐好用的键盘", "other"),
    ("老师，你上课用的什么软件", "other"),
    ("今天教室好冷", "other"),
    ("大家作业写完了吗", "other"),
    ("老师，您周末加班吗", "other"),
    ("这个课给分高吗", "other"),
]


def _fill(template: str, rng: random.Random) -> str:
    return template.format(
        course=rng.choice(COURSES),
        week=rng.randint(1, 16),
        num=rng.randint(1, 8),
        part=rng.choice(PARTS),
        concept=rng.choice(CONCEPTS),
        lang=rng.choice(LANGS),
        platform=rng.choice(PLATFORMS),
    )


TYPO_MAP = {"作业": "做业", "老师": "老丝", "考试": "考式", "系统": "统系", "登录": "登陆"}


def _add_noise(text: str, rng: random.Random) -> str:
    if rng.random() < 0.08:
        for src, dst in TYPO_MAP.items():
            if src in text and rng.random() < 0.5:
                text = text.replace(src, dst, 1)
    if rng.random() < 0.12:  # 去掉标点，模拟快速输入
        text = text.replace("，", " ").replace("。", " ").replace("？", " ")
    return text.strip()


def generate_base(seed: int = 42, per_class: dict | None = None) -> list[dict]:
    per_class = per_class or {"homework": 320, "system": 280, "exam": 240, "admin": 200, "other": 160}
    rng = random.Random(seed)
    rows, seen = [], set()
    for label in LABELS:
        target = per_class[label]
        templates = BASE_TEMPLATES[label]
        tries = 0
        while sum(1 for r in rows if r["label"] == label) < target and tries < target * 60:
            tries += 1
            core = _fill(rng.choice(templates), rng)
            text = rng.choice(PREFIXES) + core + rng.choice(SUFFIXES)
            text = _add_noise(text, rng)
            key = (text, label)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "ticket_id": f"T{len(rows) + 1:05d}",
                "text": text,
                "label": label,
                "label_cn": LABEL_CN[label],
                "is_hard": 0,
                "source": "template",
            })
    rows.sort(key=lambda r: r["ticket_id"])
    return rows


def generate_hard(seed: int = 7, repeat: int = 4) -> list[dict]:
    """把每条难例加上不同的口语前后缀，生成更多不重复文本。"""
    rng = random.Random(seed)
    rows, seen = [], set()
    prefixes = ["", "老师，", "请问", "想问下，", "助教，"]
    suffixes = ["", "？", "，谢谢", "，怎么办", "，急"]
    for _ in range(repeat):
        for text, label in HARD_CASES:
            variant = rng.choice(prefixes) + text + rng.choice(suffixes)
            if variant in seen:
                continue
            seen.add(variant)
            rows.append({
                "ticket_id": f"H{len(rows) + 1:04d}",
                "text": variant,
                "label": label,
                "label_cn": LABEL_CN[label],
                "is_hard": 1,
                "source": "hard_case",
            })
    return rows


FAQ_ROWS = [
    ("K001", "作业提交格式是什么", "一般要求 PDF 或 docx，具体命名规则以课程公告为准；代码类作业需附可运行源码与说明。", "homework", "课程助教", "课程公告模板"),
    ("K002", "作业迟交会扣分吗", "迟交扣分比例由任课教师设定，常见做法是按天扣分；具体标准请查看课程评分说明，Agent 不代替教师做决定。", "homework", "任课教师", "课程评分说明模板"),
    ("K003", "作业可以重新提交吗", "多数平台允许截止前覆盖提交；截止后是否补交需任课教师确认，系统会转人工处理。", "homework", "任课教师", "平台功能说明"),
    ("K004", "小组作业怎么分组", "分组通常在课程群或平台分组功能中完成；未分组同学由助教统一分配。", "homework", "课程助教", "课程组织说明"),
    ("K005", "作业答案或参考示例在哪", "课程不提供标准答案；可在课件、习题课回放或答疑时间获取思路提示。", "homework", "课程助教", "答疑规范"),
    ("K006", "平台打不开或 502 错误", "先检查校园网/VPN，再更换浏览器或清理缓存；若多人同时出现，属于平台故障，请等待恢复并联系技术支持。", "system", "平台技术支持", "平台故障处理手册"),
    ("K007", "附件上传失败或超过大小限制", "压缩图片或分包上传，单个附件建议小于 20MB；若仍失败，记录报错截图并提交工单。", "system", "平台技术支持", "平台使用指南"),
    ("K008", "登录提示账号不存在或密码错误", "确认学号与登录入口是否匹配；连续失败可能触发临时锁定，需等待或联系平台管理员重置。", "system", "平台技术支持", "账号问题处理流程"),
    ("K009", "收不到验证码", "检查短信拦截与手机号是否与学籍一致；运营商延迟时可尝试语音验证码；多次失败转人工。", "system", "平台技术支持", "账号问题处理流程"),
    ("K010", "课程回放没有声音", "先检查设备音量与浏览器权限，再用其他视频验证；若仅该课程无声，可能是录制文件问题，转技术支持。", "system", "平台技术支持", "多媒体故障排查"),
    ("K011", "作业显示已提交但文件为空", "可能是上传中断导致，保留提交记录截图并尽快联系助教登记，必要时重新提交。", "system", "平台技术支持", "平台故障处理手册"),
    ("K012", "课件下载后乱码或打不开", "确认下载的是 PDF/PPT 原文件而非网页快捷方式；仍异常时请助教重新上传。", "system", "课程助教", "课件管理说明"),
    ("K013", "期末考试是开卷还是闭卷", "考试形式由课程大纲确定，请以本学期课程公告和教务排考通知为准。", "exam", "任课教师", "课程大纲模板"),
    ("K014", "考试范围包括哪些章节", "复习范围以教师最后一次复习课和公告为准；课程不鼓励仅凭传言缩小范围。", "exam", "任课教师", "课程大纲模板"),
    ("K015", "补考怎么报名", "补考一般由教务统一组织，需在规定时间内于教务系统申请；具体时间以教务处通知为准。", "exam", "教务办公室", "教务处补考通知模板"),
    ("K016", "缓考需要什么材料", "通常需要医院证明或冲突证明，并在考前提交申请表；材料要求以教务处规定为准。", "exam", "教务办公室", "学籍管理规定"),
    ("K017", "考试可以带计算器/资料吗", "按课程大纲与监考要求执行；不确定时请提前向任课教师书面确认。", "exam", "任课教师", "考试管理规定"),
    ("K018", "成绩构成和平时分怎么算", "总评一般由平时作业、测验、期末等按比例组成，具体比例见课程大纲。", "exam", "任课教师", "课程大纲模板"),
    ("K019", "补考成绩什么时候公布", "补考成绩由教务统一录入，通常在补考结束后两周内发布，具体以教务系统为准。", "exam", "教务办公室", "教务处成绩管理规定"),
    ("K020", "成绩有异议怎么复核", "需在规定期限内向开课学院提交成绩复核申请，Agent 仅登记工单，不修改成绩。", "admin", "教务办公室", "成绩复核流程"),
    ("K021", "如何申请调课/换班", "需填写调课或换班申请，经任课教师与教务同意后生效；名额与时间以教务答复为准。", "admin", "教务办公室", "学籍与选课管理规定"),
    ("K022", "作业延期怎么申请", "因病或紧急事务可提交延期申请并附证明，是否批准由任课教师决定。", "admin", "任课教师", "课程评分说明模板"),
    ("K023", "在读证明/成绩单怎么开", "可在教务自助打印机或教务办公室办理；盖章与份数要求以教务窗口为准。", "admin", "教务办公室", "教务服务指南"),
    ("K024", "学生证丢失怎么补办", "先挂失，再携带照片与身份证明到学籍管理部门申请补办，具体材料以窗口要求为准。", "admin", "教务办公室", "学籍管理规定"),
    ("K025", "课程免修/免听怎么申请", "需符合学校免修条件并提交证明材料，经审核批准后生效。", "admin", "教务办公室", "学籍管理规定"),
    ("K026", "转专业/辅修怎么报名", "关注教务处通知，按要求提交申请并参加考核；时间节点以官方通知为准。", "admin", "教务办公室", "教务处通知模板"),
    ("K027", "怎么找队友/买二手教材", "可在课程群或校园二手平台交流；请注意交易安全，不要提前转账给陌生人。", "other", "群管理员", "群管理规范"),
    ("K028", "课程群二维码失效", "请联系助教重新获取入群方式，避免扫描来源不明的二维码。", "other", "课程助教", "群管理规范"),
]


def write_kb(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["faq_id", "question", "answer", "category", "owner", "source"])
        writer.writerows(FAQ_ROWS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(DATA_DIR / "tickets.csv"))
    args = parser.parse_args()

    rows = generate_base(seed=args.seed) + generate_hard(seed=args.seed + 1)
    out = Path(args.out)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    write_kb(DATA_DIR / "kb_faq.csv")

    from collections import Counter
    print(f"已生成 {len(rows)} 条工单 -> {out}")
    print("类别分布:", dict(Counter(r['label'] for r in rows)))
    print("其中难例:", sum(r['is_hard'] for r in rows))
    print(f"FAQ 知识库 -> {DATA_DIR / 'kb_faq.csv'}")


if __name__ == "__main__":
    main()
