"""Expose reviewed typed context to RAG without changing raw facts or their counts."""
import re
from pathlib import Path

from runtime_common import load, file_digest as sha
from relation_validation import source_spans, validate_artifact

ATTRIBUTION = {'observation': '该研究的观测结果', 'calculation_result': '计算或模拟相关结果',
               'author_interpretation': '作者提出的解释', 'reported_claim': '文献报告的陈述',
               'future_work': '作者提出的后续研究方向', 'unknown': '来源陈述', 'definition': '文献中的指标定义'}


def load_active(current, root, graph, resolution):
    if not current.get('relation_context'):
        return None
    root = Path(root).resolve()
    path = (root / current['relation_context']).resolve()
    if not path.is_relative_to(root) or sha(path) != current.get('relation_context_sha256'):
        raise ValueError('relation context path/hash mismatch')
    artifact = load(path)
    if artifact['source_graph_sha256'] != current['sha256'] or artifact['source_entity_resolution_sha256'] != current['entity_resolution_sha256']:
        raise ValueError('relation context graph/resolution fingerprint mismatch')
    result = validate_artifact(graph, resolution, artifact)
    if not result['valid']:
        raise ValueError(str(result))
    return artifact


def append_context(context, graph, resolution, artifact, query, concept_ids, limit=8):
    checked = validate_artifact(graph, resolution, artifact)
    if not checked['valid']:
        raise ValueError(str(checked))
    selected = []
    words = {w.casefold() for w in re.findall(r'[A-Za-z]{4,}', query)}
    for row in artifact['cases']:
        bound = {b['concept_id'] for b in row['entity_bindings'].values() if b['concept_id']}
        subject = row['subject']['text']
        name_match = bool(re.search(r'(?<![A-Za-z0-9_-])' + re.escape(subject) + r'(?![A-Za-z0-9_-])', query, re.I))
        matched = bound & set(concept_ids)
        if not matched and not name_match:
            continue
        score = len(matched) * 10 + len(words & set(row['claim'].casefold().split()))
        selected.append((score, row))
    selected.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    docs = {d['id']: d for d in graph['documents']}
    concepts = {c['id']: c for c in resolution['concepts']}
    output = []
    for _, row in selected[:limit]:
        citation = 'C' + str(len(output) + 1)
        groups = {g['id']: g['evidence']['text'] for g in row['groups']}
        def value(name):
            if name not in row:
                return None
            item = row[name]
            return {'raw': item['source']['text'], 'group_evidence': groups.get(item.get('group_id'))}
        participant_notes = []
        for role, linked in row['entity_bindings'].items():
            cid = linked['concept_id']
            participant_notes.append({'role': role, 'name': linked['surface'],
                'identity_review_required': cid is None or concepts[cid].get('identity_review_required', False)})
        output.append({'citation': citation, 'document': docs[row['document_id']]['title'],
                       'participants': participant_notes, 'claim': row['claim'],
                       'attribution': ATTRIBUTION[row['statement_type']],
                       'conditions': [{'parameter': c['parameter'], 'value': c['value']['text'],
                           'applies_to': '该记录的共同测试设置' if c['group_id'] == 'all' else groups[c['group_id']],
                           **({'unit_note': '单位按原文保留，待回查'} if c.get('source_unit_review_required') else {})} for c in row['conditions']],
                       'result': value('value'), 'baseline': value('baseline'),
                       'methods': [m['text'] for m in row['methods']],
                       'qualifiers': [{'cue': q['cue']['text'], 'scope': q['scope']} for q in row['qualifiers']],
                       'evidence': [{'quote': e['text']} for e in row['evidence']]})
        context['references'][citation] = {'relation_context_id': row['id'], 'document_id': row['document_id'],
            'evidence': [{'block_id': s['block_id'], 'start': s['start'], 'end': s['end'], 'quote': s['text']} for s in source_spans(row)]}
    context['optimized_cases'] = output
    context['instruction'] += '\noptimized_cases保留了同文献补齐的方法、条件和限定语，可用[C1]等引用。与既有事实可能重复，不把重复表述算作多份独立证据。共同测试设置仅适用于所在记录的实验；分组条件不得转移到对照组、模拟或其他文献。单位待回查的字段不能用于精确计算。保留作者解释的可能性，不升级为实验证实。'
    context['retrieval']['returned_optimized_cases'] = len(output)
    return context
