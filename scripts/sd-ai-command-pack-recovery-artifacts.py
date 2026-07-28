#!/usr/bin/env python3
"""Track and reconcile pack-created recovery artifacts (stashes and worktrees).

Recovery workflows occasionally create a throwaway ``git stash`` or a detached
linked worktree to protect work while they repair a checkout. Historically those
artifacts were invisible once the workflow finished, so proving one was safe to
drop needed a whole separate session. This module gives every pack-created
recovery artifact a versioned, user-local, private receipt the moment it is
created, so status can classify leftovers read-only and housekeeping can retire
only the artifacts whose exact identity and no-loss predicate are proven.

Two concerns are deliberately split:

* ``register`` and ``classify`` (this file) never delete a Git artifact. Register
  records a receipt atomically; classify reconciles receipts against Git and the
  owner ledger read-only.
* The destructive owner/housekeeping cleanup paths live behind their own proof
  gates and lock (added alongside their destructive-boundary tests).

The receipt never embeds an uncontrolled raw repository path, a remote URL, or a
raw filesystem error; repository identity is a digest and diagnostics are
bounded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence

try:
    from sd_ai_command_pack_lib import CommandError, git_stdout, run_git
except ImportError:  # pragma: no cover - exercised only via broken installs
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sd_ai_command_pack_lib import CommandError, git_stdout, run_git

SCHEMA_VERSION = 1
STATE_HOME_ENV = "SD_AI_COMMAND_PACK_STATE_HOME"
DEFAULT_STALE_LOCK_SECONDS = 15 * 60

MAX_RECEIPT_BYTES = 16 * 1024
MAX_RECEIPTS = 500
MAX_TEXT = 500
MAX_REFERENCE = 200

ARTIFACT_STASH = "stash"
ARTIFACT_WORKTREE = "worktree"
ARTIFACT_TYPES = (ARTIFACT_STASH, ARTIFACT_WORKTREE)

# Classifications are read-only judgements; only cleanup (a separate destructive
# path) acts on them, and only on ``safe-cleanable``.
CLASS_ACTIVE = "active"
CLASS_SAFE_CLEANABLE = "safe-cleanable"
CLASS_NEEDS_REVIEW = "needs-review"
CLASS_MISSING_ARTIFACT = "missing-artifact"
CLASS_UNOWNED_ARTIFACT = "unowned-artifact"
CLASSIFICATIONS = (
    CLASS_ACTIVE,
    CLASS_SAFE_CLEANABLE,
    CLASS_NEEDS_REVIEW,
    CLASS_MISSING_ARTIFACT,
    CLASS_UNOWNED_ARTIFACT,
)

# Pack-created recovery stashes carry this message prefix so a stash whose
# receipt was lost is still recognisable as pack-shaped (reported, never
# adopted) while genuine user stashes stay out of scope entirely.
RECOVERY_STASH_PREFIX = "sd-ai-command-pack recovery:"

ARTIFACT_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")
OID_RE = re.compile(r"^[0-9a-f]{7,64}$")
SECRET_KEY_RE = re.compile(r"secret|token|password|passwd|credential|api[_-]?key", re.IGNORECASE)


class RecoveryError(RuntimeError):
    """Raised when a recovery-artifact operation cannot complete safely."""


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# User-local private state (mirrors the work-loop patterns)
# ---------------------------------------------------------------------------


def resolve_state_root(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    os_name: str | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    override = env.get(STATE_HOME_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise RecoveryError(f"{STATE_HOME_ENV} must be an absolute path")
        return path
    xdg = env.get("XDG_STATE_HOME", "").strip()
    if xdg:
        path = Path(xdg).expanduser()
        if path.is_absolute():
            return path / "sd-ai-command-pack"
    platform_name = os.name if os_name is None else os_name
    if platform_name == "nt":
        local_app_data = env.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            windows_path = PureWindowsPath(local_app_data)
            if windows_path.is_absolute():
                path = Path(str(windows_path).replace("\\", "/"))
                return path / "sd-ai-command-pack" / "state"
    resolved_home = (home or Path.home()).expanduser()
    if not resolved_home.is_absolute():
        raise RecoveryError("home directory must resolve to an absolute path")
    return resolved_home / ".local" / "state" / "sd-ai-command-pack"


def ensure_private_directory(path: Path) -> None:
    if path.is_symlink():
        raise RecoveryError(f"state directory must not be a symlink: {path.name}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise RecoveryError(f"state directory is unusable: {path.name}")
    try:
        path.chmod(0o700)
    except OSError:
        # Permission tightening is best-effort on filesystems without chmod.
        pass


def _reject_secret_keys(value: object, *, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise RecoveryError(f"secret-like key is not allowed in a receipt: {path}.{key}")
            _reject_secret_keys(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_keys(item, path=f"{path}[{index}]")


def _json_payload(value: Mapping[str, Any]) -> str:
    _reject_secret_keys(value)
    try:
        return json.dumps(value, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as error:
        raise RecoveryError(f"receipt is not JSON serialisable: {error}") from error


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    ensure_private_directory(path.parent)
    payload = _json_payload(value)
    if len(payload.encode("utf-8")) > MAX_RECEIPT_BYTES:
        raise RecoveryError(f"refusing to write oversized receipt: {path.name}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", errors="strict") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RecoveryError(f"cannot read receipt {path.name}: {error.strerror or 'unreadable'}") from error
    if len(raw.encode("utf-8")) > MAX_RECEIPT_BYTES:
        raise RecoveryError(f"receipt is implausibly large: {path.name}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RecoveryError(f"receipt is not valid JSON: {path.name} ({error.msg})") from error
    if not isinstance(value, dict):
        raise RecoveryError(f"receipt is not a JSON object: {path.name}")
    return value


# ---------------------------------------------------------------------------
# Repository identity and Git inspection (read-only)
# ---------------------------------------------------------------------------


def canonical_remote(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip()
    if not text:
        return ""
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    return text


def resolve_repository(repo: Path) -> Path:
    toplevel = git_stdout(["rev-parse", "--show-toplevel"], cwd=repo, context="resolve repository root")
    if toplevel is None:
        raise RecoveryError("not inside a Git repository")
    return Path(toplevel).resolve()


def repository_identity(repo: Path) -> dict[str, str]:
    root = resolve_repository(repo)
    remote = git_stdout(["remote", "get-url", "origin"], cwd=root, context="resolve origin url")
    canonical = canonical_remote(remote)
    normalized_root = os.path.normcase(str(root))
    digest = hashlib.sha256(f"{normalized_root}\n{canonical}".encode("utf-8")).hexdigest()
    label = root.name
    if canonical:
        label = canonical.rstrip("/").rsplit("/", 1)[-1] or label
    return {"digest": digest, "label": _bounded(label, MAX_REFERENCE)}


def receipts_dir(digest: str, state_root: Path) -> Path:
    return state_root / "recovery-artifacts" / digest


def worktree_base(digest: str, state_root: Path) -> Path:
    return receipts_dir(digest, state_root) / "worktrees"


def object_exists(repo: Path, oid: str) -> bool:
    # ``cat-file -e`` prints nothing and communicates purely through exit status,
    # so git_stdout (which maps empty stdout to None) cannot be used here.
    if not OID_RE.match(oid):
        return False
    result = run_git(
        ["cat-file", "-e", f"{oid}^{{object}}"],
        cwd=repo,
        allowed_returncodes={0, 1, 128},
        context="probe object",
    )
    return result.returncode == 0


def commit_reachable(repo: Path, oid: str) -> bool:
    """True when ``oid`` is an ancestor of some ref (no unique work would be lost)."""

    if not OID_RE.match(oid):
        return False
    refs = git_stdout(
        ["for-each-ref", "--format=%(objectname)", "refs/heads", "refs/remotes", "refs/tags"],
        cwd=repo,
        context="list refs",
    )
    if not refs:
        return False
    seen: set[str] = set()
    for ref_oid in refs.splitlines():
        ref_oid = ref_oid.strip()
        if not ref_oid or ref_oid in seen:
            continue
        seen.add(ref_oid)
        if _is_ancestor(repo, oid, ref_oid):
            return True
    return False


def _is_ancestor(repo: Path, oid: str, ancestor_of: str) -> bool:
    # ``merge-base --is-ancestor`` signals via exit status (0 ancestor, 1 not).
    result = run_git(
        ["merge-base", "--is-ancestor", oid, ancestor_of],
        cwd=repo,
        allowed_returncodes={0, 1},
        context="reachability check",
    )
    return result.returncode == 0


def stash_entries(repo: Path) -> list[dict[str, str]]:
    """Return current stash entries as ``{ref, oid, subject}`` newest-first."""

    output = git_stdout(
        ["stash", "list", "--format=%gd%x00%H%x00%gs"],
        cwd=repo,
        context="list stashes",
    )
    entries: list[dict[str, str]] = []
    if not output:
        return entries
    for line in output.splitlines():
        parts = line.split("\x00")
        if len(parts) != 3:
            continue
        entries.append({"ref": parts[0], "oid": parts[1], "subject": parts[2]})
    return entries


def worktree_entries(repo: Path) -> list[dict[str, str]]:
    """Return linked worktrees as ``{path, head, bare, detached, locked}``."""

    output = git_stdout(["worktree", "list", "--porcelain"], cwd=repo, context="list worktrees")
    entries: list[dict[str, str]] = []
    if not output:
        return entries
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"path": line[len("worktree ") :]}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :]
        elif line == "detached":
            current["detached"] = "true"
        elif line == "bare":
            current["bare"] = "true"
        elif line.startswith("locked"):
            current["locked"] = "true"
    if current:
        entries.append(current)
    # The first entry is always the main worktree; drop it.
    return entries[1:] if entries else entries


def worktree_is_clean(worktree: Path) -> bool | None:
    # A clean tree yields empty stdout with exit 0, so git_stdout (empty -> None)
    # would be ambiguous; inspect the return code directly. ``None`` means the
    # cleanliness could not be verified (missing/broken worktree) -> not safe.
    result = run_git(["status", "--porcelain"], cwd=worktree, allowed_returncodes={0}, context="worktree status")
    if result.returncode != 0:
        return None
    return result.stdout.strip() == ""


def worktree_common_dir(worktree: Path) -> Path | None:
    common = git_stdout(["rev-parse", "--git-common-dir"], cwd=worktree, context="worktree common dir")
    if not common:
        return None
    path = Path(common)
    if not path.is_absolute():
        path = (worktree / path).resolve()
    return path.resolve()


# ---------------------------------------------------------------------------
# Bounded text
# ---------------------------------------------------------------------------


def _bounded(value: object, limit: int = MAX_TEXT) -> str:
    text = "" if value is None else str(value)
    text = "".join(character for character in text if ord(character) >= 32 or character in "\t")
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Receipt construction and validation
# ---------------------------------------------------------------------------


def new_artifact_id() -> str:
    return uuid.uuid4().hex


def build_receipt(
    *,
    artifact_id: str,
    artifact_type: str,
    repository: Mapping[str, str],
    git_identity: Mapping[str, str],
    created_by: str,
    run: Mapping[str, Any],
    purpose: str,
    original_head: str,
    expected_outcome: str,
    cleanup_predicate: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    if artifact_type not in ARTIFACT_TYPES:
        raise RecoveryError(f"unsupported artifact type: {_bounded(artifact_type, 40)}")
    if not ARTIFACT_ID_RE.match(artifact_id):
        raise RecoveryError("artifact id must be a hex token")
    receipt: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactId": artifact_id,
        "repository": {"digest": str(repository["digest"]), "label": _bounded(repository.get("label"), MAX_REFERENCE)},
        "type": artifact_type,
        "git": dict(git_identity),
        "createdBy": _bounded(created_by, 120),
        "run": {
            "runId": _bounded(run.get("runId"), 120),
            "hostname": _bounded(run.get("hostname"), 120),
            "pid": int(run["pid"]) if isinstance(run.get("pid"), int) else None,
        },
        "purpose": _bounded(purpose, MAX_TEXT),
        "createdAt": created_at,
        "originalHead": str(original_head),
        "expectedOutcome": _bounded(expected_outcome, MAX_TEXT),
        "cleanupPredicate": dict(cleanup_predicate),
        "lastReconcile": None,
    }
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        raise RecoveryError("unsupported receipt schema version")
    artifact_id = receipt.get("artifactId")
    if not isinstance(artifact_id, str) or not ARTIFACT_ID_RE.match(artifact_id):
        raise RecoveryError("receipt has no valid artifact id")
    artifact_type = receipt.get("type")
    if artifact_type not in ARTIFACT_TYPES:
        raise RecoveryError("receipt has an unsupported artifact type")
    repository = receipt.get("repository")
    if not isinstance(repository, dict) or not isinstance(repository.get("digest"), str):
        raise RecoveryError("receipt has no repository digest")
    git_identity = receipt.get("git")
    if not isinstance(git_identity, dict):
        raise RecoveryError("receipt has no git identity")
    original_head = receipt.get("originalHead")
    if not isinstance(original_head, str) or not OID_RE.match(original_head):
        raise RecoveryError("receipt has no valid original head")
    if artifact_type == ARTIFACT_STASH:
        oid = git_identity.get("object")
        if not isinstance(oid, str) or not OID_RE.match(oid):
            raise RecoveryError("stash receipt has no valid object id")
    else:
        path = git_identity.get("path")
        head = git_identity.get("head")
        if not isinstance(path, str) or not path:
            raise RecoveryError("worktree receipt has no path")
        if not isinstance(head, str) or not OID_RE.match(head):
            raise RecoveryError("worktree receipt has no valid head")
    _reject_secret_keys(receipt)


def validate_worktree_containment(receipt: Mapping[str, Any], *, digest: str, state_root: Path) -> Path:
    """Return the receipt's worktree path only if it is contained and safe."""

    git_identity = receipt.get("git", {})
    raw = git_identity.get("path") if isinstance(git_identity, dict) else None
    if not isinstance(raw, str) or not raw:
        raise RecoveryError("worktree receipt has no path")
    path = Path(raw)
    base = worktree_base(digest, state_root).resolve()
    try:
        resolved = path.resolve(strict=False)
    except OSError as error:
        raise RecoveryError(f"cannot resolve worktree path: {error.strerror or 'unresolvable'}") from error
    if resolved != base and base not in resolved.parents:
        raise RecoveryError("worktree path escapes the pack recovery directory")
    if path.is_symlink():
        raise RecoveryError("worktree path must not be a symlink")
    return path


