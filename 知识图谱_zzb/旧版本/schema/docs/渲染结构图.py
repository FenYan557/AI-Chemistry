# -*- coding: utf-8 -*-
"""渲染 Schema v1.1 的知识图谱结构图（一页纸版）· v2

用法：python -X utf8 docs/渲染结构图.py
输出：docs/知识图谱结构图.png
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['axes.unicode_minus'] = False

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '知识图谱结构图.png')

C_IN, C_L0, C_L2, C_L3, C_L4, C_OUT = '#64748B', '#2563EB', '#0E9F6E', '#D97706', '#9333EA', '#475569'
GRAY, LIGHT = '#334155', '#94A3B8'

fig, ax = plt.subplots(figsize=(16.5, 11.4), dpi=170)
ax.set_xlim(0, 24)
ax.set_ylim(0, 16.2)
ax.axis('off')


def band(y0, y1, color, label, x0=0.35, x1=23.65):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle='round,pad=0,rounding_size=0.18',
                                fc=color, ec='none', alpha=0.07, zorder=0))
    ax.add_patch(FancyBboxPatch((x0, y0), 0.30, y1 - y0,
                                boxstyle='round,pad=0,rounding_size=0.08',
                                fc=color, ec='none', alpha=0.88, zorder=1))
    ax.text(x0 + 0.155, (y0 + y1) / 2, label, rotation=90, va='center', ha='center',
            fontsize=10.2, color='white', fontweight='bold', zorder=2)


def node(x, y, w, h, name, gloss, color, ghost=False, fs=11.2, gfs=8.1):
    x0, y0 = x - w / 2, y - h / 2
    if ghost:
        ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                    fc='white', ec=color, lw=1.2, ls=(0, (3, 2)), alpha=0.92, zorder=3))
    else:
        ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                    fc='white', ec=color, lw=1.7, alpha=1.0, zorder=3))
        ax.add_patch(FancyBboxPatch((x0, y0 + h - 0.075), w, 0.075,
                                    boxstyle='round,pad=0,rounding_size=0.04',
                                    fc=color, ec='none', alpha=0.85, zorder=4))
    ax.text(x, y + h / 2 - 0.33, name, ha='center', va='center', fontsize=fs,
            color=color if ghost else GRAY, fontweight='bold', zorder=5)
    if gloss:
        ax.text(x, y - 0.22, gloss, ha='center', va='center', fontsize=gfs, color=GRAY,
                linespacing=1.35, zorder=5)
    return (x0, y0, w, h)


def side(r, s):
    x0, y0, w, h = r
    return {'left': (x0, y0 + h / 2), 'right': (x0 + w, y0 + h / 2),
            'top': (x0 + w / 2, y0 + h), 'bottom': (x0 + w / 2, y0)}[s]


def arrow(p1, p2, label=None, color=GRAY, dashed=False, lw=1.35, rad=0.0,
          fs=7.5, lx=0.0, ly=0.0, ha='center'):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=13, lw=lw,
                                 color=color, alpha=0.92,
                                 ls=(0, (4, 2.5)) if dashed else '-',
                                 connectionstyle='arc3,rad=%s' % rad,
                                 shrinkA=1.5, shrinkB=2.5, zorder=2))
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + lx, (p1[1] + p2[1]) / 2 + ly
        ax.text(mx, my, label, ha=ha, va='center', fontsize=fs, color=color,
                bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)


def elbow(pts, label=None, color=GRAY, dashed=False, lw=1.35, fs=7.5, at=0.5, lx=0.0, ly=0.0):
    """折线路径：前几段用直线，最后一段带箭头。"""
    for i in range(len(pts) - 2):
        ax.plot([pts[i][0], pts[i + 1][0]], [pts[i][1], pts[i + 1][1]],
                color=color, lw=lw, ls=(0, (4, 2.5)) if dashed else '-', alpha=0.92, zorder=2)
    arrow(pts[-2], pts[-1], color=color, dashed=dashed, lw=lw)
    if label:
        # 取中间段的标签位置
        (x1, y1), (x2, y2) = pts[1], pts[2] if len(pts) > 3 else pts[1]
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, ha='center', va='center',
                fontsize=fs, color=color,
                bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)


def note(x, y, w, h, lines, color, title=None, fs=8.3, tfs=9.3, step=0.38):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.14',
                                fc='#FFFBEB', ec=color, lw=1.0, alpha=0.96, zorder=3))
    ty = y + h - 0.32
    if title:
        ax.text(x + 0.20, ty, title, ha='left', va='center', fontsize=tfs,
                color=color, fontweight='bold', zorder=4)
        ty -= step + 0.04
    for ln in lines:
        ax.text(x + 0.20, ty, ln, ha='left', va='center', fontsize=fs, color=GRAY, zorder=4)
        ty -= step


# ── 标题 ───────────────────────────────────────────────────────────────
ax.text(0.40, 15.95, '电镀添加剂选型知识图谱 · 结构总览', fontsize=20, fontweight='bold', color='#0F172A')
ax.text(0.42, 15.50, 'Schema v1.1 ｜ 24 类节点 · 34 条边 · 16 个谓词 · 51 条约束 ｜ '
        '图只画主干，字段与逐条规则见 docs/实体关系与约束清单.md', fontsize=10, color=LIGHT)

# ── 输入 ───────────────────────────────────────────────────────────────
band(14.25, 15.30, C_IN, '输入')
node(4.90, 14.78, 8.2, 0.90, '48 篇清洗产物', 'blocks 5316 · chunks 5638 · 表格 98 张 · 图注 809', C_IN)
node(15.90, 14.78, 12.9, 0.90, '两份契约，不产数据',
     'claims.schema.json（抽取输出 = 归一化输入）  →  nodes.jsonl / edges.jsonl', C_IN)

# ── L0 锚点层 ──────────────────────────────────────────────────────────
band(12.55, 14.05, C_L0, 'L0 锚点层')
d = node(2.65, 13.28, 2.2, 1.05, 'Document', '一篇文献\n归属与版本', C_L0, fs=10.6)
b = node(5.35, 13.28, 2.2, 1.05, 'Block', '一段可回读的原文\n位置哈希 ID', C_L0, fs=10.6)
tb = node(8.02, 13.28, 2.2, 1.05, 'Table', '表 + 单元格\n数值锚点', C_L0, fs=10.6)
fg = node(10.45, 13.28, 2.2, 1.05, 'Figure', '图 + 图注\n只登记不反推', C_L0, fs=10.6)
eq = node(12.75, 13.28, 2.2, 1.05, 'Equation', '公式\n指标定义来源', C_L0, fs=10.6)
bb = node(15.02, 13.28, 2.2, 1.05, 'BibEntry', '参考文献条目\nP1 · 待 enrich', C_L0, fs=10.6, ghost=True)
arrow(side(d, 'right'), side(b, 'left'), 'HAS_*', fs=7.0, ly=0.20)
note(16.75, 12.62, 6.8, 1.36, [
    'anchor = doc_id + page + quote；锚点全挂 Document（C-ANCHOR-01/03）',
    'quote 须与 block.text 子串匹配，复述式引用拒收（C-ANCHOR-02）',
    '表格数值必须锚到 row/col，整表锚点不认（C-ANCHOR-04）',
], C_L0, title='没有可回读位置的句子，在图里不存在', fs=7.9, tfs=9.0)

# ── L2 事件层 + L1 观测层 ──────────────────────────────────────────────
band(9.15, 12.30, C_L2, 'L2 事件层 · L1 观测层')
ex = node(2.45, 10.95, 2.4, 1.15, 'Experiment', '共享装置/浴液的\n实验系列', C_L2, fs=10.6)
rn = node(5.75, 10.95, 2.4, 1.15, 'Run', '一次条件组合\n表格一行', C_L2, fs=10.6)
au = node(9.05, 10.95, 2.8, 1.15, 'AdditiveUsage', '某分子在本次实验\n的角色 + 浓度', C_L2, fs=10.6)
ob = node(13.60, 10.95, 3.2, 1.35, 'Observation', '一个测量结果\n值 + 单位 + 口径', C_L2, fs=12.0)

arrow(side(ex, 'right'), side(rn, 'left'), 'HAS_RUN', ly=0.21, fs=7.2)
arrow(side(rn, 'right'), side(au, 'left'), 'USES', ly=0.21, fs=7.2)
elbow([(5.75, 10.375), (5.75, 9.42), (12.30, 9.42), (12.30, 10.28)], color=C_L2)
ax.text(6.98, 9.58, 'YIELDS', fontsize=7.2, color=C_L2, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
elbow([(5.35, 12.705), (5.35, 12.00), (13.60, 12.00), (13.60, 11.63)], color=C_L0, dashed=True)
ax.text(9.50, 12.17, 'measured_at → anchor', fontsize=7.2, color=C_L0, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
note(16.50, 9.62, 7.05, 0.84, [
    '空条件的 Run 不许存在（C-EXP-01）；扫的轴须真有 ≥2 个取值（C-EXP-02）',
], C_L2, title='条件与结果钉在同一单元里', fs=7.5, tfs=9.0)

# ── L3 概念层 ──────────────────────────────────────────────────────────
band(6.10, 9.05, C_L3, 'L3 概念层')
y1 = 8.30
bath = node(2.55, y1, 2.05, 1.05, 'Bath', '具体镀液\n篇内不合并', C_L3, fs=10.2)
bcl = node(4.84, y1, 2.05, 1.05, 'BathClass', '体系类别\n11 类枚举', C_L3, fs=10.2)
fea = node(7.13, y1, 2.05, 1.05, 'Feature', '通孔/盲孔/沟槽\nAR 与孔径', C_L3, fs=10.2)
rol = node(9.42, y1, 2.05, 1.05, 'Role', '功能角色\n13 类枚举', C_L3, fs=10.2)
che = node(11.71, y1, 2.05, 1.05, 'Chemical', '物质身份\nInChIKey 为准', C_L3, fs=10.2)
mot = node(14.00, y1, 2.05, 1.05, 'Motif', '结构基元\n20 条（草案）', C_L3, fs=10.2)
ind = node(16.29, y1, 2.05, 1.05, 'Indicator', '37 个指标\n分四族', C_L3, fs=10.2)
met = node(18.58, y1, 2.05, 1.05, 'Method', '测量手段\n17 类枚举', C_L3, fs=10.2)
mec = node(20.87, y1, 2.05, 1.05, 'Mechanism', '机理模式\n12 类枚举', C_L3, fs=10.2)
par = node(22.85, y1, 1.60, 1.05, 'Parameter', '变量注册表\n不落节点', C_L3, fs=9.4, ghost=True)

arrow((5.35, 10.375), (2.55, 8.825), color=C_L3, lw=1.3)
ax.text(3.90, 9.86, 'IN_BATH', fontsize=7.0, color=C_L3, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
arrow((8.62, 10.375), (9.42, 8.825), color=C_L3, lw=1.3)
ax.text(8.55, 9.90, 'HAS_ROLE', fontsize=7.0, color=C_L3, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
arrow((9.55, 10.375), (11.71, 8.825), color=C_L3, lw=1.3)
ax.text(10.44, 9.84, 'OF_CHEMICAL', fontsize=7.0, color=C_L3, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
arrow((14.55, 10.28), (16.29, 8.825), color=C_L3, lw=1.3)
ax.text(15.72, 9.70, 'MEASURES', fontsize=7.0, color=C_L3, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
arrow((11.71, 8.825), (20.87, 8.825), color=C_L3, rad=-0.045, lw=1.3)
ax.text(17.45, 9.14, 'OPERATES_BY', fontsize=7.0, color=C_L3, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)

note(2.55, 6.15, 9.90, 1.45, [
    '角色属于工况，不属于分子（C-ROLE-01）',
    '整平结论必须带孔型与 AR（C-IND-02）；跨族指标不得当选型证据（C-IND-04）',
    'Motif 共享的是结构，不是效果；机理须经 EXPLAINS 接回观测（C-EXPLAIN-01）',
], C_L3, title='概念层的几句硬话', fs=7.8, tfs=9.0, step=0.30)
note(12.75, 6.15, 10.80, 1.45, [
    'has_role · affects_indicator · improves · degrades · causes_defect · invalid_in',
    'component_of · has_motif · acts_by · precedes · motif_improves · analogous_to',
    'derived_from · defined_by · supersedes · reported_in ｜ 论断经 ABOUT 挂到观测与概念',
], C_L3, title='16 个谓词是 Claim 唯一合法的关系名（未登记 → 待审，不得入图）', fs=7.4, tfs=8.8, step=0.30)

# ── L4 知识层 ──────────────────────────────────────────────────────────
band(3.05, 5.95, C_L4, 'L4 知识层')
el = node(3.05, 4.45, 2.90, 1.30, 'EvidenceLink', '支撑关系 + 证据等级\nT1–T4', C_L4, fs=10.8)
cl = node(7.60, 4.45, 2.70, 1.30, 'Claim', '我们的结构化论断\n谓词 + 窗口 + 极性', C_L4, fs=11.6)
cf = node(12.05, 4.45, 2.50, 1.30, 'Conflict', '同口径内的矛盾\n+ 裁决类型', C_L4, fs=10.8)
ku = node(16.60, 4.45, 3.30, 1.30, 'KnowledgeUnit', '同口径证据聚合\n有效窗口 + 支持度', C_L4, fs=11.6)

arrow(side(el, 'right'), side(cl, 'left'), 'SUPPORTED_BY', lw=1.8, fs=8.0, ly=0.22)
arrow(side(cl, 'right'), side(cf, 'left'), 'IN_CONFLICT', lw=1.5, fs=7.6, ly=0.22)
arrow((8.60, 3.86), (14.90, 3.92), color=C_L4, lw=2.0, rad=0.12)
ax.text(11.60, 3.30, 'AGGREGATES', fontsize=8.0, color=C_L4, ha='center', va='center',
        bbox=dict(boxstyle='round,pad=0.16', fc='white', ec='none', alpha=0.94), zorder=6)
arrow((2.20, 5.10), (2.20, 6.08), color=C_L4, dashed=True)
ax.text(2.45, 5.72, 'EVIDENCE：anchors 回读 L0（Block / TableCell / Figure / Equation）',
        fontsize=7.5, color=C_L4, ha='left', va='center', zorder=6)
note(18.70, 3.20, 4.80, 2.00, [
    '① 锚点：每条事实能回查到',
    '    块 / 单元格 / 图 / 式',
    '② 口径：comparability_key',
    '    不同不得比大小',
    '③ 聚合：KU.tier 不高于',
    '    最强的那条单条证据',
], C_L4, title='三道门禁', fs=7.8, tfs=9.2, step=0.27)

# ── 输出 ───────────────────────────────────────────────────────────────
band(1.45, 2.85, C_OUT, '输出')
o1 = node(4.20, 2.15, 6.0, 1.05, '选型推荐', '同口径内偏序：tier → 共识 → 文献数 → 年份', C_OUT, fs=11.2)
o2 = node(11.90, 2.15, 6.0, 1.05, '化学问答', '机理链 + 逐条证据，必须能落到原文', C_OUT, fs=11.2)
o3 = node(19.40, 2.15, 6.2, 1.05, '拒答 / 说不知道', '缺参数或口径不同时输出 missing_params', C_OUT, fs=11.2)
for src, tgt in ((15.20, o1), (16.60, o2), (18.00, o3)):
    xx = tgt[0] + tgt[2] / 2
    elbow([(src, 3.80), (src, 2.98), (xx, 2.98), (xx, 2.68)], color=C_OUT, lw=1.2)

# ── 图例与脚注 ─────────────────────────────────────────────────────────
ax.add_patch(FancyArrowPatch((0.62, 1.05), (1.45, 1.05), arrowstyle='-|>', mutation_scale=12, lw=1.4, color=GRAY))
ax.text(1.60, 1.05, '结构 / 数据流', fontsize=8.4, va='center', color=GRAY)
ax.add_patch(FancyArrowPatch((4.10, 1.05), (4.93, 1.05), arrowstyle='-|>', mutation_scale=12, lw=1.4,
                             color=GRAY, ls=(0, (4, 2.5))))
ax.text(5.08, 1.05, '回查 / 校验', fontsize=8.4, va='center', color=GRAY)
ax.add_patch(FancyBboxPatch((7.30, 0.94), 0.70, 0.22, boxstyle='round,pad=0,rounding_size=0.06',
                            fc='white', ec=C_L3, lw=1.1, ls=(0, (3, 2))))
ax.text(8.12, 1.05, '虚线框 = 词表枚举，不落实例', fontsize=8.4, va='center', color=GRAY)
ax.text(0.62, 0.62,
        '读法：文献先落成可回读的锚点 → 锚点与条件产生观测 → 观测被概念层解释 → '
        'Claim / EvidenceLink 形成可判冲突、可聚合的知识 → 出口只有排序、带证据的回答、明确的拒答。',
        fontsize=8.2, color=GRAY)
ax.text(0.62, 0.26,
        '未画的边：NEXT · CITES · REFERS_TO · CONTROL_OF · ON_FEATURE · BY_METHOD · OF_CLASS · CONTAINS · '
        'ALIAS_OF · SIMILAR_TO · DERIVED_FROM · PRECEDES · DEFINES · IN_CLASS · CONTRADICTS · ABOUT（端点 8 类）',
        fontsize=7.6, color=LIGHT)

plt.tight_layout(pad=0.2)
fig.savefig(OUT, bbox_inches='tight', facecolor='white')
print('已输出:', OUT)
