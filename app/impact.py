"""Provenance-aware bounded graph traversal; stale or unauthorized edges are never emitted."""
from __future__ import annotations
from collections import defaultdict, deque
from .config import MAX_IMPACT_DEPTH, MAX_IMPACT_PATHS
from .security import role_for, document_permitted


def direct_links(conn, actor, project, node):
    role_for(conn,actor,project)
    raw = conn.execute('''SELECT dep.*,doc.version AS latest_version FROM dependencies dep
       JOIN documents doc ON doc.id=dep.evidence_doc_id
       WHERE dep.project_id=? AND dep.upstream=? ORDER BY dep.id''',(project,node)).fetchall()
    result, suppressed = [], {'stale':0,'unauthorized':0}
    for r in raw:
        if not document_permitted(conn, actor, project, r['evidence_doc_id']):
            suppressed['unauthorized'] += 1
        elif r['evidence_version'] != r['latest_version']:
            suppressed['stale'] += 1
        else:
            result.append({'id':r['id'],'from':r['upstream'],'to':r['downstream'],
                           'description':r['description'],'source_id':r['evidence_doc_id'],
                           'source_version':r['evidence_version']})
    return {'node':node,'links':result,'suppressed':suppressed}


def trace_impact(conn, actor, project, root, max_depth=MAX_IMPACT_DEPTH):
    role_for(conn,actor,project)
    max_depth = max(1,min(max_depth,MAX_IMPACT_DEPTH))
    # Only expose paths with a sequence of verified, currently authorized evidence edges.
    queue = deque([(root,[root],[])])
    paths, affected = [], set()
    suppressed = {'unauthorized':0,'stale':0,'cycle':0,'depth_limit':0}
    truncated = False
    while queue:
        node,nodes,edges = queue.popleft()
        if len(nodes)-1 >= max_depth:
            if direct_links(conn,actor,project,node)['links']:
                suppressed['depth_limit'] += 1
            continue
        result = direct_links(conn,actor,project,node)
        for key in ('unauthorized','stale'):
            suppressed[key] += result['suppressed'][key]
        for edge in result['links']:
            nxt = edge['to']
            if nxt in nodes:
                suppressed['cycle'] += 1
                continue
            new_nodes = nodes+[nxt]
            new_edges = edges+[edge]
            paths.append({'nodes':new_nodes, 'evidence':[{'dependency_id':e['id'],
                'source_id':e['source_id'],'source_version':e['source_version']} for e in new_edges]})
            affected.add(nxt)
            if len(paths) >= MAX_IMPACT_PATHS:
                truncated = True
                queue.clear()
                break
            queue.append((nxt,new_nodes,new_edges))
        if truncated:
            break
    return {'root':root,'affected_nodes':sorted(affected),'paths':paths,
            'path_count':len(paths),'suppressed':suppressed,
            'truncated':truncated, 'explanation':'每條路徑僅代表已記錄的可能影響，並非已證明延誤或故障。'}


def node_source_requirements(impact):
    """For each affected node, the alternative sets of source_ids whose provenance
    proves that node reachable. A node is visible to a reader only if they currently
    hold access to every source_id in at least one of its sets -- this is the same
    all-or-nothing rule direct_links/trace_impact already apply when first building the
    path, kept as a reusable snapshot so callers can re-check it later against a
    different (future) reader without re-running the live dependency graph."""
    by_node = {}
    for path in impact.get('paths',[]) or []:
        if not path.get('nodes'):
            continue
        node = path['nodes'][-1]
        sources = sorted({e['source_id'] for e in path.get('evidence',[]) or [] if e.get('source_id')})
        if sources and sources not in by_node.setdefault(node,[]):
            by_node[node].append(sources)
    return by_node
