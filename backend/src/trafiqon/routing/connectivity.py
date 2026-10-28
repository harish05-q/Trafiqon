"""Strong connectivity of the open road network (iterative Tarjan; no recursion limits)."""

from __future__ import annotations

from trafiqon.domain.models import Graph


def strongly_connected_components(graph: Graph) -> int:
    """Number of strongly connected components using open edges only."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    components = 0
    for root in graph.nodes:
        if root in index:
            continue
        work = [(root, iter(graph.out_edges(root)))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, edges = work[-1]
            advanced = False
            for edge in edges:
                nxt = edge.target
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(graph.out_edges(nxt))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                components += 1
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    if member == node:
                        break
    return components
