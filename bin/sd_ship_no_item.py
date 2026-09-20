"""No-item review records: identity, checkpoint keys, and repository indexes.

This adapter performs no item lookup and constructs no publication client.
It reuses the provisioned `sd_db.ship` checkpoint
primitives with separate keys, so absence is never encoded as a synthetic row.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import sd_lib
import sd_ship_evidence
from sd_ship_history import (
    AUTOMATIC_CODE_REVIEW_PASSES,
    ItemHistory,
    digest,
    full_branch_coverage,
)
from sd_ship_identity import ReviewIdentity
from sd_ship_remote import Refusal, git, slug
from sd_ship_review import SharedReview
from sd_ship_workflow import success

REVIEW_PREFIX = "ship-review-no-item:"
ACCEPTANCE_PREFIX = "ship-adjudication-no-item:"
INDEX_PREFIX = "ship-review-no-item-index:"
ITEM_PREFIX = "ship:"
SCHEMA_VERSION = 1

#: The checkpoint layout this adapter was tested against. It reads the existing
#: `state` table exactly as `sd_db.ship.for_item` does; it requires no
#: enumeration API and no schema change. Validate before every enumeration.
SCHEMA_CONTRACT = {
    "library": "sd_db",
    "tested_version": "0.1.0",
    "table": "state",
    "columns": ("id", "kind", "key", "timestamp", "body"),
    "kind": "checkpoint",
}
#: Enumeration and index growth are bounded. Exceeding a limit refuses the
#: operation and keeps every existing record readable.
RECEIPT_LIMIT = 5000
INDEX_LIMIT = 2000
FAMILIES = ("branch", "head", "tree")

#: An imported manifest is untrusted operator evidence. Its shape is closed:
#: an unknown field is a different schema, not a field to ignore.
IMPORT_SCHEMA_VERSION = 1
MANIFEST_FIELDS = ("schema_version", "repository", "passes")
PASS_FIELDS = ("ordinal", "head", "report", "request", "prior_input", "exit_code", "execution_error")
CLAIM_FIELDS = ("path", "sha256")
MAX_IMPORT_PASSES = 50
MAX_CLAIM_BYTES = 4 * 1024 * 1024
UNTRUSTED = "untrusted imported evidence; it consumes budget and proves no coverage"
#: The combined history digest is versioned, and it covers only what history is:
#: the canonical repository, the stable review ID, and the two ordered record
#: lists. Branch, lifecycle, and identity revision are mutable and stay out.
HISTORY_DIGEST_VERSION = 1


def observed_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def suffix(repository: str, review_id: str) -> str:
    """Unambiguous field separation: a review ID never contains a NUL byte."""
    return hashlib.sha256(f"{repository}\0{review_id}".encode()).hexdigest()


def review_key(repository: str, review_id: str) -> str:
    return REVIEW_PREFIX + suffix(repository, review_id)


def no_item_acceptance_key(repository: str, review_id: str) -> str:
    # Derived from identity, never by stripping a prefix off the review key.
    return ACCEPTANCE_PREFIX + suffix(repository, review_id)


def index_key(repository: str, family: str, value: str) -> str:
    if family not in FAMILIES:
        raise Refusal(f"unknown no-item index family: {family}")
    token = hashlib.sha256(f"{repository}\0{family}\0{value}".encode()).hexdigest()
    return f"{INDEX_PREFIX}{family}:{token}"


def validate_schema(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(state)")}
    if not columns:
        raise Refusal("no-item records need the sd_db checkpoint table; its state table is missing")
    missing = [name for name in SCHEMA_CONTRACT["columns"] if name not in columns]
    if missing:
        raise Refusal(
            "sd_db checkpoint schema does not match this adapter's tested layout; "
            f"the state table is missing {', '.join(missing)}"
        )


def enumerate_keys(connection: sqlite3.Connection, prefix: str, limit: int) -> list[str]:
    validate_schema(connection)
    try:
        rows = connection.execute(
            "SELECT key FROM state WHERE kind='checkpoint' AND key LIKE ? GROUP BY key ORDER BY key",
            (prefix + "%",),
        )
        keys = [row[0] for row in rows]
    except sqlite3.Error as error:
        raise Refusal(
            f"no-item {prefix} enumeration query failed: {error}; "
            "a failed query refuses and is never read as empty history"
        ) from None
    if len(keys) > limit:
        raise Refusal(
            f"{len(keys)} stored {prefix} records exceed this adapter's documented limit of {limit}; "
            "every existing record remains readable and nothing was written"
        )
    return keys


def bounded_bytes(path: pathlib.Path, label: str) -> bytes:
    if not path.is_absolute() or path.resolve() != path:
        raise Refusal(f"{label} must name a canonical absolute path, not {path}")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise Refusal(f"{label} cannot be read: {path}: {error.strerror}") from None
    if len(data) > MAX_CLAIM_BYTES:
        raise Refusal(f"{label} exceeds this adapter's documented limit of {MAX_CLAIM_BYTES} bytes")
    return data


def claim_bytes(claim, label: str) -> bytes:
    if not isinstance(claim, dict) or tuple(sorted(claim)) != tuple(sorted(CLAIM_FIELDS)):
        raise Refusal(f"{label} must name exactly a path and its sha256")
    data = bounded_bytes(pathlib.Path(claim["path"]), label)
    if hashlib.sha256(data).hexdigest() != claim["sha256"]:
        raise Refusal(f"{label} does not match its recorded SHA256; its original bytes were not preserved")
    return data


def claim_json(claim, label: str) -> tuple[bytes, dict]:
    data = claim_bytes(claim, label)
    try:
        value = json.loads(data)
    except ValueError as error:
        raise Refusal(f"{label} is not bounded JSON: {error}") from None
    if not isinstance(value, dict):
        raise Refusal(f"{label} must be a JSON object")
    return data, value


def retained(claim, label: str) -> dict | None:
    """Store original bytes beside their hash; a projection never replaces them."""
    if claim is None:
        return None
    data = claim_bytes(claim, label)
    return {"sha256": claim["sha256"], "bytes_base64": base64.b64encode(data).decode(),
            "bytes": len(data), "source_path": claim["path"], "operator_context": UNTRUSTED}


def ancestor_head(root: pathlib.Path, head, current: str, label: str) -> str:
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise Refusal(f"{label} must name one full commit SHA")
    try:
        git(root, "merge-base", "--is-ancestor", head, current)
    except Refusal:
        raise Refusal(f"{label} {head} is not an ancestor of this history head {current}") from None
    return head


def imported_pass(root: pathlib.Path, entry, ordinal: int, current: str) -> dict:
    label = f"imported pass {ordinal}"
    if not isinstance(entry, dict) or any(name not in PASS_FIELDS for name in entry):
        raise Refusal(f"{label} carries an unknown manifest field; this is a different schema")
    if entry.get("ordinal") != ordinal:
        raise Refusal(f"{label} is out of order; imported records keep their original ordinals")
    head = ancestor_head(root, entry.get("head"), current, f"{label} head")
    report = retained(entry.get("report"), f"{label} report")
    if report is None and not isinstance(entry.get("execution_error"), dict):
        raise Refusal(f"{label} has no report and no execution error; a missing report stays explicit")
    prior = retained(entry.get("prior_input"), f"{label} prior input")
    if prior is not None:
        _data, value = claim_json(entry["report"], f"{label} report")
        _prior_data, prior_value = claim_json(entry["prior_input"], f"{label} prior input")
        if value.get("resume_report_digest") != digest(prior_value):
            raise Refusal(f"{label} does not reference its own prior input digest")
    return {"ordinal": ordinal, "head": head, "exit_code": entry.get("exit_code"), "report": report,
            "execution_error": entry.get("execution_error"), "prior_input": prior,
            "request": retained(entry.get("request"), f"{label} request"), "operator_context": UNTRUSTED}


def imported_passes(root: pathlib.Path, path: pathlib.Path, repository: str, current: str) -> tuple[list[dict], str]:
    data = bounded_bytes(path, "imported history manifest")
    try:
        manifest = json.loads(data)
    except ValueError as error:
        raise Refusal(f"imported history manifest is not bounded JSON: {error}") from None
    rows = manifest.get("passes") if isinstance(manifest, dict) else None
    if not isinstance(manifest, dict) or any(name not in MANIFEST_FIELDS for name in manifest):
        raise Refusal("imported history manifest carries an unknown field; this is a different schema")
    if manifest.get("schema_version") != IMPORT_SCHEMA_VERSION:
        raise Refusal(f"imported history manifest needs schema_version {IMPORT_SCHEMA_VERSION}")
    if manifest.get("repository") != repository:
        raise Refusal(f"imported history manifest claims repository {manifest.get('repository')}, not {repository}")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_IMPORT_PASSES:
        raise Refusal(f"imported history manifest needs between one and {MAX_IMPORT_PASSES} ordered passes")
    passes = [imported_pass(root, entry, ordinal, current) for ordinal, entry in enumerate(rows, 1)]
    return passes, hashlib.sha256(data).hexdigest()


def import_claim(root: pathlib.Path, args, facts: GitFacts) -> tuple[list[dict], dict] | tuple[None, None]:
    """Parse and validate before any write; an import never dispatches a provider."""
    if args.import_history is None:
        return None, None
    if not args.assert_history_complete:
        raise Refusal(
            "--import-history requires --assert-history-complete: only the operator can assert that "
            "the supplied history is complete, and no hash can prove an omitted record never existed"
        )
    passes, manifest_digest = imported_passes(root, args.import_history, facts.repository, facts.head)
    evidence = {"schema_version": IMPORT_SCHEMA_VERSION, "manifest_digest": manifest_digest,
                "manifest_path": str(args.import_history), "imported_at": observed_at(),
                "completeness_assertion": "operator asserted completeness; not proof and not authorization"}
    return passes, evidence


@dataclass(frozen=True)
class GitFacts:
    repository: str
    branch: str
    head: str
    tree: str
    base: str
    commits: tuple[str, ...]
    trees: tuple[str, ...]


def committed_facts(root: pathlib.Path, *, require_diff: bool = True) -> GitFacts:
    """Resolve canonical identity from Git alone, after refreshing the base.

    An outstanding branch diff is an eligibility rule for allocating and
    dispatching, not part of identity. A record outlives its diff: once the work
    merges and the refreshed base catches up, `base..head` is empty, and close,
    reopen and rebind still have to run on it. `require_diff=False` reads the
    identity without that rule, so a finished record can be closed and its
    branch alias released instead of staying active forever.
    """
    # Canonical identity is the configured remote, never the URL a local
    # `insteadOf` rewrite resolves for transport.
    try:
        configured = git(root, "config", "--get", "remote.origin.url")
    except Refusal:
        raise Refusal("this checkout has no origin remote; no-item records need one canonical repository") from None
    repository = slug(configured)
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if git(root, "status", "--porcelain"):
        raise Refusal("this checkout has uncommitted changes; allocation requires a clean checkout")
    remote, default = sd_lib.upstream(root)
    git(root, "fetch", "--quiet", remote)
    head = git(root, "rev-parse", "HEAD")
    base = git(root, "merge-base", head, f"refs/remotes/{remote}/{default}")
    commits = tuple(git(root, "rev-list", f"{base}..{head}").split())
    if require_diff and not commits:
        raise Refusal(
            "this branch has no committed diff against the refreshed default branch; "
            "commit the proposed change before allocating a record"
        )
    trees = tuple(git(root, "rev-parse", f"{commit}^{{tree}}") for commit in commits)
    return GitFacts(repository, branch, head, git(root, "rev-parse", "HEAD^{tree}"), base, commits, trees)


def receipt_covers(receipt: dict, facts: GitFacts) -> bool:
    """Whether a retained item-backed receipt already covers this exact work.

    Commits already included in the refreshed base are not related merely
    because they are ancestors; only the proposed branch diff counts.
    """
    if receipt.get("repository") != facts.repository:
        return False
    heads = {entry.get("head") for entry in receipt.get("passes") or [] if isinstance(entry, dict)}
    heads.update(value for value in (receipt.get("head"), receipt.get("reviewed_head")) if value)
    return bool(receipt.get("branch") == facts.branch or heads & set(facts.commits))


def check_item_receipts(connection: sqlite3.Connection, store, facts: GitFacts) -> None:
    for key in enumerate_keys(connection, ITEM_PREFIX, RECEIPT_LIMIT):
        # A malformed or unreadable receipt refuses; it is never empty history.
        _revision, receipt = store.read(connection, key)
        if receipt_covers(receipt, facts):
            raise Refusal(
                f"item-backed ship receipt {key} already covers this work for item {receipt.get('item')}; "
                "no-item operation refuses; use the existing item-backed workflow"
            )


def index_owner(connection: sqlite3.Connection, store, facts: GitFacts, family: str, value: str) -> str | None:
    _revision, entry = store.read(connection, index_key(facts.repository, family, value))
    return entry.get("review_id") if entry else None


def index_claims(facts: GitFacts) -> tuple[tuple[str, str], ...]:
    claims = [("branch", facts.branch), ("tree", facts.tree)]
    claims += [("head", commit) for commit in facts.commits]
    claims += [("tree", tree) for tree in facts.trees]
    return tuple(dict.fromkeys(claims))


def check_no_item_records(connection: sqlite3.Connection, store, facts: GitFacts) -> None:
    validate_schema(connection)
    for family, value in index_claims(facts):
        owner = index_owner(connection, store, facts, family, value)
        if owner is None:
            continue
        _revision, record = store.read(connection, review_key(facts.repository, owner))
        if family == "branch" and record.get("lifecycle") != "active":
            continue
        raise Refusal(
            f"an existing no-item record {owner} already owns this {family}; "
            "reuse that review ID, or rebind it; branch renames and HEAD copies create no fresh budget"
        )


def with_digest(record: dict) -> dict:
    """Every write carries the digest its own records compute, never a stale one."""
    record["history_digest"] = combined_digest(record)
    return record


def allocation_record(review_id: str, facts: GitFacts, imported: list[dict] | None, evidence: dict | None) -> dict:
    return with_digest({
        "schema_version": SCHEMA_VERSION,
        "identity_mode": "no-item",
        "review_id": review_id,
        "repository": facts.repository,
        "branch": facts.branch,
        "branch_aliases": [facts.branch],
        "lifecycle": "active",
        "identity_revision": 1,
        "allocation": {"head": facts.head, "tree": facts.tree, "merge_base": facts.base},
        "heads": [facts.head],
        "trees": [facts.tree],
        "passes": [],
        "historical_passes": imported or [],
        "imported_history": evidence,
        "created_at": observed_at(),
    })


def library_transaction(connection: sqlite3.Connection):
    """The checkpoint transaction, reached the way every entrypoint must reach it.

    One gateway for both write paths, so neither of them imports `sd_db` on the
    strength of a caller having done this already.
    """
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise Refusal(imported.problem)
    from sd_db.database import transaction

    return transaction(connection)


def write_allocation(connection: sqlite3.Connection, store, review_id: str, facts: GitFacts,
                     imported: list[dict] | None = None, evidence: dict | None = None) -> int:
    """Record and index in one transaction, under the caller's repository lock."""
    claims = index_claims(facts)
    if len(claims) + len(enumerate_keys(connection, INDEX_PREFIX, INDEX_LIMIT)) > INDEX_LIMIT:
        raise Refusal(
            f"no-item identity indexes reached this adapter's documented limit of {INDEX_LIMIT}; "
            "nothing was written and every existing record remains readable"
        )
    with library_transaction(connection):
        record = allocation_record(review_id, facts, imported, evidence)
        revision = store.save(connection, review_key(facts.repository, review_id), 0, record)
        for family, value in claims:
            key = index_key(facts.repository, family, value)
            previous, _entry = store.read(connection, key)
            store.save(connection, key, previous, {"review_id": review_id, "family": family, "value": value,
                                                   "repository": facts.repository})
    return revision


