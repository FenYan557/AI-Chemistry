#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读语料普查 + schema 对齐检查 —— 评估 schema 里哪些字段真的填得出来，
以及清洗产物里有没有 schema 没建模的字段（防"清洗改了、schema 不知道"）。

不产图、不写任何产物；只读清洗产物并打印统计（历史结果已归档；当前统计以本次输出为准）。

用法：
  python survey_corpus.py --corpus "<...\\知识抽取\\清洗\\02_清洗\\out>"

注意：正则统计很会骗人。第一版温度正则末尾多了个 \\b，把 23/48 读成 4/48。
任何用于决策的数字都要换一种写法复核一遍（本脚本温度同时用 °C 与 K 两种形态交叉验证）。
"""
import argparse
import csv
import glob
import json
import os
import re
from collections import Counter

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

UNIT = (r'(?:mg/L|g/L|ppm|mol/L|mmol/L|mM|µM|μM|wt%|at%|mA/cm2|mA/cm²|A/dm2|A/dm²|ASD|mA/mm2'
        r'|mV|V|eV|nm|µm|μm|mm|Å|°C|K|rpm|r/min|min|h|s|%|kJ/mol|kcal/mol|MPa|GPa|μΩ·cm|mC/cm2|GU|HV)')
NUM_UNIT = re.compile(r'\d+(?:\.\d+)?\s*' + UNIT)
FLOAT = re.compile(r'^\s*[-+−]?\d+(?:\.\d+)?\s*$')
REF_EL = re.compile(
    r'\b(SCE|Ag/AgCl|AgAgCl|SMSE|SSE|Hg/Hg2SO4|saturated\s+\w*\s*electrode'
    r'|saturated calomel|mercurous sulfate electrode|reference electrode)\b', re.I)
CUR = re.compile(r'\d+(?:\.\d+)?\s*(?:ASD|A\s*/\s*dm2|A/dm²|mA\s*/\s*cm2|mA/cm²)', re.I)
TEMP_C = re.compile(r'\d{2}\s*(?:°\s*C|℃)')
TEMP_K = re.compile(r'\b(2[89]\d|3[0-4]\d)\s*K\b')
WAVE = re.compile(r'\b(DC|PPR|PR|pulse|pulsed|reverse pulse|galvanostatic|potentiostatic)\b', re.I)
BASIS = re.compile(r'\b(geometric|true area|apparent area|nominal)\b', re.I)


def load_block_fields():
    schema = yaml.safe_load(open(os.path.join(ROOT, 'schema.yaml'), encoding='utf-8'))
    fields = set(schema['nodes']['Block'].get('fields') or {})
    tm = (schema['nodes']['Block']['fields'].get('table_meta') or {}).get('fields') or {}
    for k in tm:
        fields.add('table_meta.' + k)
    return fields, schema


def survey(corpus):
    schema_fields, schema = load_block_fields()
    docs = {}
    cand = total_text = 0
    hit_docs = Counter()
    seen_keys = Counter()
    types = Counter()
    ocr = Counter()
    evidence = Counter()

    for path in glob.glob(os.path.join(corpus, 'blocks', '*.jsonl')):
        doc = os.path.basename(path)[:-len('.jsonl')]
        n_text = n_cand = 0
        hits = Counter()
        for line in open(path, encoding='utf-8'):
            b = json.loads(line)
            types[b.get('type')] += 1
            for k, v in b.items():
                seen_keys[('table_meta.' + k) if b.get('type') == 'table' and k in
                          ('n_rows', 'n_cols', 'ragged', 'header_levels', 'header', 'class',
                           'csv', 'evidence', 'ocr_status') else k] += 1
            if b.get('type') == 'table':
                ocr[b.get('ocr_status')] += 1
                evidence[b.get('evidence')] += 1
            if b.get('type') != 'text':
                continue
            txt = b.get('text') or ''
            n_text += 1
            if NUM_UNIT.search(txt):
                n_cand += 1
            if REF_EL.search(txt):
                hits['ref_electrode'] += 1
            if CUR.search(txt):
                hits['current_density'] += 1
            if TEMP_C.search(txt) or TEMP_K.search(txt):
                hits['temperature'] += 1
            if WAVE.search(txt):
                hits['waveform'] += 1
            if BASIS.search(txt):
                hits['current_basis'] += 1
        docs[doc] = (n_text, n_cand)
        total_text += n_text
        cand += n_cand
        for k in ('ref_electrode', 'current_density', 'temperature', 'waveform', 'current_basis'):
            if hits.get(k):
                hit_docs[k] += 1
    n_docs = len(docs)

    print('=== 块统计（%s）' % os.path.basename(corpus))
    print('  块类型:', dict(types))
    print('  表块 ocr_status:', dict(ocr), ' evidence:', dict(evidence))

    print('\n=== 正文可获得性（%d 篇）' % n_docs)
    print('  正文段落 %d，含"数字+单位"的候选句 %d（%.1f%%）'
          % (total_text, cand, 100.0 * cand / max(total_text, 1)))
    for key, label in [('ref_electrode', '提到参比电极'), ('current_density', '电流密度+单位'),
                       ('temperature', '温度+单位（°C 或 K）'), ('waveform', '波形/方法词'),
                       ('current_basis', '说明面积基准')]:
        print('  %s: %d/%d (%.0f%%)' % (label, hit_docs[key], n_docs, 100.0 * hit_docs[key] / n_docs))

    tables = []
    for path in glob.glob(os.path.join(corpus, 'tables', '*.csv')):
        if 'tables_index' in path:
            continue
        rows = list(csv.reader(open(path, encoding='utf-8-sig')))
        if not rows:
            continue
        header = ' | '.join(rows[0])
        tables.append({
            'rows': len(rows),
            'data_rows': max(len(rows) - 2, 0),
            'numeric': sum(1 for r in rows for c in r if FLOAT.match(c)),
            'conc': bool(re.search(r'(ppm|mg/L|g/L|mol/L|mM)', header, re.I)),
            'temp': bool(re.search(r'(temp|°C|℃)', header, re.I)),
            'cur': bool(re.search(r'(current density|ASD|A/dm|mA/cm)', header, re.I)),
            'rpm': bool(re.search(r'(rpm|rotation|r/min)', header, re.I)),
            'ref': bool(REF_EL.search(header)),
        })

    print('\n=== 表格表头可获得性（%d 张）' % len(tables))
    for key, label in [('conc', '浓度列'), ('temp', '温度列'), ('cur', '电流密度列'),
                       ('rpm', '转速列'), ('ref', '参比电极')]:
        print('  含%s: %d' % (label, sum(t[key] for t in tables)))
    both = sum(1 for t in tables if t['conc'] and t['cur'])
    print('  浓度+电流密度同时在表头（T1 数值支能否满足的关键）: %d/%d (%.0f%%)'
          % (both, len(tables), 100.0 * both / len(tables)))
    print('\n=== 规模')
    print('  数据行合计 %d（Run 上限）；数值格 %d'
          % (sum(t['data_rows'] for t in tables), sum(t['numeric'] for t in tables)))

    # ── schema ↔ 产物 对齐 ─────────────────────────────────────────────
    DERIVED = {'block_id', 'doc_id', 'section_role', 'text_sha1', 'table_meta'}
    FROM_ENRICH = {'cites', 'refers_to'}
    RENAMED = {'type': 'block_type'}      # 产物里的 type = 块类型；图里叫 block_type（type 留给节点类名）
    data_fields = {RENAMED.get(k, k) for k in seen_keys}
    unmodeled = sorted(data_fields - schema_fields)
    absent = sorted(schema_fields - data_fields)
    absent_derived = [f for f in absent if f in DERIVED]
    absent_enrich = [f for f in absent if f in FROM_ENRICH]
    absent_other = [f for f in absent if f not in DERIVED and f not in FROM_ENRICH]
    print('\n=== schema 对齐（Block）')
    print('  数据里有、schema 未建模:', unmodeled or '无')
    print('  派生字段（产物里本来就没有，物化时算）:', absent_derived or '无')
    print('  依赖 enrich 工序（跑完 enriched 才有）:', absent_enrich or '无')
    print('  其它缺失:', absent_other or '无')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', required=True)
    args = ap.parse_args()
    survey(args.corpus)


if __name__ == '__main__':
    main()
