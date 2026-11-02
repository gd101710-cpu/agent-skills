#!/usr/bin/env python3
"""Dependency order for open GitHub issues. Read-only; stdlib only, Python 3.10+.

Input is `gh issue list --state open --json number,title,body` output. Declared
dependencies are read from `Depends on: #N` and `Blocked by #N` lines in issue
bodies; `--depends` and `--conflict` add edges the agent inferred. A dependency
on an issue that is not open counts as satisfied and is reported under `external`.
"""
import argparse
import heapq
import json
from pathlib import Path
import re
import sys


DECLARED_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:depends on|blocked by)\b:?(.*)$", re.IGNORECASE | re.MULTILINE)
REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")


class OrderError(Exception):
    pass


def pair(value):
    match = re.fullmatch(r"#?(\d+):#?(\d+)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"expected N:M, got {value!r}")
    left, right = int(match[1]), int(match[2])
    if left == right:
        raise argparse.ArgumentTypeError(f"an issue cannot relate to itself: {value!r}")
    return left, right


def declared(body):
    refs = set()
    for match in DECLARED_RE.finditer(body or ""):
        refs.update(int(ref) for ref in REF_RE.findall(match[1]))
    return refs


def load_issues(path):
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        issues = json.loads(text)
    except (OSError, ValueError) as exc:
        raise OrderError(f"Invalid issue list {path}: {exc}")
    if not isinstance(issues, list) or not all(isinstance(item, dict) and "number" in item for item in issues):
        raise OrderError("Issue list must be a JSON array of objects with `number`")
    return {int(item["number"]): item for item in issues}


def components(nodes, links):
    parent = {node: node for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in links:
        parent[find(left)] = find(right)
    groups = {}
    for node in sorted(nodes):
        groups.setdefault(find(node), []).append(node)
    return sorted(groups.values())


def topo(nodes, deps):
    """Kahn's algorithm with the lowest issue number first; returns (order, cyclic)."""
    nodes = set(nodes)
    pending = {node: {dep for dep in deps[node] if dep in nodes} for node in nodes}
    dependents = {node: [] for node in nodes}
    for node, needs in pending.items():
        for dep in needs:
            dependents[dep].append(node)
    heap = [node for node, needs in pending.items() if not needs]
    heapq.heapify(heap)
    order = []
    while heap:
        node = heapq.heappop(heap)
        order.append(node)
        for child in dependents[node]:
            pending[child].discard(node)
            if not pending[child]:
                heapq.heappush(heap, child)
    return order, sorted(nodes - set(order))


def reaches(start, target, deps):
    seen, stack = set(), list(deps[start])
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(deps[node])
    return False


def analyze(issues, extra_deps=(), conflicts=(), active=()):
    open_issues = set(issues)
    active = set(active) & open_issues
    deps = {number: declared(issue.get("body")) - {number} for number, issue in issues.items()}
    for left, right in extra_deps:
        if left in deps:
            deps[left].add(right)
    external = {number: sorted(refs - open_issues) for number, refs in deps.items() if refs - open_issues}
    deps = {number: refs & open_issues for number, refs in deps.items()}
    conflict_map = {number: set() for number in open_issues}
    for left, right in conflicts:
        if left in open_issues and right in open_issues:
            conflict_map[left].add(right)
            conflict_map[right].add(left)

    _, residual = topo(open_issues, deps)
    cyclic = [number for number in residual if reaches(number, number, deps)]
    stuck = set(residual)

    links = [(number, dep) for number in open_issues for dep in deps[number]]
    links += [(left, right) for left in open_issues for right in conflict_map[left]]
    tracks = []
    for group in components(open_issues, links):
        order, _ = topo(set(group) - stuck, deps)
        if order:
            tracks.append(order)
    tracks.sort()

    ready = sorted(
        number for number in open_issues - active - stuck
        if not deps[number] and not conflict_map[number] & active
    )
    start_now, taken = [], set(active)
    for number in ready:
        if not conflict_map[number] & taken:
            start_now.append(number)
            taken.add(number)

    def status(number):
        if number in active:
            return "active"
        if number in cyclic:
            return "cycle"
        if number in stuck:
            return "blocked-by-cycle"
        return "ready" if number in ready else "waiting"

    return {
        "start_now": start_now,
        "ready": ready,
        "tracks": tracks,
        "order": [number for track in tracks for number in track],
        "cycles": cyclic,
        "external": {str(number): refs for number, refs in sorted(external.items())},
        "issues": {
            str(number): {
                "title": issues[number].get("title", ""),
                "status": status(number),
                "depends_on": sorted(deps[number]),
                "conflicts_with": sorted(conflict_map[number]),
            }
            for number in sorted(open_issues)
        },
    }


def render(result):
    lines = []
    tag = {"active": " (active)", "cycle": " (cycle)", "blocked-by-cycle": " (blocked by cycle)"}
    for index, track in enumerate(result["tracks"], 1):
        chain = " -> ".join(f"#{n}{tag.get(result['issues'][str(n)]['status'], '')}" for n in track)
        lines.append(f"Track {index}: {chain}")
    lines.append("Start now (one terminal each): " + (", ".join(f"#{n}" for n in result["start_now"]) or "none"))
    held = [n for n in result["ready"] if n not in result["start_now"]]
    if held:
        lines.append("Ready but conflicting with a started issue: " + ", ".join(f"#{n}" for n in held))
    lines.append("Single-terminal order: " + (" -> ".join(f"#{n}" for n in result["order"]) or "none"))
    for number, info in result["issues"].items():
        notes = []
        if info["depends_on"]:
            notes.append("waits for " + ", ".join(f"#{n}" for n in info["depends_on"]))
        if info["conflicts_with"]:
            notes.append("conflicts with " + ", ".join(f"#{n}" for n in info["conflicts_with"]))
        lines.append(f"  #{number} [{info['status']}] {info['title']}" + (f" — {'; '.join(notes)}" if notes else ""))
    if result["cycles"]:
        lines.append("Cycles (fix the declarations): " + ", ".join(f"#{n}" for n in result["cycles"]))
    for number, refs in result["external"].items():
        lines.append(f"  #{number} references non-open " + ", ".join(f"#{n}" for n in refs) + " (treated as satisfied)")
    return "\n".join(lines)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issues", required=True, help="gh issue list JSON path, or - for stdin")
    parser.add_argument("--depends", type=pair, action="append", default=[], metavar="N:M",
                        help="issue N depends on issue M (inferred edge)")
    parser.add_argument("--conflict", type=pair, action="append", default=[], metavar="N:M",
                        help="issues N and M must not run at the same time")
    parser.add_argument("--active", type=int, action="append", default=[], metavar="N",
                        help="issue already in progress (claimed workspace or open PR)")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    try:
        result = analyze(load_issues(args.issues), args.depends, args.conflict, args.active)
    except OrderError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(render(result) if args.format == "text" else json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
