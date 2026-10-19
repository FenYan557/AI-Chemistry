#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图层校验器 v1.0 —— 校验"节点表 + 边表"是否符合 schema.yaml，并跑跨记录规则。

本脚本只校验别人产出的图，自己不产图。输入两份 JSONL（每行一个对象）：

  nodes.jsonl  {"id": "obs:…", "type": "Observation", "indicator": "delta_eta", …}
  edges.jsonl  {"from": "run:…", "type": "YIELDS", "to": "obs:…", …}

用法：
  python validate_graph.py --nodes nodes.jsonl --edges edges.jsonl [--json report.json]

三层检查：
  1) 结构：节点类型已登记、必填字段在、内联枚举合法、外链词表取值合法
  2) 边：边类型已登记、端点类型匹配签名、指向的 id 存在
  3) 跨记录（本层核心）：可比性键、冲突口径、KU 支持度阈值/等级不虚高、解释链带条件

退出码 1 表示存在 reject。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEV_ORDER = {'warn': 0, 'downgrade': 1, 'reject': 2}

# 词表引用 → (文件, 顶层键)
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
CANONICAL_UNITS = set()


# 工艺/填充类谓词：证据若来自 ANOVA 表则不得成立（C-TABLE-03）
PROCESS_PREDICATES = {
    'improves', 'degrades', 'has_role', 'causes_defect', 'affects_indicator', 'invalid_in',
}


def load_all():
    lex = {}
    for name in ['units_params', 'entities', 'indicators', 'structures_methods', 'pitfalls', 'tables_sections']:
        lex[name] = yaml.safe_load(open(os.path.join(ROOT, 'lexicon', name + '.yaml'), encoding='utf-8'))
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
    CANONICAL_UNITS.update({g['canonical'] for g in lex['units_params']['units'].values()
                            if isinstance(g, dict) and g.get('canonical')})
    schema = yaml.safe_load(open(os.path.join(ROOT, 'schema.yaml'), encoding='utf-8'))
    return schema, lex


def lex_values(lex, ref):
    if ref not in LEX_REF:
        return None
    fname, key = LEX_REF[ref]
    obj = lex[fname].get(key)
    if isinstance(obj, dict):
        return set(obj)
    if isinstance(obj, list):
        return {o.get('name') if isinstance(o, dict) else o for o in obj}
    return set()


def endpoint_types(expr):
    return [t.strip() for t in str(expr).split('|')]


class Report:
    def __init__(self):
        self.items = []
        self.counts = Counter()
        self.by_rule = defaultdict(Counter)

    def add(self, obj_id, rule, severity, msg, check=None):
        self.items.append({'object': obj_id, 'rule': rule, 'severity': severity, 'msg': msg, 'check': check})
        self.counts[severity] += 1
        self.by_rule[rule][severity] += 1

    def decision_of(self, obj_id):
        worst = None
        for it in self.items:
            if it['object'] == obj_id:
                if worst is None or SEV_ORDER[it['severity']] > SEV_ORDER[worst]:
                    worst = it['severity']
        return worst


