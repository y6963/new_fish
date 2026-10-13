# -*- coding: utf-8 -*-
"""生成《MiroFish 数据流转全景》演示文稿（学术蓝白风，1280x720）"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
import copy

# ---------- 设计令牌（学术蓝白） ----------
MAIN = '1E4FA8'      # 主蓝
NAVY = '0E3F8C'      # 藏蓝
LBLUE = 'E8EFF8'     # 浅蓝
LBLUE2 = 'F0F5FC'    # 更浅蓝
MBLUE = '3D7BD9'     # 中蓝
RED = 'D9534F'       # 警示红
YELLOW = 'FFC107'    # 数据黄
TXT = '1A2230'       # 主文本
TXT2 = '4A5568'      # 副文本
TXT3 = '8B97A8'      # 辅助
LINE = 'D6DCE5'      # 线框
BG = 'FFFFFF'
BG2 = 'F7F9FC'
WHITE = 'FFFFFF'

CN = 'Microsoft YaHei'
MONO = 'Consolas'

W = Inches(13.3333)
H = Inches(7.5)
MARGIN = Inches(0.4167)          # 40px
CONTENT_W = Inches(12.5)         # 1200px
BAR_H = Inches(0.75)             # 顶条 72px
TOP = Inches(0.92)               # 内容区起点
BOTTOM = Inches(6.875)           # 内容区底 660px


def rgb(h):
    return RGBColor.from_string(h)


def set_font(run, name=CN, size=None, bold=False, color=TXT, italic=False):
    f = run.font
    f.name = name
    if size:
        f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = rgb(color)
    rPr = run._r.get_or_add_rPr()
    latin = rPr.find(qn('a:latin'))
    if latin is not None:
        ea = rPr.find(qn('a:ea'))
        if ea is None:
            ea = latin.makeelement(qn('a:ea'), {})
            latin.addnext(ea)
        ea.set('typeface', name)


def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return tb


def put(tb, lines, size=18, color=TXT, bold=False, name=CN, line_spacing=1.25,
        space_after=4, align=PP_ALIGN.LEFT, first=False):
    """lines: list of (text, {overrides}) 或 str"""
    tf = tb.text_frame
    for i, item in enumerate(lines):
        if isinstance(item, str):
            item = (item, {})
        txt, ov = item
        p = tf.paragraphs[0] if (i == 0 and first) else tf.add_paragraph()
        p.alignment = ov.get('align', align)
        p.line_spacing = ov.get('line_spacing', line_spacing)
        p.space_after = Pt(ov.get('space_after', space_after))
        r = p.add_run()
        r.text = txt
        set_font(r,
                 name=ov.get('name', name),
                 size=ov.get('size', size),
                 bold=ov.get('bold', bold),
                 color=ov.get('color', color),
                 italic=ov.get('italic', False))
    if not first and tf.paragraphs and tf.paragraphs[0].runs == []:
        p0 = tf.paragraphs[0]
        p0._element.getparent().remove(p0._element)
    return tb


def rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.03):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    if fill:
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb(fill)
    else:
        sp.fill.background()
    if line:
        sp.line.color.rgb = rgb(line)
        sp.line.width = Pt(line_w)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE and adj is not None:
        try:
            sp.adjustments[0] = adj
        except Exception:
            pass
    tf = sp.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return sp


def header(slide, title, sub=None):
    bar = rect(slide, Inches(0), Inches(0), W, BAR_H, fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tf = bar.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.4167)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    set_font(r, size=26, bold=True, color=WHITE)
    if sub:
        tb = textbox(slide, MARGIN, Inches(0.79), CONTENT_W, Inches(0.32))
        put(tb, [(sub, {'size': 15, 'color': TXT2})], first=True)
        return Inches(1.16)
    return Inches(1.05)


def footer(slide, idx, total, note='MiroFish 数据流转全景 · 基于代码分析'):
    ln = rect(slide, MARGIN, Inches(6.88), CONTENT_W, Emu(9525), fill=LINE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(slide, MARGIN, Inches(6.94), Inches(9), Inches(0.32))
    put(tb, [(note, {'size': 12, 'color': TXT3})], first=True)
    tb2 = textbox(slide, Inches(11.6), Inches(6.94), Inches(1.31), Inches(0.32))
    put(tb2, [(f'{idx} / {total}', {'size': 13, 'color': MAIN, 'bold': True, 'align': PP_ALIGN.RIGHT})], first=True)


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


# ==================== 页面 ====================
TOTAL = 21


def p01_cover(prs):
    s = blank(prs)
    rect(s, Inches(0), Inches(0), W, H, fill=BG, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(0), Inches(0), W, Inches(1.05), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(0), Inches(6.45), W, Inches(1.05), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(0.9), Inches(2.05), Inches(0.09), Inches(2.9), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)

    tb = textbox(s, Inches(1.25), Inches(2.0), Inches(11), Inches(1.1))
    put(tb, [('MiroFish 数据流转全景', {'size': 46, 'bold': True, 'color': NAVY})], first=True)

    tb = textbox(s, Inches(1.25), Inches(3.05), Inches(11), Inches(0.75))
    put(tb, [('从种子文件到智能体人设：数据结构如何一步步变形',
              {'size': 24, 'bold': True, 'color': MAIN})], first=True)

    tb = textbox(s, Inches(1.25), Inches(3.95), Inches(10.4), Inches(1.9))
    put(tb, [
        ('每一页回答同一个问题：这一步拿到什么、吐出什么、数据长什么样、由谁执行。',
         {'size': 17, 'color': TXT2}),
        ('全部结论来自源码逐行核对（backend/app 与 backend/scripts），不含推测。',
         {'size': 17, 'color': TXT2}),
        ('主流程讲原理与数据结构，末尾附录给出文件路径、行号与断点位置。',
         {'size': 17, 'color': TXT2}),
    ], first=True, line_spacing=1.55, space_after=10)

    tb = textbox(s, Inches(1.25), Inches(6.72), Inches(11), Inches(0.42))
    put(tb, [('技术讲解 · 2026 年 9 月 · 基线 git HEAD 39d8491', {'size': 15, 'color': WHITE})], first=True)


def p02_catalog(prs):
    s = blank(prs)
    y = header(s, '目录', '五章：全景 → 种子 → 图谱 → 人设 → 复盘与附录')
    items = [
        ('01', '全景与总览', '谁在什么时候做什么：六次模型调用与数据形态总表'),
        ('02', '种子与文本', '文件如何变成字符串、如何被切成块、本体如何被设计出来'),
        ('03', '文本到知识图谱', '本体装载、Zep 抽取黑盒、节点读回与过滤'),
        ('04', '图谱到智能体', '画像生成、行为配置、事件与时间配置'),
        ('05', '变形复盘与附录', '信息在哪些步骤丢失、断点清单与已知缺陷'),
    ]
    card_h = Inches(0.98)
    gap = Inches(0.145)
    cur = y
    for num, t, d in items:
        rect(s, MARGIN, cur, CONTENT_W, card_h, fill=BG2, line=LINE)
        rect(s, MARGIN, cur, Inches(0.98), card_h, fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, MARGIN, cur, Inches(0.98), card_h, MSO_ANCHOR.MIDDLE)
        put(tb, [(num, {'size': 26, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
        tb = textbox(s, Inches(1.18), Inches(0) + cur + Inches(0.13), Inches(2.5), Inches(0.4))
        put(tb, [(t, {'size': 21, 'bold': True, 'color': NAVY})], first=True)
        tb = textbox(s, Inches(1.18), Inches(0) + cur + Inches(0.53), Inches(10.8), Inches(0.4))
        put(tb, [(d, {'size': 15, 'color': TXT2})], first=True)
        cur = cur + card_h + gap
    footer(s, 2, TOTAL)


def section(prs, num, title, points, idx):
    s = blank(prs)
    rect(s, Inches(0), Inches(0), W, H, fill=BG, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(0), Inches(0), Inches(3.6), H, fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(3.6), Inches(0), Inches(0.06), H, fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)

    tb = textbox(s, Inches(0.55), Inches(2.0), Inches(2.9), Inches(2.2))
    put(tb, [(num, {'size': 112, 'bold': True, 'color': 'FFFFFF'})], first=True)

    tb = textbox(s, Inches(4.25), Inches(2.15), Inches(8.4), Inches(0.9))
    put(tb, [(title, {'size': 38, 'bold': True, 'color': NAVY})], first=True)

    cur = Inches(3.35)
    for pt in points:
        rect(s, Inches(4.25), cur + Inches(0.13), Inches(0.14), Inches(0.34), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, Inches(4.56), cur, Inches(8.1), Inches(0.6))
        put(tb, [(pt, {'size': 18, 'color': TXT})], first=True)
        cur = cur + Inches(0.72)

    tb = textbox(s, Inches(4.25), Inches(6.6), Inches(8.4), Inches(0.4))
    put(tb, [(f'第 {idx} 页 / 共 {TOTAL} 页', {'size': 13, 'color': TXT3})], first=True)


def p04_pipeline(prs):
    s = blank(prs)
    y = header(s, '全景：数据如何在六个阶段变形', '三个执行者交替接力：本项目代码 / 本项目调用的模型 / Zep 云端')

    stages = [
        ('① 本体生成', '本项目 · 模型', MAIN, '文本 → 类型 schema'),
        ('② 装载本体', '本项目 · 代码', TXT2, 'schema → Pydantic 类'),
        ('③ 实体抽取', 'Zep 云端 · 黑盒', RED, '文本块 → 节点与边'),
        ('④ 画像生成', '本项目 · 模型', MAIN, '实体 → 人设'),
        ('⑤ 行为配置', '本项目 · 模型', MAIN, '实体 → 行为参数'),
        ('⑥ 事件配置', '本项目 · 模型', MAIN, '实体 → 初始帖子'),
    ]
    n = len(stages)
    gap = Inches(0.11)
    total_gap = gap * (n - 1)
    card_w = int((CONTENT_W - total_gap) / n)
    cur_x = MARGIN
    top = Inches(1.62)
    card_h = Inches(2.35)
    for title, who, color, io in stages:
        rect(s, cur_x, top, card_w, card_h, fill=BG2, line=LINE)
        rect(s, cur_x, top, card_w, Inches(0.42), fill=color, shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, cur_x, top, card_w, Inches(0.42), MSO_ANCHOR.MIDDLE)
        put(tb, [(title, {'size': 15, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
        tb = textbox(s, cur_x + Inches(0.1), top + Inches(0.56), card_w - Inches(0.2), Inches(0.5))
        put(tb, [(who, {'size': 13, 'bold': True, 'color': color, 'align': PP_ALIGN.CENTER})], first=True)
        tb = textbox(s, cur_x + Inches(0.1), top + Inches(1.02), card_w - Inches(0.2), Inches(1.2), MSO_ANCHOR.TOP)
        put(tb, [(io, {'size': 14, 'color': TXT, 'align': PP_ALIGN.CENTER})], first=True, line_spacing=1.4)
        cur_x = cur_x + card_w + gap

    # 阶段 0（前置）
    rect(s, MARGIN, Inches(4.18), CONTENT_W, Inches(0.62), fill=LBLUE, line=MBLUE)
    tb = textbox(s, MARGIN + Inches(0.2), Inches(4.18), CONTENT_W - Inches(0.4), Inches(0.62), MSO_ANCHOR.MIDDLE)
    put(tb, [('阶段 0（前置，纯代码）：文件 → 文本 → 按 500 字符切块。它是后面所有阶段的输入源头。',
              {'size': 16, 'bold': True, 'color': NAVY})], first=True)

    # 结论条
    rect(s, MARGIN, Inches(5.02), CONTENT_W, Inches(1.62), fill=NAVY)
    tb = textbox(s, MARGIN + Inches(0.28), Inches(5.18), CONTENT_W - Inches(0.56), Inches(1.3))
    put(tb, [
        ('关键判断：六次模型调用里，只有 ③ 不在本项目内。', {'size': 19, 'bold': True, 'color': 'FFC107'}),
        ('③ 由 Zep Cloud 服务端完成，代码里没有任何抽取提示词可以修改。想提升抽取质量，',
         {'size': 15, 'color': WHITE}),
        ('只能改本体的类型定义，或改喂进去的文本块——这正是种子结构设计的价值所在。',
         {'size': 15, 'color': WHITE}),
    ], first=True, line_spacing=1.5, space_after=6)
    footer(s, 4, TOTAL)


def p05_table(prs):
    s = blank(prs)
    y = header(s, '数据形态总表：每一步的输入与输出', '同一份素材，形态被改写六次')

    rows = [
        ['阶段', '输入', '输出', '数据结构', '执行者'],
        ['0 解析', 'pdf / md / txt', '带文档头的长文本', 'str', '代码'],
        ['0 切块', '长文本', '若干文本块', 'List[str]（500 字 / 50 重叠）', '代码'],
        ['① 本体', 'List[str] + 需求', '10 类实体 + 边类型', 'dict（entity_types / edge_types）', '模型'],
        ['② 装载', '本体 dict', 'Zep 侧类型约束', '动态 Pydantic 类', '代码'],
        ['③ 抽取', '文本块 + 类型约束', '节点与边', 'Zep 图对象（黑盒）', 'Zep 云端'],
        ['④ 读回', '图节点', '带上下文的实体', 'EntityNode（dataclass）', '代码'],
        ['⑤ 画像', 'EntityNode', '人设字段', 'OasisAgentProfile（dataclass）', '模型'],
        ['⑥ 配置', '实体列表', '行为与事件参数', 'AgentActivityConfig / EventConfig', '模型'],
    ]
    tbl_h = Inches(5.6)
    shape = s.shapes.add_table(len(rows), 5, MARGIN, Inches(1.30), CONTENT_W, tbl_h)
    table = shape.table
    table.columns[0].width = Inches(1.15)
    table.columns[1].width = Inches(2.55)
    table.columns[2].width = Inches(2.5)
    table.columns[3].width = Inches(4.0)
    table.columns[4].width = Inches(2.3)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.cell(ri, ci)
            cell.text = val
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.1)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.04)
            p = cell.text_frame.paragraphs[0]
            for r in p.runs:
                if ri == 0:
                    set_font(r, size=15, bold=True, color=WHITE)
                else:
                    set_font(r, size=13.5,
                             bold=(ci == 0),
                             color=(NAVY if ci == 0 else TXT))
            if ri == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(NAVY)
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(BG if ri % 2 else LBLUE2)

    rect(s, MARGIN, Inches(6.99), CONTENT_W, Inches(0.02), fill=LINE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(7.02), CONTENT_W, Inches(0.36))
    put(tb, [('读法：横着看是「形态怎么变」，竖着看是「谁在负责」。执行者为「代码」的两行不需要模型参与。',
              {'size': 14, 'bold': True, 'color': NAVY})], first=True)
    footer(s, 5, TOTAL)


def p07_stage0(prs):
    s = blank(prs)
    y = header(s, '阶段 0：文件如何变成文本块', 'file_parser.py 与 text_processor.py，全程无模型参与')

    # 左：输入
    rect(s, MARGIN, Inches(1.30), Inches(3.9), Inches(2.5), fill=BG2, line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(3.9), Inches(0.42), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(3.9), Inches(0.42), MSO_ANCHOR.MIDDLE)
    put(tb, [('输入：三种文件格式', {'size': 15, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, MARGIN + Inches(0.22), Inches(1.86), Inches(3.46), Inches(1.92))
    put(tb, [
        ('支持 pdf / md / markdown / txt，', {'size': 13.5, 'color': TXT}),
        ('编码走 UTF-8 → charset-normalizer', {'size': 13.5, 'color': TXT}),
        ('→ chardet 的三级回退。', {'size': 13.5, 'color': TXT}),
        ('多文件合并时，每篇前面会插入：', {'size': 13.5, 'bold': True, 'color': NAVY}),
        ('=== 文档 N: 文件名 ===', {'size': 13, 'color': RED, 'name': MONO}),
    ], first=True, line_spacing=1.32, space_after=5)

    # 中：切块
    rect(s, Inches(4.6), Inches(1.30), Inches(3.7), Inches(2.5), fill=BG2, line=LINE)
    rect(s, Inches(4.6), Inches(1.30), Inches(3.7), Inches(0.42), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(4.6), Inches(1.30), Inches(3.7), Inches(0.42), MSO_ANCHOR.MIDDLE)
    put(tb, [('处理：按字符切块', {'size': 15, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, Inches(4.82), Inches(1.86), Inches(3.26), Inches(1.92))
    put(tb, [
        ('split_text_into_chunks(', {'size': 13, 'color': NAVY, 'name': MONO}),
        ('    500, 50)', {'size': 13, 'color': NAVY, 'name': MONO}),
        ('每块 500 字符，重叠 50。', {'size': 13.5, 'color': TXT}),
        ('切点优先找句号 / 换行等边界，', {'size': 13.5, 'color': TXT}),
        ('但本质是字符窗口，不是语义单元。', {'size': 13.5, 'color': TXT, 'bold': True}),
    ], first=True, line_spacing=1.3, space_after=5)

    # 右：输出
    rect(s, Inches(8.6), Inches(1.30), Inches(4.3), Inches(2.5), fill=BG2, line=LINE)
    rect(s, Inches(8.6), Inches(1.30), Inches(4.3), Inches(0.42), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(8.6), Inches(1.30), Inches(4.3), Inches(0.42), MSO_ANCHOR.MIDDLE)
    put(tb, [('输出：List[str]', {'size': 15, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, Inches(8.82), Inches(1.86), Inches(3.86), Inches(1.92))
    put(tb, [
        ('写入 Zep 时每块成为一个 episode，', {'size': 13.5, 'color': TXT}),
        ('元数据只有块序号与哈希。', {'size': 13.5, 'color': TXT}),
        ('来源、发布时间、传播量', {'size': 13.5, 'color': RED, 'bold': True}),
        ('在这一步就已经丢失。', {'size': 13.5, 'color': RED, 'bold': True}),
    ], first=True, line_spacing=1.3, space_after=5)

    # 底部警示
    rect(s, MARGIN, Inches(4.05), CONTENT_W, Inches(1.05), fill=LBLUE, line=MBLUE)
    tb = textbox(s, MARGIN + Inches(0.25), Inches(4.05), CONTENT_W - Inches(0.5), Inches(1.05), MSO_ANCHOR.MIDDLE)
    put(tb, [('机械切块的后果：一条微博和一篇新闻可能被切进同一块；长文切到第 3 块之后，来源头信息全部消失。',
              {'size': 17, 'bold': True, 'color': NAVY})], first=True)

    # 两个杠杆
    rect(s, MARGIN, Inches(5.28), CONTENT_W, Inches(1.4), fill=NAVY)
    tb = textbox(s, MARGIN + Inches(0.28), Inches(5.42), CONTENT_W - Inches(0.56), Inches(1.15))
    put(tb, [
        ('所以最小单元应该是「一条证据」，不是字符窗口。', {'size': 19, 'bold': True, 'color': 'FFC107'}),
        ('改进方向：让每个文本块自带来源、时间与传播量的头部，并按证据边界切，而不是按字符数切。',
         {'size': 15, 'color': WHITE}),
    ], first=True, line_spacing=1.45, space_after=6)
    footer(s, 7, TOTAL)


def p08_ontology(prs):
    s = blank(prs)
    y = header(s, '阶段 ①：本体生成——让模型设计类型', 'ontology_generator.py，全系统唯一的领域自适应机制')

    # 左：提示词约束
    rect(s, MARGIN, Inches(1.30), Inches(5.5), Inches(5.3), fill=BG2, line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(5.5), Inches(0.44), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(5.5), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('输入：提示词里写死的硬约束', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, MARGIN + Inches(0.24), Inches(1.90), Inches(5.02), Inches(4.62))
    put(tb, [
        ('必须正好 10 个实体类型', {'size': 14, 'bold': True, 'color': NAVY}),
        ('最后 2 个必须是 Person 与 Organization 兜底', {'size': 14, 'color': TXT}),
        ('实体必须能在社媒发声（明文禁止抽象概念、话题、观点）', {'size': 14, 'color': TXT}),
        ('边类型 6–10 个，需声明 source / target', {'size': 14, 'color': TXT}),
        ('类型名用英文 PascalCase，边名用 UPPER_SNAKE', {'size': 14, 'color': TXT}),
        ('属性名不能撞保留字（name / uuid / created_at）', {'size': 14, 'color': TXT}),
        ('每类附 1–3 个属性与若干示例实体', {'size': 14, 'color': TXT}),
        ('', {'size': 8}),
        ('另外注入两份内容：模拟需求 + 文档正文。', {'size': 14, 'bold': True, 'color': MAIN}),
        ('正文超过 5 万字会等距抽样，最多 60 块。', {'size': 13.5, 'color': TXT2}),
    ], first=True, line_spacing=1.3, space_after=7)

    # 右：输出示例
    rect(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(5.3), fill='FFFFFF', line=LINE)
    rect(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(0.44), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('输出：模型返回的本体（节选）', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        '{',
        '  "entity_types": [',
        '    { "name": "Celebrity",',
        '      "description": "Public figure ...",',
        '      "attributes": [{"name":"full_name"}],',
        '      "examples": ["罗永浩"] },',
        '    { "name": "Company", ... },',
        '    { "name": "MediaOutlet", ... },',
        '    ...',
        '    { "name": "Person", ... },        // 兜底',
        '    { "name": "Organization", ... }   // 兜底',
        '  ],',
        '  "edge_types": [',
        '    { "name": "CRITICIZES",',
        '      "source_targets": [',
        '        {"source":"Celebrity","target":"Company"} ] }',
        '  ],',
        '  "analysis_summary": "..."',
        '}',
    ]
    tb = textbox(s, Inches(6.35), Inches(1.92), Inches(6.35), Inches(4.5))
    put(tb, [(c, {'size': 12.5, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.06, space_after=0)
    footer(s, 8, TOTAL)


def p09_validate(prs):
    s = blank(prs)
    y = header(s, '阶段 ①之后：代码强制校验发生了什么', '_validate_and_process，提示词之外的一道保险')

    cards = [
        ('10 个上限', MAIN,
         ['超过就截断末尾，', '保留前 8 个具体类型', '再加两个兜底。', 'Zep 侧的硬顶，绕不过去。']),
        ('自动补兜底', NAVY,
         ['模型没给 Person /', 'Organization 时，代码', '直接补上；位置不够就', '把末尾类型砍掉腾位。']),
        ('中文名静默丢弃', RED,
         ['PascalCase 转换按', '非字母数字分词，中文', '被整个吃掉后返回', 'Unknown，直接跳过。']),
    ]
    cw = Inches(3.98)
    gap = Inches(0.28)
    cx = MARGIN
    for title, color, lines in cards:
        rect(s, cx, Inches(1.30), cw, Inches(2.85), fill=BG2, line=LINE)
        rect(s, cx, Inches(1.30), cw, Inches(0.46), fill=color, shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, cx, Inches(1.30), cw, Inches(0.46), MSO_ANCHOR.MIDDLE)
        put(tb, [(title, {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
        tb = textbox(s, cx + Inches(0.22), Inches(1.98), cw - Inches(0.44), Inches(2.0))
        put(tb, [(l, {'size': 15.5, 'color': TXT}) for l in lines],
            first=True, line_spacing=1.42, space_after=4)
        cx = cx + cw + gap

    # 实测
    rect(s, MARGIN, Inches(4.35), CONTENT_W, Inches(0.52), fill=LBLUE, line=MBLUE)
    tb = textbox(s, MARGIN + Inches(0.22), Inches(4.35), CONTENT_W - Inches(0.44), Inches(0.52), MSO_ANCHOR.MIDDLE)
    put(tb, [('实测（本机运行）：输入 celebrity / criticizes / 罗永浩的粉丝', {'size': 16, 'bold': True, 'color': NAVY})], first=True)

    code = [
        "输入：{'entity_types':[{'name':'celebrity'},{'name':'罗永浩的粉丝'}],",
        "       'edge_types':[{'name':'criticizes', ...}]}",
        '',
        "输出：entity_types = ['Celebrity', 'Person', 'Organization']",
        "      edge_types  = ['CRITICIZES']",
        '',
        "日志：Entity type name 'celebrity' auto-converted to 'Celebrity'",
        "      → 中文类型名没有报错，只是消失了",
    ]
    rect(s, MARGIN, Inches(4.95), CONTENT_W, Inches(1.95), fill='FFFFFF', line=LINE)
    tb = textbox(s, MARGIN + Inches(0.24), Inches(5.05), CONTENT_W - Inches(0.48), Inches(1.78))
    put(tb, [(c, {'size': 12, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.15, space_after=0)
    footer(s, 9, TOTAL)


def p11_load(prs):
    s = blank(prs)
    y = header(s, '阶段 ②：装载本体——把 JSON 变成类', 'graph_builder.set_ontology，纯代码，无模型参与')

    rect(s, MARGIN, Inches(1.30), Inches(5.9), Inches(4.9), fill='FFFFFF', line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(5.9), Inches(0.44), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(5.9), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('代码动态生成的 Pydantic 类', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        'type("Celebrity", (EntityModel,), {',
        '    "__annotations__": {',
        '        "full_name": Optional[EntityText],',
        '    },',
        '    "full_name": Field(',
        '        description="Real name",',
        '        default=None',
        '    )',
        '})',
        '',
        'client.graph.set_ontology(',
        '    entities=entity_types,',
        '    edges=edge_definitions',
        ')',
    ]
    tb = textbox(s, MARGIN + Inches(0.24), Inches(1.92), Inches(5.42), Inches(4.1))
    put(tb, [(c, {'size': 13.5, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.22, space_after=0)

    # 右侧
    rect(s, Inches(6.55), Inches(1.30), Inches(6.15), Inches(2.35), fill=BG2, line=LINE)
    rect(s, Inches(6.55), Inches(1.30), Inches(6.15), Inches(0.44), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(6.55), Inches(1.30), Inches(6.15), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('这一步在做什么', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, Inches(6.77), Inches(1.92), Inches(5.71), Inches(1.55))
    put(tb, [
        ('把「类型定义」注册到 Zep 图谱上，成为后续抽取时的约束。',
         {'size': 15.5, 'color': TXT}),
        ('属性撞上保留字会被自动改名（如 name → entity_name）。',
         {'size': 15.5, 'color': TXT}),
    ], first=True, line_spacing=1.45, space_after=8)

    rect(s, Inches(6.55), Inches(3.78), Inches(6.15), Inches(2.5), fill=LBLUE, line=MBLUE)
    tb = textbox(s, Inches(6.77), Inches(3.90), Inches(5.71), Inches(2.34))
    put(tb, [
        ('为什么重要', {'size': 17, 'bold': True, 'color': NAVY}),
        ('这一步决定了 ③ 能抽出什么。', {'size': 14.5, 'color': TXT}),
        ('类型描述越清楚、示例给得越准，', {'size': 14.5, 'color': TXT}),
        ('Zep 抽取时的命中率越高。', {'size': 14.5, 'color': TXT}),
        ('示例里写「罗永浩」，就等于直接', {'size': 14.5, 'color': TXT}),
        ('给 Celebrity 类型打了个靶。', {'size': 14.5, 'bold': True, 'color': MAIN}),
    ], first=True, line_spacing=1.35, space_after=5)
    footer(s, 11, TOTAL)


def p12_zep(prs):
    s = blank(prs)
    y = header(s, '阶段 ③：实体抽取发生在 Zep 云端', '这是唯一一处代码里没有提示词、也无法打断点的环节')

    # 左：输入
    rect(s, MARGIN, Inches(1.30), Inches(3.75), Inches(3.05), fill=BG2, line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(3.75), Inches(0.44), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(3.75), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('输入：文本块 + 类型约束', {'size': 15, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, MARGIN + Inches(0.2), Inches(1.88), Inches(3.35), Inches(2.32))
    put(tb, [
        ('每个块 ≤ 10000 字符，', {'size': 13.5, 'color': TXT}),
        ('单批 ≤ 350 条，', {'size': 13.5, 'color': TXT}),
        ('总量 ≤ 50000 条。', {'size': 13.5, 'color': TXT}),
        ('', {'size': 7}),
        ('你能看到的只有「发出去的文本」，', {'size': 13.5, 'bold': True, 'color': RED}),
        ('服务端怎么抽，是黑盒。', {'size': 13.5, 'bold': True, 'color': RED}),
    ], first=True, line_spacing=1.3, space_after=4)

    # 中：黑盒
    rect(s, Inches(4.45), Inches(1.30), Inches(3.3), Inches(3.05), fill=NAVY, line=NAVY)
    tb = textbox(s, Inches(4.45), Inches(1.30), Inches(3.3), Inches(3.05), MSO_ANCHOR.MIDDLE)
    put(tb, [
        ('Zep Cloud', {'size': 26, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER}),
        ('服务端抽取', {'size': 20, 'bold': True, 'color': 'FFC107', 'align': PP_ALIGN.CENTER}),
        ('', {'size': 8}),
        ('无提示词可改', {'size': 14, 'color': 'FFFFFF', 'align': PP_ALIGN.CENTER}),
        ('无断点可打', {'size': 14, 'color': 'FFFFFF', 'align': PP_ALIGN.CENTER}),
    ], first=True, line_spacing=1.25, space_after=4)

    # 右：输出
    rect(s, Inches(8.05), Inches(1.30), Inches(4.85), Inches(3.05), fill='FFFFFF', line=LINE)
    rect(s, Inches(8.05), Inches(1.30), Inches(4.85), Inches(0.44), fill=MBLUE, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(8.05), Inches(1.30), Inches(4.85), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('输出：节点与边', {'size': 15, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        '// 节点',
        '{ "name": "罗永浩",',
        '  "labels": ["Entity","Celebrity"],',
        '  "summary": "锤子科技创始人…",',
        '  "attributes": {"full_name":"罗永浩"} }',
        '',
        '// 边',
        '{ "name": "CRITICIZES",',
        '  "fact": "罗永浩质疑西贝…",',
        '  "source_node_name": "罗永浩",',
        '  "target_node_name": "西贝" }',
    ]
    tb = textbox(s, Inches(8.25), Inches(1.88), Inches(4.45), Inches(2.4))
    put(tb, [(c, {'size': 11.5, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.12, space_after=0)

    # 底部两个杠杆
    rect(s, MARGIN, Inches(4.42), CONTENT_W, Inches(0.5), fill=LBLUE, line=MBLUE)
    tb = textbox(s, MARGIN + Inches(0.22), Inches(4.42), CONTENT_W - Inches(0.44), Inches(0.5), MSO_ANCHOR.MIDDLE)
    put(tb, [('既然改不了提示词，能影响抽取质量的只有两个杠杆：', {'size': 16, 'bold': True, 'color': NAVY})], first=True)

    lv = [
        ('杠杆一：本体定义质量', 'description 是否清楚、examples 是否命中、属性是否合理'),
        ('杠杆二：文本块质量', '来源、时间、传播量是否写进了正文（唯一能影响黑盒的入口）'),
    ]
    cx = MARGIN
    for i, (t, d) in enumerate(lv):
        rect(s, cx, Inches(5.08), Inches(6.14), Inches(1.42), fill=BG2, line=LINE)
        rect(s, cx, Inches(5.08), Inches(0.08), Inches(1.42), fill=(MAIN if i == 0 else RED), shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, cx + Inches(0.24), Inches(5.22), Inches(5.66), Inches(0.42))
        put(tb, [(t, {'size': 17, 'bold': True, 'color': NAVY})], first=True)
        tb = textbox(s, cx + Inches(0.24), Inches(5.68), Inches(5.66), Inches(0.72))
        put(tb, [(d, {'size': 14.5, 'color': TXT})], first=True, line_spacing=1.3)
        cx = cx + Inches(6.36)
    footer(s, 12, TOTAL)


def p13_readback(prs):
    s = blank(prs)
    y = header(s, '阶段 ④：读回与过滤——不是所有节点都能留下', 'zep_entity_reader.py，决定哪些实体能变成智能体')

    rect(s, MARGIN, Inches(1.30), Inches(5.5), Inches(3.1), fill='FFFFFF', line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(5.5), Inches(0.44), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(5.5), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('数据结构：EntityNode', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        '@dataclass',
        'class EntityNode:',
        '    uuid: str',
        '    name: str',
        '    labels: List[str]',
        '    summary: str',
        '    attributes: Dict[str, Any]',
        '    related_edges: List[Dict]   # 出/入边与 fact',
        '    related_nodes: List[Dict]   # 关联实体摘要',
    ]
    tb = textbox(s, MARGIN + Inches(0.24), Inches(1.92), Inches(5.02), Inches(2.3))
    put(tb, [(c, {'size': 13, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.2, space_after=0)

    rect(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(3.1), fill=BG2, line=LINE)
    rect(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(0.44), fill=RED, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('过滤规则：只有 Entity / Node 标签 → 丢弃', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, Inches(6.37), Inches(1.90), Inches(6.31), Inches(2.42))
    put(tb, [
        ('Zep 会为所有节点打上 Entity 标签；', {'size': 14.5, 'color': TXT}),
        ('只有被本体覆盖的节点才会多出一个具体标签。', {'size': 14.5, 'color': TXT}),
        ('', {'size': 7}),
        ('因此：本体没覆盖的实体，在这一步静默消失。', {'size': 15, 'bold': True, 'color': RED}),
        ('这不是 Zep 抽错了，是本体没给它一个位置。', {'size': 14.5, 'color': TXT}),
        ('', {'size': 7}),
        ('排查「实体太少」时，先看这里，再看抽取。', {'size': 14.5, 'bold': True, 'color': NAVY}),
    ], first=True, line_spacing=1.3, space_after=4)

    rect(s, MARGIN, Inches(4.62), CONTENT_W, Inches(2.0), fill=NAVY)
    tb = textbox(s, MARGIN + Inches(0.28), Inches(4.78), CONTENT_W - Inches(0.56), Inches(1.7))
    put(tb, [
        ('本体 10 个类型的硬顶，在这里变成实体多样性的天花板。', {'size': 19, 'bold': True, 'color': 'FFC107'}),
        ('一个真实后果：如果本体里没有「消费者协会」这类组织，相关实体全部进不了图，',
         {'size': 15, 'color': WHITE}),
        ('后续也就不会有人设、不会参与模拟——它在第一步就被提示词的「10 个」挤掉了。',
         {'size': 15, 'color': WHITE}),
    ], first=True, line_spacing=1.45, space_after=6)
    footer(s, 13, TOTAL)


def p15_profile(prs):
    s = blank(prs)
    y = header(s, '阶段 ⑤：画像生成——把实体写成人', 'oasis_profile_generator.py，每个实体一次模型调用')

    rect(s, MARGIN, Inches(1.30), Inches(5.5), Inches(5.3), fill=BG2, line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(5.5), Inches(0.44), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(5.5), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('输入：四段拼起来的上下文', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, MARGIN + Inches(0.24), Inches(1.92), Inches(5.02), Inches(4.5))
    put(tb, [
        ('① 实体属性', {'size': 16, 'bold': True, 'color': NAVY}),
        ('   full_name、role 等', {'size': 14.5, 'color': TXT2}),
        ('② 相关事实与关系（来自边的 fact）', {'size': 16, 'bold': True, 'color': NAVY}),
        ('   罗永浩质疑西贝使用预制菜…', {'size': 14.5, 'color': TXT2}),
        ('③ 关联实体摘要', {'size': 16, 'bold': True, 'color': NAVY}),
        ('   西贝（Company）：连锁餐饮企业…', {'size': 14.5, 'color': TXT2}),
        ('④ Zep 检索补充的事实', {'size': 16, 'bold': True, 'color': NAVY}),
        ('   图搜索 top 结果去重后并入', {'size': 14.5, 'color': TXT2}),
        ('', {'size': 8}),
        ('上下文整体截断到 3000 字符。', {'size': 15, 'bold': True, 'color': RED}),
        ('实体在图上边太少 → 上下文就薄 → 人设就空。', {'size': 15, 'color': TXT}),
    ], first=True, line_spacing=1.28, space_after=7)

    rect(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(5.3), fill='FFFFFF', line=LINE)
    rect(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(0.44), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(6.15), Inches(1.30), Inches(6.75), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('输出：OasisAgentProfile', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        '{',
        '  "bio": "锤子科技创始人，知名意见领袖…",',
        '  "persona": "（约 2000 字：基本信息 /',
        '     人物背景 / 性格特征 / 社媒行为 /',
        '     立场观点 / 个人记忆）",',
        '  "age": 53,',
        '  "gender": "male",',
        '  "mbti": "ENTP",',
        '  "country": "中国",',
        '  "profession": "创业者",',
        '  "interested_topics": ["餐饮","消费者权益"]',
        '}',
    ]
    tb = textbox(s, Inches(6.35), Inches(1.92), Inches(6.35), Inches(2.9))
    put(tb, [(c, {'size': 12.5, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.12, space_after=0)

    rect(s, Inches(6.35), Inches(4.72), Inches(6.35), Inches(1.85), fill=LBLUE, line=MBLUE)
    tb = textbox(s, Inches(6.55), Inches(4.84), Inches(5.95), Inches(1.66))
    put(tb, [
        ('提示词明确要求 persona 包含', {'size': 13.5, 'color': NAVY}),
        ('「这个个体在事件中的已有动作与反应」，', {'size': 13.5, 'color': NAVY}),
        ('让智能体带着真实历史进场。', {'size': 13.5, 'bold': True, 'color': NAVY}),
        ('', {'size': 6}),
        ('已知缺陷：follower_count 硬编码 150，', {'size': 13, 'color': RED}),
        ('影响力维度目前是假的。', {'size': 13, 'bold': True, 'color': RED}),
    ], first=True, line_spacing=1.25, space_after=2)
    footer(s, 15, TOTAL)


def p16_config(prs):
    s = blank(prs)
    y = header(s, '阶段 ⑥：行为与事件配置', 'simulation_config_generator.py，把实体翻译成可执行的模拟参数')

    left = [
        ('AgentActivityConfig（每个智能体一份）', MAIN, [
            'activity_level 活跃度 0–1',
            'posts_per_hour 发帖频率',
            'comments_per_hour 评论频率',
            'active_hours 活跃时段',
            'response_delay_min / max 响应延迟',
            'sentiment_bias 情绪倾向 −1~1',
            'stance 立场（4 选 1 英文枚举）',
            'influence_weight 影响力权重',
        ]),
    ]
    rect(s, MARGIN, Inches(1.30), Inches(6.05), Inches(4.05), fill=BG2, line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(6.05), Inches(0.44), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(6.05), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('行为配置：9 个字段', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    tb = textbox(s, MARGIN + Inches(0.24), Inches(1.92), Inches(5.57), Inches(3.25))
    put(tb, [(l, {'size': 14.5, 'color': TXT, 'name': MONO}) for _, _, ls in left for l in ls],
        first=True, line_spacing=1.32, space_after=4)

    rect(s, Inches(6.85), Inches(1.30), Inches(6.05), Inches(4.05), fill='FFFFFF', line=LINE)
    rect(s, Inches(6.85), Inches(1.30), Inches(6.05), Inches(0.44), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(6.85), Inches(1.30), Inches(6.05), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('事件与时间配置', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        'EventConfig:',
        '  hot_topics: ["预制菜","定价","知情权"]',
        '  narrative_direction: "从个人质疑扩散…"',
        '  initial_posts: [',
        '    { "content": "西贝的菜…",',
        '      "poster_type": "Celebrity" }',
        '  ]',
        '',
        'TimeSimulationConfig:',
        '  total_simulation_hours: 72   # 模型拍的',
        '  peak_hours: [19,20,21,22]',
        '  off_peak_hours: [0..5]',
    ]
    tb = textbox(s, Inches(7.05), Inches(1.92), Inches(5.65), Inches(3.25))
    put(tb, [(c, {'size': 13, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.22, space_after=0)

    rect(s, MARGIN, Inches(5.55), CONTENT_W, Inches(1.08), fill=LBLUE, line=MBLUE)
    tb = textbox(s, MARGIN + Inches(0.25), Inches(5.55), CONTENT_W - Inches(0.5), Inches(1.08), MSO_ANCHOR.MIDDLE)
    put(tb, [
        ('提示词里硬编码了一组经验规则：官方机构活跃度 0.1–0.3、媒体全天响应快、个人晚间活跃。',
         {'size': 15.5, 'color': NAVY}),
        ('而 total_simulation_hours、hot_topics、initial_posts 完全靠模型从文档里猜——这是可优化点。',
         {'size': 15.5, 'bold': True, 'color': RED}),
    ], first=True, line_spacing=1.35, space_after=4)
    footer(s, 16, TOTAL)


def p18_transform(prs):
    s = blank(prs)
    y = header(s, '变形复盘：同一条素材的七次改写', '以「罗永浩质疑西贝」为例，看信息如何被逐步结构化')

    rows = [
        ['#', '形态', '内容示例', '结构'],
        ['0', '原始文章', '2026 年 9 月 18 日晚，罗永浩发微博质疑西贝…', '自由文本'],
        ['1', '文档文本', '=== 文档 1: xxx.md ===\n2026 年 9 月 18 日…', 'str + 文档头'],
        ['2', '文本块', '…发微博质疑西贝使用预制菜…（500 字符窗口）', 'List[str]'],
        ['3', '本体', 'Celebrity / Company / CRITICIZES', 'dict（schema）'],
        ['4', '图节点', 'name=罗永浩, labels=[Entity, Celebrity]', 'Zep 节点'],
        ['5', '图边', 'CRITICIZES: 罗永浩 → 西贝（fact 文本）', 'Zep 边'],
        ['6', '实体对象', 'EntityNode + related_edges + related_nodes', 'dataclass'],
        ['7', '智能体', 'persona 2000 字 + stance=opposing + influence 2.8', 'profile + config'],
    ]
    tbl_h = Inches(5.35)
    shape = s.shapes.add_table(len(rows), 4, MARGIN, Inches(1.32), CONTENT_W, tbl_h)
    table = shape.table
    table.columns[0].width = Inches(0.6)
    table.columns[1].width = Inches(1.7)
    table.columns[2].width = Inches(7.2)
    table.columns[3].width = Inches(3.0)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.cell(ri, ci)
            cell.text = val
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = Inches(0.1)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            p = cell.text_frame.paragraphs[0]
            for r in p.runs:
                if ri == 0:
                    set_font(r, size=14, bold=True, color=WHITE)
                else:
                    set_font(r, size=13, bold=(ci <= 1),
                             color=(NAVY if ci <= 1 else TXT), name=(MONO if ci == 2 else CN))
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(NAVY if ri == 0 else (BG if ri % 2 else LBLUE2))

    tb = textbox(s, MARGIN, Inches(6.78), CONTENT_W, Inches(0.4))
    put(tb, [('规律：前两步在做「降维」（文本 → 窗口），中间在「升维」（加类型与关系），最后又「降维」成人设文本。',
              {'size': 14.5, 'bold': True, 'color': NAVY})], first=True)
    footer(s, 18, TOTAL)


def p19_loss(prs):
    s = blank(prs)
    y = header(s, '信息衰减：什么在每一步悄悄丢了', '这是判断「为什么模拟结果不对」的第一张地图')

    losses = [
        ('阶段 0 切块', RED, '来源、发布时间、传播量',
         '切块只保留字符，元信息不在块内 → 后文无从得知这条来自哪、什么时候。'),
        ('阶段 ③ 抽取', RED, '时间与顺序',
         'BatchAddItem 支持 created_at 但没有传，所有 episode 时间都是「现在」，演化顺序失真。'),
        ('阶段 ④ 过滤', RED, '本体未覆盖的实体',
         '只有 Entity / Node 标签的节点被丢弃，10 个类型之外的实体全部消失。'),
        ('阶段 ⑤ 画像', YELLOW, '上下文之外的细节',
         '上下文截断 3000 字符；边少的实体写出来的 persona 会很空。'),
        ('阶段 ⑥ 配置', YELLOW, '真实影响力',
         'follower_count 硬编码 150，用户名后缀随机数，影响力维度目前不反映现实。'),
    ]
    cur = Inches(1.28)
    for title, color, what, why in losses:
        rect(s, MARGIN, cur, CONTENT_W, Inches(1.02), fill=BG2, line=LINE)
        rect(s, MARGIN, cur, Inches(0.09), Inches(1.02), fill=color, shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, MARGIN + Inches(0.25), cur + Inches(0.1), Inches(2.1), Inches(0.38))
        put(tb, [(title, {'size': 15.5, 'bold': True, 'color': NAVY})], first=True)
        tb = textbox(s, MARGIN + Inches(0.25), cur + Inches(0.52), Inches(2.1), Inches(0.46))
        put(tb, [(what, {'size': 12.5, 'bold': True, 'color': color})], first=True)
        tb = textbox(s, Inches(2.95), cur + Inches(0.22), Inches(9.4), Inches(0.62), MSO_ANCHOR.MIDDLE)
        put(tb, [(why, {'size': 14.5, 'color': TXT})], first=True, line_spacing=1.25)
        cur = cur + Inches(1.09)

    rect(s, MARGIN, Inches(6.62), CONTENT_W, Inches(0.02), fill=LINE, shape=MSO_SHAPE.RECTANGLE)
    footer(s, 19, TOTAL)


def p20_appendix(prs):
    s = blank(prs)
    y = header(s, '附录：断点清单与离线验证', '不用启动服务就能验证前面大部分结论')

    rect(s, MARGIN, Inches(1.30), Inches(6.05), Inches(5.28), fill='FFFFFF', line=LINE)
    rect(s, MARGIN, Inches(1.30), Inches(6.05), Inches(0.44), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, MARGIN, Inches(1.30), Inches(6.05), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('断点打在这四处', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    bps = [
        ('ontology_generator.py:235', '看模型收到的完整 messages'),
        ('graph_builder.py:470', '看喂给 Zep 的文本块长什么样'),
        ('oasis_profile_generator.py:530', '看画像的上下文够不够'),
        ('report_agent.py:1460', '看工具调用如何执行'),
    ]
    tb = textbox(s, MARGIN + Inches(0.24), Inches(1.92), Inches(5.57), Inches(4.4))
    lines = []
    for f, d in bps:
        lines.append((f, {'size': 14.5, 'bold': True, 'color': NAVY, 'name': MONO}))
        lines.append((d, {'size': 14, 'color': TXT, 'space_after': 10}))
    put(tb, lines, first=True, line_spacing=1.3, space_after=2)

    rect(s, Inches(6.85), Inches(1.30), Inches(6.05), Inches(5.28), fill=BG2, line=LINE)
    rect(s, Inches(6.85), Inches(1.30), Inches(6.05), Inches(0.44), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    tb = textbox(s, Inches(6.85), Inches(1.30), Inches(6.05), Inches(0.44), MSO_ANCHOR.MIDDLE)
    put(tb, [('零成本看提示词（不烧 token）', {'size': 16, 'bold': True, 'color': WHITE, 'align': PP_ALIGN.CENTER})], first=True)
    code = [
        'from app.services.ontology_generator \\',
        '    import OntologyGenerator',
        '',
        '# 用 __new__ 绕过 __init__，不建 LLMClient',
        'g = OntologyGenerator.__new__(',
        '        OntologyGenerator)',
        'print(g._build_user_message(',
        '    ["罗永浩质疑西贝预制菜"],',
        '    "预测西贝舆情走势", None))',
    ]
    tb = textbox(s, Inches(7.05), Inches(1.92), Inches(5.65), Inches(2.6))
    put(tb, [(c, {'size': 12.5, 'color': TXT, 'name': MONO}) for c in code],
        first=True, line_spacing=1.16, space_after=0)

    tb = textbox(s, Inches(7.05), Inches(4.62), Inches(5.65), Inches(1.8))
    put(tb, [
        ('四个会浪费时间的坑', {'size': 16, 'bold': True, 'color': NAVY}),
        ('1. 后台线程异常被 fail_task 吞掉，日志无堆栈', {'size': 13.5, 'color': TXT}),
        ('2. TaskManager 是内存单例，重启后任务全丢', {'size': 13.5, 'color': TXT}),
        ('3. 调试配置必须加 --no-reload，否则断点不命中', {'size': 13.5, 'color': TXT}),
        ('4. 模拟子进程断点进不去，需手动运行脚本', {'size': 13.5, 'color': TXT}),
    ], first=True, line_spacing=1.3, space_after=4)
    footer(s, 20, TOTAL)


def p21_ending(prs):
    s = blank(prs)
    rect(s, Inches(0), Inches(0), W, H, fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(0), Inches(6.9), W, Inches(0.6), fill=MAIN, shape=MSO_SHAPE.RECTANGLE)
    rect(s, Inches(1.0), Inches(1.85), Inches(0.09), Inches(3.0), fill='FFC107', shape=MSO_SHAPE.RECTANGLE)

    tb = textbox(s, Inches(1.35), Inches(1.85), Inches(11), Inches(0.9))
    put(tb, [('三句话记住这套系统', {'size': 40, 'bold': True, 'color': WHITE})], first=True)

    pts = [
        ('数据只认文本', '结构化字段必须渲染进正文，否则等于没传。'),
        ('抽取不在本地', '实体与边由 Zep 云端完成，能改的只有本体定义与文本质量。'),
        ('领域自适应在本体', '10 个类型由模型按任务现场生成，种子越通用，下游越自由。'),
    ]
    cur = Inches(3.05)
    for t, d in pts:
        rect(s, Inches(1.35), cur + Inches(0.08), Inches(0.16), Inches(0.42), fill='FFC107', shape=MSO_SHAPE.RECTANGLE)
        tb = textbox(s, Inches(1.72), cur, Inches(10.2), Inches(0.5))
        put(tb, [(t, {'size': 23, 'bold': True, 'color': 'FFC107'})], first=True)
        tb = textbox(s, Inches(1.72), cur + Inches(0.52), Inches(10.2), Inches(0.45))
        put(tb, [(d, {'size': 17, 'color': 'FFFFFF'})], first=True)
        cur = cur + Inches(1.15)

    tb = textbox(s, Inches(1.35), Inches(7.03), Inches(11), Inches(0.35))
    put(tb, [('配套文档：docs/debugging-guide.md · docs/tech-roadmap.md · docs/seed-package-schema.md',
              {'size': 14, 'color': 'FFFFFF'})], first=True)


def main():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    p01_cover(prs)
    p02_catalog(prs)
    section(prs, '01', '全景与总览', [
        '六个阶段，三个执行者交替接力',
        '只有实体抽取不在本项目内',
        '一张表看清每一步的输入与输出',
    ], 3)
    p04_pipeline(prs)
    p05_table(prs)
    section(prs, '02', '种子与文本', [
        '文件如何变成字符串与文本块',
        '本体如何被模型设计出来',
        '代码在模型返回后又改了什么',
    ], 6)
    p07_stage0(prs)
    p08_ontology(prs)
    p09_validate(prs)
    section(prs, '03', '文本到知识图谱', [
        'JSON 本体如何变成 Zep 的类型约束',
        '实体抽取的黑盒里发生了什么',
        '读回时谁被留下、谁被丢弃',
    ], 10)
    p11_load(prs)
    p12_zep(prs)
    p13_readback(prs)
    section(prs, '04', '图谱到智能体', [
        '实体如何被写成人设',
        '行为参数与事件如何被配置',
        '哪些参数是模型猜出来的',
    ], 14)
    p15_profile(prs)
    p16_config(prs)
    section(prs, '05', '变形复盘与附录', [
        '同一条素材的七次改写',
        '信息在哪些步骤悄悄丢失',
        '断点清单与离线验证命令',
    ], 17)
    p18_transform(prs)
    p19_loss(prs)
    p20_appendix(prs)
    p21_ending(prs)

    out = '/home/A/ysy/fish/MiroFish数据流转/MiroFish数据流转全景.pptx'
    prs.save(out)
    print('saved:', out, 'slides:', len(prs.slides.__iter__.__self__._sldIdLst))


if __name__ == '__main__':
    main()