# ---------------------------------------------------------------------------
# Register (atomic; never touches a Git artifact)
# ---------------------------------------------------------------------------


def register(
    *,
    repo: Path,
    artifact_type: str,
    git_identity: Mapping[str, str],
    created_by: str,
    run: Mapping[str, Any],
    purpose: str,
    original_head: str,
    expected_outcome: str,
    cleanup_predicate: Mapping[str, Any] | None = None,
    state_root: Path | None = None,
    now: datetime | None = None,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Validate an already-created artifact's identity and record its receipt.

    Registration is atomic (temp file + ``os.replace``). It never creates or
    mutates a Git artifact; the caller owns creation and, on failure here, owns
    verified rollback of the artifact it just made (R3).
    """

    identity = repository_identity(repo)
    state = resolve_state_root() if state_root is None else state_root
    digest = identity["digest"]
    moment = now or now_utc()
    chosen_id = artifact_id or new_artifact_id()

    normalized_git = _validate_created_identity(repo, artifact_type, git_identity, digest=digest, state_root=state)

    receipt = build_receipt(
        artifact_id=chosen_id,
        artifact_type=artifact_type,
        repository=identity,
        git_identity=normalized_git,
        created_by=created_by,
        run=run,
        purpose=purpose,
        original_head=original_head,
        expected_outcome=expected_outcome,
        cleanup_predicate=dict(cleanup_predicate or {}),
        created_at=iso_utc(moment),
    )

    _reject_duplicate(repo, receipt, digest=digest, state_root=state)

    directory = receipts_dir(digest, state)
    ensure_private_directory(directory)
    atomic_write_json(directory / f"{chosen_id}.json", receipt)
    return receipt


def _validate_created_identity(
    repo: Path,
    artifact_type: str,
    git_identity: Mapping[str, str],
    *,
    digest: str,
    state_root: Path,
) -> dict[str, str]:
    if artifact_type == ARTIFACT_STASH:
        oid = git_identity.get("object", "")
        if not OID_RE.match(oid):
            raise RecoveryError("stash object id is not a valid oid")
        if not object_exists(repo, oid):
            raise RecoveryError("stash object does not exist; refusing to register a phantom artifact")
        return {
            "object": oid,
            "subject": _bounded(git_identity.get("subject"), MAX_REFERENCE),
        }
    if artifact_type == ARTIFACT_WORKTREE:
        path = git_identity.get("path", "")
        head = git_identity.get("head", "")
        if not path:
            raise RecoveryError("worktree path is required")
        if not OID_RE.match(head):
            raise RecoveryError("worktree head is not a valid oid")
        candidate = {"path": str(Path(path).resolve(strict=False)), "head": head}
        validate_worktree_containment({"git": candidate}, digest=digest, state_root=state_root)
        registered = {entry.get("path", "") for entry in worktree_entries(repo)}
        if str(Path(path).resolve(strict=False)) not in {str(Path(item).resolve(strict=False)) for item in registered}:
            raise RecoveryError("worktree is not a registered linked worktree of this repository")
        gitdir = git_identity.get("gitdir")
        if isinstance(gitdir, str) and gitdir:
            candidate["gitdir"] = str(Path(gitdir).resolve(strict=False))
        return candidate
    raise RecoveryError(f"unsupported artifact type: {_bounded(artifact_type, 40)}")


def _reject_duplicate(repo: Path, receipt: Mapping[str, Any], *, digest: str, state_root: Path) -> None:
    identity_key = _identity_key(receipt)
    for existing, _path in _iter_receipts(digest, state_root):
        if existing.get("artifactId") == receipt.get("artifactId"):
            continue
        if _identity_key(existing) == identity_key:
            raise RecoveryError("an active receipt already records this exact artifact identity")


def _identity_key(receipt: Mapping[str, Any]) -> tuple[str, str]:
    git_identity = receipt.get("git", {})
    if receipt.get("type") == ARTIFACT_STASH:
        return (ARTIFACT_STASH, str(git_identity.get("object", "")))
    return (ARTIFACT_WORKTREE, str(git_identity.get("path", "")))


# ---------------------------------------------------------------------------
# Read-only reconciliation / classification
# ---------------------------------------------------------------------------


def _iter_receipts(digest: str, state_root: Path) -> Iterable[tuple[dict[str, Any], Path]]:
    directory = receipts_dir(digest, state_root)
    if not directory.is_dir():
        return
    count = 0
    for entry in sorted(directory.glob("*.json")):
        if entry.is_symlink() or not entry.is_file():
            continue
        count += 1
        if count > MAX_RECEIPTS:
            break
        try:
            yield read_json(entry), entry
        except RecoveryError:
            # Corrupt receipts are surfaced by classify(); skip them here.
            continue


def _owner_live(receipt: Mapping[str, Any]) -> bool:
    run = receipt.get("run", {})
    if not isinstance(run, dict):
        return False
    hostname = run.get("hostname")
    pid = run.get("pid")
    if hostname != socket.gethostname():
        return False
    return _process_alive(pid)


def _process_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if not hasattr(os, "kill"):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def classify_repository(
    repo: Path,
    *,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Reconcile receipts against Git and the owner ledger, read-only.

    Performs no writes of any kind: no receipt is created, repaired, or deleted
    and no Git artifact is touched. Suitable for ``sd-status``.
    """

    identity = repository_identity(repo)
    digest = identity["digest"]
    state = resolve_state_root() if state_root is None else state_root

    stashes = {entry["oid"]: entry for entry in stash_entries(repo)}
    worktrees = {
        str(Path(entry.get("path", "")).resolve(strict=False)): entry
        for entry in worktree_entries(repo)
        if entry.get("path")
    }

    receipts_report: list[dict[str, Any]] = []
    corrupt: list[dict[str, Any]] = []
    matched_stash_oids: set[str] = set()
    matched_worktree_paths: set[str] = set()

    directory = receipts_dir(digest, state)
    if directory.is_dir():
        count = 0
        for entry in sorted(directory.glob("*.json")):
            if entry.is_symlink() or not entry.is_file():
                corrupt.append({"reference": _bounded(entry.name, MAX_REFERENCE), "reason": "not a regular file"})
                continue
            count += 1
            if count > MAX_RECEIPTS:
                break
            try:
                receipt = read_json(entry)
                validate_receipt(receipt)
            except RecoveryError as error:
                corrupt.append({"reference": _bounded(entry.name, MAX_REFERENCE), "reason": _bounded(str(error), 200)})
                continue
            item = _classify_receipt(
                repo,
                receipt,
                digest=digest,
                state_root=state,
                stashes=stashes,
                worktrees=worktrees,
            )
            if item["type"] == ARTIFACT_STASH and item.get("_oid"):
                matched_stash_oids.add(item["_oid"])
            if item["type"] == ARTIFACT_WORKTREE and item.get("_path"):
                matched_worktree_paths.add(item["_path"])
            item.pop("_oid", None)
            item.pop("_path", None)
            receipts_report.append(item)

    unowned = _find_unowned(stashes, matched_stash_oids, worktrees, matched_worktree_paths, digest=digest, state_root=state)

    counts = {name: 0 for name in CLASSIFICATIONS}
    for item in receipts_report:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    counts[CLASS_UNOWNED_ARTIFACT] += len(unowned)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "repository": {"digest": digest, "label": identity["label"]},
        "receipts": receipts_report,
        "unowned": unowned,
        "corrupt": corrupt,
        "counts": counts,
    }