@dataclass(frozen=True)
class NoItemIdentity(ReviewIdentity):
    review_id: str
    repository: str
    root: pathlib.Path

    def _acceptance_namespace(self, review_key: str) -> str:
        return no_item_acceptance_key(self.repository, self.review_id)

    def _identity_bindings(self, state: dict) -> dict:
        # The archive joins the bindings only once it exists, so a template and
        # its unprepared proposal bind the same absence.
        archive = sd_ship_evidence.archive_descriptor(self.root, self.review_id)
        return {"identity_mode": "no-item", "review_id": self.review_id,
                "identity_revision": state.get("identity_revision"),
                "schema_version": state.get("schema_version"),
                **({"evidence_archive": archive} if archive else {})}

    def _check_evidence(self, proposal: dict) -> None:
        sd_ship_evidence.check_archive(self.root, self.review_id, proposal)

    def _prepare_evidence(self, proposal: dict) -> dict:
        return sd_ship_evidence.prepare_archive(self.root, self.review_id, proposal)

    def _identity_output(self, state: dict) -> dict:
        return {"identity_mode": "no-item", "review_id": self.review_id,
                "branch": state.get("branch"), "lifecycle": state.get("lifecycle"),
                "identity_revision": state.get("identity_revision"),
                "head": state.get("head"), "reviewed_head": state.get("reviewed_head"),
                "pull_request": state.get("pull_request"), "warnings": state.get("warnings", []),
                "review_clearance": state.get("review_clearance")}


