#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""回归自测：用人造夹具验证校验器「该拦的拦住、不该拦的不拦」。

不读真实语料，不写仓库；所有夹具建在系统临时目录，跑完删除。
用法：python scripts/selftest.py [-v]
退出码 0 = 全部符合预期；1 = 有不符合项。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATE = os.path.join(HERE, 'validate.py')
GRAPH = os.path.join(HERE, 'validate_graph.py')


# ── 夹具构造 ────────────────────────────────────────────────────────────
def build_corpus(root):
    blocks = os.path.join(root, 'blocks')
    tables = os.path.join(root, 'tables')
    os.makedirs(blocks)
    os.makedirs(tables)
    rows = [
        # (page, bbox, class, csv)
        (3, [48, 762, 475, 900], 'result', 'tables\\demo__p3_0.csv'),
        (5, [48, 100, 400, 200], 'spectra', 'tables\\demo__p5_0.csv'),
        (6, [48, 100, 400, 200], 'data_unnamed', 'tables\\demo__p6_0.csv'),
        (7, [48, 100, 400, 200], 'result', 'tables\\demo__p7_0.csv'),
    ]
    with open(os.path.join(blocks, 'demo.jsonl'), 'w', encoding='utf-8') as f:
        f.write(json.dumps({'type': 'text', 'page': 3, 'bbox': [10, 20, 100, 40],
                            'text': 'The potential difference increased by 14 mV at 2 ASD.'},
                           ensure_ascii=False) + '\n')
        for page, bbox, cls, csv_rel in rows:
            f.write(json.dumps({'type': 'table', 'page': page, 'bbox': bbox,
                                'caption': 'Plating results', 'n_rows': 3, 'n_cols': 2,
                                'header': ['Case', 'E (mV)'], 'class': cls, 'csv': csv_rel,
                                'evidence': 'text_layer', 'ocr_status': 'confirmed'},
                               ensure_ascii=False) + '\n')
    csvs = {
        'demo__p3_0.csv': [['Case', 'E (mV)'], ['Case', 'E (mV)'], ['1', '14']],
        'demo__p5_0.csv': [['Wavelength', 'Intensity'], ['Wavelength', 'Intensity'], ['400', '5']],
        'demo__p6_0.csv': [['A', 'B'], ['A', 'B'], ['x', '7']],
        'demo__p7_0.csv': [['Case', 'E (mV)'], ['Case', 'E (mV)'], ['1', 'N/A']],
    }
    for name, grid in csvs.items():
        with open(os.path.join(tables, name), 'w', encoding='utf-8', newline='') as f:
            for row in grid:
                f.write(','.join(row) + '\n')


def claim(claim_id, table_id, row, col, quote):
    return {
        'claim_id': claim_id, 'claim_kind': 'observation_report', 'doc_id': 'demo',
        'subject': {'type': 'Chemical', 'name_raw': 'diazine black'},
        'predicate': 'affects_indicator',
        'object': {'type': 'Indicator', 'indicator': 'delta_eta', 'magnitude': '14 mV'},
        'window': {'params': [{'param': 'concentration', 'of': 'diazine black', 'presence': 'reported',
                               'kind': 'point', 'value': 1, 'unit': 'ppm', 'raw': '1'}]},
        'polarity': 'assert', 'evidence_tier': 'T2', 'stance': 'support', 'quote_verdict': 'supported',
        'anchors': [{'kind': 'table_cell', 'doc_id': 'demo', 'page': 3, 'table_id': table_id,
                     'row': row, 'col': col, 'quote': quote}],
        'extractor': {'model': 'selftest', 'prompt_ver': 'v1', 'date': '2026-10-19'},
        'review': 'pending',
    }


