# -*- coding: utf-8 -*-
"""把 stardust_news/ 下 6 篇原始素材合成一个文件，并在篇内补足来源标记。

用法：
    python test_scenarios/_merge.py
产物：
    test_scenarios/星尘科技_原始素材合集.md
"""
import re
from pathlib import Path

SRC = Path(__file__).parent / "stardust_news"
OUT = Path(__file__).parent / "星尘科技_原始素材合集.md"

# (文件名, 来源方, 来源类型, 日期, 作者)  —— 按发布日期排序
META = [
    ("01_快讯_星尘发布Star-7B.md",    "硅立方",   "科技媒体快讯",       "2026-03-18", "记者 周婷"),
    ("02_评测视频文字稿_K实测质疑.md", "视频平台", "KOL 评测视频文字稿", "2026-05-06", "UP主 K"),
    ("03_云枢智能官方声明.md",         "云枢智能", "企业官方声明",       "2026-05-09", "法务与公关部"),
    ("05_社区讨论帖_开发者吵翻了.md",  "开源社区", "社区讨论帖整理",     "2026-06-14", "网友留言"),
    ("06_行业背景与监管动向.md",       "产业观察", "行业与政策报道",     "2026-07-08", "产业观察"),
    ("04_财经报道_估值下调与裁员.md",  "资本观察", "财经媒体调查报道",   "2026-09-16", "记者 郑亦"),
]

# 篇内每隔多少字补一次来源标记（略小于切块长度 500，保证每块至少命中一次）
INLINE_EVERY = 360

parts = []
parts.append("# 星尘科技开源模型争议 · 原始素材合集\n")
parts.append(
    "> 本合集由 6 篇公开素材按发布时间拼接而成，用于测试知识图谱构建环节。\n"
    "> 素材中保留了该场景本来的样子：重复数据、相互矛盾的数字、人物别名、\n"
    "> 主观判断、广告与跑题内容，均未做清洗。\n"
)
parts.append("\n---\n")

for idx, (fname, org, kind, date, author) in enumerate(META, start=1):
    text = (SRC / fname).read_text(encoding="utf-8").strip()
    header = f"\n=== 素材 {idx}/6 | {org}（{kind}）| {date} | {author} ===\n"
    tag = f"（以上及以下均出自：素材 {idx} · {org} · {date}）"

    # 篇内按空行切段，累计字数超阈值时补一行标记
    blocks = re.split(r"\n\s*\n", text)
    buf, acc = [], 0
    for b in blocks:
        if acc >= INLINE_EVERY:
            buf.append(tag)
            acc = 0
        buf.append(b)
        acc += len(b)
    body = "\n\n".join(buf)

    parts.append(header)
    parts.append(body)
    parts.append("\n")

OUT.write_text("\n".join(parts), encoding="utf-8")
print("已生成:", OUT)
print("字符数:", len(OUT.read_text(encoding="utf-8")))
