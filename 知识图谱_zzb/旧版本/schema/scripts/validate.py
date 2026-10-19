#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""断言层校验器 —— 把 schema/constraints/lexicon 变成可执行门禁。

本脚本只校验"断言 JSONL"这种中间产物，不产图、不读语料（除非显式给 --corpus）。

用法：
  python validate.py --claims claims.jsonl
  python validate.py --claims claims.jsonl --corpus "<清洗产物目录>"   # 额外核对 block_id/quote/单元格
  python validate.py --claims claims.jsonl --json report.json

三层检查：
  1) 结构层：claims.schema.json（JSON Schema 2020-12）
  2) 约束层：constraints.yaml 里 check 键与本文件同名函数
  3) 语料层（可选）：--corpus 给定时核对 block_id 存在、quote 命中原文、表格单元格对齐

图层规则（可比性键、聚合层阈值、解释链）在 validate_graph.py，不在本文件。
输出每条断言一行判定（pass / downgrade / reject）；退出码 1 表示存在 reject。
未实现的规则会明确列在报告里（不假装做过）。
"""
import argparse
import csv
import difflib
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

import yaml
from jsonschema import Draft202012Validator

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SEV_ORDER = {'warn': 0, 'downgrade': 1, 'reject': 2}
NUMERIC_INDICATORS_UNIT_REQUIRED = {
    'delta_eta', 'potential_shift', 'filling_ratio', 'tp', 'dimple', 'hardness',
    'glossiness', 'roughness', 'resistivity', 'stress', 'mtf', 'contact_angle',
    'surface_energy', 'thickness', 'homo', 'lumo', 'energy_gap', 'adsorption_energy',
    'binding_energy', 'electronegativity', 'chemical_hardness', 'e_corr', 'j_corr',
    'r_ct', 'c_dl', 'areal_charge', 'diffusion_coeff', 'composition_at',
    'composition_wt', 'grain_size',
}
POTENTIAL_INDICATORS = {'delta_eta', 'potential_shift', 'e_corr'}
AMBIGUOUS_INDICATORS = {'energy_gap', 'potential_shift', 'delta_eta', 'chemical_hardness'}
FILLING_NEEDS_FEATURE = {'filling_ratio', 'void_seam', 'dimple'}


# ── 载入 ────────────────────────────────────────────────────────────────────
def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_lexicon():
    lex = {}
    for name in ['units_params', 'entities', 'indicators', 'structures_methods',
                 'pitfalls', 'tables_sections']:
        lex[name] = load_yaml(os.path.join(ROOT, 'lexicon', name + '.yaml'))
    units = set()
    for group in lex['units_params']['units'].values():
        if not isinstance(group, dict):
            continue
        if group.get('canonical'):
            units.add(group['canonical'])
            for alias in (group.get('exact_scale') or {}):
                units.add(alias)
        for alias in (group.get('inexact') or {}):
            units.add(alias)
    lex['_units'] = units
    lex['_params'] = set(lex['units_params']['params'])
    lex['_indicators'] = set(lex['indicators']['indicators'])
    lex['_roles'] = set(lex['entities']['roles'])
    lex['_motifs'] = set(lex['structures_methods']['motifs'])
    lex['_mechanisms'] = set(lex['structures_methods']['mechanisms'])
    return lex


def load_schema():
    schema = load_yaml(os.path.join(ROOT, 'schema.yaml'))
    preds = {p['name']: p for p in schema['predicates']}
    return schema, preds


def build_corpus_index(corpus):
    """block_id → 块记录；table_id → csv 路径 + 画像线索。优先读新 blocks/，退回 enriched/。"""
    if not corpus or not os.path.isdir(corpus):
        return None
    blocks, tables, docs, table_meta = {}, {}, set(), {}
    src = os.path.join(corpus, 'blocks', '*.jsonl')
    if not glob.glob(src):
        src = os.path.join(corpus, 'enriched', '*.jsonl')
    for path in glob.glob(src):
        doc_id = os.path.basename(path)[:-len('.jsonl')]
        docs.add(doc_id)
        with open(path, encoding='utf-8') as f:
            for line in f:
                d = json.loads(line)
                bbox = ','.join(str(int(x)) for x in d.get('bbox') or [0, 0, 0, 0])
                part = d.get('part') or 0          # 长段切分后各 part 共享 bbox，必须进哈希
                key = '%s|%s|%s|%s|%s' % (doc_id, d.get('page'), bbox, d.get('type'), part)
                block_id = 'blk:' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]
                blocks[block_id] = {
                    'doc_id': doc_id, 'page': d.get('page'), 'type': d.get('type'),
                    'text': d.get('text') or d.get('caption') or '',
                }
                tm = d.get('table_meta') or {}
                if not tm and d.get('csv'):
                    tm = {k: d.get(k) for k in ('class', 'header', 'n_rows', 'n_cols',
                                                'evidence', 'ocr_status', 'csv')}
                if tm.get('csv'):
                    base = os.path.basename(str(tm['csv']).replace('\\', '/'))[:-4]
                    m = re.match(r'^(?P<doc>.+)__p(?P<page>\d+)_(?P<i>\d+)$', base)
                    if m:
                        table_meta['tbl:%s:p%s:%s' % (m.group('doc'), m.group('page'), m.group('i'))] = {
                            'class': tm.get('class'), 'header': tm.get('header'),
                            'n_rows': tm.get('n_rows'), 'n_cols': tm.get('n_cols'),
                            'evidence': tm.get('evidence'), 'ocr_status': tm.get('ocr_status'),
                        }
    for path in glob.glob(os.path.join(corpus, 'tables', '*.csv')):
        name = os.path.basename(path)[:-4]
        m = re.match(r'^(?P<doc>.+)__p(?P<page>\d+)_(?P<i>\d+)$', name)
        if m:
            tid = 'tbl:%s:p%s:%s' % (m.group('doc'), m.group('page'), m.group('i'))
            tables[tid] = path
    # 若 blocks 里没有画像（旧 enriched 或无表块），退回 _tables_index.csv，按 (doc,page) 顺序对齐
    idx = os.path.join(corpus, 'tables', '_tables_index.csv')
    if os.path.isfile(idx) and len(table_meta) < len(tables):
        by_page = {}
        for row in csv.DictReader(open(idx, encoding='utf-8-sig')):
            by_page.setdefault((row.get('doc_id'), row.get('page')), []).append(row)
        for tid in tables:
            m = re.match(r'^tbl:(?P<doc>.+):p(?P<page>\d+):(?P<i>\d+)$', tid)
            if not m or tid in table_meta:
                continue
            rows = by_page.get((m.group('doc'), m.group('page'))) or []
            i = int(m.group('i'))
            if i < len(rows):
                table_meta[tid] = {'class': rows[i].get('class'), 'header': rows[i].get('header')}
    return {'blocks': blocks, 'tables': tables, 'docs': docs, 'table_meta': table_meta}


def norm(s):
    if not s:
        return ''
    s = s.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2013', '-').replace('\u2014', '-').replace('\u2212', '-')
    return re.sub(r'\s+', ' ', s).strip()


# ── 检查函数：名字与 constraints.yaml 的 check 键一致 ───────────────────────
def check_anchor_required(ctx):
    if not ctx['anchors']:
        return 'reject', '无锚点'
    for a in ctx['anchors']:
        if not a.get('doc_id') or not a.get('page'):
            return 'reject', '锚点缺 doc_id/page: %s' % a.get('kind')
    return None


def check_block_id_exists(ctx):
    corpus = ctx['corpus']
    if not corpus:
        return None
    missing = [a['block_id'] for a in ctx['anchors']
               if a.get('kind') == 'block' and a.get('block_id') not in corpus['blocks']]
    if missing:
        return 'reject', 'block_id 不存在: %s' % ','.join(missing[:3])
    return None


def check_quote_must_match_block(ctx):
    corpus = ctx['corpus']
    if not corpus:
        return None
    problems = []
    for a in ctx['anchors']:
        quote = norm(a.get('quote'))
        if not quote:
            problems.append('空 quote')
            continue
        if a.get('kind') == 'block':
            rec = corpus['blocks'].get(a.get('block_id'))
            if not rec:
                continue
            text = norm(rec['text'])
            if quote in text:
                a['quote_check'] = 'exact'
                continue
            ratio = difflib.SequenceMatcher(None, quote, text).ratio()
            if ratio >= 0.90 or quote[:40] in text:
                a['quote_check'] = 'fuzzy'
                continue
            a['quote_check'] = 'failed'
            problems.append('quote 未命中 %s（相似度 %.2f）' % (a.get('block_id'), ratio))
        elif a.get('kind') == 'table_cell':
            path = corpus['tables'].get(a.get('table_id'))
            if not path:
                problems.append('table_id 未知: %s' % a.get('table_id'))
                continue
            rows = list(csv.reader(open(path, encoding='utf-8-sig')))
            r, c = a.get('row'), a.get('col')
            if r is None or c is None or r >= len(rows) or c >= len(rows[r]):
                problems.append('单元格越界 %s r%s c%s' % (a.get('table_id'), r, c))
                continue
            cell = norm(rows[r][c])
            if quote in cell or cell == quote:
                a['quote_check'] = 'exact'
            else:
                problems.append('单元格内容不符: 期望 %r 实际 %r' % (quote, cell))
    if problems:
        return 'reject', '; '.join(problems[:3])
    return None


def check_numeric_from_table_cell(ctx):
    rec = ctx['rec']
    magnitude = ((rec.get('object') or {}).get('magnitude') or '')
    if not re.match(r'^\s*[-+]?\d', str(magnitude)):
        return None
    if not any(a.get('kind') == 'table_cell' for a in ctx['anchors']):
        return 'warn', '数值未锚到表格单元格（只锚到整段）'
    return None


def check_numeric_requires_unit(ctx):
    rec, lex = ctx['rec'], ctx['lex']
    obj = rec.get('object') or {}
    ind = obj.get('indicator')
    magnitude = str(obj.get('magnitude') or '').strip()
    if ind in NUMERIC_INDICATORS_UNIT_REQUIRED and magnitude:
        has_unit = bool(re.search(r'[A-Za-z%°Ω]', magnitude))
        if not has_unit:
            return 'reject', '%s 的数值缺单位: %r（C-UNIT-01）' % (ind, magnitude)
    for pv in (rec.get('window') or {}).get('params') or []:
        if pv.get('presence') != 'reported':
            continue
        if pv.get('kind') in ('point', 'range') and not pv.get('unit'):
            return 'reject', '参数 %s 缺单位: %r' % (pv.get('param'), pv.get('raw'))
        unit = pv.get('unit')
        if unit and unit not in lex['_units']:
            return 'reject', '单位不在白名单: %s' % unit
    return None


def check_param_registered(ctx):
    known = ctx['lex']['_params']
    conc_seen = 0
    for pv in (ctx['rec'].get('window') or {}).get('params') or []:
        p = pv.get('param')
        if p not in known:
            return 'reject', '未登记参数: %s' % p
        if p == 'concentration':
            conc_seen += 1
            if conc_seen > 1 and not pv.get('of'):
                return 'reject', '同窗口多个浓度但缺 of 字段（分不清是谁的浓度）'
    return None


def check_concentration_basis_consistency(ctx):
    bases = set()
    for pv in (ctx['rec'].get('window') or {}).get('params') or []:
        if pv.get('param') == 'concentration' and pv.get('presence') == 'reported':
            bases.add(pv.get('basis') or 'unknown')
    if len([b for b in bases if b != 'unknown']) > 1:
        return 'reject', '同窗口跨 basis 浓度混用: %s' % sorted(bases)
    return None


def check_window_bounds_valid(ctx):
    for pv in (ctx['rec'].get('window') or {}).get('params') or []:
        if pv.get('kind') == 'range':
            lo, hi = pv.get('lo'), pv.get('hi')
            if lo is None or hi is None:
                return 'reject', '区间参数 %s 缺 lo/hi' % pv.get('param')
            if lo > hi:
                return 'reject', '区间反了 %s: %s > %s' % (pv.get('param'), lo, hi)
    return None


def check_not_reported_not_satisfied(ctx):
    params = (ctx['rec'].get('window') or {}).get('params') or []
    if not params:
        return None
    if all(pv.get('presence') == 'not_reported' for pv in params):
        return 'downgrade', '窗口里没有一个已报道参数（全是 not_reported）→ 只能定性'
    return None


def check_predicate_registered(ctx):
    if ctx['rec'].get('predicate') not in ctx['preds']:
        return 'warn', '谓词未登记: %s → 进待审区，入图前需人工决定合并或新增' % ctx['rec'].get('predicate')
    return None


def check_predicate_slot_match(ctx):
    sig = ctx['preds'].get(ctx['rec'].get('predicate'))
    if not sig:
        return None
    sub_t = (ctx['rec'].get('subject') or {}).get('type')
    obj_t = (ctx['rec'].get('object') or {}).get('type')
    allowed_sub = [t.strip() for t in sig['signature'].split('->')[0].split('|')]
    allowed_obj = [t.strip() for t in sig['signature'].split('->')[1].split('|')]
    if sub_t not in allowed_sub:
        return 'reject', 'subject 类型 %s 不在 %s 签名内' % (sub_t, sig['name'])
    if obj_t not in allowed_obj:
        return 'reject', 'object 类型 %s 不在 %s 签名内' % (obj_t, sig['name'])
    has_win = bool((ctx['rec'].get('window') or {}).get('params'))
    if sig.get('window') == 'required' and not has_win:
        return 'reject', '%s 要求带窗口，实际没有' % sig['name']
    if sig.get('window') == 'forbidden' and has_win:
        return 'reject', '%s 不允许带窗口' % sig['name']
    return None


def check_tier1_requirements(ctx):
    rec = ctx['rec']
    if rec.get('evidence_tier') != 'T1':
        return None
    if rec.get('quote_verdict') != 'supported':
        return 'downgrade', 'T1 但 quote_verdict=%s' % rec.get('quote_verdict')
    numeric_kinds = {'observation_report', 'composition_window', 'window_regime', 'composition'}
    if rec.get('claim_kind') in numeric_kinds:
        obj = rec.get('object') or {}
        magnitude = str(obj.get('magnitude') or '')
        ind = obj.get('indicator')
        if ind in NUMERIC_INDICATORS_UNIT_REQUIRED and not magnitude:
            return 'downgrade', 'T1 数值支缺 magnitude'
        own = {pv.get('param') for pv in (rec.get('window') or {}).get('params') or []
               if pv.get('presence') == 'reported'}
        inherited = set((rec.get('condition_source') or {}).get('inherited') or [])
        n_cond = len(own | inherited)
        if n_cond < 2:
            return 'downgrade', 'T1 数值支要求条件参数 ≥2（own∪inherited），实际 %d' % n_cond
        if not any(a.get('kind') in ('block', 'table_cell') for a in ctx['anchors']):
            return 'downgrade', 'T1 锚点必须是 block/table_cell'
    else:
        obj = rec.get('object') or {}
        if not (obj.get('name_raw') or obj.get('value')):
            return 'downgrade', 'T1 明确措辞支缺原文措辞'
    return None


def check_inherited_requires_run(ctx):
    src = ctx['rec'].get('condition_source') or {}
    inherited = src.get('inherited') or []
    if inherited and not src.get('run_ref'):
        return 'reject', '声明继承 %s 但没有 run_ref（凭空补条件）' % inherited
    return None


def check_tier2_no_numeric(ctx):
    rec = ctx['rec']
    if rec.get('evidence_tier') != 'T2':
        return None
    magnitude = str((rec.get('object') or {}).get('magnitude') or '')
    if re.match(r'^\s*[-+]?\d', magnitude):
        return 'downgrade', 'T2 断言不允许带数值: %r' % magnitude
    return None


def check_potential_needs_ref_electrode(ctx):
    ind = (ctx['rec'].get('object') or {}).get('indicator')
    if ind not in POTENTIAL_INDICATORS:
        return None
    if not ctx['rec'].get('reference_electrode'):
        return 'downgrade', '%s 缺参比电极 → 降级 T2（数值三要素不全）' % ind
    return None


def check_filling_ratio_needs_feature(ctx):
    rec = ctx['rec']
    ind = (rec.get('object') or {}).get('indicator')
    if ind not in FILLING_NEEDS_FEATURE or rec.get('evidence_tier') != 'T1':
        return None
    params = {pv.get('param') for pv in (rec.get('window') or {}).get('params') or []}
    if not params & {'pore_diameter', 'aspect_ratio', 'pore_depth'}:
        return 'downgrade', '%s 类 T1 断言缺基体结构（孔型/AR/孔径）→ 降级' % ind
    return None


def check_tp_needs_definition(ctx):
    obj = ctx['rec'].get('object') or {}
    if obj.get('indicator') == 'tp' and not obj.get('definition_eq'):
        return 'downgrade', 'TP 断言未绑定定义式 eq_id → 降级待人工'
    return None


def check_no_cross_family_reasoning(ctx):
    rec, lex = ctx['rec'], ctx['lex']
    ind = (rec.get('object') or {}).get('indicator')
    fam = ((lex['indicators']['indicators'].get(ind) or {}) or {}).get('family')
    if rec.get('claim_kind') == 'structure_activity' and rec.get('evidence_tier') == 'T1':
        return 'downgrade', '基元层结论单篇不得给 T1（跨文献聚合才能给）'
    # 只抓最危险的一类：用镀层性能（硬度/光泽/外观）当整平/填充能力的证据
    if fam == 'film_performance' and rec.get('predicate') == 'improves':
        return 'warn', '%s 属镀层性能族，不得用来支撑填充/整平结论（C-IND-04）' % ind
    return None


def check_ambiguous_symbol_resolved(ctx):
    obj = ctx['rec'].get('object') or {}
    ind = obj.get('indicator')
    if ind in AMBIGUOUS_INDICATORS and not obj.get('magnitude') and ctx['rec'].get('evidence_tier') == 'T1':
        return 'downgrade', '%s 是有歧义的符号且无数值 → 只能 T2' % ind
    return None


def check_current_density_needs_waveform(ctx):
    reported = {pv.get('param') for pv in (ctx['rec'].get('window') or {}).get('params') or []
                if pv.get('presence') == 'reported'}
    if 'current_density' in reported and 'waveform' not in reported:
        return 'warn', '有电流密度但未声明波形（DC/PPR/PR）'
    return None


def check_no_inexact_conversion(ctx):
    for pv in (ctx['rec'].get('window') or {}).get('params') or []:
        if pv.get('unit') in ('ppm', 'wt%') and pv.get('presence') == 'reported':
            if not pv.get('converted') and not pv.get('basis'):
                return 'warn', '%s 用 %s 表示但缺 basis/converted 标记' % (pv.get('param'), pv.get('unit'))
    return None


def check_role_on_run_not_chemical(ctx):
    rec = ctx['rec']
    if rec.get('predicate') != 'has_role':
        return None
    if (rec.get('subject') or {}).get('type') == 'Chemical' and not (rec.get('run_local') or rec.get('experiment_local')):
        return 'warn', '角色断言没有 Run 上下文：分子级角色不成立，需挂到具体 Run（C-ROLE-01）'
    return None


def check_unknown_role_consistency(ctx):
    rec = ctx['rec']
    if rec.get('predicate') == 'has_role':
        val = (rec.get('object') or {}).get('value')
        if val not in ctx['lex']['_roles']:
            return 'reject', '角色不在词表: %s' % val
    return None


def check_extractor_provenance(ctx):
    ex = ctx['rec'].get('extractor') or {}
    missing = [k for k in ('model', 'prompt_ver', 'date') if not ex.get(k)]
    if missing:
        return 'reject', 'extractor 缺 %s' % ','.join(missing)
    return None


def check_enum_membership(ctx):
    rec, lex = ctx['rec'], ctx['lex']
    obj = rec.get('object') or {}
    ind = obj.get('indicator')
    if ind and ind not in lex['_indicators']:
        return 'reject', '指标不在词表: %s' % ind
    if obj.get('type') == 'Motif' and obj.get('value') not in lex['_motifs']:
        return 'reject', '基元不在词表: %s' % obj.get('value')
    if obj.get('type') == 'Mechanism' and obj.get('value') not in lex['_mechanisms']:
        return 'reject', '机理不在词表: %s' % obj.get('value')
    return None


def check_doc_id_in_manifest(ctx):
    corpus = ctx['corpus']
    if not corpus:
        return None
    doc = ctx['rec'].get('doc_id')
    if doc not in corpus['docs']:
        return 'reject', 'doc_id 不在 48 篇清单: %s' % doc
    return None


def check_run_has_conditions(ctx):
    params = (ctx['rec'].get('window') or {}).get('params') or []
    if ctx['rec'].get('run_local') and not params:
        return 'reject', '声明了 Run 却没有任何已报道条件'
    return None


def check_swept_consistency(ctx):
    return None  # 需跨 Run 聚合，改由 validate_graph.py 实现（C-EXP-02）


NUMERIC_CELL = re.compile(r'^[\s±+\-−–~]*(?:\d|\.\d)')
NUMERIC_INCAPABLE_CLASSES = {'descriptive', 'spectra', 'formula', 'method_eval', 'pretreat'}


def _claim_is_numeric(rec):
    obj = rec.get('object') or {}
    if re.match(r'^\s*[-+]?\d', str(obj.get('magnitude') or '')):
        return True
    return obj.get('indicator') in NUMERIC_INDICATORS_UNIT_REQUIRED


def check_cell_numeric_parsable(ctx):
    corpus = ctx['corpus']
    if not corpus or not _claim_is_numeric(ctx['rec']):
        return None
    for a in ctx['anchors']:
        if a.get('kind') != 'table_cell':
            continue
        path = corpus['tables'].get(a.get('table_id'))
        if not path:
            return 'reject', 'table_id 未知: %s' % a.get('table_id')
        rows = list(csv.reader(open(path, encoding='utf-8-sig')))
        r, c = a.get('row'), a.get('col')
        if r is None or c is None or r >= len(rows) or c >= len(rows[r]):
            return 'reject', '单元格越界 %s r%s c%s' % (a.get('table_id'), r, c)
        cell = norm(rows[r][c])
        if not NUMERIC_CELL.match(cell):
            return 'reject', '单元格不是数值: %r（%s r%s c%s）' % (cell, a.get('table_id'), r, c)
    return None


def check_profile_required_for_numeric(ctx):
    corpus = ctx['corpus']
    if not corpus or not _claim_is_numeric(ctx['rec']):
        return None
    meta_all = corpus.get('table_meta') or {}
    for a in ctx['anchors']:
        if a.get('kind') != 'table_cell':
            continue
        cls = (meta_all.get(a.get('table_id')) or {}).get('class')
        if not cls:
            return 'warn', '表格无画像线索（%s），数值断言需人工确认 etl_profile' % a.get('table_id')
        if cls in NUMERIC_INCAPABLE_CLASSES:
            return 'reject', '表格 class=%s 不能承载工艺数值（%s）' % (cls, a.get('table_id'))
        if cls == 'data_unnamed':
            return 'warn', '表格 class=data_unnamed（画像未定），人工确认前数值断言只警告'
    return None


CHECKS = {
    'anchor_required': check_anchor_required,
    'block_id_exists': check_block_id_exists,
    'quote_must_match_block': check_quote_must_match_block,
    'numeric_from_table_cell': check_numeric_from_table_cell,
    'numeric_requires_unit': check_numeric_requires_unit,
    'param_registered': check_param_registered,
    'concentration_basis_consistency': check_concentration_basis_consistency,
    'window_bounds_valid': check_window_bounds_valid,
    'not_reported_not_satisfied': check_not_reported_not_satisfied,
    'predicate_registered': check_predicate_registered,
    'predicate_slot_match': check_predicate_slot_match,
    'tier1_requirements': check_tier1_requirements,
    'inherited_requires_run': check_inherited_requires_run,
    'tier2_no_numeric': check_tier2_no_numeric,
    'potential_needs_ref_electrode': check_potential_needs_ref_electrode,
    'filling_ratio_needs_feature': check_filling_ratio_needs_feature,
    'tp_needs_definition': check_tp_needs_definition,
    'no_cross_family_reasoning': check_no_cross_family_reasoning,
    'ambiguous_symbol_resolved': check_ambiguous_symbol_resolved,
    'current_density_needs_waveform': check_current_density_needs_waveform,
    'no_inexact_conversion': check_no_inexact_conversion,
    'role_on_run_not_chemical': check_role_on_run_not_chemical,
    'unknown_role_consistency': check_unknown_role_consistency,
    'extractor_provenance': check_extractor_provenance,
    'enum_membership': check_enum_membership,
    'doc_id_in_manifest': check_doc_id_in_manifest,
    'run_has_conditions': check_run_has_conditions,
    'swept_consistency': check_swept_consistency,
    'cell_numeric_parsable': check_cell_numeric_parsable,
    'profile_required_for_numeric': check_profile_required_for_numeric,
}

# 仍未实现、需要人工或跨记录才能判的规则：明确标出，不假装跑过
PENDING_CHECKS = {
    'acid_base_compatible', 'metal_consistency', 'acid_copper_composition',
}


def validate_file(path, schema_validator, constraints, preds, lex, corpus):
    rules = {r['check']: r for r in constraints['rules'] if r.get('check')}
    reports, counts = [], Counter()
    by_rule = defaultdict(Counter)
    with open(path, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                reports.append({'line': lineno, 'claim_id': None, 'decision': 'reject',
                                'findings': [{'rule': 'C-JSON-00', 'severity': 'reject', 'msg': 'JSON 解析失败: %s' % e}]})
                counts['reject'] += 1
                continue
            findings = []
            for err in schema_validator.iter_errors(rec):
                loc = '/'.join(str(p) for p in err.absolute_path) or '<root>'
                findings.append({'rule': 'C-SCHEMA-00', 'severity': 'reject',
                                 'msg': '结构不合规 @%s: %s' % (loc, err.message)})
            ctx = {'rec': rec, 'anchors': rec.get('anchors') or [], 'corpus': corpus,
                   'lex': lex, 'preds': preds}
            for check, fn in CHECKS.items():
                try:
                    res = fn(ctx)
                except Exception as e:  # 单条规则炸了不影响整批
                    findings.append({'rule': 'C-ENGINE', 'severity': 'warn',
                                     'msg': '规则 %s 执行异常: %s' % (check, e)})
                    continue
                if not res:
                    continue
                sev, msg = res
                rule_id = '(未登记)'
                for r in rules.values():
                    if r['check'] == check:
                        rule_id = r['id']
                        break
                findings.append({'rule': rule_id, 'check': check, 'severity': sev, 'msg': msg})
            decision = 'pass'
            for f in findings:
                if SEV_ORDER[f['severity']] > SEV_ORDER.get(decision, -1):
                    decision = f['severity']
            for f in findings:
                by_rule[f['rule']][f['severity']] += 1
            counts[decision] += 1
            reports.append({'line': lineno, 'claim_id': rec.get('claim_id'),
                            'claim_kind': rec.get('claim_kind'), 'decision': decision,
                            'findings': findings})
    return reports, counts, by_rule


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--claims', nargs='+', required=True)
    ap.add_argument('--corpus', default=None,
                    help='可选：清洗产物目录；给了才做 block_id/quote/单元格核对，不给就只跑结构+约束')
    ap.add_argument('--json', dest='json_out', default=None)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    lex = load_lexicon()
    _, preds = load_schema()
    constraints = load_yaml(os.path.join(ROOT, 'constraints.yaml'))
    with open(os.path.join(ROOT, 'claims.schema.json'), encoding='utf-8') as f:
        schema_validator = Draft202012Validator(json.load(f))
    corpus = build_corpus_index(args.corpus) if args.corpus else None
    if corpus is None:
        if args.corpus:
            print('[warn] 语料目录不可用，跳过 block_id/quote/单元格校验：%s' % args.corpus, file=sys.stderr)
        else:
            print('[info] 未给 --corpus：只做结构层与约束层校验', file=sys.stderr)
    else:
        print('[corpus] %d blocks / %d tables / %d docs'
              % (len(corpus['blocks']), len(corpus['tables']), len(corpus['docs'])), file=sys.stderr)

    all_reports, total = [], Counter()
    for path in args.claims:
        reports, counts, by_rule = validate_file(path, schema_validator, constraints, preds, lex, corpus)
        for r in reports:
            r['file'] = os.path.basename(path)
        all_reports.extend(reports)
        total.update(counts)
        if not args.quiet:
            print('\n=== %s' % os.path.basename(path))
            for r in reports:
                mark = {'pass': 'PASS', 'warn': 'WARN', 'downgrade': 'DOWN', 'reject': 'REJECT'}[r['decision']]
                print('%-6s %-28s %s' % (mark, r['claim_id'], r.get('claim_kind') or ''))
                for f in r['findings']:
                    print('        [%s] %s %s' % (f['severity'], f['rule'], f['msg']))
            print('  小计: ' + ', '.join('%s=%d' % (k, v) for k, v in counts.items()))

    impl = len(CHECKS)
    total_rules = len(constraints['rules'])
    print('\n=== 总计: ' + ', '.join('%s=%d' % (k, v) for k, v in sorted(total.items())))
    print('断言层已实现 %d 条检查；图层规则见 validate_graph.py；仍待实现: %s'
          % (impl, ', '.join(sorted(PENDING_CHECKS)) or '无'))

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump({'reports': all_reports, 'summary': dict(total),
                       'implemented_checks': sorted(CHECKS),
                       'pending_checks': sorted(PENDING_CHECKS)}, f, ensure_ascii=False, indent=2)
        print('报告已写入 %s' % args.json_out)

    hard = total.get('reject', 0)
    return 1 if hard else 0


if __name__ == '__main__':
    sys.exit(main())
