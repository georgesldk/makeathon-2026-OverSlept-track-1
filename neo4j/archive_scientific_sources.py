#!/usr/bin/env python3
"""Archive pipeline JSON outputs as native graph values, excluding external caches."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

from neo4j import GraphDatabase
from structured_values import _key, _kind

ROOT = Path(__file__).resolve().parent.parent
DIRECTORIES = ('matching', 'historical_texts', 'scientific_name_sources', 'common_name_sources', 'description_sources', 'claims', 'stage3')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON object key cannot be archived without loss: {key!r}')
        result[key] = value
    return result


def outputs():
    for directory in DIRECTORIES:
        for path in sorted((ROOT / directory).rglob('*')):
            if (path.is_file() and path.suffix in ('.json', '.jsonl', '.csv')
                    and 'cache' not in path.parts and (path.suffix != '.csv' or 'data' not in path.parts)):
                yield path


def stream(value, owner, field):
    """Stream a value tree without constructing the whole node list in memory."""
    def visit(item, path):
        kind = _kind(item)
        identifier = _key('source-value-v1', owner, field, path)
        node = {'id': identifier, 'kind': kind, 'owner_id': owner, 'source_field': field}
        if kind == 'object':
            node['keys'] = list(item)
            scalars = [k for k, v in item.items() if _kind(v) in ('string', 'boolean', 'integer', 'number')]
            node['scalar_keys'] = scalars
            for k in scalars:
                node['p_' + k] = item[k]
            yield 'node', node
            scalar_set = set(scalars)
            for k, v in item.items():
                if k not in scalar_set:
                    sub = path + [['key', k]]
                    yield from visit(v, sub)
                    yield 'edge', {'parent': identifier, 'child': _key('source-value-v1', owner, field, sub), 'field': k, 'index': None}
        elif kind == 'array':
            node['length'] = len(item)
            kinds = {_kind(x) for x in item}
            if len(kinds) <= 1 and (not kinds or kinds <= {'string', 'integer', 'number', 'boolean'}):
                node['values'] = item
                node['item_kind'] = next(iter(kinds), 'empty')
                yield 'node', node
            else:
                yield 'node', node
                for i, child in enumerate(item):
                    sub = path + [['index', i]]
                    yield from visit(child, sub)
                    yield 'edge', {'parent': identifier, 'child': _key('source-value-v1', owner, field, sub), 'field': None, 'index': i}
        else:
            if kind != 'null':
                node['value'] = item
            yield 'node', node
    return _key('source-value-v1', owner, field, []), visit(value, [])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', required=True)
    p.add_argument('--inventory', action='store_true', help='List source files without connecting')
    args = p.parse_args()
    paths = list(outputs())
    if args.inventory:
        for path in paths:
            print(path.relative_to(ROOT), path.stat().st_size)
        print('Total files:', len(paths), 'bytes:', sum(p.stat().st_size for p in paths))
        return
    driver = GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ.get('NEO4J_USER', 'neo4j'), os.environ['NEO4J_PASSWORD']))
    with driver, driver.session(database=args.database) as s:
        if s.run('MATCH (n:StructuredBuild {status:"complete"}) RETURN count(n) AS n').single()['n'] != 1:
            raise ValueError('Expected a completed structured graph build')
        s.run('CREATE CONSTRAINT source_document_id IF NOT EXISTS FOR (n:SourceDocument) REQUIRE n.id IS UNIQUE').consume()
        node_q = 'UNWIND $rows AS r MERGE (n:SourceValue {id:r.id}) SET n += r RETURN count(n) AS n'
        edge_q = 'UNWIND $rows AS r MATCH (a:SourceValue {id:r.parent}), (b:SourceValue {id:r.child}) MERGE (a)-[e:HAS_VALUE]->(b) SET e.field=r.field, e.position=r.index RETURN count(e) AS n'
        for path in paths:
            rel = str(path.relative_to(ROOT))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            doc_id = _key('scientific-source-document-v1', rel, digest)
            if s.run('MATCH (d:SourceDocument {id:$id, status:"complete"}) RETURN count(d) AS n', id=doc_id).single()['n']:
                print('Already archived', rel, flush=True)
                continue
            s.run('MATCH (b:StructuredBuild {status:"complete"}) MERGE (d:SourceDocument {id:$id}) SET d.path=$path, d.sha256=$sha, d.format=$format, d.status="loading" MERGE (b)-[:INCLUDES_SOURCE]->(d)', id=doc_id, path=rel, sha=digest, format=path.suffix[1:]).consume()
            nodes, edges, roots = [], [], []
            def flush():
                if nodes:
                    if s.run(node_q, rows=nodes).single()['n'] != len(nodes): raise RuntimeError('Node count mismatch')
                    nodes.clear()
                if edges:
                    if s.run(edge_q, rows=edges).single()['n'] != len(edges): raise RuntimeError('Edge endpoint missing')
                    edges.clear()
                if roots:
                    q = 'UNWIND $rows AS r MATCH (d:SourceDocument {id:r.doc}), (v:SourceValue {id:r.root}) MERGE (d)-[:HAS_RECORD {position:r.position}]->(v) RETURN count(v) AS n'
                    if s.run(q, rows=roots).single()['n'] != len(roots): raise RuntimeError('Document record missing')
                    roots.clear()
            def write(value, position):
                owner = _key(doc_id, 'record', position)
                root, events = stream(value, owner, 'content')
                for kind, row in events:
                    (nodes if kind == 'node' else edges).append(row)
                    if len(nodes) >= 1000 or len(edges) >= 1000: flush()
                roots.append({'doc': doc_id, 'root': root, 'position': position})
                if len(roots) >= 1000: flush()
            if path.suffix == '.csv':
                with path.open(encoding='utf-8-sig', newline='') as f:
                    reader = csv.reader(f)
                    header = next(reader, [])
                    s.run('MATCH (d:SourceDocument {id:$id}) SET d.columns=$columns', id=doc_id, columns=header).consume()
                    for position, record in enumerate(reader, 1):
                        write(record, position)
            elif path.suffix == '.jsonl':
                with path.open(encoding='utf-8') as f:
                    for line_no, line in enumerate(f, 1):
                        if line.strip(): write(json.loads(line, object_pairs_hook=unique_object), line_no)
            else:
                with path.open(encoding='utf-8') as f: write(json.load(f, object_pairs_hook=unique_object), 0)
            flush()
            s.run('MATCH (d:SourceDocument {id:$id}) SET d.status="complete"', id=doc_id).consume()
            print('Archived', rel, flush=True)


if __name__ == '__main__': main()