def create_record(root: pathlib.Path, connection: sqlite3.Connection, database: pathlib.Path, args, store) -> dict:
    if not args.assert_new_work:
        raise Refusal(
            "--create-record requires --assert-new-work: creation asserts new work, "
            "not a renamed or rewritten continuation, and hashes cannot prove that"
        )
    if args.review_id:
        raise Refusal("--create-record allocates a new record; it cannot name an existing --review-id")
    facts = committed_facts(root)
    imported, evidence = import_claim(root, args, facts)
    check_item_receipts(connection, store, facts)
    check_no_item_records(connection, store, facts)
    review_id = secrets.token_hex(16)
    with store.repository_lock(database, facts.repository):
        # Recheck under the lock: a concurrent writer may have claimed this work.
        check_item_receipts(connection, store, facts)
        check_no_item_records(connection, store, facts)
        write_allocation(connection, store, review_id, facts, imported, evidence)
    _revision, state = store.read(connection, review_key(facts.repository, review_id))
    return no_item_result(root, "created", review_id, facts.repository, state,
                          {"allocation": state["allocation"], "spent_passes": spent_passes(state)})


def spent_passes(state: dict) -> int:
    """Imported records consume budget; only native results can prove coverage."""
    return len(state.get("historical_passes") or []) + len(state.get("passes") or [])


