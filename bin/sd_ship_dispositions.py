"""Explicit operator acceptance, separate from immutable external review reports.

Hashes bind evidence and assertions within the trusted OS account. They neither
prove user authorization nor establish whether a rebuttal is substantively true.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import stat
from datetime import datetime, timezone
from typing import Any

from sd_ship_remote import Refusal, git

MAX_PROPOSAL_BYTES = 2_000_000
MAX_EVIDENCE_BYTES = 32_000_000


def digest(value: Any) -> str:
    try:
        data = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise Refusal("disposition value is not valid finite JSON") from None
    return hashlib.sha256(data).hexdigest()


def read_file(path: pathlib.Path, limit: int) -> bytes:
    """Refuse aliases, special files and oversized reads; never follow a final link."""
    try:
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise Refusal("disposition evidence must name a canonical absolute file")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise Refusal("disposition evidence must be a regular file with one hard link")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            current = path.lstat()
            fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, name) != getattr(after, name) or getattr(after, name) != getattr(current, name) for name in fields):
                raise Refusal("disposition evidence changed during its read")
        if len(data) > limit:
            raise Refusal("disposition file exceeds its bounded input size")
        return data
    except OSError as error:
        raise Refusal(f"disposition evidence cannot be read: {path}: {error.strerror}") from None


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate JSON object key")
    return value


def key(operation: Any) -> str:
    # for_item enumerates only literal ship: keys, not this separate namespace.
    return "ship-adjudication:" + operation.key.removeprefix("ship:")


def context(operation: Any, head: str) -> tuple[dict, list[dict]]:
    if git(operation.root, "status", "--porcelain", "--untracked-files=all") or git(operation.root, "rev-parse", "HEAD") != head:
        raise Refusal("adjudication requires the clean exact reviewed head")
    report = operation.review_inputs(head)
    if report["status"] != "blocking":
        raise Refusal("adjudication requires a complete blocking report")
    outcomes, reviewed = report.get("outcomes"), report.get("reviewed_by")
    if not isinstance(outcomes, list) or any(not isinstance(row, dict) for row in outcomes):
        raise Refusal("adjudication requires complete outcome evidence")
    completed = [row.get("backend") for row in outcomes if row.get("status") in ("clean", "findings")]
    check_exit = report.get("check", {}).get("exit_code")
    if (any(not isinstance(name, str) or not name for name in completed) or len(set(completed)) != len(completed)
            or reviewed != completed or len(completed) != report["completed_reviews"]
            or type(check_exit) is not int or check_exit != 0):
        raise Refusal("adjudication cannot waive incomplete transport or deterministic checks")
    rows = [{"index": index, "finding_digest": digest(row), "raw_finding": row}
            for index, row in enumerate(report["findings"], 1) if row["disposition"] == "blocking"]
    if not rows:
        raise Refusal("blocking report has no blocking findings to adjudicate")
    folder = pathlib.Path(__file__).resolve().parent
    tools = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
             for name in ("sd-ship", "sd_ship_dispositions.py", "sd_ship_remote.py")}
    tools["sd_db.ship"] = hashlib.sha256(pathlib.Path(operation.store.__file__).read_bytes()).hexdigest()
    for name in ("skills/sd-ship/SKILL.md", ".claude/rules/sd-planning-adversarial-review.md"):
        tools[name] = hashlib.sha256((folder.parent / name).read_bytes()).hexdigest()
    return {"repository": operation.repository, "branch": operation.branch, "item": operation.args.item, "head": head,
            "passes_digest": digest(operation.state["passes"]), "report_digest": digest(report),
            "review_binding": operation.state["binding"], "adjudicator_binding": digest(tools)}, rows


def text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > 4096:
        raise Refusal(f"disposition {label} needs nonempty bounded text")


def validate(operation: Any, head: str, proposal: Any) -> str:
    bindings, expected = context(operation, head)
    if (not isinstance(proposal, dict) or set(proposal) != {"schema_version", "bindings", "operator", "authority_context", "findings"}
            or type(proposal["schema_version"]) is not int or proposal["schema_version"] != 1
            or digest(proposal["bindings"]) != digest(bindings)):
        raise Refusal("disposition proposal does not bind the current review, history, tools and head")
    text(proposal["operator"], "operator")
    text(proposal["authority_context"], "authority context")
    rows = proposal["findings"]
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise Refusal("every blocking finding needs one separate accepted disposition")
    for row, identity in zip(rows, expected, strict=True):
        if (not isinstance(row, dict) or set(row) != set(identity) | {"response_disposition", "reason", "owner", "trigger", "evidence"}
                or type(row.get("index")) is not int or digest({name: row.get(name) for name in identity}) != digest(identity)):
            raise Refusal("disposition finding indices, raw findings or digests changed")
        if row["response_disposition"] not in ("rebutted", "parked"):
            raise Refusal("only evidenced rebuttals or explicit parked-risk acceptance can clear a blocker")
        text(row["reason"], "reason")
        if not isinstance(row["owner"], str) or not isinstance(row["trigger"], str):
            raise Refusal("disposition owner and trigger must be text")
        if row["response_disposition"] == "parked":
            text(row["owner"], "risk owner")
            text(row["trigger"], "risk revisit trigger")
        evidence = row["evidence"]
        if not isinstance(evidence, list) or not evidence or len(evidence) > 32:
            raise Refusal("each disposition needs bounded local file evidence")
        for entry in evidence:
            if (not isinstance(entry, dict) or set(entry) != {"path", "sha256"}
                    or not isinstance(entry["path"], str) or not isinstance(entry["sha256"], str)):
                raise Refusal("disposition evidence needs a file path and SHA256")
            data = read_file(pathlib.Path(entry["path"]), MAX_EVIDENCE_BYTES)
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise Refusal("disposition evidence changed or its SHA256 is wrong")
    return digest(proposal)


def accepted(operation: Any, head: str) -> dict:
    revision, value = operation.store.read(operation.connection, key(operation))
    if not revision or value.get("decision") != "accepted":
        raise Refusal("local review contains blocking findings without accepted dispositions")
    proposal_digest = validate(operation, head, value.get("proposal"))
    if value.get("proposal_digest") != proposal_digest:
        raise Refusal("accepted disposition receipt digest does not match")
    return {"kind": "adjudicated", "key": key(operation), "revision": revision, "digest": proposal_digest}


def adjudicate(operation: Any) -> dict:
    args = operation.args
    bindings, rows = context(operation, args.expected_head)
    if args.dispositions_file is None:
        if args.accept_dispositions is not None:
            raise Refusal("acceptance requires a validated --dispositions-file")
        proposal = {"schema_version": 1, "bindings": bindings, "operator": "", "authority_context": "",
                    "findings": [dict(row, response_disposition="", reason="", owner="", trigger="", evidence=[]) for row in rows]}
        return operation.result("disposition_template", proposal=proposal)
    try:
        proposal = json.loads(read_file(args.dispositions_file, MAX_PROPOSAL_BYTES), object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise Refusal("disposition proposal is not bounded valid JSON") from None
    proposal_digest = validate(operation, args.expected_head, proposal)
    if args.accept_dispositions is None:
        return operation.result("disposition_validated", proposal=proposal, acceptance_digest=proposal_digest)
    if args.accept_dispositions != proposal_digest:
        raise Refusal("--accept-dispositions must equal the exact validated proposal digest")
    from sd_db.database import transaction
    with transaction(operation.connection):
        source_revision, source_state = operation.store.read(operation.connection, operation.key)
        if source_revision != operation.revision or source_state != operation.state:
            raise Refusal("ship receipt changed before disposition acceptance")
        previous, prior = operation.store.read(operation.connection, key(operation))
        revision = operation.store.save(operation.connection, key(operation), previous, {
            "decision": "accepted", "proposal": proposal, "proposal_digest": proposal_digest,
            "source_checkpoint": source_revision, "previous_adjudication_digest": digest(prior),
            "accepted_at": datetime.now(timezone.utc).isoformat(), "invoked_by_uid": os.getuid(),
            "authority_boundary": "explicit operator assertion within a trusted OS account; not authenticated user approval"})
    return operation.result("disposition_accepted", acceptance_digest=proposal_digest, adjudication_revision=revision)