def build_graph(root, *, profile='result_grid', predicate='improves', swept='constant', confidence=False):
    nodes = [
        {'id': 'blk:b1', 'type': 'Block', 'doc_id': 'd', 'page': 3, 'bbox': [0, 0, 1, 1],
         'block_type': 'table',
         'table_meta': {'n_rows': 3, 'n_cols': 2, 'csv': 'tables\\d__p3_0.csv', 'class': 'result',
                        'evidence': 'text_layer', 'ocr_status': 'confirmed'}},
        {'id': 'tbl:d:p3:0', 'type': 'Table', 'doc_id': 'd', 'page': 3, 'block_id': 'blk:b1',
         'n_rows': 3, 'n_cols': 2, 'etl_profile': profile, 'etl_profile_source': 'human'},
        {'id': 'exp:1', 'type': 'Experiment', 'doc_id': 'd', 'swept_params': ['current_density'],
         'design_type': 'ofat', 'evidence_scope': 'experimental',
         'narrative_anchor': {'kind': 'block', 'doc_id': 'd', 'page': 3, 'block_id': 'blk:b1', 'quote': 'x'}},
        {'id': 'obs:1', 'type': 'Observation', 'indicator': 'delta_eta', 'outcome_kind': 'numeric',
         'method': ['galvanostatic'], 'reference_electrode': 'SCE', 'doc_id': 'd',
         'measured_at': {'kind': 'table_cell', 'doc_id': 'd', 'page': 3, 'table_id': 'tbl:d:p3:0',
                         'row': 2, 'col': 1, 'quote': '14'},
         'value': {'kind': 'point', 'value': 14, 'unit': 'mV', 'raw': '14 mV'},
         'comparability_key': 'delta_eta|galvanostatic|SCE|na|na|na'},
        {'id': 'claim:1', 'type': 'Claim', 'claim_kind': 'observation_report',
         'subject': {'type': 'Chemical'}, 'predicate': predicate, 'object': {'type': 'Indicator'},
         'polarity': 'assert', 'evidence_tier': 'T1', 'observation_ids': ['obs:1'],
         'extractor': {'model': 'selftest', 'prompt_ver': 'v1', 'date': '2026-10-19'},
         'review': 'pass'},
    ]
    vals = [2, 2] if swept == 'constant' else [2, 4]
    for i, v in enumerate(vals):
        nodes.append({'id': 'run:%d' % i, 'type': 'Run', 'exp_id': 'exp:1', 'doc_id': 'd',
                      'conditions': [{'param': 'current_density', 'presence': 'reported',
                                      'kind': 'point', 'value': v, 'unit': 'ASD', 'raw': str(v)}],
                      'anchor': {'kind': 'block', 'doc_id': 'd', 'page': 3,
                                 'block_id': 'blk:b1', 'quote': 'x'}})
    if confidence:
        nodes[-1]['confidence'] = 0.92
        nodes.append({'id': 'claim:conf', 'type': 'Claim', 'claim_kind': 'composition',
                      'subject': {'type': 'Chemical'}, 'predicate': 'has_role',
                      'object': {'type': 'Role'}, 'polarity': 'assert', 'evidence_tier': 'T2',
                      'confidence': 0.92, 'observation_ids': [],
                      'extractor': {'model': 'selftest', 'prompt_ver': 'v1', 'date': '2026-10-19'},
                      'review': 'pass'})
    edges = [{'from': 'claim:1', 'type': 'ABOUT', 'to': 'obs:1'}]
    with open(os.path.join(root, 'nodes.jsonl'), 'w', encoding='utf-8') as f:
        for n in nodes:
            f.write(json.dumps(n, ensure_ascii=False) + '\n')
    with open(os.path.join(root, 'edges.jsonl'), 'w', encoding='utf-8') as f:
        for e in edges:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')