def _classify_receipt(
    repo: Path,
    receipt: Mapping[str, Any],
    *,
    digest: str,
    state_root: Path,
    stashes: Mapping[str, Mapping[str, str]],
    worktrees: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    artifact_type = receipt["type"]
    artifact_id = receipt["artifactId"]
    owner_live = _owner_live(receipt)
    base = {
        "artifactId": artifact_id,
        "type": artifact_type,
        "ownerLive": owner_live,
        "createdBy": _bounded(receipt.get("createdBy"), 120),
    }

    if artifact_type == ARTIFACT_STASH:
        oid = str(receipt.get("git", {}).get("object", ""))
        base["_oid"] = oid
        base["reference"] = _bounded(oid[:12], MAX_REFERENCE)
        if oid not in stashes:
            base["classification"] = CLASS_MISSING_ARTIFACT
            base["detail"] = "recorded stash is no longer in the stash list; receipt is stale"
            return base
        if owner_live:
            base["classification"] = CLASS_ACTIVE
            base["detail"] = "owning run is still live; in use"
            return base
        proof = stash_cleanup_proof(repo, receipt, stashes=stashes)
        base["classification"] = CLASS_SAFE_CLEANABLE if proof["safe"] else CLASS_NEEDS_REVIEW
        base["detail"] = proof["detail"]
        base["stashRef"] = _bounded(stashes[oid].get("ref"), 40)
        return base

    # worktree
    try:
        path = validate_worktree_containment(receipt, digest=digest, state_root=state_root)
    except RecoveryError as error:
        base["classification"] = CLASS_NEEDS_REVIEW
        base["detail"] = _bounded(str(error), 200)
        base["reference"] = _bounded(artifact_id, MAX_REFERENCE)
        return base
    resolved = str(path.resolve(strict=False))
    base["_path"] = resolved
    base["reference"] = _bounded(path.name, MAX_REFERENCE)
    if resolved not in worktrees:
        base["classification"] = CLASS_MISSING_ARTIFACT
        base["detail"] = "recorded worktree is no longer linked; receipt is stale"
        return base
    if owner_live:
        base["classification"] = CLASS_ACTIVE
        base["detail"] = "owning run is still live; in use"
        return base
    proof = worktree_cleanup_proof(repo, receipt, path)
    base["classification"] = CLASS_SAFE_CLEANABLE if proof["safe"] else CLASS_NEEDS_REVIEW
    base["detail"] = proof["detail"]
    return base


def _find_unowned(
    stashes: Mapping[str, Mapping[str, str]],
    matched_stash_oids: set[str],
    worktrees: Mapping[str, Mapping[str, str]],
    matched_worktree_paths: set[str],
    *,
    digest: str,
    state_root: Path,
) -> list[dict[str, Any]]:
    """Report pack-shaped artifacts that lack a receipt; never adopt or delete.

    Genuine user stashes and worktrees (no pack marker, outside the pack
    worktree base) are intentionally ignored: taking ownership of them is out of
    scope.
    """

    unowned: list[dict[str, Any]] = []
    for oid, entry in stashes.items():
        if oid in matched_stash_oids:
            continue
        subject = entry.get("subject", "")
        if RECOVERY_STASH_PREFIX in subject:
            unowned.append(
                {
                    "type": ARTIFACT_STASH,
                    "reference": _bounded(oid[:12], MAX_REFERENCE),
                    "inspect": f"git stash show -p {oid}",
                    "detail": "pack-shaped stash without a receipt",
                }
            )
    base = worktree_base(digest, state_root).resolve()
    for resolved in worktrees:
        if resolved in matched_worktree_paths:
            continue
        try:
            candidate = Path(resolved)
        except (TypeError, ValueError):
            continue
        if candidate == base or base in candidate.parents:
            unowned.append(
                {
                    "type": ARTIFACT_WORKTREE,
                    "reference": _bounded(candidate.name, MAX_REFERENCE),
                    "inspect": "git worktree list",
                    "detail": "pack-shaped worktree without a receipt",
                }
            )
    return unowned


# ---------------------------------------------------------------------------
# Cleanup proofs (read-only; the destructive cleanup path re-checks these)
# ---------------------------------------------------------------------------


def worktree_cleanup_proof(repo: Path, receipt: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Prove a worktree can be retired with no loss (R7). Read-only."""

    if not path.exists():
        return {"safe": False, "detail": "worktree path is missing"}
    common = worktree_common_dir(path)
    repo_common = worktree_common_dir(repo)
    if common is None or repo_common is None or common != repo_common:
        return {"safe": False, "detail": "worktree git common directory does not match this repository"}
    clean = worktree_is_clean(path)
    if clean is None:
        return {"safe": False, "detail": "worktree status could not be verified"}
    if not clean:
        return {"safe": False, "detail": "worktree has uncommitted changes; preserved"}
    entry = next((item for item in worktree_entries(repo) if str(Path(item.get("path", "")).resolve(strict=False)) == str(path.resolve(strict=False))), None)
    if entry is None:
        return {"safe": False, "detail": "worktree is no longer linked"}
    if entry.get("locked") == "true":
        return {"safe": False, "detail": "worktree is locked by a live owner; preserved"}
    head = str(receipt.get("git", {}).get("head", ""))
    current_head = entry.get("head", "")
    if current_head and head and current_head != head:
        return {"safe": False, "detail": "worktree head moved since registration; preserved"}
    retained = bool(receipt.get("cleanupPredicate", {}).get("retainCommit"))
    if not retained and not commit_reachable(repo, head):
        return {"safe": False, "detail": "worktree head is not reachable from any ref; preserved"}
    return {"safe": True, "detail": "clean, matching, reachable worktree; safe to retire"}


def stash_cleanup_proof(repo: Path, receipt: Mapping[str, Any], *, stashes: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Prove a stash is redundant/superseded (R7). Read-only.

    A stash is provably safe only when its recorded contents are already present
    in history: either the stash commit is reachable from a ref, or its diff
    against the original head is empty. Anything with unique content is
    preserve-only.
    """

    oid = str(receipt.get("git", {}).get("object", ""))
    if oid not in stashes:
        return {"safe": False, "detail": "stash object is no longer present"}
    if commit_reachable(repo, oid):
        return {"safe": True, "detail": "stash commit is reachable from a ref; redundant"}
    predicate = receipt.get("cleanupPredicate", {})
    base = predicate.get("supersededBy") if isinstance(predicate, dict) else None
    if isinstance(base, str) and OID_RE.match(base) and object_exists(repo, base):
        # The stash's tree matches a superseding commit's tree -> no unique work.
        stash_tree = git_stdout(["rev-parse", f"{oid}^{{tree}}"], cwd=repo, context="stash tree")
        base_tree = git_stdout(["rev-parse", f"{base}^{{tree}}"], cwd=repo, context="base tree")
        if stash_tree and base_tree and stash_tree == base_tree:
            return {"safe": True, "detail": "stash tree matches its recorded superseding commit; redundant"}
    return {"safe": False, "detail": "stash content is not provably redundant; preserved"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _state_root_arg(value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RecoveryError("--state-home must be an absolute path")
    return path


def _cmd_register(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    run = {"runId": args.run_id, "hostname": args.hostname or socket.gethostname(), "pid": args.pid}
    git_identity: dict[str, str] = {}
    if args.type == ARTIFACT_STASH:
        git_identity = {"object": args.object or "", "subject": args.subject or ""}
    else:
        git_identity = {"path": args.worktree_path or "", "head": args.head or ""}
        if args.gitdir:
            git_identity["gitdir"] = args.gitdir
    predicate: dict[str, Any] = {}
    if args.superseded_by:
        predicate["supersededBy"] = args.superseded_by
    if args.retain_commit:
        predicate["retainCommit"] = True
    receipt = register(
        repo=repo,
        artifact_type=args.type,
        git_identity=git_identity,
        created_by=args.created_by,
        run=run,
        purpose=args.purpose,
        original_head=args.original_head,
        expected_outcome=args.expected_outcome,
        cleanup_predicate=predicate,
        state_root=_state_root_arg(args.state_home),
    )
    _print({"registered": receipt["artifactId"], "type": receipt["type"]})
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    report = classify_repository(repo, state_root=_state_root_arg(args.state_home))
    _print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track and reconcile pack-created recovery artifacts.")
    parser.add_argument("--state-home", help="absolute user-local state directory")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    register_parser = sub.add_parser("register", help="record a receipt for an already-created artifact")
    register_parser.add_argument("--repo", required=True)
    register_parser.add_argument("--type", required=True, choices=ARTIFACT_TYPES)
    register_parser.add_argument("--object", help="stash object id")
    register_parser.add_argument("--subject", help="stash subject")
    register_parser.add_argument("--worktree-path", help="worktree path")
    register_parser.add_argument("--head", help="worktree head oid")
    register_parser.add_argument("--gitdir", help="worktree gitdir")
    register_parser.add_argument("--created-by", required=True)
    register_parser.add_argument("--run-id", required=True)
    register_parser.add_argument("--hostname")
    register_parser.add_argument("--pid", type=int)
    register_parser.add_argument("--purpose", required=True)
    register_parser.add_argument("--original-head", required=True)
    register_parser.add_argument("--expected-outcome", default="")
    register_parser.add_argument("--superseded-by", help="oid that supersedes a stash")
    register_parser.add_argument("--retain-commit", action="store_true")
    register_parser.set_defaults(func=_cmd_register)

    classify_parser = sub.add_parser("classify", help="reconcile receipts against Git (read-only)")
    classify_parser.add_argument("--repo", required=True)
    classify_parser.set_defaults(func=_cmd_classify)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except RecoveryError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except CommandError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
