"""One rule: a grouping's members read along the flow that runs through them.

The rule was implemented twice, for the two paths that emit a grouping's hidden spread chain —
the auto-layout that rewrites an authored PUML body (`application.modeling.artifact_write_layout`)
and the renderer that generates one from model records (`infrastructure.rendering._diagram_layout`).
Two copies of an ordering rule drift, and this pair had: the authored path was corrected to follow
the flow while the generated path still chained members in the order the type grouping built them,
which is by artifact type then id. So the *Promote Artifacts* view laid eight functions out as
Validate, Execute, Resolve, Run, Verify, Select, Detect, Replace, and every triggering arrow
criss-crossed the row.

It lives here, beside the auto-layout it was extracted from, because it is presentation: where an
element sits on a spread axis says nothing about the model and is not a fact the domain holds. The
domain holds what a diagram *is* — its entities, connections and bindings — and this decides only
how one is read. Both callers may depend on this layer (the renderer is infrastructure and already
reaches into `application` for alias normalisation), so one copy suffices without inverting any
dependency. What differs between them is only how they obtain the directed pairs — one parses arrows
out of PUML text, the other reads connection records — and that stays with each caller.

Ordering is by depth along the whole flow graph, not by a sort restricted to the group's own
members. A triggering chain routinely leaves a group and returns (a function triggers an event, the
event triggers the next function); an order computed from the members' own edges cannot see that
and reports the re-entry point as another beginning.
"""

from __future__ import annotations

from collections import defaultdict


def flow_depths(flow_edges: list[tuple[str, str]]) -> dict[str, int]:
    """Longest-path depth of every alias the flow reaches.

    Longest path rather than first-visit order: an element must sit after *everything* that leads
    to it, so where two paths of different lengths converge the longer one decides.
    """
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree: dict[str, int] = defaultdict(int)
    nodes: set[str] = set()
    for source_alias, target_alias in flow_edges:
        if source_alias == target_alias:
            continue  # a self-loop orders nothing
        nodes.update((source_alias, target_alias))
        if target_alias not in outgoing[source_alias]:
            outgoing[source_alias].add(target_alias)
            indegree[target_alias] += 1

    depth = dict.fromkeys(nodes, 0)
    queue = sorted(node for node in nodes if indegree[node] == 0)
    resolved: set[str] = set()
    while queue:
        current = queue.pop(0)
        resolved.add(current)
        for successor in sorted(outgoing.get(current, ())):
            depth[successor] = max(depth[successor], depth[current] + 1)
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
                queue.sort()

    # A feedback loop leaves its members unresolved: they never reach indegree zero.
    # A chain that leaves a container and RETURNS to it is such a loop once edges are
    # lifted to the containers, and it still has one obvious reading direction — so
    # break the loop instead of flattening it: walk depth-first from the loop's entry
    # points in deterministic order, ignoring edges back into already-placed nodes,
    # and place each member one step after its predecessor.
    unresolved = nodes - resolved
    if unresolved:
        base_depth = max(depth.values(), default=0)
        entries = sorted(
            unresolved,
            key=lambda node: (
                # Prefer entering where the resolved flow points into the loop.
                0 if any(node in outgoing.get(done, ()) for done in resolved) else 1,
                node,
            ),
        )
        placed: set[str] = set()
        for entry in entries:
            if entry in placed:
                continue
            stack = [(entry, base_depth + 1)]
            while stack:
                current, current_depth = stack.pop()
                if current in placed:
                    continue
                placed.add(current)
                depth[current] = max(depth.get(current, 0), current_depth)
                for successor in sorted(outgoing.get(current, ()), reverse=True):
                    if successor in unresolved and successor not in placed:
                        stack.append((successor, current_depth + 1))
    return depth


def order_aliases_along_flow(
    *,
    aliases: list[str],
    flow_edges: list[tuple[str, str]],
) -> list[str]:
    """`aliases` in the order the flow running through them reads.

    Stable: members the flow does not reach keep their relative position and follow the ones it
    does, so a grouping expressing no flow is emitted exactly as it arrived. Their incoming order
    is the caller's (artifact type, then label), which is the only thing left to fall back on.
    """
    depth_by_alias = flow_depths(flow_edges)
    original_index = {alias: index for index, alias in enumerate(aliases)}

    def _sort_key(alias: str) -> tuple[int, int, int]:
        position = original_index[alias]
        if alias in depth_by_alias:
            return (0, depth_by_alias[alias], position)
        return (1, 0, position)

    return sorted(aliases, key=_sort_key)
