"""Losslessly represent JSON values as native Neo4j properties and ordered nodes.

The JSON text itself is never stored; object scalar fields become `p_<key>`
properties, and nested objects, arrays and nulls become SourceValue nodes.
"""
import hashlib
import json


def _key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _kind(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError('JSON integer exceeds Neo4j signed 64-bit range')
        return 'integer'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    raise TypeError(f'Unsupported JSON value: {type(value)}')


def encode(value, owner_id, field):
    """Return root ID, source-value nodes and ordered child edges."""
    nodes, edges = [], []

    def visit(item, path):
        kind = _kind(item)
        node_id = _key('source-value-v1', owner_id, field, path)
        node = {'id': node_id, 'kind': kind, 'owner_id': owner_id, 'source_field': field}
        nodes.append(node)
        if kind == 'object':
            node['keys'] = list(item.keys())
            scalar_keys = []
            for name, child in item.items():
                child_kind = _kind(child)
                if child_kind in ('string', 'boolean', 'integer', 'number'):
                    node['p_' + name] = child
                    scalar_keys.append(name)
                else:
                    cid = visit(child, path + [['key', name]])
                    edges.append({'parent': node_id, 'child': cid, 'field': name, 'index': None})
            node['scalar_keys'] = scalar_keys
        elif kind == 'array':
            node['length'] = len(item)
            kinds = {_kind(x) for x in item}
            if len(kinds) <= 1 and (not kinds or kinds <= {'string', 'integer', 'number', 'boolean'}):
                node['values'] = item
                node['item_kind'] = next(iter(kinds), 'empty')
            else:
                for i, child in enumerate(item):
                    cid = visit(child, path + [['index', i]])
                    edges.append({'parent': node_id, 'child': cid, 'field': None, 'index': i})
        elif kind != 'null':
            node['value'] = item
        return node_id

    root = visit(value, [])
    return root, nodes, edges


def decode(root, nodes, edges):
    """Reconstruct a value for validation; node and edge data are Neo4j-safe."""
    by_id = {n['id']: n for n in nodes}
    children = {}
    for e in edges:
        children.setdefault(e['parent'], []).append(e)

    def visit(identifier):
        n = by_id[identifier]
        kind = n['kind']
        if kind == 'object':
            child_by_field = {e['field']: e['child'] for e in children.get(identifier, [])}
            scalars = set(n['scalar_keys'])
            return {name: n['p_' + name] if name in scalars else visit(child_by_field[name]) for name in n['keys']}
        if kind == 'array':
            if 'item_kind' in n:
                return n.get('values', [])
            return [visit(e['child']) for e in sorted(children.get(identifier, []), key=lambda x: x['index'])]
        return None if kind == 'null' else n['value']

    return visit(root)