def no_item_result(root: pathlib.Path, phase: str, review_id: str, repository: str, state: dict, extra: dict) -> dict:
    result = NoItemIdentity(review_id, repository, root).result_fields(phase, state, observed_at(), extra)
    result["workflow"] = success(phase)
    return result


def selected_record(connection: sqlite3.Connection, store, root: pathlib.Path, args,
                    *, require_diff: bool = True) -> tuple[str, GitFacts, int, dict]:
    # Dispatch and clearance read the same table, so they own the same guard.
    validate_schema(connection)
    facts = committed_facts(root, require_diff=require_diff)
    key = review_key(facts.repository, args.review_id)
    revision, state = store.read(connection, key)
    if not state:
        raise Refusal(f"no no-item record {args.review_id} exists in this repository")
    if state.get("lifecycle") != "active":
        raise Refusal(f"no-item record {args.review_id} is closed; reopen it before any further operation")
    if state.get("branch") != facts.branch:
        raise Refusal(
            f"no-item record {args.review_id} is bound to branch {state.get('branch')}, not {facts.branch}; "
            "rebind the record explicitly before any other operation"
        )
    return key, facts, revision, state


def refuse_existing_history(state: dict, review_id: str) -> None:
    if state.get("historical_passes") or state.get("passes"):
        raise Refusal(
            f"no-item record {review_id} already holds history; an import never replaces or merges "
            "existing records, and every implicated pass is preserved"
        )


