#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
给素材合集自动补「篇内来源标记」。

为什么需要：MiroFish 的切块是按字符切的（默认 500 字一块、重叠 50 字），
而系统只在**整个文件开头**加一次来源头。同一篇素材被切成第 2 块、第 3 块之后，
那些块就成了「无源文本」，报告阶段说不清结论来自哪篇报道。

本脚本在正文里每隔 ~EVERY 个字符插一行来源标记，把带源块的比例拉到 100%。

用法：
    python _tag_sources.py <输入.md> [--every 250] [--out 输出.md]

不加 --out 就直接覆盖原文件。
"""

import re
import sys
import argparse
from pathlib import Path

HEAD_RE = re.compile(r"^===\s*素材\s*(\d+)(?:/\d+)?\s*\|([^|]*)\|([^|]*)\|")
TAG_RE = re.compile(r"^（以上及以下均出自")


def short_src(m):
    """把 '=== 素材 1/9 | USA Today Network（综合民调盘点）| 2026-09-23 | xxx ==='
    压成 '素材 1 · USA Today Network · 2026-09-23'"""
    idx, media, date = m.group(1), m.group(2).strip(), m.group(3).strip()
    media = re.sub(r"[（(].*?[)）]", "", media).strip()
    return f"素材 {idx} · {media} · {date}"


def tag_file(path: Path, every: int) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").split("\n")
    out, cur_src, acc, added = [], None, 0, 0

    for line in lines:
        m = HEAD_RE.match(line.strip())
        if m:
            cur_src = short_src(m)
            acc = 0
            out.append(line)
            continue

        # 已有标记行：重置计数，不重复插
        if TAG_RE.match(line.strip()):
            acc = 0
            out.append(line)
            continue

        # 只在正文（非空、非标题、非分隔线）前插标记
        is_body = (
            line.strip()
            and not line.lstrip().startswith("#")
            and not line.strip().startswith("---")
            and not line.strip().startswith(">")
        )
        if is_body and cur_src and acc >= every:
            out.append(f"（以上及以下均出自：{cur_src}）")
            added += 1
            acc = 0

        out.append(line)
        acc += len(line)

    path.write_text("\n".join(out), encoding="utf-8")
    return added, len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--every", type=int, default=250)
    ap.add_argument("--out")
    a = ap.parse_args()

    src = Path(a.src)
    dst = Path(a.out) if a.out else src
    if a.out:
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    n, total = tag_file(dst, a.every)
    print(f"已插入 {n} 处来源标记（阈值 {a.every} 字）-> {dst}  ({total} 行)")


if __name__ == "__main__":
    main()
