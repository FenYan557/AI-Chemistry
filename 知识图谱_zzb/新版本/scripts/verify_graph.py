"""Verify the current standalone v2 package without consulting backups or a network."""
import argparse
import ast
import json
from pathlib import Path

from runtime_common import ROOT, load, file_digest
from relation_validation import validate_artifact
from validate import validate


def check(root=ROOT):
    root = Path(root).resolve()
    current = load(root / 'CURRENT.json')
    manifest = load(root / current['manifest'])
    errors = []
    def local(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or '备份' in path.relative_to(root).parts:
            raise ValueError('active dependency must be inside the current package, outside backups')
        return path
    if current['current_version_id'] != manifest['version_id']:
        errors.append('version_id_mismatch')
    for relative, info in manifest['assets'].items():
        path = local(relative)
        if not path.is_file() or path.stat().st_size != info['bytes'] or file_digest(path) != info['sha256']:
            errors.append('asset_changed:' + relative)
    for key, hash_key in [('graph', 'sha256'), ('entity_resolution', 'entity_resolution_sha256'), ('relation_context', 'relation_context_sha256')]:
        if file_digest(local(current[key])) != current[hash_key]:
            errors.append('selector_hash_mismatch:' + key)
    graph = load(local(current['graph']))
    resolution = load(local(current['entity_resolution']))
    context = load(local(current['relation_context']))
    if resolution['source_graph'] != current['graph'] or resolution['source_sha256'] != current['sha256']:
        errors.append('entity_source_mismatch')
    if context['source_graph_sha256'] != current['sha256'] or context['source_entity_resolution_sha256'] != current['entity_resolution_sha256']:
        errors.append('context_source_mismatch')
    mentions = {m['id'] for m in graph['mentions']}
    concepts = {c['id'] for c in resolution['concepts']}
    if set(resolution['mention_to_concept']) != mentions or not set(resolution['mention_to_concept'].values()) <= concepts:
        errors.append('mention_concept_coverage_mismatch')
    if {r['fact_id'] for r in resolution['contextual_facts']} != {f['id'] for f in graph['facts']}:
        errors.append('resolved_fact_coverage_mismatch')
    raw = validate(graph)
    if not raw['valid']:
        errors.append('raw_graph_validation_failed')
    supplemental = validate_artifact(graph, resolution, context)
    if not supplemental['valid']:
        errors.extend(supplemental['errors'])
    counts = {'documents': len(graph['documents']), 'blocks': len(graph['blocks']), 'mentions': len(graph['mentions']),
              'concepts': len(resolution['concepts']), 'facts': len(graph['facts']), 'edges': len(graph['edges']),
              'optimized_cases': len(context['cases'])}
    if counts != manifest['counts']:
        errors.append('counts_mismatch')
    # No runtime module should import archived extraction/development code.
    script_paths = {p.stem: p for p in (root / 'scripts').glob('*.py')}
    banned = {'resolve_entities_llm', 'relation_optimization', 'extraction_llm', 'kg_versions', 'register_relation_optimization'}
    for name, path in script_paths.items():
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split('.')[0] in banned:
                errors.append('archived_runtime_dependency:' + name + ':' + node.module)
    return {'valid': not errors, 'errors': errors, 'version': current['current_version_id'], 'counts': counts,
            'raw_validation_tiers': raw['tier_counts'], 'relation_context_valid': supplemental['valid'],
            'network_calls': 0, 'backup_dependencies': 0, 'semantic_expert_review': 'pending'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['valid'] else 1)