def import_into_record(root: pathlib.Path, connection: sqlite3.Connection, database: pathlib.Path, args, store) -> dict:
    key, facts, revision, state = selected_record(connection, store, root, args)
    imported, evidence = import_claim(root, args, facts)
    refuse_existing_history(state, args.review_id)
    check_item_receipts(connection, store, facts)
    with store.repository_lock(database, facts.repository):
        revision, state = store.read(connection, key)
        # Recheck under the lock, as allocation does. Parsing the manifest and
        # walking its ancestry is slow, so a second import can finish that work
        # while the first holds the lock; writing then would overwrite an import
        # that already landed, and recompute the digest over the budget it lost.
        refuse_existing_history(state, args.review_id)
        check_item_receipts(connection, store, facts)
        state.update(historical_passes=imported, imported_history=evidence)
        store.save(connection, key, revision, with_digest(state))
    _revision, state = store.read(connection, key)
    return no_item_result(root, "imported", args.review_id, facts.repository, state,
                          {"spent_passes": spent_passes(state), "native_passes": len(state["passes"])})




def historical_report(record: dict) -> dict | None:
    """The parsed projection of one imported report; the bytes remain the record."""
    report = record.get("report")
    if report is None:
        return None
    data = base64.b64decode(report["bytes_base64"], validate=True)
    if hashlib.sha256(data).hexdigest() != report["sha256"]:
        raise Refusal("imported report bytes no longer match their recorded SHA256")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise Refusal("imported report is not an object")
    return value


def imported_entries(state: dict) -> list[dict]:
    return [{"head": record["head"], "report": historical_report(record),
             "execution_error": record.get("execution_error")}
            for record in state.get("historical_passes") or []]


def combined_digest(state: dict, native: list[dict] | None = None) -> str:
    records = state.get("historical_passes") or []
    passes = state.get("passes") or [] if native is None else native
    return digest({"version": HISTORY_DIGEST_VERSION, "repository": state.get("repository"),
                   "review_id": state.get("review_id"), "historical": records, "native": passes})