def load_jsonl(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                raise SystemExit('%s 第 %d 行不是合法 JSON: %s' % (path, i, e))
    return rows


def check_nodes(nodes, schema, lex, rep):
    types = schema['nodes']
    for lineno, n in nodes:
        nid = n.get('id') or '<line %d>' % lineno
        ntype = n.get('type')
        if ntype not in types:
            rep.add(nid, 'C-SCHEMA-01', 'reject', '节点类型未登记: %s' % ntype, 'node_type_registered')
            continue
        key_field = types[ntype].get('key')
        for fname, fdef in (types[ntype].get('fields') or {}).items():
            if fdef.get('required'):
                # 序列化约定：统一用 id 承载各节点的 key 字段（见 schema.yaml#serialization）
                val = n.get('id') if fname == key_field else n.get(fname)
                if val in (None, '', [], {}):
                    rep.add(nid, 'C-SCHEMA-02', 'reject', '%s 缺必填字段 %s' % (ntype, fname), 'node_required_field')
                    continue
            val = n.get(fname)
            if val is None:
                continue
            inline = fdef.get('enum')
            if isinstance(inline, list) and isinstance(val, str) and val not in inline:
                rep.add(nid, 'C-META-02', 'reject', '%s.%s=%r 不在枚举内' % (ntype, fname, val), 'enum_membership')
            ref = fdef.get('ref')
            if ref:
                allowed = lex_values(lex, ref)
                if allowed:
                    vals = val if isinstance(val, list) else [val]
                    bad = [v for v in vals if v not in allowed]
                    if bad:
                        rep.add(nid, 'C-META-02', 'reject',
                                '%s.%s 取值不在词表 %s: %s' % (ntype, fname, ref.split('#')[-1], bad), 'enum_membership')
    # 唯一 id
    seen = {}
    for lineno, n in nodes:
        nid = n.get('id')
        if not nid:
            continue
        if nid in seen:
            rep.add(nid, 'C-ID-01', 'reject', '节点 id 重复（第 %d 行与第 %d 行）' % (seen[nid], lineno), 'node_id_unique')
        seen[nid] = lineno
    return {n.get('id'): n for _, n in nodes if n.get('id')}


def check_edges(edges, schema, node_index, rep):
    etypes = {e['name']: e for e in schema['edges']}
    for lineno, e in edges:
        et = e.get('type')
        eid = '%s->%s' % (e.get('from'), e.get('to'))
        if et not in etypes:
            rep.add(eid, 'C-SCHEMA-03', 'reject', '边类型未登记: %s' % et, 'edge_type_registered')
            continue
        spec = etypes[et]
        src, dst = node_index.get(e.get('from')), node_index.get(e.get('to'))
        if not src:
            rep.add(eid, 'C-SCHEMA-04', 'reject', '%s 的 from 不存在: %s' % (et, e.get('from')), 'edge_endpoint_exists')
        if not dst:
            rep.add(eid, 'C-SCHEMA-04', 'reject', '%s 的 to 不存在: %s' % (et, e.get('to')), 'edge_endpoint_exists')
        if src:
            allowed = endpoint_types(spec['from'])
            if src.get('type') not in allowed:
                rep.add(eid, 'C-SCHEMA-05', 'reject',
                        '%s 的 from 类型 %s 不在 %s 内' % (et, src.get('type'), allowed), 'edge_endpoint_type')
        if dst:
            allowed = endpoint_types(spec['to'])
            if dst.get('type') not in allowed:
                rep.add(eid, 'C-SCHEMA-05', 'reject',
                        '%s 的 to 类型 %s 不在 %s 内' % (et, dst.get('type'), allowed), 'edge_endpoint_type')


def compute_comparability_key(obs):
    """派生物料的唯一实现，免得检索层各算一套（见 schema.yaml#derived_fields）。"""
    ind = obs.get('indicator')
    if not ind:
        return None
    methods = obs.get('method') or []
    method = methods[0] if methods else 'na'
    ref = obs.get('reference_electrode') or 'na'
    # feature / AR 来自观测所属 Run；Observation 上可带冗余字段以便独立计算
    feat = obs.get('feature_kind') or 'na'
    basis = obs.get('current_basis') or 'na'
    ar = obs.get('aspect_ratio')
    if ar is None:
        bucket = 'na'
    else:
        bucket = 'AR<3' if ar < 3 else ('3<=AR<5' if ar < 5 else 'AR>=5')
    return '%s|%s|%s|%s|%s|%s' % (ind, method, ref, feat, bucket, basis)


def check_cross_record(nodes_by_id, edges, rep, nodes):
    # 1) 可比性键可算且不缺失（C-CMP-01 的计算侧）
    keys = {}
    for nid, n in nodes_by_id.items():
        if n.get('type') != 'Observation':
            continue
        key = n.get('comparability_key') or compute_comparability_key(n)
        if not key or key.startswith('|') or '|na|na|na' in key and not n.get('indicator'):
            rep.add(nid, 'C-CMP-01', 'reject', '无法计算 comparability_key（缺 indicator）', 'comparability_required')
            continue
        stored = n.get('comparability_key')
        if stored and stored != compute_comparability_key(n):
            rep.add(nid, 'C-CMP-01', 'warn',
                    '存下来的 comparability_key 与按 derived_fields 重算不一致：%r vs %r'
                    % (stored, compute_comparability_key(n)), 'comparability_required')
        if "na" in key.split("|"):
            rep.add(nid, "C-CMP-01", "warn", "口径含 na；仅允许候选召回，数值比较前须确认必需口径已知，不能将两个未知视为相同", "comparability_required")
        keys[nid] = key

    # 2) Conflict 必须同 indicator 同口径
    for nid, n in nodes_by_id.items():
        if n.get('type') != 'Conflict':
            continue
        claims = n.get('claims') or []
        claim_nodes = [nodes_by_id.get(c) for c in claims]
        if len([c for c in claim_nodes if c]) < 2:
            rep.add(nid, 'C-EV-03', 'reject', 'Conflict 少于 2 条有效 claim', 'conflict_has_report')
            continue
        if not n.get('report'):
            rep.add(nid, 'C-EV-03', 'reject', 'Conflict 缺 report（没写清为什么冲突）', 'conflict_has_report')
        obs_keys = []
        for c in claim_nodes:
            if not c:
                continue
            for oid in (c.get('observation_ids') or []):
                if oid in keys:
                    obs_keys.append(keys[oid])
        if len(set(obs_keys)) > 1 and n.get('conflict_type') != 'measurement_mismatch':
            rep.add(nid, 'C-CMP-02', 'reject',
                    '冲突各方的 comparability_key 不同（%s），应标 measurement_mismatch' % sorted(set(obs_keys)),
                    'conflict_same_indicator_key')

    # 3) KnowledgeUnit：支持度阈值、等级不虚高、窗口只用 reported、跨口径不得合并
    for nid, n in nodes_by_id.items():
        if n.get('type') != 'KnowledgeUnit':
            continue
        n_docs = n.get('n_docs') or 0
        n_runs = n.get('n_independent_runs') or 0
        support = n.get('support_class')
        if support == 'consensus' and not (n_docs >= 2 or n_runs >= 3):
            rep.add(nid, 'C-KU-01', 'reject',
                    'consensus 但 n_docs=%d / n_runs=%d 不足阈值（2 篇或 3 个独立 Run）' % (n_docs, n_runs),
                    'ku_consensus_threshold')
        claims = [nodes_by_id.get(c) for c in (n.get('evidence_claims') or [])]
        tiers = [c.get('evidence_tier') for c in claims if c and c.get('evidence_tier')]
        order = {'T1': 0, 'T2': 1, 'T3': 2, 'T4': 3}
        if tiers and n.get('tier') and order.get(n['tier'], 9) < min(order.get(t, 9) for t in tiers):
            rep.add(nid, 'C-KU-03', 'reject',
                    'KU tier=%s 高于最强单篇证据 %s（等级不能靠数量累加）' % (n['tier'], min(tiers, key=lambda t: order[t])),
                    'ku_tier_not_inflated')
        if n.get('effective_window') is not None and not isinstance(n.get('effective_window'), dict):
            rep.add(nid, 'C-KU-02', 'reject', 'effective_window 必须为 window 对象或 null', 'ku_window_reported_only')
            continue
        win = n.get('effective_window') or {}
        for pv in win.get('params') or []:
            if pv.get('presence') != 'reported':
                rep.add(nid, 'C-KU-02', 'reject',
                        'effective_window 含非 reported 参数 %s' % pv.get('param'), 'ku_window_reported_only')
            if pv.get('unit') and pv.get('unit') not in CANONICAL_UNITS:
                rep.add(nid, 'C-WIN-03', 'reject',
                        'effective_window 单位不是 canonical: %s' % pv.get('unit'), 'window_units_normalized')
        ku_keys = {keys[o] for c in claims if c for o in (c.get('observation_ids') or []) if o in keys}
        if len(ku_keys) > 1:
            rep.add(nid, 'C-CMP-01', 'reject',
                    'KU 合并了多个比较口径（%s），必须拆分' % sorted(ku_keys), 'comparability_required')
        if n.get('query_spec') or n.get('query') or n.get('window_query') or n.get('q'):
            rep.add(nid, 'C-CMP-01', 'reject', 'KU 上不得挂查询对象（KU 是知识，不是检索结果）', 'comparability_required')

    # 4) EXPLAINS：必须带条件或显式 unconstrained
    for lineno, e in edges:
        if e.get('type') != 'EXPLAINS':
            continue
        eid = '%s->%s' % (e.get('from'), e.get('to'))
        strength = e.get('strength')
        if strength not in (None, 'strong', 'partial', 'speculative'):
            rep.add(eid, 'C-EXPLAIN-01', 'reject', 'strength 非法: %r' % strength, 'explains_requires_scope')
        has_win = bool((e.get('window') or {}).get('params'))
        if not has_win and not e.get('unconstrained') and not e.get('scope_note'):
            rep.add(eid, 'C-EXPLAIN-01', 'warn', '解释链未带条件（window/unconstrained/scope_note 三缺）', 'explains_requires_scope')

    # 5) 未标定的加权分（C-CMP-03）
    for nid, n in nodes_by_id.items():
        for bad in ('evidence_score', 'score', 'rank_score'):
            if bad in n:
                rep.add(nid, 'C-CMP-03', 'warn', '节点带未标定的加权分 %s；v0 只允许偏序' % bad,
                        'no_weighted_score_uncalibrated')

    # 6) 化学身份与体系相容（节点层能判的几条）
    for nid, n in nodes_by_id.items():
        if n.get('type') == 'Chemical':
            if (n.get('smiles') or n.get('inchi_key')) and n.get('resolution_source') in (None, 'none'):
                rep.add(nid, 'C-CHEM-01', 'reject', '有 SMILES/InChIKey 但没有外部来源记录（禁猜）', 'no_guessed_structure')
        if n.get('type') == 'AdditiveUsage' and n.get('is_component') and n.get('role') not in (None, 'unknown'):
            rep.add(nid, 'C-CHEM-05', 'reject', '体系组分（主盐/酸/络合剂）不得带功能角色', 'component_not_candidate')

    # 7) 条件继承：声明的 inherited 参数必须在所引 Run 上真的 reported（C-EV-06）
    claim_runs = defaultdict(set)
    for lineno, e in edges:
        if e.get('type') == 'ABOUT':
            src, dst = nodes_by_id.get(e.get('from')), nodes_by_id.get(e.get('to'))
            if src and dst and src.get('type') == 'Claim' and dst.get('type') == 'Run':
                claim_runs[src['id']].add(dst['id'])
    for nid, n in nodes_by_id.items():
        if n.get('type') != 'Claim':
            continue
        cs = n.get('condition_source') or {}
        inherited = set(cs.get('inherited') or [])
        if not inherited:
            continue
        run_id = cs.get('run_ref')
        if not run_id or run_id not in nodes_by_id:
            rep.add(nid, 'C-EV-06', 'reject', '声明继承 %s 但 run_ref 无效: %r' % (sorted(inherited), run_id),
                    'inherited_requires_run')
            continue
        run = nodes_by_id[run_id]
        reported = {pv.get('param') for pv in (run.get('conditions') or [])
                    if pv.get('presence') == 'reported'}
        missing = inherited - reported
        if missing:
            rep.add(nid, 'C-EV-06', 'reject',
                    '继承的参数在 Run %s 上并非 reported: %s' % (run_id, sorted(missing)), 'inherited_requires_run')
        if run_id not in claim_runs.get(nid, set()):
            rep.add(nid, 'C-EV-06', 'warn',
                    'run_ref=%s 但缺少 Claim-ABOUT->Run 边，溯源链不完整' % run_id, 'inherited_requires_run')

    # 8) 表格来源可信度：OCR 链路与表块↔CSV 对齐（清洗 v2）
    tables = {nid: n for nid, n in nodes_by_id.items() if n.get('type') == 'Table'}
    obs_table = {}
    for nid, n in nodes_by_id.items():
        if n.get('type') != 'Observation':
            continue
        mt = n.get('measured_at') or {}
        if mt.get('table_id'):
            obs_table[nid] = mt['table_id']

    for tid, t in tables.items():
        blk = nodes_by_id.get(t.get('block_id'))
        if t.get('block_id') and not blk:
            rep.add(tid, 'C-ANCHOR-05', 'reject', 'block_id 指向不存在的 Block: %s' % t.get('block_id'),
                    'table_block_csv_link')
        if blk:
            if blk.get('block_type') != 'table':
                rep.add(tid, 'C-ANCHOR-05', 'reject', 'block_id 指向的 Block 不是 table 类型', 'table_block_csv_link')
            tm = blk.get('table_meta') or {}
            for key in ('n_rows', 'n_cols'):
                if t.get(key) is not None and tm.get(key) is not None and t[key] != tm[key]:
                    rep.add(tid, 'C-TABLE-06', 'reject',
                            '%s 不一致：Table=%s vs Block.table_meta=%s' % (key, t[key], tm[key]),
                            'table_dim_alignment')
            csv_rel = tm.get('csv')
            if csv_rel:
                base = os.path.basename(str(csv_rel).replace('\\', '/'))
                m = re.match(r'^(?P<doc>.+)__p(?P<page>\d+)_(?P<i>\d+)\.csv$', base)
                if m:
                    expect = 'tbl:%s:p%s:%s' % (m.group('doc'), m.group('page'), m.group('i'))
                    if tid != expect:
                        rep.add(tid, 'C-ANCHOR-05', 'reject',
                                'table_id 与 CSV 文件名不符：期望 %s 实际 %s' % (expect, tid),
                                'table_block_csv_link')
                else:
                    rep.add(tid, 'C-ANCHOR-05', 'warn', 'CSV 文件名不符合 {doc}__p{page}_{i}.csv：%s' % base,
                            'table_block_csv_link')
            if not csv_rel:
                rep.add(tid, 'C-ANCHOR-05', 'warn', '表块没有 table_meta.csv，无法反查矩阵', 'table_block_csv_link')

    # OCR 可信度对断言的影响
    claim_obs = {}
    for nid, n in nodes_by_id.items():
        if n.get('type') != 'Claim':
            continue
        ids = set(n.get('observation_ids') or [])
        for lineno, e in edges:
            if e.get('type') == 'ABOUT' and e.get('from') == nid:
                dst = nodes_by_id.get(e.get('to'))
                if dst and dst.get('type') == 'Observation':
                    ids.add(dst['id'])
        claim_obs[nid] = ids
    obs_by_id = {nid: n for nid, n in nodes_by_id.items() if n.get('type') == 'Observation'}

    for tid, t in tables.items():
        status = t.get('ocr_status')
        if not status:
            continue
        affected = [oid for oid, owner in obs_table.items() if owner == tid]
        numeric_obs = [oid for oid in affected
                       if (obs_by_id.get(oid) or {}).get('outcome_kind') in ('numeric', 'range')]
        if status == 'unreadable' and numeric_obs:
            rep.add(tid, 'C-TABLE-04', 'reject',
                    'ocr_status=unreadable 却产出了 %d 条数值观测: %s' % (len(numeric_obs), numeric_obs[:3]),
                    'unreadable_table_no_numeric')
        if status in ('partial', 'unreadable') or t.get('evidence') == 'raster_or_image':
            for cid, oids in claim_obs.items():
                if set(oids) & set(affected) and (nodes_by_id.get(cid) or {}).get('evidence_tier') == 'T1':
                    rep.add(cid, 'C-TABLE-05', 'downgrade',
                            '证据来自 %s 表（ocr_status=%s, evidence=%s），T1 应降为 T2'
                            % (tid, status, t.get('evidence')), 'partial_ocr_tier_cap')

    # 9) 其余可机判规则：ANOVA 表、扫轴一致性、自评 confidence 冒充证据等级
    exp_runs = defaultdict(list)
    for nid, n in nodes_by_id.items():
        if n.get('type') == 'Run' and n.get('exp_id'):
            exp_runs[n['exp_id']].append(n)

    for tid, t in tables.items():
        if t.get('etl_profile') != 'anova':
            continue
        affected = {oid for oid, owner in obs_table.items() if owner == tid}
        for cid, oids in claim_obs.items():
            if not (set(oids) & affected):
                continue
            c = nodes_by_id.get(cid) or {}
            if c.get('predicate') in PROCESS_PREDICATES:
                rep.add(cid, 'C-TABLE-03', 'reject',
                        '证据来自 ANOVA 表（%s），不得产工艺/填充断言（predicate=%s）'
                        % (tid, c.get('predicate')), 'anova_no_process_claim')

    for eid, runs in exp_runs.items():
        exp = nodes_by_id.get(eid) or {}
        for p in exp.get('swept_params') or []:
            seen, vals = False, set()
            for r in runs:
                for pv in r.get('conditions') or []:
                    if pv.get('param') == p and pv.get('presence') == 'reported':
                        seen = True
                        vals.add((pv.get('kind'), pv.get('value'), pv.get('lo'), pv.get('hi')))
            if not seen:
                rep.add(eid, 'C-EXP-02', 'warn',
                        '声明为扫轴（%s）但在所有 Run 中都未报道' % p, 'swept_consistency')
            elif len(vals) < 2:
                rep.add(eid, 'C-EXP-02', 'warn',
                        '扫轴 %s 只有 1 个取值，不能算扫过' % p, 'swept_consistency')

    for nid, n in nodes_by_id.items():
        if n.get('type') in ('Claim', 'EvidenceLink') and n.get('confidence') is not None:
            rep.add(nid, 'C-EV-04', 'warn',
                    '模型自评 confidence=%r 不能当作证据等级（用 T1–T4）' % (n.get('confidence'),),
                    'confidence_not_tier')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nodes', required=True)
    ap.add_argument('--edges', required=True)
    ap.add_argument('--json', dest='json_out')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    schema, lex = load_all()
    nodes = load_jsonl(args.nodes)
    edges = load_jsonl(args.edges)
    rep = Report()
    node_index = check_nodes(nodes, schema, lex, rep)
    check_edges(edges, schema, node_index, rep)
    check_cross_record(node_index, edges, rep, nodes)

    if not args.quiet:
        for it in rep.items:
            print('%-6s %-10s %-38s %s' % (it['severity'].upper(), it.get('rule') or '-', it['object'], it['msg']))
    print('=== 节点 %d / 边 %d；问题: %s'
          % (len(nodes), len(edges), ', '.join('%s=%d' % (k, v) for k, v in sorted(rep.counts.items())) or '无'))
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump({'items': rep.items, 'summary': dict(rep.counts),
                       'nodes': len(nodes), 'edges': len(edges)}, f, ensure_ascii=False, indent=2)
        print('报告已写入 %s' % args.json_out)
    return 1 if rep.counts.get('reject') else 0


CHECKS = {
    'comparability_required', 'conflict_same_indicator_key', 'no_weighted_score_uncalibrated',
    'ku_consensus_threshold', 'ku_window_reported_only', 'ku_tier_not_inflated',
    'explains_requires_scope', 'no_guessed_structure', 'component_not_candidate',
    'inherited_requires_run',
    'unreadable_table_no_numeric', 'partial_ocr_tier_cap',
    'table_dim_alignment', 'table_block_csv_link',
    'anova_no_process_claim', 'swept_consistency', 'confidence_not_tier',
    'conflict_has_report', 'window_units_normalized',
    'node_type_registered', 'node_required_field', 'node_id_unique',
    'edge_type_registered', 'edge_endpoint_exists', 'edge_endpoint_type',
}

if __name__ == '__main__':
    sys.exit(main())
