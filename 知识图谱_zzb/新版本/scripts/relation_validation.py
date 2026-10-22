"""Validation of the active grounded relation context; no historical-run dependency."""
import re

STATEMENTS = {'calculation_result', 'observation', 'author_interpretation', 'unknown', 'definition', 'future_work', 'reported_claim'}
KINDS = {'indicator_definition', 'baseline_observation', 'measurement', 'adsorption', 'complexation', 'method_setting', 'recommendation', 'effect', 'composition'}


def source_spans(value):
    if isinstance(value, dict):
        if {'block_id', 'start', 'end', 'text'} <= value.keys():
            yield value
        else:
            for item in value.values():
                yield from source_spans(item)
    elif isinstance(value, list):
        for item in value:
            yield from source_spans(item)


def binding(span, graph, resolution, *, allow_contained=False):
    candidates = sorted({resolution['mention_to_concept'][m['id']] for m in graph['mentions']
                         if m['surface'] == span['text'] and m['evidence'].get('block_id') == span['block_id']
                         and m['id'] in resolution['mention_to_concept']})
    status = 'bound_existing_source_name'
    if not candidates and allow_contained:
        # Only remove grammatical wrappers, not chemical qualifiers/specifications.
        name = re.sub(r'^the\s+', '', span['text'])
        name = re.sub(r'\s+molecule$', '', name)
        candidates = sorted({resolution['mention_to_concept'][m['id']] for m in graph['mentions']
            if m['surface'] == name and m['evidence'].get('block_id') == span['block_id']
            and isinstance(m['evidence'].get('start'), int) and isinstance(m['evidence'].get('end'), int)
            and span['start'] <= m['evidence']['start'] < m['evidence']['end'] <= span['end']
            and m['id'] in resolution['mention_to_concept']})
        status = 'bound_existing_contained_name'
    return {'surface': span['text'], 'concept_id': candidates[0] if len(candidates) == 1 else None,
            'candidate_concept_ids': candidates, 'status': status if len(candidates) == 1 else 'unresolved'}


def validate_artifact(graph, resolution, artifact, *, require_review=True):
    errors, ids = [], set()
    if artifact.get('format_version') != 1 or not isinstance(artifact.get('cases'), list) or not artifact['cases']:
        return {'valid': False, 'errors': ['invalid_or_empty_artifact'], 'cases': 0}
    blocks = {b['id']: b for b in graph['blocks']}
    concepts = {c['id'] for c in resolution['concepts']}
    for row in artifact.get('cases', []):
        tag = row.get('id', 'missing')
        if tag in ids:
            errors.append('duplicate_case_id')
        ids.add(tag)
        if row.get('statement_type') not in STATEMENTS or row.get('kind') not in KINDS:
            errors.append(tag + ':invalid_type_label')
        if require_review and row.get('review', {}).get('status') != 'accepted_for_context':
            errors.append(tag + ':review_pending')
        if row.get('review', {}).get('expert_verified') or artifact.get('expert_verified'):
            errors.append(tag + ':unsupported_expert_verification')
        if not row.get('evidence') or not row.get('subject'):
            errors.append(tag + ':missing_subject_or_evidence')
        spans = list(source_spans(row))
        if not spans:
            errors.append(tag + ':no_source_spans')
        for span in spans:
            block = blocks.get(span['block_id'])
            if not block or span['block_id'] not in row.get('source_block_ids', []) or block['document_id'] != row['document_id']:
                errors.append(tag + ':foreign_source')
            elif not isinstance(span['start'], int) or not isinstance(span['end'], int) or not 0 <= span['start'] < span['end'] <= len(block['text']) or block['text'][span['start']:span['end']] != span['text']:
                errors.append(tag + ':source_offset_mismatch')
        group_ids = {item['id'] for item in row.get('groups', [])}
        if len(group_ids) != len(row.get('groups', [])) or 'all' in group_ids:
            errors.append(tag + ':invalid_groups')
        keys = []
        for condition in row.get('conditions', []):
            gid = condition.get('group_id')
            if gid != 'all' and gid not in group_ids:
                errors.append(tag + ':unknown_condition_group')
            keys.append((condition['parameter'].strip().casefold(), gid))
        if len(keys) != len(set(keys)) or any((p, 'all') in keys and g != 'all' for p, g in keys):
            errors.append(tag + ':condition_conflict')
        for name in ('baseline', 'value'):
            if group_ids and row.get(name) and row[name].get('group_id') not in group_ids:
                errors.append(tag + ':unknown_value_group')
        for role, linked in row.get('entity_bindings', {}).items():
            cid = linked.get('concept_id')
            if cid is not None and cid not in concepts:
                errors.append(tag + ':unknown_concept')
            elif role not in row or linked != binding(row[role], graph, resolution, allow_contained=role == 'subject'):
                errors.append(tag + ':source_binding_mismatch')
    return {'valid': not errors, 'errors': errors, 'cases': len(artifact.get('cases', []))}