class NoItemHistory(ItemHistory):
    """Combined counts, global ordinals, and prefixes over two record lists.

    Imported records never become native results and never authorize anything.
    Only native results can establish current coverage and tool bindings.
    """

    def _records(self, state: dict) -> list[dict]:
        return list(state.get("historical_passes") or []) + self.native(state)

    def _continuation(self, state: dict) -> bool:
        # After any import every native pass needs its own explicit request.
        return bool(state.get("historical_passes"))

    def _digest(self, state: dict) -> str:
        return combined_digest(state)

    def _entries(self, state: dict, before_last: bool) -> list[dict]:
        passes = self.native(state)
        return imported_entries(state) + (passes[:-1] if before_last else passes)

    def _request_fields(self, state: dict) -> dict:
        return {"identity_mode": "no-item", "review_id": state.get("review_id"),
                "identity_revision": state.get("identity_revision"), "branch": state.get("branch")}

    def _stamp(self, state: dict) -> dict:
        return with_digest(state)

    def _validate_requests(self, state: dict) -> None:
        """Every request binds the combined prefix, imported history or not.

        The digest a request carries is the one `history_digest` wrote, and in
        this mode that is always the combined form. Reading a native-only
        record against the raw native prefix instead compared two formats that
        never match: the pass was spent, and its clearance then refused.

        An import changes how many passes need a request, not what one says. It
        spends the budget, so every native pass after an import carries its
        own; without one the automatic passes are the initial review and the
        fix verifications the cap allows, exactly as the item mode has them.
        """
        imported = len(state.get("historical_passes") or [])
        passes = self.native(state)
        start = 0 if imported else AUTOMATIC_CODE_REVIEW_PASSES
        for index, entry in enumerate(passes):
            request = entry.get("additional_review_request")
            # A request below `start` is not required, and is still read: a
            # receipt written under a lower cap carries one where today's cap
            # expects none, and skipping it would leave it unauthenticated.
            if request is None and index < start:
                continue
            if (not isinstance(request, dict) or request.get("head") != entry.get("head")
                    or not isinstance(request.get("reason"), str) or not request["reason"].strip()
                    or type(request.get("allowed_passes")) is not int or request["allowed_passes"] != 1
                    or request.get("prior_history_digest") != combined_digest(state, passes[:index])):
                raise Refusal(
                    f"native pass {imported + index + 1} does not bind its exact combined prior history "
                    "and head; imported requests are never authenticated"
                )

    def _validate_coverage(self, state: dict, report: dict) -> None:
        if not state.get("historical_passes"):
            super()._validate_coverage(state, report)
            return
        # Every native pass after an import is a full-branch continuation over
        # the complete combined history; imported evidence is never fix-only.
        self._validate_requests(state)
        full_branch_coverage(report, self.aggregate(state, before_last=True))


def stored_digest(state: dict) -> dict:
    """A cached digest that disagrees with its own records is never trusted."""
    recomputed = combined_digest(state)
    if state.get("history_digest") not in (None, recomputed):
        raise Refusal("stored no-item history digest disagrees with its records; reconcile before continuing")
    return state


def open_review(root: pathlib.Path, connection, database: pathlib.Path, args, store, runtime,
                *, require_diff: bool | None = None) -> SharedReview:
    key, facts, revision, state = selected_record(connection, store, root, args,
                                                 require_diff=args.command not in ("reconcile", "merge") if require_diff is None else require_diff)
    return SharedReview(root, connection, database, args, store=store, repository=facts.repository,
                        branch=facts.branch, head=facts.head, key=key, revision=revision,
                        state=stored_digest(state), identity=NoItemIdentity(args.review_id, facts.repository, root),
                        history=NoItemHistory(), runtime=runtime)


def publication_review(root: pathlib.Path, connection, database: pathlib.Path, args, store, runtime) -> SharedReview:
    """Observation reads a durable identity without inspecting or changing the current branch."""
    validate_schema(connection)
    repository = slug(git(root, "config", "--get", "remote.origin.url"))
    key = review_key(repository, args.review_id)
    revision, state = store.read(connection, key)
    if not state:
        raise Refusal(f"no no-item record {args.review_id} exists in this repository")
    if args.command != "observe":
        require_diff = args.command == "prepare" and state.get("phase") not in ("merged", "merge_dispatch")
        return open_review(root, connection, database, args, store, runtime, require_diff=require_diff)
    return SharedReview(root, connection, database, args, store=store, repository=repository,
                        branch=state["branch"], head=state.get("head", ""), key=key, revision=revision,
                        state=stored_digest(state), identity=NoItemIdentity(args.review_id, repository, root),
                        history=NoItemHistory(), runtime=runtime)


