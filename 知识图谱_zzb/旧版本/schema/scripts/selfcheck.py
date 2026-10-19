#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""schema 自检 —— 不产数据，只确认这套契约自己站得住。

检查项：
  1) 全部 YAML 可解析
  2) claims.schema.json 是合法的 2020-12 schema
  3) 谓词签名的端点类型都已登记为节点
  4) 边的端点类型都已登记为节点
  5) 节点/值对象里的 ref 都指向存在的词表或值对象
  6) 指标 family 只取四类
  7) 约束表 id 唯一，且每条 check 都有落地处（断言层 / 图层 / 显式待实现）
  8) meta.counts 与实际节点/边/谓词数一致（防止文档说一套、文件是另一套）
  9) derives：derived_fields 里引用的字段在节点里存在
"""
import json
import os
import sys
import glob

import yaml
from jsonschema import Draft202012Validator

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

LEX_REF = {
    'lexicon/units_params.yaml#params': ('units_params', 'params'),
    'lexicon/units_params.yaml#units': ('units_params', 'units'),
    'lexicon/entities.yaml#roles': ('entities', 'roles'),
    'lexicon/entities.yaml#metals': ('entities', 'metals'),
    'lexicon/entities.yaml#bath_classes': ('entities', 'bath_classes'),
    'lexicon/entities.yaml#feature_kinds': ('entities', 'feature_kinds'),
    'lexicon/entities.yaml#substrates': ('entities', 'substrates'),
    'lexicon/indicators.yaml#indicators': ('indicators', 'indicators'),
    'lexicon/structures_methods.yaml#motifs': ('structures_methods', 'motifs'),
    'lexicon/structures_methods.yaml#mechanisms': ('structures_methods', 'mechanisms'),
    'lexicon/structures_methods.yaml#methods': ('structures_methods', 'methods'),
    'lexicon/structures_methods.yaml#reference_electrodes': ('structures_methods', 'reference_electrodes'),
    'lexicon/tables_sections.yaml#table_etl_profiles': ('tables_sections', 'table_etl_profiles'),
    'lexicon/tables_sections.yaml#section_roles': ('tables_sections', 'section_roles'),
}


def main():
    errs, notes = [], []

    ymls = glob.glob(os.path.join(ROOT, '**', '*.yaml'), recursive=True)
    parsed = {}
    for p in ymls:
        try:
            parsed[p] = yaml.safe_load(open(p, encoding='utf-8'))
        except Exception as e:
            errs.append('YAML 解析失败 %s: %s' % (os.path.basename(p), e))
    notes.append('YAML 解析通过: %d 个' % len(ymls))

    js = json.load(open(os.path.join(ROOT, 'claims.schema.json'), encoding='utf-8'))
    try:
        Draft202012Validator.check_schema(js)
        notes.append('claims.schema.json 合法（2020-12）')
    except Exception as e:
        errs.append('JSON Schema 不自洽: %s' % e)

    schema = parsed[os.path.join(ROOT, 'schema.yaml')]
    lex = {n: parsed[os.path.join(ROOT, 'lexicon', n + '.yaml')]
           for n in ['units_params', 'entities', 'indicators', 'structures_methods',
                     'pitfalls', 'tables_sections']}
    node_types = set(schema['nodes'])
    value_objects = set(schema['value_objects'])

    # 3) 谓词签名（端点可以是节点类型，也可以是值对象，如 DefectKind）
    endpoints_ok = node_types | value_objects
    bad = []
    for p in schema['predicates']:
        for side in p['signature'].split('->'):
            for t in [x.strip() for x in side.split('|')]:
                if t not in endpoints_ok:
                    bad.append((p['name'], t))
    if bad:
        errs.append('谓词签名引用了未登记的类型: %s' % bad)
    else:
        notes.append('%d 条谓词签名端点类型全部已登记' % len(schema['predicates']))

    # 4) 边端点
    bad = []
    for e in schema['edges']:
        for side in ('from', 'to'):
            for t in [x.strip() for x in str(e[side]).split('|')]:
                if t != 'enum' and t not in node_types:
                    bad.append((e['name'], side, t))
    if bad:
        errs.append('边引用了未登记的节点类型: %s' % bad)
    else:
        notes.append('%d 条边端点类型全部已登记' % len(schema['edges']))

    # 5) ref 指向
    empty = [k for k in LEX_REF
             if not parsed[os.path.normpath(os.path.join(ROOT, k.split('#')[0]))].get(LEX_REF[k][1])]
    if empty:
        errs.append('词表为空: %s' % empty)

    sections = value_objects | node_types | set(schema)   # 内部引用可指向值对象/节点/顶层段（如 #predicates）

    def walk(o, path=''):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == 'ref' and isinstance(v, str):
                    if v.startswith('#'):
                        if v[1:] not in sections:
                            errs.append('未知内部引用 %s @%s' % (v, path))
                    elif v not in LEX_REF:
                        errs.append('未知词表引用 %s @%s' % (v, path))
                walk(v, path + '/' + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, path + '[%d]' % i)

    walk(schema)
    notes.append('节点/值对象的 ref 全部指向已存在的词表或值对象')

    # 6) 指标 family
    fam = {k: (v or {}).get('family') for k, v in lex['indicators']['indicators'].items()}
    badfam = {k: f for k, f in fam.items() if f not in
              {'filling_behavior', 'film_performance', 'method_derived', 'composition_structure'}}
    if badfam:
        errs.append('指标 family 非法: %s' % badfam)
    else:
        notes.append('指标 %d 条，family 四类齐全' % len(fam))

    # 7) 约束落地
    cons = parsed[os.path.join(ROOT, 'constraints.yaml')]
    ids = [r['id'] for r in cons['rules']]
    if len(ids) != len(set(ids)):
        errs.append('约束 id 重复')
    import validate as V
    import validate_graph as G
    landing = set(V.CHECKS) | set(G.CHECKS) | set(V.PENDING_CHECKS)
    orphan = [r['id'] for r in cons['rules'] if r.get('check') and r['check'] not in landing]
    if orphan:
        errs.append('约束 check 没有落地处（既未实现也未标待实现）: %s' % orphan)
    stale = set(V.PENDING_CHECKS) & (set(V.CHECKS) | set(G.CHECKS))
    if stale:
        errs.append('这些 check 已实现却仍留在 PENDING_CHECKS: %s' % sorted(stale))
    notes.append('约束 %d 条：断言层 %d / 图层 %d / 待实现 %d'
                 % (len(ids), len(V.CHECKS), len(G.CHECKS), len(V.PENDING_CHECKS)))
    declared = (cons.get('meta') or {}).get('rule_count')
    if declared is not None and declared != len(ids):
        errs.append('constraints.meta.rule_count=%s 与实际 %d 条不一致' % (declared, len(ids)))

    # 8) meta.counts 与实际一致
    counts = (schema.get('meta') or {}).get('counts') or {}
    actual = {'nodes': len(schema['nodes']), 'edges': len(schema['edges']),
              'predicates': len(schema['predicates']),
              'value_objects': len(schema['value_objects']),
              'derived_fields': len(schema.get('derived_fields') or {})}
    mismatch = {k: (counts.get(k), v) for k, v in actual.items() if counts.get(k) != v}
    if mismatch:
        errs.append('meta.counts 与实际不一致（声明值, 实际值）: %s' % mismatch)
    else:
        notes.append('meta.counts 与实际一致: %s' % actual)

    # 9) derived_fields 引用的字段存在
    obs_fields = set((schema['nodes']['Observation'].get('fields') or {}))
    for f in ['comparability_key']:
        if f not in obs_fields:
            errs.append('derived_fields 用到的 Observation.%s 未定义' % f)
    ku_fields = set((schema['nodes'].get('KnowledgeUnit', {}).get('fields') or {}))
    for f in ['effective_window', 'support_class', 'n_docs', 'n_independent_runs']:
        if f not in ku_fields:
            errs.append('KnowledgeUnit 缺字段 %s（derived_fields 依赖它）' % f)
    notes.append('derived_fields 依赖的字段都存在')

    print('\n'.join('  OK  ' + n for n in notes))
    if errs:
        print('\nFAIL:')
        print('\n'.join('  - ' + e for e in errs))
        return 1
    print('\n自检全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
