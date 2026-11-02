#!/usr/bin/env python3
"""Local task progress ledger and per-issue workspace registry.

The helper records workflow state and evidence, and `workspace` creates one Git
worktree and branch per issue. It does not execute tests, create commits, or
perform remote writes other than fetching the base branch. Stdlib only, Python 3.10+.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


HEAD_RE = re.compile(r"^## (T\d{3}):\s*(.+)$", re.MULTILINE)
DEP_RE = re.compile(r"^- Depends on:\s*(.+?)\s*$", re.MULTILINE)
TOUCHES_RE = re.compile(r"^- Touches:\s*(.*?)\s*$", re.MULTILINE)
APPROVED_RE = re.compile(r"^Plan approval:\s*approved\s*$", re.MULTILINE | re.IGNORECASE)
SOURCE_DIGEST_RE = re.compile(r"^Source digest:\s*(sha256:[0-9a-f]{64})\s*$", re.MULTILINE)
SOURCE_RE = re.compile(r"^Source:\s*(.+?)\s*$", re.MULTILINE)


class WorkflowError(Exception):
    pass


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git(*args, cwd=None, check=True):
    # Read-only inspection of another session's worktree must not take index.lock and break its commits.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, env=env)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkflowError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def git_context():
    root = Path(git("rev-parse", "--show-toplevel")).resolve()
    location = git("rev-parse", "--git-path", "agent-workflow/progress.json", cwd=root)
    state_path = Path(location)
    if not state_path.is_absolute():
        state_path = root / state_path
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=root, check=False)
    head = git("rev-parse", "--verify", "HEAD", cwd=root, check=False)
    return root, state_path.resolve(), branch, head


def plan_load(path, require_approval=False):
    plan_path = Path(path).expanduser().resolve()
    if not plan_path.is_file():
        raise WorkflowError(f"Plan file not found: {plan_path}")
    content = plan_path.read_text(encoding="utf-8")
    matches = list(HEAD_RE.finditer(content))
    if not matches:
        raise WorkflowError("No tasks. Expected headings `## T001: ...`.")
    tasks = []
    for index, match in enumerate(matches):
        ident, title = match.groups()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        block = content[match.start():end].rstrip()
        dependencies = DEP_RE.findall(block)
        if len(dependencies) != 1:
            raise WorkflowError(f"{ident}: exactly one `- Depends on:` line is required")
        raw = dependencies[0].strip()
        deps = [] if raw.lower() in ("none", "[]") else [item.strip() for item in raw.split(",")]
        if any(not re.fullmatch(r"T\d{3}", dep) for dep in deps) or len(deps) != len(set(deps)):
            raise WorkflowError(f"{ident}: invalid/duplicate dependencies: {raw}")
        touches = TOUCHES_RE.findall(block)
        if len(touches) > 1:
            raise WorkflowError(f"{ident}: at most one `- Touches:` line is allowed")
        tasks.append({"id": ident, "title": title.strip(), "depends_on": deps,
                      "touches": [item.strip() for item in touches[0].split(",") if item.strip()]
                      if touches else None,
                      "fingerprint": digest(block)})
    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise WorkflowError("Duplicate task IDs")
    if ids != [f"T{index:03d}" for index in range(1, len(ids) + 1)]:
        raise WorkflowError("Task IDs must be sequential T001, T002, ... in document order")
    seen = set()
    for task in tasks:
        for dependency in task["depends_on"]:
            if dependency not in seen:
                raise WorkflowError(
                    f"{task['id']}: dependency {dependency} must exist earlier in the ordered plan"
                )
        seen.add(task["id"])
    approved = bool(APPROVED_RE.search(content))
    if require_approval and not approved:
        raise WorkflowError("Plan not approved. Need exact `Plan approval: approved` following user sign-off")
    source_digest_lines = re.findall(r"^Source digest:.*$", content, re.MULTILINE)
    source_digest = SOURCE_DIGEST_RE.search(content)
    if len(source_digest_lines) > 1 or (source_digest_lines and source_digest is None):
        raise WorkflowError("Source digest must be one exact `Source digest: sha256:<64 lowercase hex>` line")
    source = SOURCE_RE.search(content)
    issue_source = bool(source and "github.com/" in source.group(1) and "/issues/" in source.group(1))
    if issue_source and not source_digest:
        raise WorkflowError("GitHub issue plans require a canonical `Source digest` line")
    return {
        "path": str(plan_path),
        "sha256": digest(content),
        "approved": approved,
        "source_digest": source_digest.group(1) if source_digest else None,
        "issue_source": issue_source,
        "tasks": tasks,
    }


def canonical_issue_digest(path):
    try:
        if path == "-":
            source = json.load(sys.stdin)
        else:
            source = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"Invalid issue JSON: {exc}")
    if not isinstance(source, dict):
        raise WorkflowError("Issue JSON must be an object")
    comments = source.get("comments", [])
    labels = source.get("labels", [])
    if not isinstance(comments, list) or not isinstance(labels, list):
        raise WorkflowError("Issue comments and labels must be lists")
    try:
        canonical = {
            "body": source.get("body") or "",
            "comments": [
                {"body": comment.get("body") or "", "id": str(comment["id"])}
                for comment in comments
            ],
            "labels": sorted({str(label["name"]) for label in labels}),
            "state": str(source["state"]),
            "title": str(source["title"]),
        }
    except (KeyError, TypeError) as exc:
        raise WorkflowError(f"Issue JSON is missing a canonical content field: {exc}")
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "source_digest": "sha256:" + digest(encoded),
        "canonical_fields": ["title", "body", "state", "labels", "comments"],
    }


def read_state(path):
    if not path.exists():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"Unreadable progress state: {path}: {exc}")
    if result.get("version") == 1:
        raise WorkflowError(
            "Legacy progress state lacks feature/base branch evidence; manual reconciliation required"
        )
    if result.get("version") != 2 or "tasks" not in result:
        raise WorkflowError("Unsupported/corrupt progress state; manual reconciliation required")
    return result


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".progress-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.chmod(name, 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def assert_clean(root):
    status = git("status", "--porcelain", "--untracked-files=normal", cwd=root)
    if status:
        raise WorkflowError(
            "Working tree is not clean. Inspect and preserve changes before proceeding:\n" + status[:2500]
        )


def plan_storage_mode(plan_path, root, workflow_dir):
    path = Path(plan_path).resolve()
    try:
        path.relative_to(workflow_dir.resolve())
        return "git-metadata"
    except ValueError:
        pass
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = None
    if relative is not None:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(relative)],
            cwd=root, text=True, capture_output=True,
        )
        if tracked.returncode:
            raise WorkflowError(
                "A repository-local approved plan must be tracked and committed on the feature branch"
            )
        return "tracked"
    raise WorkflowError(
        "An external plan must be preserved under the worktree's git agent-workflow directory"
    )


def create_state(plan, root, branch, base_branch, base_sha, baseline_sha, storage):
    return {
        "version": 2,
        "plan_path": plan["path"],
        "plan_sha256": plan["sha256"],
        "repo_root": str(root),
        "branch": branch,
        "base_branch": base_branch,
        "base_sha": base_sha,
        "baseline_sha": baseline_sha,
        "plan_storage": storage,
        "created_at": now(),
        "whole_plan_verification": None,
        "tasks": {
            task["id"]: {"status": "pending", "fingerprint": task["fingerprint"]}
            for task in plan["tasks"]
        },
    }


def assert_current(plan, state, root, branch, require_branch=False):
    if state["repo_root"] != str(root):
        raise WorkflowError("Progress ledger belongs to a different checkout")
    if state["plan_path"] != plan["path"]:
        raise WorkflowError("This worktree ledger belongs to another task plan")
    if state["plan_sha256"] != plan["sha256"]:
        raise WorkflowError("Plan changed. Review approved diff and run `sync-plan --approved` before continuing")
    if require_branch and (not branch or state["branch"] != branch):
        raise WorkflowError(f"Branch mismatch: ledger={state['branch']}, checkout={branch or 'detached'}")


def next_task(plan, state):
    states = state["tasks"]
    for task in plan["tasks"]:
        if states[task["id"]]["status"] == "blocked":
            raise WorkflowError(f"Blocked task {task['id']}; resolve and resume it before advancing")
    active = [task for task in plan["tasks"] if states[task["id"]]["status"] == "in_progress"]
    if active:
        if len(active) > 1:
            raise WorkflowError("More than one in-progress task; manual correction required")
        return active[0]
    for task in plan["tasks"]:
        entry = states[task["id"]]
        if entry["status"] == "pending" and all(
            states[dependency]["status"] == "completed" for dependency in task["depends_on"]
        ):
            return task
    if all(entry["status"] == "completed" for entry in states.values()):
        return None
    raise WorkflowError("No executable task; inspect dependency/status state")


def validate_receipt(path, head, task_id=None, require_diff_review=False):
    evidence_path = Path(path).expanduser().resolve()
    try:
        receipt = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError("Invalid evidence file: " + str(exc))
    if not isinstance(receipt, dict) or receipt.get("commit_sha") != head:
        raise WorkflowError("Evidence commit SHA does not match HEAD")
    if task_id is not None and receipt.get("task_id") != task_id:
        raise WorkflowError("Evidence task ID does not match requested task")
    if receipt.get("acceptance") != "passed":
        raise WorkflowError("Evidence acceptance must be passed")
    if require_diff_review and receipt.get("diff_review") != "passed":
        raise WorkflowError("Evidence diff_review must be passed")
    checks = receipt.get("checks")
    if not isinstance(checks, list) or not checks or any(
        not isinstance(check, dict)
        or check.get("status") != "passed"
        or not isinstance(check.get("command"), str)
        or not check["command"].strip()
        for check in checks
    ):
        raise WorkflowError("At least one actually performed passing check is required")
    if not isinstance(receipt.get("limitations", []), list):
        raise WorkflowError("limitations must be a list")
    return receipt


def verification_status(state, head):
    receipt = state.get("whole_plan_verification")
    if not receipt:
        return "missing"
    return "current" if receipt.get("commit_sha") == head else "stale"


def initialize(args, plan, root, state_path, branch, head, state):
    if not branch:
        raise WorkflowError("Detached HEAD not supported; select an execution branch first")
    if plan["issue_source"] and not args.base_branch:
        raise WorkflowError("GitHub issue execution requires `--base-branch` and a feature branch")
    if not head:
        raise WorkflowError("Repository has no commits. Create the reviewed planning baseline commit first")
    base_sha = None
    if args.base_branch:
        if branch == args.base_branch:
            raise WorkflowError("Issue execution must be initialized on a feature branch, not the base branch")
        base_sha = git("show-ref", "--hash", "--verify", f"refs/heads/{args.base_branch}",
                       cwd=root, check=False)
        if not base_sha:
            raise WorkflowError(f"Base branch does not resolve locally: {args.base_branch}")
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_sha, head], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode:
            raise WorkflowError("Feature branch HEAD must descend from the recorded base branch")
    assert_clean(root)
    storage = plan_storage_mode(plan["path"], root, state_path.parent)
    if state is not None:
        assert_current(plan, state, root, branch, require_branch=True)
        if state.get("base_branch") != args.base_branch:
            raise WorkflowError("Existing ledger records a different base branch")
        return {"initialized": False, "branch": branch, "base_branch": args.base_branch,
                "baseline_sha": state.get("baseline_sha"), "state_path": str(state_path)}
    state = create_state(plan, root, branch, args.base_branch, base_sha, head, storage)
    atomic_json(state_path, state)
    return {"initialized": True, "branch": branch, "base_branch": args.base_branch,
            "baseline_sha": head, "plan_storage": storage, "state_path": str(state_path)}


@contextmanager
def registry_lock(registry, timeout=30.0):
    registry.mkdir(parents=True, exist_ok=True)
    with open(registry / ".lock", "a", encoding="utf-8") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise WorkflowError(
                        f"Workspace registry is locked by another process after {timeout:g}s; retry later"
                    )
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def workspace_context():
    cwd = Path.cwd()
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)).resolve()
    listing = git("worktree", "list", "--porcelain", cwd=cwd)
    main_root = Path(listing.splitlines()[0].split(" ", 1)[1]).resolve()
    current = Path(git("rev-parse", "--show-toplevel", cwd=cwd)).resolve()
    return main_root, common, common / "agent-workflow" / "issues", current


def registry_entries(registry):
    if not registry.is_dir():
        return []
    entries = []
    for path in sorted(registry.glob("*.json"), key=lambda item: int(item.stem)):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise WorkflowError(f"Unreadable workspace registry entry: {path}: {exc}")
    return entries


def registry_read(registry, issue):
    path = registry / f"{issue}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"Unreadable workspace registry entry: {path}: {exc}")


def worktree_branches(main_root):
    branches, path = {}, None
    for line in git("worktree", "list", "--porcelain", cwd=main_root).splitlines():
        if line.startswith("worktree "):
            path = str(Path(line.split(" ", 1)[1]).resolve())
            branches[path] = None
        elif line.startswith("branch ") and path:
            branches[path] = line.split(" ", 1)[1].removeprefix("refs/heads/")
    return branches


def branch_exists(root, branch):
    return subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                          cwd=root).returncode == 0


def default_base(main_root):
    remote_head = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD",
                      cwd=main_root, check=False)
    if remote_head:
        return remote_head.split("/", 1)[1]
    if branch_exists(main_root, "main"):
        return "main"
    raise WorkflowError("Cannot determine the base branch; pass --base")


def ensure_excluded(common):
    exclude = common / "info" / "exclude"
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    if ".worktrees/" not in lines:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as stream:
            if lines and lines[-1] != "":
                stream.write("\n")
            stream.write(".worktrees/\n")


def infer_issue(registry, current):
    entries = registry_entries(registry)
    for entry in entries:
        if Path(entry["worktree"]).resolve() == current:
            return entry["issue"]
    active = ", ".join(f"#{entry['issue']} ({entry['worktree']})" for entry in entries) or "none"
    raise WorkflowError(f"Current checkout is not a registered issue workspace; pass --issue. Active: {active}")


def workspace_get(args, main_root, common, registry, current):
    issue = args.issue if args.issue is not None else infer_issue(registry, current)
    with registry_lock(registry, args.lock_timeout):
        entry = registry_read(registry, issue)
        if entry is not None:
            path = str(Path(entry["worktree"]).resolve())
            if worktree_branches(main_root).get(path) != entry["branch"]:
                raise WorkflowError(
                    f"Registered worktree for #{issue} is missing or not on {entry['branch']}; reconcile manually"
                )
            return entry
        base = args.base or default_base(main_root)
        branch = args.branch or f"fix/issue-{issue}"
        path = main_root / ".worktrees" / f"issue-{issue}"
        if path.exists():
            raise WorkflowError(f"Unregistered path already exists: {path}")
        if branch_exists(main_root, branch):
            raise WorkflowError(f"Unregistered branch already exists: {branch}; verify ownership manually")
        start = base
        if git("remote", cwd=main_root).split().count("origin"):
            git("fetch", "origin", base, cwd=main_root)
            start = f"origin/{base}"
        ensure_excluded(common)
        git("worktree", "add", "--no-track", "-b", branch, str(path), start, cwd=main_root)
        entry = {
            "issue": issue,
            "worktree": str(path.resolve()),
            "branch": branch,
            "base": base,
            "plan": str(path.resolve() / "docs" / "tasks" / f"issue-{issue}.md"),
            "stages": [],
            "created_at": now(),
        }
        atomic_json(registry / f"{issue}.json", entry)
        return entry


def workspace_list(registry):
    result = []
    for entry in registry_entries(registry):
        path = Path(entry["worktree"])
        exists = path.is_dir()
        dirty = None
        if exists:
            dirty = bool(git("status", "--porcelain", "--untracked-files=normal", cwd=path))
        result.append({**entry, "state": entry.get("state") or {"value": "pending"},
                       "exists": exists, "dirty": dirty})
    return {"workspaces": result}


def workspace_remove(args, main_root, registry):
    with registry_lock(registry, args.lock_timeout):
        entry = registry_read(registry, args.issue)
        if entry is None:
            raise WorkflowError(f"Issue #{args.issue} has no registered workspace; nothing removed")
        if entry.get("lease"):
            raise WorkflowError(f"Issue #{args.issue} is claimed by {entry['lease']['owner']}; release it first")
        path = Path(entry["worktree"])
        archived = None
        if path.is_dir():
            if git("status", "--porcelain", "--untracked-files=normal", cwd=path):
                raise WorkflowError(f"Workspace {path} has uncommitted changes; preserve them before removal")
            ledger = Path(git("rev-parse", "--path-format=absolute", "--git-path",
                              "agent-workflow/progress.json", cwd=path))
            if ledger.exists():
                archived = registry.parent / "history" / f"issue-{args.issue}" / "progress.json"
                atomic_json(archived, json.loads(ledger.read_text(encoding="utf-8")))
            git("worktree", "remove", str(path), cwd=main_root)
        else:
            git("worktree", "prune", cwd=main_root)
        (registry / f"{args.issue}.json").unlink()
        return {"removed": True, "issue": args.issue, "worktree": str(path), "branch": entry["branch"],
                "archived_ledger": str(archived) if archived else None}


def workspace_lease(args, registry):
    with registry_lock(registry, args.lock_timeout):
        entry = registry_read(registry, args.issue)
        if entry is None:
            raise WorkflowError(f"Issue #{args.issue} has no registered workspace; run `workspace get` first")
        lease = entry.get("lease")
        if args.workspace_command == "claim":
            if lease and lease["owner"] != args.owner:
                raise WorkflowError(
                    f"Issue #{args.issue} is claimed by {lease['owner']} since {lease['claimed_at']}; "
                    "inspect its worktree and release it explicitly if that session has stopped"
                )
            entry["lease"] = {"owner": args.owner, "claimed_at": lease["claimed_at"] if lease else now()}
        else:
            if lease and lease["owner"] != args.owner and not args.force:
                raise WorkflowError(f"Issue #{args.issue} is claimed by {lease['owner']}; use --force only after "
                                    "confirming that session has stopped")
            entry["lease"] = None
        atomic_json(registry / f"{args.issue}.json", entry)
        return entry


def workspace_act(args):
    main_root, common, registry, current = workspace_context()
    if args.workspace_command == "get":
        return workspace_get(args, main_root, common, registry, current)
    if args.workspace_command == "list":
        return workspace_list(registry)
    if args.workspace_command in ("claim", "release"):
        return workspace_lease(args, registry)
    if args.workspace_command == "stage":
        return workspace_stage(args, registry)
    if args.workspace_command == "state":
        return workspace_state(args, registry)
    return workspace_remove(args, main_root, registry)


def touch_overlaps(left, right):
    """Approximate glob intersection; reports a false overlap rather than miss a real one."""
    def normalize(pattern):
        pattern = pattern.removeprefix("shared:").strip()
        return pattern + "**" if pattern.endswith("/") else pattern

    def static(pattern):
        match = re.search(r"[*?\[]", pattern)
        return pattern[:match.start()] if match else pattern

    left, right = normalize(left), normalize(right)
    left_wild, right_wild = static(left) != left, static(right) != right
    if not left_wild and not right_wild:
        return left == right
    if left_wild and not right_wild:
        return fnmatch.fnmatchcase(right, left) or right.startswith(static(left))
    if right_wild and not left_wild:
        return fnmatch.fnmatchcase(left, right) or left.startswith(static(right))
    return static(left).startswith(static(right)) or static(right).startswith(static(left))


def overlap(paths):
    plans, unknown = [], []
    for path in paths:
        plan = plan_load(path)
        missing = [task["id"] for task in plan["tasks"] if task["touches"] is None]
        if missing:
            unknown.append({"plan": plan["path"], "tasks": missing})
        plans.append((plan["path"], sorted({item for task in plan["tasks"] for item in task["touches"] or []})))
    conflicts = []
    for index, (left_path, left_touches) in enumerate(plans):
        for right_path, right_touches in plans[index + 1:]:
            pairs = [
                [left, right] for left in left_touches for right in right_touches
                if left.startswith("shared:") or right.startswith("shared:") or touch_overlaps(left, right)
            ]
            if pairs:
                conflicts.append({"plans": [left_path, right_path], "paths": pairs})
    return {
        "verdict": "sequential" if conflicts or unknown else "parallel",
        "conflicts": conflicts,
        "unknown": unknown,
    }


SKILLS_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_STAGES = {"builtin:precheck"}
STAGE_ACCESS = {"read", "local-write", "remote"}
STAGE_GATES = {"none", "approval"}
STAGE_FLAGS = ("modifies-code", "verifies", "optional")
DEFAULT_PIPELINE = {
    "stages": [
        {"id": "precheck", "skill": "builtin:precheck", "access": "read"},
        {"id": "plan", "skill": "plan-tasks", "gate": "approval", "access": "local-write"},
        {"id": "execute", "skill": "execute-tasks", "access": "local-write",
         "modifies-code": True, "verifies": True},
        {"id": "explain", "skill": "explain-diff", "gate": "approval", "access": "remote", "optional": True},
        {"id": "pr", "skill": "create-pr", "gate": "approval", "access": "remote"},
    ],
}


def normalize_stage(stage):
    if not isinstance(stage, dict):
        raise WorkflowError(f"Stage must be an object: {stage!r}")
    result = {"mode": "per-issue", "gate": "none", **stage}
    for flag in STAGE_FLAGS:
        result[flag] = bool(result.get(flag, False))
    return result


def validate_stages(stages):
    if not isinstance(stages, list) or not stages:
        raise WorkflowError("Pipeline needs a non-empty `stages` list")
    stages = [normalize_stage(stage) for stage in stages]
    seen, unverified = set(), None
    for stage in stages:
        ident = stage.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", ident):
            raise WorkflowError(f"Invalid stage id: {ident!r}")
        if ident in seen:
            raise WorkflowError(f"Duplicate stage id: {ident}")
        seen.add(ident)
        skill = stage.get("skill")
        if skill not in BUILTIN_STAGES and not (
            isinstance(skill, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", skill)
            and (SKILLS_ROOT / skill / "SKILL.md").is_file()
        ):
            raise WorkflowError(f"Stage {ident}: skill not found: {skill!r}")
        if stage["mode"] != "per-issue":
            raise WorkflowError(f"Stage {ident}: unsupported mode {stage['mode']!r}")
        if stage.get("access") not in STAGE_ACCESS:
            raise WorkflowError(f"Stage {ident}: access must be one of {sorted(STAGE_ACCESS)}")
        if stage["gate"] not in STAGE_GATES:
            raise WorkflowError(f"Stage {ident}: gate must be one of {sorted(STAGE_GATES)}")
        if stage["access"] == "remote" and stage["gate"] != "approval":
            raise WorkflowError(f"Stage {ident}: remote stages require gate `approval`")
        if stage["modifies-code"] and not stage["verifies"]:
            unverified = ident
        elif stage["verifies"]:
            unverified = None
        if stage["access"] == "remote" and unverified:
            raise WorkflowError(f"Stage {unverified} modifies code but is not verified before remote stage {ident}")
    return stages


def load_pipeline(path=None):
    if path is None:
        main_root = workspace_context()[0]
        path = main_root / ".agent-workflow" / "pipeline.json"
        if not path.exists():
            return DEFAULT_PIPELINE, "default"
    path = Path(path).expanduser().resolve()
    try:
        pipeline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowError(f"Invalid pipeline file {path}: {exc}")
    if not isinstance(pipeline, dict):
        raise WorkflowError(f"Invalid pipeline file {path}: expected an object")
    return pipeline, str(path)


RUN_STATES = {"pending", "running", "blocked", "interrupted", "done"}


def issue_stages(stages, entry):
    stages = [dict(stage) for stage in stages]
    for extra in entry.get("extra_stages", []):
        position = next((index for index, stage in enumerate(stages) if stage["id"] == extra["after"]), None)
        if position is None:
            raise WorkflowError(f"One-off stage {extra['stage']['id']} follows missing stage {extra['after']}")
        stages.insert(position + 1, {**extra["stage"], "one_off": True})
    return validate_stages(stages)


def issue_progress(stages, entry):
    completed = entry.get("stages", [])
    ids = [stage["id"] for stage in stages]
    last_done = max((ids.index(stage) for stage in completed if stage in ids), default=-1)
    passed = [stage for stage in stages[:last_done + 1] if stage["id"] not in completed]
    next_stage = next((ident for ident in ids[last_done + 1:] if ident not in completed), None)
    return {
        "completed": completed,
        "skipped_new": [stage["id"] for stage in passed if not stage["optional"]],
        "skipped_optional": [stage["id"] for stage in passed if stage["optional"]],
        "next_stage": next_stage,
        "state": entry.get("state") or {"value": "pending"},
    }


def workspace_stage(args, registry):
    with registry_lock(registry, args.lock_timeout):
        entry = registry_read(registry, args.issue)
        if entry is None:
            raise WorkflowError(f"Issue #{args.issue} has no registered workspace; run `workspace get` first")
        pipeline, _ = load_pipeline()
        stages = issue_stages(validate_stages(pipeline.get("stages")), entry)
        ids = [stage["id"] for stage in stages]
        if args.complete:
            if args.complete not in ids:
                raise WorkflowError(f"Unknown stage for issue #{args.issue}: {args.complete}")
            if args.complete in entry.get("stages", []):
                return entry
            skipped = issue_progress(stages, entry)["skipped_new"]
            blocking = [
                stage["id"] for stage in stages[:ids.index(args.complete)]
                if stage["id"] not in entry.get("stages", []) and not stage["optional"]
                and stage["id"] not in skipped
            ]
            if blocking:
                raise WorkflowError(f"Stage {args.complete} cannot complete before {blocking[0]}")
            entry["stages"] = [ident for ident in ids if ident in {*entry.get("stages", []), args.complete}]
        else:
            if args.after not in ids:
                raise WorkflowError(f"Unknown stage to insert after: {args.after}")
            stage = {"id": args.id or args.insert, "skill": args.insert, "access": args.access,
                     "gate": args.gate, "modifies-code": args.modifies_code, "verifies": args.verifies}
            extras = entry.get("extra_stages", []) + [{"after": args.after, "stage": stage}]
            issue_stages(validate_stages(pipeline.get("stages")), {**entry, "extra_stages": extras})
            entry["extra_stages"] = extras
        atomic_json(registry / f"{args.issue}.json", entry)
        return entry


def workspace_state(args, registry):
    with registry_lock(registry, args.lock_timeout):
        entry = registry_read(registry, args.issue)
        if entry is None:
            raise WorkflowError(f"Issue #{args.issue} has no registered workspace; run `workspace get` first")
        entry["state"] = {"value": args.set, "reason": args.reason, "updated_at": now()}
        atomic_json(registry / f"{args.issue}.json", entry)
        return entry


def pipeline_act(args):
    pipeline, source = load_pipeline(args.file)
    stages = validate_stages(pipeline.get("stages"))
    if args.pipeline_command == "validate":
        return {"valid": True, "source": source, "stage_count": len(stages)}
    if args.issue is None:
        return {"source": source, "stages": stages}
    entry = registry_read(workspace_context()[2], args.issue)
    if entry is None:
        raise WorkflowError(f"Issue #{args.issue} has no registered workspace; run `workspace get` first")
    stages = issue_stages(stages, entry)
    return {"source": source, "issue": args.issue, "stages": stages,
            **issue_progress(stages, entry)}


def act(args):
    if args.command == "source-digest":
        return canonical_issue_digest(args.input)
    if args.command == "pipeline":
        return pipeline_act(args)
    if args.command == "workspace":
        return workspace_act(args)
    if args.command == "overlap":
        return overlap(args.plans)

    plan = plan_load(args.plan, require_approval=args.command != "validate")
    if args.command == "validate":
        return {
            "valid": True,
            "approved": plan["approved"],
            "source_digest": plan["source_digest"],
            "task_count": len(plan["tasks"]),
            "tasks": [
                {"id": task["id"], "depends_on": task["depends_on"]} for task in plan["tasks"]
            ],
        }

    root, state_path, branch, head = git_context()
    state = read_state(state_path)
    if args.command == "init":
        return initialize(args, plan, root, state_path, branch, head, state)
    if state is None:
        raise WorkflowError(
            "No progress ledger. Commit/preserve the approved plan on a feature branch, then run `init`"
        )

    if args.command == "sync-plan":
        if not args.approved:
            raise WorkflowError("Explicit --approved flag required after user-approved plan revision")
        if (state["repo_root"] != str(root) or state["plan_path"] != plan["path"]
                or state["branch"] != branch):
            raise WorkflowError("Plan/repository/branch mismatch; cannot synchronize")
        assert_clean(root)
        plan_storage_mode(plan["path"], root, state_path.parent)
        current_tasks = {task["id"]: task for task in plan["tasks"]}
        for old_id, old in state["tasks"].items():
            if old["status"] == "completed":
                if old_id not in current_tasks or current_tasks[old_id]["fingerprint"] != old["fingerprint"]:
                    raise WorkflowError(f"Cannot modify/remove completed task {old_id}")
            elif old["status"] in ("in_progress", "blocked") and old_id not in current_tasks:
                raise WorkflowError(f"Cannot remove an active/blocked task {old_id}")
        for task in plan["tasks"]:
            if task["id"] not in state["tasks"]:
                state["tasks"][task["id"]] = {"status": "pending", "fingerprint": task["fingerprint"]}
            elif state["tasks"][task["id"]]["status"] != "completed":
                state["tasks"][task["id"]]["fingerprint"] = task["fingerprint"]
        for old_id in list(state["tasks"]):
            if old_id not in current_tasks:
                del state["tasks"][old_id]
        for task in plan["tasks"]:
            if state["tasks"][task["id"]]["status"] in ("completed", "in_progress", "blocked"):
                if any(state["tasks"][dependency]["status"] != "completed"
                       for dependency in task["depends_on"]):
                    raise WorkflowError(f"Started task {task['id']} now depends on incomplete work")
        state["plan_sha256"] = plan["sha256"]
        state["plan_revision_sha"] = head
        state["whole_plan_verification"] = None
        state["synced_at"] = now()
        atomic_json(state_path, state)
        return {"synced": True, "plan_revision_sha": head, "state_path": str(state_path)}

    assert_current(plan, state, root, branch, require_branch=args.command != "status")
    if args.command == "status":
        return {
            "plan": plan["path"],
            "branch": state["branch"],
            "checkout_branch": branch,
            "base_branch": state.get("base_branch"),
            "baseline_sha": state.get("baseline_sha"),
            "state_path": str(state_path),
            "whole_plan_verification": verification_status(state, head),
            "tasks": [
                {"id": task["id"], "title": task["title"], **state["tasks"][task["id"]]}
                for task in plan["tasks"]
            ],
        }
    if args.command == "next":
        task = next_task(plan, state)
        return {
            "next": task,
            "all_task_commits_recorded": task is None,
            "whole_plan_verification": verification_status(state, head),
        }
    if args.command == "verify-plan":
        if next_task(plan, state) is not None:
            raise WorkflowError("Whole-plan verification requires every task to be completed")
        assert_clean(root)
        receipt = validate_receipt(args.evidence, head)
        receipt["verified_at"] = now()
        state["whole_plan_verification"] = receipt
        atomic_json(state_path, state)
        return {"verified": True, "branch": branch, "head": head, "state_path": str(state_path)}
    if args.command == "pr-evidence":
        if next_task(plan, state) is not None:
            raise WorkflowError("PR evidence is unavailable until every task is completed")
        if verification_status(state, head) != "current":
            raise WorkflowError("PR evidence requires current whole-plan verification at HEAD")
        if not state.get("base_branch") or not state.get("base_sha"):
            raise WorkflowError("Legacy ledger lacks base-branch evidence; reconcile and reinitialize manually")
        assert_clean(root)
        return {
            "ready_for_pr": True,
            "plan": plan["path"],
            "plan_sha256": plan["sha256"],
            "source_digest": plan["source_digest"],
            "base_branch": state["base_branch"],
            "base_sha": state["base_sha"],
            "feature_branch": state["branch"],
            "baseline_sha": state["baseline_sha"],
            "head_sha": head,
            "tasks": [
                {"id": task["id"], "commit_sha": state["tasks"][task["id"]].get("commit_sha"),
                 "evidence": state["tasks"][task["id"]].get("evidence")}
                for task in plan["tasks"]
            ],
            "whole_plan_verification": state["whole_plan_verification"],
        }

    task_id = args.task
    if task_id not in state["tasks"]:
        raise WorkflowError("Unknown task: " + str(task_id))
    entry = state["tasks"][task_id]
    if args.command == "start":
        task = next_task(plan, state)
        if not task or task["id"] != task_id or entry["status"] != "pending":
            raise WorkflowError("Task is not the next ready pending task")
        assert_clean(root)
        entry.update({"status": "in_progress", "started_at": now(), "start_sha": head})
    elif args.command == "block":
        if entry["status"] != "in_progress":
            raise WorkflowError("Can block only an in-progress task")
        entry.update({"status": "blocked", "reason": args.reason, "blocked_at": now()})
    elif args.command == "resume":
        if entry["status"] != "blocked":
            raise WorkflowError("Can resume only a blocked task")
        entry.update({"status": "in_progress", "resumed_at": now()})
        entry.pop("reason", None)
    elif args.command == "complete":
        if entry["status"] != "in_progress":
            raise WorkflowError("Complete requires an in-progress task")
        if not head or head == entry.get("start_sha"):
            raise WorkflowError("Expected a new verified commit for this task")
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", entry["start_sha"], head], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode:
            raise WorkflowError("Current HEAD does not descend from task start commit")
        assert_clean(root)
        receipt = validate_receipt(args.evidence, head, task_id=task_id, require_diff_review=True)
        entry.update({"status": "completed", "completed_at": now(), "commit_sha": head,
                      "evidence": receipt})
        state["whole_plan_verification"] = None
    else:
        raise WorkflowError("Unsupported command")
    atomic_json(state_path, state)
    return {"task": task_id, "status": entry["status"], "branch": branch, "head": head,
            "state_path": str(state_path)}


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    digest_parser = subparsers.add_parser("source-digest")
    digest_parser.add_argument("--input", required=True, help="gh issue view JSON path, or - for stdin")
    pipeline_parser = subparsers.add_parser("pipeline")
    pipeline_commands = pipeline_parser.add_subparsers(dest="pipeline_command", required=True)
    for name in ("show", "validate"):
        command_parser = pipeline_commands.add_parser(name)
        command_parser.add_argument("--file")
        if name == "show":
            command_parser.add_argument("--issue", type=int)
    overlap_parser = subparsers.add_parser("overlap")
    overlap_parser.add_argument("--plans", nargs="+", required=True)
    workspace_parser = subparsers.add_parser("workspace")
    workspace_commands = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    get_parser = workspace_commands.add_parser("get")
    get_parser.add_argument("--issue", type=int)
    get_parser.add_argument("--base")
    get_parser.add_argument("--branch")
    workspace_commands.add_parser("list")
    remove_parser = workspace_commands.add_parser("remove")
    remove_parser.add_argument("--issue", type=int, required=True)
    for name in ("claim", "release"):
        lease_parser = workspace_commands.add_parser(name)
        lease_parser.add_argument("--issue", type=int, required=True)
        lease_parser.add_argument("--owner", required=True)
        if name == "release":
            lease_parser.add_argument("--force", action="store_true")
    stage_parser = workspace_commands.add_parser("stage")
    stage_parser.add_argument("--issue", type=int, required=True)
    stage_action = stage_parser.add_mutually_exclusive_group(required=True)
    stage_action.add_argument("--complete")
    stage_action.add_argument("--insert", metavar="SKILL")
    stage_parser.add_argument("--after")
    stage_parser.add_argument("--id")
    stage_parser.add_argument("--access", default="local-write")
    stage_parser.add_argument("--gate", default="none")
    stage_parser.add_argument("--modifies-code", action="store_true")
    stage_parser.add_argument("--verifies", action="store_true")
    state_parser = workspace_commands.add_parser("state")
    state_parser.add_argument("--issue", type=int, required=True)
    state_parser.add_argument("--set", required=True, choices=sorted(RUN_STATES))
    state_parser.add_argument("--reason")
    for command_parser in workspace_commands.choices.values():
        command_parser.add_argument("--lock-timeout", type=float, default=30.0)
    for name in (
        "validate", "init", "status", "next", "start", "complete", "block", "resume",
        "sync-plan", "verify-plan", "pr-evidence",
    ):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("--plan", required=True)
        if name == "init":
            command_parser.add_argument("--base-branch")
        if name in ("start", "complete", "block", "resume"):
            command_parser.add_argument("--task", required=True)
        if name in ("complete", "verify-plan"):
            command_parser.add_argument("--evidence", required=True)
        if name == "block":
            command_parser.add_argument("--reason", required=True)
        if name == "sync-plan":
            command_parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    try:
        result = act(args)
    except WorkflowError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(2)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