def dispatch_review(root: pathlib.Path, connection, database: pathlib.Path, args, store, runtime) -> dict:
    review = open_review(root, connection, database, args, store, runtime)
    head = runtime.current_head(root)
    with store.repository_lock(database, review.repository):
        review.revision, review.state = store.read(connection, review.key)
        stored_digest(review.state)
        review.review(head)
    return review.result("reviewed", spent_passes=spent_passes(review.state),
                         native_passes=len(review.state["passes"]),
                         history_digest=review.state["history_digest"])


def verify_review(root: pathlib.Path, connection, database: pathlib.Path, args, store, runtime) -> dict:
    """Read-only clearance: it writes nothing and dispatches no provider."""
    review = open_review(root, connection, database, args, store, runtime)
    head = runtime.current_head(root)
    if args.expected_head != head:
        raise Refusal(f"expected head {args.expected_head} is not this checkout's clean current HEAD {head}")
    if not review.history.native(review.state):
        raise Refusal(
            f"no-item record {args.review_id} has no completed native review receipt; "
            "imported history consumes budget but never establishes current coverage"
        )
    # A standalone record has no prepared delivery receipt to hold a prior
    # clearance, so the acceptance record itself is the authority, and it is
    # revalidated here against the current head, bindings and durable evidence.
    clearance = review.check_review(head, refresh_adjudication=True)
    return review.result("verified", clearance=clearance, spent_passes=spent_passes(review.state),
                         history_digest=review.state["history_digest"])


def adjudicate_review(root: pathlib.Path, connection, database: pathlib.Path, args, store, runtime) -> dict:
    """Template, preparation and validation read; only acceptance writes."""
    review = open_review(root, connection, database, args, store, runtime)
    if args.accept_dispositions is None:
        return review.adjudicate()
    with store.repository_lock(database, review.repository):
        review.revision, review.state = store.read(connection, review.key)
        stored_digest(review.state)
        return review.adjudicate()


def any_record(connection: sqlite3.Connection, store, root: pathlib.Path, args) -> tuple[str, GitFacts, int, dict]:
    """Read a record without the branch and lifecycle guards the others apply.

    Rebinding, closing and reopening are the operations a record needs after its
    work has landed, so they read identity without the outstanding-diff rule.
    """
    validate_schema(connection)
    facts = committed_facts(root, require_diff=False)
    key = review_key(facts.repository, args.review_id)
    revision, state = store.read(connection, key)
    if not state:
        raise Refusal(f"no no-item record {args.review_id} exists in this repository")
    return key, facts, revision, stored_digest(state)


def claim_branch(connection: sqlite3.Connection, store, repository: str, branch: str, review_id: str | None) -> None:
    key = index_key(repository, "branch", branch)
    previous, _entry = store.read(connection, key)
    store.save(connection, key, previous, {"review_id": review_id, "family": "branch",
                                           "value": branch, "repository": repository})


def write_identity(connection: sqlite3.Connection, store, key: str, revision: int, state: dict, **updates) -> None:
    """One transaction: the revision rises and prior acceptance stops counting."""
    with library_transaction(connection):
        state.update(updates, identity_revision=state.get("identity_revision", 1) + 1, review_clearance=None)
        store.save(connection, key, revision, with_digest(state))


def rebind_record(root: pathlib.Path, connection, database: pathlib.Path, args, store) -> dict:
    key, facts, revision, state = any_record(connection, store, root, args)
    if state.get("branch") != args.rebind_branch:
        raise Refusal(f"--rebind-branch must name the stored branch {state.get('branch')}")
    walked = NoItemHistory().ancestry_heads(state)
    for previous in walked:
        ancestor_head(root, previous, facts.head, "reserved head")
    with store.repository_lock(database, facts.repository):
        revision, state = store.read(connection, key)
        if state.get("branch") != args.rebind_branch:
            raise Refusal("no-item record changed concurrently; reconcile before rebinding")
        # The walk asks Git, so it stays outside the lock, where a pass reserved
        # since the read would go unwalked. Only a head this call has not walked
        # already is walked here, which asks nothing when none appeared.
        for previous in NoItemHistory().ancestry_heads(state):
            if previous not in walked:
                ancestor_head(root, previous, facts.head, "reserved head")
        owner = index_owner(connection, store, facts, "branch", facts.branch)
        # This record's own claim is not another record's: a rebind whose
        # identity write did not land has to be repeatable.
        if facts.branch != state["branch"] and owner not in (None, args.review_id):
            raise Refusal(f"another no-item record {owner} already owns branch {facts.branch}")
        aliases = list(dict.fromkeys([*(state.get("branch_aliases") or []), facts.branch]))
        # A stored branch name is a name, not current ownership. A closed record
        # released its alias, and another record may hold that branch now;
        # releasing it unconditionally would erase a live claim and hand the same
        # branch a second budget.
        if index_owner(connection, store, facts, "branch", args.rebind_branch) == args.review_id:
            claim_branch(connection, store, facts.repository, args.rebind_branch, None)
        claim_branch(connection, store, facts.repository, facts.branch, args.review_id)
        write_identity(connection, store, key, revision, state, branch=facts.branch, branch_aliases=aliases)
    _revision, state = store.read(connection, key)
    return no_item_result(root, "rebound", args.review_id, facts.repository, state,
                          {"spent_passes": spent_passes(state), "history_digest": state["history_digest"]})