# ── 运行与断言 ──────────────────────────────────────────────────────────
def run(script, args):
    p = subprocess.run([sys.executable, '-X', 'utf8', script] + args,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def expect(name, code, out, rules, forbid=(), want_rc=None):
    problems = []
    for r in rules:
        if r not in out:
            problems.append('缺少预期规则 %s' % r)
    for r in forbid:
        if r in out:
            problems.append('出现不应有的规则 %s' % r)
    if want_rc is not None and code != want_rc:
        problems.append('退出码 %d，期望 %d' % (code, want_rc))
    status = 'PASS' if not problems else 'FAIL'
    print('%-4s %-42s %s' % (status, name, '; '.join(problems)))
    if problems:
        snippet = ' | '.join(l.strip() for l in out.strip().splitlines()[:6])
        print('     实际输出: %s' % snippet[:400])
    return not problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()
    ok = True
    tmp = tempfile.mkdtemp(prefix='kg_selftest_')
    try:
        corpus = os.path.join(tmp, 'corpus')
        os.makedirs(corpus)
        build_corpus(corpus)
        claims_dir = os.path.join(tmp, 'claims')
        os.makedirs(claims_dir)
        cases = {
            'claim_ok_result_table': claim('c:ok', 'tbl:demo:p3:0', 2, 1, '14'),
            'claim_reject_spectra_table': claim('c:spectra', 'tbl:demo:p5:0', 2, 1, '5'),
            'claim_warn_unnamed_table': claim('c:unnamed', 'tbl:demo:p6:0', 2, 1, '7'),
            'claim_reject_cell_not_numeric': claim('c:notnum', 'tbl:demo:p7:0', 2, 1, 'N/A'),
        }
        for name, rec in cases.items():
            with open(os.path.join(claims_dir, name + '.jsonl'), 'w', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')

        def claim_case(name, file, rules, forbid=(), want_rc=0):
            code, out = run(VALIDATE, ['--claims', os.path.join(claims_dir, file + '.jsonl'),
                                       '--corpus', corpus])
            return expect(name, code, out, rules, forbid, want_rc)

        ok &= claim_case('断言: 结果表数值锚点正常', 'claim_ok_result_table', [], ['C-TABLE-01', 'C-TABLE-02'])
        ok &= claim_case('断言: spectra 表出数值 → 拒收', 'claim_reject_spectra_table',
                         ['C-TABLE-01'], want_rc=1)
        ok &= claim_case('断言: data_unnamed 表出数值 → 警告', 'claim_warn_unnamed_table',
                         ['C-TABLE-01'], want_rc=0)
        ok &= claim_case('断言: 单元格非数值 → 拒收', 'claim_reject_cell_not_numeric',
                         ['C-TABLE-02'], want_rc=1)

        gdir = os.path.join(tmp, 'graph')
        os.makedirs(gdir)

        seen = []

        def graph_case(name, rules, forbid=(), want_rc=None, **kw):
            sub = os.path.join(gdir, 'case%d' % (len(seen) + 1))
            seen.append(name)
            os.makedirs(sub, exist_ok=True)
            build_graph(sub, **kw)
            code, out = run(GRAPH, ['--nodes', os.path.join(sub, 'nodes.jsonl'),
                                    '--edges', os.path.join(sub, 'edges.jsonl')])
            return expect(name, code, out, rules, forbid, want_rc)

        ok &= graph_case('图层: ANOVA 表 + 工艺谓词 → 拒收', ['C-TABLE-03'],
                         want_rc=1, profile='anova', predicate='improves')
        ok &= graph_case('图层: ANOVA 表 + 统计谓词 → 不报', [], ['C-TABLE-03'],
                         profile='anova', predicate='reports_statistics')
        ok &= graph_case('图层: 扫轴只有 1 个取值 → 警告', ['C-EXP-02'], swept='constant')
        ok &= graph_case('图层: 扫轴确有变化 → 不报', [], ['C-EXP-02'], swept='varying')
        ok &= graph_case('图层: 自评 confidence → 警告', ['C-EV-04'], confidence=True)
    finally:
        if args.verbose:
            print('夹具目录（已删除）：%s' % tmp)
        shutil.rmtree(tmp, ignore_errors=True)

    print('\n%s' % ('全部通过' if ok else '存在不符合预期项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