def close_record(root: pathlib.Path, connection, database: pathlib.Path, args, store) -> dict:
    key, facts, revision, state = any_record(connection, store, root, args)
    if not (args.close_record or "").strip():
        raise Refusal("--close-record needs a nonempty reason; closing records whether work completed or was abandoned")
    if state.get("lifecycle") != "active":
        raise Refusal(f"no-item record {args.review_id} is already closed")
    with store.repository_lock(database, facts.repository):
        revision, state = store.read(connection, key)
        # The alias is released; every HEAD, tree, reservation and reference
        # stays. Release and identity write are one transaction, the shape
        # `write_allocation` already uses for record-and-index: the release is
        # an unversioned save and the identity write is the versioned one, so
        # ordering them without a transaction let a concurrent revision bump
        # refuse the close after the branch claim was already given up. The
        # record stayed active with its name free, and the next allocation on
        # that name took a fresh budget -- the one thing a closed alias must
        # never grant.
        with library_transaction(connection):
            claim_branch(connection, store, facts.repository, state["branch"], None)
            state.update(lifecycle="closed", identity_revision=state.get("identity_revision", 1) + 1,
                         review_clearance=None,
                         closed={"reason": args.close_record.strip(), "closed_at": observed_at()})
            store.save(connection, key, revision, with_digest(state))
    _revision, state = store.read(connection, key)
    return no_item_result(root, "closed", args.review_id, facts.repository, state,
                          {"spent_passes": spent_passes(state), "history_digest": state["history_digest"]})


def reopen_record(root: pathlib.Path, connection, database: pathlib.Path, args, store) -> dict:
    key, facts, revision, state = any_record(connection, store, root, args)
    if state.get("lifecycle") != "closed":
        raise Refusal(f"no-item record {args.review_id} is already active")
    with store.repository_lock(database, facts.repository):
        revision, state = store.read(connection, key)
        owner = index_owner(connection, store, facts, "branch", state["branch"])
        if owner not in (None, args.review_id):
            raise Refusal(f"another no-item record {owner} now owns branch {state['branch']}")
        claim_branch(connection, store, facts.repository, state["branch"], args.review_id)
        # Reopening resumes the same spent count; abandonment never refunds budget.
        write_identity(connection, store, key, revision, state, lifecycle="active", closed=None)
    _revision, state = store.read(connection, key)
    return no_item_result(root, "reopened", args.review_id, facts.repository, state,
                          {"spent_passes": spent_passes(state), "history_digest": state["history_digest"]})


LIFECYCLE = (("rebind_branch", rebind_record), ("close_record", close_record), ("reopen_record", reopen_record))


def run_no_item(root: pathlib.Path, connection: sqlite3.Connection, database: pathlib.Path, args, store, runtime) -> dict:
    if args.command not in ("review", "verify-review", "adjudicate"):
        raise Refusal(f"--no-item does not support {args.command} in this scope")
    if args.command == "review" and args.create_record:
        return create_record(root, connection, database, args, store)
    if not args.review_id:
        raise Refusal(
            "no-item commands require --review-id ID; missing record identity "
            "never allocates a fresh review budget"
        )
    if args.command == "verify-review":
        return verify_review(root, connection, database, args, store, runtime)
    if args.command == "adjudicate":
        return adjudicate_review(root, connection, database, args, store, runtime)
    selected = [action for name, action in LIFECYCLE if getattr(args, name, None)]
    if len(selected) > 1 or (selected and args.import_history is not None):
        raise Refusal("each no-item record operation runs on its own; they never combine")
    if selected:
        return selected[0](root, connection, database, args, store)
    if args.import_history is not None:
        return import_into_record(root, connection, database, args, store)
    return dispatch_review(root, connection, database, args, store, runtime)
