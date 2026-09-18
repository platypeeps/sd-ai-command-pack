"""No-item CLI contracts use real Git and sd_db, never providers or GitHub."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sd_db import connect, initialise
from sd_db import ship as receipts
from sd_db.testing.remote import FixtureRemote, _git

from tests import test_sd_ship as fixture

ship = fixture.ship
no_item = importlib.import_module("sd_ship_no_item")
bindings = importlib.import_module("sd_ship_bindings")


class NoItemContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sd-no-item-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = pathlib.Path(temporary.name).resolve()
        self.remote = FixtureRemote(self.directory / "remote")
        self.remote.commit_on(
            "topic", "change\n\nAuthored-with: human", files={"src.py": "value = 1\n"}
        )
        self.root = self.directory / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(self.remote.path), str(self.root)], check=True
        )
        _git(self.root, "checkout", "topic")
        _git(self.root, "config", "user.name", "Fixture")
        _git(self.root, "config", "user.email", "fixture@example.invalid")
        self.remote_url = "https://github.com/fixture/repo.git"
        _git(self.root, "remote", "set-url", "origin", self.remote_url)
        self.head = _git(self.root, "rev-parse", "HEAD")
        self.base = _git(self.root, "rev-parse", "origin/main")
        self.database = self.directory / "store" / "sd.db"
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        self.environment = {
            "HOME": str(self.directory / "home"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{self.remote.path}.insteadOf",
            "GIT_CONFIG_VALUE_0": self.remote_url,
        }

    def snapshot(self):
        return list(self.connection.iterdump())

    def keys(self, prefix="ship-review-no-item:"):
        return [
            row[0]
            for row in self.connection.execute(
                "SELECT DISTINCT key FROM state WHERE kind='checkpoint' AND key LIKE ? ORDER BY key",
                (prefix + "%",),
            )
        ]

    def record(self, review_id):
        matches = [
            (key, receipts.read(self.connection, key))
            for key in self.keys()
            if receipts.read(self.connection, key)[1].get("review_id") == review_id
        ]
        self.assertEqual(len(matches), 1, matches)
        return matches[0]

    def cli(self, command, *extra, reviewer=None, root=None):
        """`root` runs the command in another checkout of the same repository."""
        output, errors = io.StringIO(), io.StringIO()
        args = [command, "--no-item", "--json", "--database", str(self.database), *extra]
        previous = pathlib.Path.cwd()
        with (
            patch.dict(os.environ, self.environment),
            patch.object(receipts, "identity", side_effect=AssertionError("item lookup")),
            patch.object(ship.Ship, "__init__", side_effect=AssertionError("item-bound constructor")),
            patch.object(ship, "GitHub", side_effect=AssertionError("publication client")),
            patch("sd_ship_remote.GitHub", side_effect=AssertionError("publication client")),
            patch.object(
                ship,
                "review_process",
                side_effect=reviewer or AssertionError("unexpected provider dispatch"),
            ),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            try:
                os.chdir(root or self.root)
                try:
                    code = ship.main(args)
                except SystemExit as error:
                    code = error.code
            finally:
                os.chdir(previous)
        try:
            value = json.loads(output.getvalue())
        except ValueError:
            value = {}
        return code, value, output.getvalue() + errors.getvalue()

    def success(self, command, *args, **kwargs):
        code, value, diagnostic = self.cli(command, *args, **kwargs)
        self.assertEqual(code, 0, diagnostic)
        self.assertIs(value.get("ok"), True, diagnostic)
        self.assertEqual(value.get("identity_mode"), "no-item", diagnostic)
        self.assertNotIn("item", value)
        return value

    def refused(self, command, *args, pattern, **kwargs):
        before = self.snapshot()
        code, value, diagnostic = self.cli(command, *args, **kwargs)
        self.assertEqual(code, 3, diagnostic)
        self.assertIs(value.get("ok"), False, diagnostic)
        self.assertRegex(value.get("error", ""), pattern)
        self.assertEqual(self.snapshot(), before)
        return value

    def create(self, *extra):
        return self.success(
            "review", "--create-record", "--assert-new-work", *extra
        )["review_id"]

    def file_claim(self, name, value):
        path = self.directory / name
        data = (json.dumps(value, indent=2) + "\n").encode()
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    def commit_fix(self, name, value):
        """Commit a descendant of the current head and return the head it left."""
        (self.root / name).write_text(value)
        _git(self.root, "add", name)
        _git(self.root, "commit", "-q", "-m", f"fix {name}\n\nAuthored-with: human")
        previous, self.head = self.head, _git(self.root, "rev-parse", "HEAD")
        return previous

    def report(self, *, blocking=False):
        return {
            "scope": "branch",
            "status": "blocking" if blocking else "clean",
            "subject": {"head": self.head, "base": self.base},
            "authorship_base": self.base,
            "authored_with": ["historical-author"],
            "requested_reviews": 1,
            "completed_reviews": 1,
            "reviewed_by": ["fixture"],
            "outcomes": [{"backend": "fixture", "status": "findings" if blocking else "clean"}],
            "check": {"status": "pass", "exit_code": 0},
            "findings": [
                {"path": "src.py", "line": 1, "disposition": "blocking", "summary": "fixture dispute"}
            ] if blocking else [],
        }

    def manifest(self, count, *, missing=False):
        rows = []
        for ordinal in range(1, count + 1):
            report = None if missing and ordinal == count else self.file_claim(
                f"report-{ordinal}.json", self.report(blocking=True)
            )
            rows.append({
                "ordinal": ordinal,
                "head": self.head,
                "report": report,
                "request": None,
                "prior_input": None,
                "exit_code": 124 if report is None else 1,
                "execution_error": {"kind": "watchdog_expired"} if report is None else None,
            })
        value = {"schema_version": 1, "repository": "fixture/repo", "passes": rows}
        claim = self.file_claim(f"history-{count}.json", value)
        return pathlib.Path(claim["path"]), value

    def import_history(self, count, *, missing=False):
        path, manifest = self.manifest(count, missing=missing)
        review_id = self.create(
            "--import-history", str(path), "--assert-history-complete"
        )
        return review_id, manifest

    def native_reviewer(self, review_id, *, imported=0, blocking=False, interrupt=False, duplicate=False,
                        resume=None, shape=None):
        """`resume` continues a full history without an import; `shape` adjusts
        the report the stub returns, which is how a fix verification says which
        head and which prior report it continues.
        """
        calls = []
        resume = bool(imported) if resume is None else resume
        _key, (_revision, initial) = self.record(review_id)
        initial_native = len(initial["passes"])

        def reviewer(_root, argv, *, timeout):
            self.assertGreater(timeout, 0)
            if "--explain" in argv:
                plan = {
                    "status": "explained", "requested_reviews": 1,
                    "timing": {
                        "phase_seconds": 60, "setup_seconds": 3600,
                        "execution_seconds": 3720,
                        "candidates": [{"name": "fixture", "recipient": "fixture@local"}],
                    },
                }
                return subprocess.CompletedProcess(argv, 0, json.dumps(plan), "")
            # The persisted reservation, not an in-memory list, owns this pass.
            _key, (_revision, state) = self.record(review_id)
            self.assertEqual(len(state["historical_passes"]), imported)
            self.assertEqual(len(state["passes"]), initial_native + len(calls) + 1)
            self.assertEqual(state["passes"][-1]["head"], self.head)
            self.assertNotIn("report", state["passes"][-1])
            calls.append(argv)
            if interrupt:
                raise ship.ReviewTimeout({"kind": "watchdog_expired", "allowed_seconds": timeout})
            report = self.report(blocking=blocking)
            if duplicate:
                report["findings"].append(dict(report["findings"][0]))
            if resume:
                self.assertIn("--resume-report", argv)
                self.assertNotIn("--verify-report", argv)
                self.assertNotIn("--base", argv)
                prior = pathlib.Path(argv[argv.index("--resume-report") + 1])
                aggregate = json.loads(prior.read_bytes())
                self.assertEqual(len(aggregate["history"]), imported + initial_native + len(calls) - 1)
                if imported:
                    self.assertIn("historical-author", aggregate["authored_with"])
                report["resume_report_digest"] = ship.digest(aggregate)
            if shape is not None:
                shape(report, state, argv)
            return subprocess.CompletedProcess(argv, 1 if blocking else 0, json.dumps(report), "")

        return reviewer, calls

    def evidence_snapshot(self):
        folder = self.root / ".git" / "sd-review-evidence"
        if not folder.exists():
            return {}
        return {
            str(path.relative_to(folder)): (
                hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
            )
            for path in folder.rglob("*") if path.is_file()
        }

    def blocking_proposal(self, *, duplicate=False, prepare=True):
        review_id = self.create()
        reviewer, calls = self.native_reviewer(review_id, blocking=True, duplicate=duplicate)
        code, value, diagnostic = self.cli("review", "--review-id", review_id, reviewer=reviewer)
        self.assertEqual(code, 3, diagnostic)
        self.assertIn("blocking", value["error"])
        self.assertEqual(len(calls), 1)
        before = self.snapshot()
        result = self.success(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head
        )
        self.assertEqual(self.snapshot(), before)
        proposal = result["proposal"]
        proposal.update(operator="fixture operator", authority_context="fixture assertion; not authenticated approval")
        data = b"fixture source and regression evidence\n"
        sha256 = hashlib.sha256(data).hexdigest()
        path = self.directory / "temporary-source-evidence.txt"
        path.write_bytes(data)
        self.source_evidence = path
        for row in proposal["findings"]:
            row.update(
                response_disposition="rebutted", reason="fixture evidence contradicts this claim",
                owner="", trigger="", evidence=[{"path": str(path), "sha256": sha256}],
            )
        proposal_path = self.directory / "dispositions.json"
        proposal_path.write_text(json.dumps(proposal))
        if prepare:
            result = self.success(
                "adjudicate", "--review-id", review_id, "--expected-head", self.head,
                "--dispositions-file", str(proposal_path), "--prepare-evidence",
            )
            proposal = result["proposal"]
            proposal_path.write_text(json.dumps(proposal))
            self.assertEqual(self.keys("ship-adjudication-no-item:"), [])
            path = pathlib.Path(proposal["findings"][0]["evidence"][0]["path"])
            folder = self.root / ".git" / "sd-review-evidence" / review_id
            self.assertNotEqual(path, self.source_evidence)
            self.assertTrue(path.is_relative_to(folder))
            self.assertEqual(path.resolve(strict=True), path)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(self.source_evidence.read_bytes(), data)
            self.evidence_archive = proposal["bindings"]["evidence_archive"]
            self.assertEqual(self.evidence_archive["schema_version"], 1)
            self.assertTrue(self.evidence_archive["members"])
            archive = pathlib.Path(self.evidence_archive["path"])
            self.assertTrue(archive.is_relative_to(folder))
            self.assertEqual(archive.resolve(strict=True), archive)
            self.assertEqual(archive.stat().st_nlink, 1)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), self.evidence_archive["sha256"])
        return review_id, proposal, proposal_path, path

    def accept(self, review_id, proposal_path):
        args = (
            "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path),
        )
        before = self.snapshot()
        evidence_before = self.evidence_snapshot()
        validated = self.success("adjudicate", *args)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.evidence_snapshot(), evidence_before)
        result = self.success(
            "adjudicate", *args, "--accept-dispositions", validated["acceptance_digest"]
        )
        self.assertEqual(result["acceptance_digest"], validated["acceptance_digest"])
        return result

    def test_fixture_starts_without_items_and_uses_only_local_git_transport(self):
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM item").fetchone()[0], 0)
        with patch.dict(os.environ, self.environment):
            remote = _git(self.root, "ls-remote", "origin", "refs/heads/topic")
        self.assertEqual(remote.split()[0], self.head)

    def test_create_is_provider_free_and_persists_no_item_identity(self):
        review_id = self.create()
        self.assertIsInstance(review_id, str)
        self.assertTrue(review_id)
        key, (revision, record) = self.record(review_id)
        self.assertGreater(revision, 0)
        suffix = hashlib.sha256(("fixture/repo\0" + review_id).encode()).hexdigest()
        self.assertEqual(key, "ship-review-no-item:" + suffix)
        self.assertEqual(record["identity_mode"], "no-item")
        self.assertEqual(record["repository"], "fixture/repo")
        self.assertEqual(record["branch"], "topic")
        self.assertEqual(record["passes"], [])
        self.assertEqual(record["historical_passes"], [])
        self.assertNotIn("item", record)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM item").fetchone()[0], 0)
        self.assertEqual(self.keys("ship:"), [])
        self.assertTrue(self.keys("ship-review-no-item-index:"))

    def test_create_requires_explicit_new_work_assertion(self):
        self.refused("review", "--create-record", pattern="new work|assert-new-work")

    def test_missing_record_identity_never_allocates_a_budget(self):
        self.refused("review", pattern="review-id|record identity")
        self.assertEqual(self.keys(), [])

    def test_dirty_checkout_and_empty_branch_refuse_creation(self):
        (self.root / "src.py").write_text("value = 2\n")
        self.refused("review", "--create-record", "--assert-new-work", pattern="uncommitted|clean")
        _git(self.root, "commit", "-am", "fixture edit\n\nAuthored-with: human")
        _git(self.root, "checkout", "-b", "empty", self.base)
        self.refused("review", "--create-record", "--assert-new-work", pattern="empty|nonempty|committed diff")

    def test_same_head_alias_cannot_allocate_another_budget(self):
        review_id = self.create()
        _git(self.root, "checkout", "-b", "copied-topic")
        failure = self.refused("review", "--create-record", "--assert-new-work", pattern="existing|record|owned")
        self.assertIn(review_id, failure["error"])
        self.assertEqual(len(self.keys()), 1)

    def test_distinct_committed_work_can_share_a_merge_base(self):
        first = self.create()
        _git(self.root, "checkout", "-b", "independent", self.base)
        (self.root / "other.py").write_text("other = 2\n")
        _git(self.root, "add", "other.py")
        _git(self.root, "commit", "-m", "independent work\n\nAuthored-with: human")
        second = self.create()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.keys()), 2)

    def test_import_preserves_three_spent_passes_and_exact_original_bytes(self):
        review_id, manifest = self.import_history(3, missing=True)
        _key, (_revision, record) = self.record(review_id)
        self.assertEqual(len(record["historical_passes"]), 3)
        self.assertEqual(record["passes"], [])
        for source, stored in zip(manifest["passes"], record["historical_passes"], strict=True):
            self.assertEqual(stored["ordinal"], source["ordinal"])
            self.assertEqual(stored["head"], source["head"])
            self.assertEqual(stored["exit_code"], source["exit_code"])
            if source["report"] is None:
                self.assertIsNone(stored["report"])
                self.assertEqual(stored["execution_error"], source["execution_error"])
            else:
                self.assertEqual(stored["report"]["sha256"], source["report"]["sha256"])
                self.assertEqual(
                    base64.b64decode(stored["report"]["bytes_base64"], validate=True),
                    pathlib.Path(source["report"]["path"]).read_bytes(),
                )
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="native|completed|coverage",
        )

    def test_import_requires_completeness_and_matching_raw_hash(self):
        review_id = self.create()
        path, manifest = self.manifest(1)
        self.refused("review", "--review-id", review_id, "--import-history", str(path), pattern="complete|assert-history-complete")
        manifest["passes"][0]["report"]["sha256"] = "0" * 64
        path.write_text(json.dumps(manifest))
        self.refused(
            "review", "--review-id", review_id, "--import-history", str(path),
            "--assert-history-complete", pattern="hash|SHA256|digest",
        )

    def test_import_rejects_unknown_schema_fields_and_foreign_repository(self):
        review_id = self.create()
        path, original = self.manifest(1)
        for field, value in (("schema_version", 2), ("repository", "other/repo"), ("trusted", True)):
            with self.subTest(field=field):
                path.write_text(json.dumps({**original, field: value}))
                self.refused(
                    "review", "--review-id", review_id, "--import-history", str(path),
                    "--assert-history-complete", pattern="schema|repository|field|manifest",
                )

    def test_imported_prior_input_digest_must_match_original_report(self):
        review_id = self.create()
        path, manifest = self.manifest(1)
        prior = self.file_claim("prior.json", {"findings": [], "authored_with": []})
        report = self.report()
        report["resume_report_digest"] = "0" * 64
        manifest["passes"][0].update(
            report=self.file_claim("linked-report.json", report), prior_input=prior
        )
        path.write_text(json.dumps(manifest))
        self.refused(
            "review", "--review-id", review_id, "--import-history", str(path),
            "--assert-history-complete", pattern="input|digest|reference",
        )

    def test_foreign_history_head_refuses_without_writing_import(self):
        review_id = self.create()
        self.remote.commit_on("foreign", "unrelated", files={"foreign.py": "foreign = 1\n"})
        with patch.dict(os.environ, self.environment):
            _git(self.root, "fetch", "origin", "foreign")
        foreign = _git(self.root, "rev-parse", "FETCH_HEAD")
        path, manifest = self.manifest(1)
        report = self.report()
        report["subject"]["head"] = foreign
        manifest["passes"][0].update(head=foreign, report=self.file_claim("foreign-report.json", report))
        path.write_text(json.dumps(manifest))
        self.refused(
            "review", "--review-id", review_id, "--import-history", str(path),
            "--assert-history-complete", pattern="ancestor|ancestry|history head",
        )

    def test_each_short_import_requires_explicit_native_continuation(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                # Independent databases keep each case's identity registry isolated.
                self.database = self.directory / f"history-case-{count}.db"
                initialise(self.database)
                self.connection = connect(self.database)
                self.addCleanup(self.connection.close)
                review_id, _manifest = self.import_history(count)
                self.refused("review", "--review-id", review_id, pattern="explicit|request|continuation")
                _key, (_revision, state) = self.record(review_id)
                self.assertEqual(len(state["historical_passes"]), count)
                self.assertEqual(state["passes"], [])

    def test_imported_continuation_reserves_global_fourth_pass_before_dispatch(self):
        review_id, _manifest = self.import_history(3)
        _key, (_revision, state) = self.record(review_id)
        history_digest = state["history_digest"]
        reviewer, calls = self.native_reviewer(review_id, imported=3)
        self.success(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--review-history-digest", history_digest, "--request-reason", "fixture approval assertion",
            reviewer=reviewer,
        )
        self.assertEqual(len(calls), 1)
        _key, (_revision, state) = self.record(review_id)
        self.assertEqual(len(state["historical_passes"]) + len(state["passes"]), 4)
        self.assertEqual(state["passes"][0]["additional_review_request"]["prior_history_digest"], history_digest)

    def test_stale_import_continuation_digest_refuses_without_reservation(self):
        review_id, _manifest = self.import_history(3)
        self.refused(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--review-history-digest", "0" * 64, "--request-reason", "fixture assertion",
            pattern="history|digest",
        )

    def test_one_and_two_imports_dispatch_full_history_at_global_ordinals(self):
        for count in (1, 2):
            with self.subTest(count=count):
                self.database = self.directory / f"approved-history-{count}.db"
                initialise(self.database)
                self.connection = connect(self.database)
                self.addCleanup(self.connection.close)
                review_id, _manifest = self.import_history(count)
                _key, (_revision, state) = self.record(review_id)
                prefix = state["history_digest"]
                reviewer, calls = self.native_reviewer(review_id, imported=count)
                self.success(
                    "review", "--review-id", review_id, "--additional-review-for", self.head,
                    "--review-history-digest", prefix, "--request-reason", "fixture continuation assertion",
                    reviewer=reviewer,
                )
                self.assertEqual(len(calls), 1)
                _key, (_revision, state) = self.record(review_id)
                self.assertEqual(len(state["historical_passes"]) + len(state["passes"]), count + 1)
                self.assertEqual(state["passes"][0]["additional_review_request"]["prior_history_digest"], prefix)
                self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)

    def test_rebind_after_native_continuation_preserves_original_request_binding(self):
        review_id, _manifest = self.import_history(1)
        _key, (_revision, state) = self.record(review_id)
        reviewer, _calls = self.native_reviewer(review_id, imported=1)
        self.success(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--review-history-digest", state["history_digest"], "--request-reason", "fixture assertion",
            reviewer=reviewer,
        )
        _key, (_revision, original) = self.record(review_id)
        _git(self.root, "branch", "-m", "renamed-after-native")
        self.success("review", "--review-id", review_id, "--rebind-branch", "topic")
        _key, (_revision, current) = self.record(review_id)
        self.assertEqual(current["historical_passes"], original["historical_passes"])
        self.assertEqual(current["passes"], original["passes"])
        self.assertEqual(current["history_digest"], original["history_digest"])
        self.assertGreater(current["identity_revision"], original["identity_revision"])
        reviewer, calls = self.native_reviewer(review_id, imported=1)
        self.success(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--review-history-digest", current["history_digest"], "--request-reason", "fixture renewed assertion",
            reviewer=reviewer,
        )
        self.assertEqual(len(calls), 1)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)

    def test_related_item_receipt_refuses_allocation_without_item_lookup(self):
        key = receipts.receipt_key("fixture/repo", "topic", 41)
        receipts.save(self.connection, key, 0, {
            "repository": "fixture/repo", "branch": "topic", "item": 41,
            "passes": [{"head": self.head}],
        })
        failure = self.refused("review", "--create-record", "--assert-new-work", pattern="item|item-backed")
        self.assertIn("41", failure["error"])
        self.assertIn(key, failure["error"])

    def test_malformed_item_receipt_cannot_be_treated_as_empty_history(self):
        self.connection.execute(
            "INSERT INTO state(kind,key,timestamp,body) VALUES ('checkpoint',?,?,?)",
            ("ship:unreadable", "2026-09-17T00:00:00Z", "not JSON"),
        )
        self.connection.commit()
        self.refused("review", "--create-record", "--assert-new-work", pattern="unreadable|malformed|history")

    def test_rebind_and_lifecycle_preserve_spent_history_and_invalidate_identity(self):
        review_id, _manifest = self.import_history(3)
        _key, (_revision, original) = self.record(review_id)
        _git(self.root, "branch", "-m", "renamed")
        self.refused("review", "--review-id", review_id, pattern="branch|rebind")
        self.success("review", "--review-id", review_id, "--rebind-branch", "topic")
        self.success("review", "--review-id", review_id, "--close-record", "fixture abandoned")
        self.refused("verify-review", "--review-id", review_id, "--expected-head", self.head, pattern="closed")
        self.success("review", "--review-id", review_id, "--reopen-record")
        _key, (_revision, current) = self.record(review_id)
        self.assertEqual(current["historical_passes"], original["historical_passes"])
        self.assertEqual(current["passes"], original["passes"])
        self.assertEqual(current["history_digest"], original["history_digest"])
        self.assertEqual(current["identity_revision"], original["identity_revision"] + 3)
        self.assertEqual(current["branch"], "renamed")

    def test_verify_without_native_coverage_is_read_only_and_provider_free(self):
        review_id = self.create()
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="native|completed|coverage|receipt",
        )

    def test_native_clean_clearance_is_read_only_and_creates_no_item_rows(self):
        review_id = self.create()
        reviewer, calls = self.native_reviewer(review_id)
        self.success("review", "--review-id", review_id, reviewer=reviewer)
        before = self.snapshot()
        for _ in range(2):
            self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM item").fetchone()[0], 0)

    def test_interrupted_native_reservation_survives_close_and_reopen(self):
        review_id = self.create()
        reviewer, calls = self.native_reviewer(review_id, interrupt=True)
        code, value, diagnostic = self.cli("review", "--review-id", review_id, reviewer=reviewer)
        self.assertEqual(code, 3, diagnostic)
        self.assertIn("watchdog", value["error"])
        self.assertEqual(len(calls), 1)
        _key, (_revision, interrupted) = self.record(review_id)
        self.assertEqual(len(interrupted["passes"]), 1)
        self.success("review", "--review-id", review_id, "--close-record", "fixture interruption")
        self.success("review", "--review-id", review_id, "--reopen-record")
        _key, (_revision, reopened) = self.record(review_id)
        self.assertEqual(reopened["passes"], interrupted["passes"])
        self.refused("review", "--review-id", review_id, pattern="incomplete|retry|request")

    def test_acceptance_requires_exact_digest_and_never_dispatches_a_provider(self):
        review_id, _proposal, proposal_path, _evidence = self.blocking_proposal()
        self.refused(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path), "--accept-dispositions", "0" * 64,
            pattern="digest|accept-dispositions",
        )
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="blocking|accepted dispositions",
        )
        self.accept(review_id, proposal_path)
        suffix = hashlib.sha256(("fixture/repo\0" + review_id).encode()).hexdigest()
        self.assertEqual(self.keys("ship-adjudication-no-item:"), ["ship-adjudication-no-item:" + suffix])
        self.assertEqual(self.keys("ship-adjudication:"), [])
        before = self.snapshot()
        for _ in range(2):
            self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        self.assertEqual(self.snapshot(), before)

    def test_accepted_clearance_refuses_changed_durable_evidence(self):
        review_id, _proposal, proposal_path, evidence = self.blocking_proposal()
        self.accept(review_id, proposal_path)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        evidence.write_text("changed evidence\n")
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="evidence|SHA256|digest",
        )

    def test_prepared_evidence_survives_missing_temporary_source(self):
        review_id, proposal, proposal_path, durable = self.blocking_proposal()
        source_bytes = self.source_evidence.read_bytes()
        self.source_evidence.rename(self.source_evidence.with_suffix(".unavailable"))
        self.assertFalse(self.source_evidence.exists())
        self.assertEqual(durable.read_bytes(), source_bytes)
        self.assertEqual(proposal["bindings"]["evidence_archive"], self.evidence_archive)
        self.accept(review_id, proposal_path)
        before = self.snapshot()
        evidence_before = self.evidence_snapshot()
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.evidence_snapshot(), evidence_before)

    def test_prepare_evidence_cannot_accept_dispositions_in_the_same_command(self):
        review_id, _proposal, proposal_path, _source = self.blocking_proposal(prepare=False)
        before = self.evidence_snapshot()
        self.refused(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path), "--prepare-evidence",
            "--accept-dispositions", "0" * 64, pattern="prepare-evidence|prepare|accept",
        )
        self.assertEqual(self.evidence_snapshot(), before)
        self.assertEqual(self.keys("ship-adjudication-no-item:"), [])

    def test_unprepared_temporary_evidence_cannot_validate_or_implicitly_copy(self):
        review_id, _proposal, proposal_path, _source = self.blocking_proposal(prepare=False)
        before = self.evidence_snapshot()
        self.refused(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path), pattern="prepare|durable|archive|evidence",
        )
        self.assertEqual(self.evidence_snapshot(), before)

    def test_accepted_clearance_refuses_missing_archive_without_restoring_it(self):
        review_id, _proposal, proposal_path, _durable = self.blocking_proposal()
        self.accept(review_id, proposal_path)
        archive = pathlib.Path(self.evidence_archive["path"])
        archive.rename(archive.with_suffix(archive.suffix + ".unavailable"))
        before = self.evidence_snapshot()
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="archive|evidence|cannot be read|missing",
        )
        self.assertFalse(archive.exists())
        self.assertEqual(self.evidence_snapshot(), before)

    def test_accepted_clearance_refuses_changed_archive(self):
        review_id, _proposal, proposal_path, _durable = self.blocking_proposal()
        self.accept(review_id, proposal_path)
        archive = pathlib.Path(self.evidence_archive["path"])
        archive.write_bytes(archive.read_bytes() + b"fixture archive mutation")
        before = self.evidence_snapshot()
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="archive|evidence|SHA256|digest",
        )
        self.assertEqual(self.evidence_snapshot(), before)

    def test_repeated_validate_and_clearance_open_database_read_only(self):
        review_id, _proposal, proposal_path, _durable = self.blocking_proposal()
        self.accept(review_id, proposal_path)
        before = self.snapshot()
        evidence_before = self.evidence_snapshot()
        opened = []

        def readonly(database, *, write=True):
            self.assertEqual(pathlib.Path(database), self.database)
            self.assertIs(write, False, "read-only commands must not request a writable connection")
            opened.append(database)
            return connect(database, write=False)

        with patch("sd_db.database.connect", side_effect=readonly):
            for _ in range(2):
                self.success(
                    "adjudicate", "--review-id", review_id, "--expected-head", self.head,
                    "--dispositions-file", str(proposal_path),
                )
                self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        self.assertEqual(len(opened), 4)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.evidence_snapshot(), evidence_before)

    def test_accepted_clearance_refuses_changed_head(self):
        review_id, _proposal, proposal_path, _evidence = self.blocking_proposal()
        self.accept(review_id, proposal_path)
        (self.root / "src.py").write_text("value = 2\n")
        _git(self.root, "commit", "-am", "later change\n\nAuthored-with: human")
        changed = _git(self.root, "rev-parse", "HEAD")
        for expected in (self.head, changed):
            with self.subTest(expected=expected):
                self.refused(
                    "verify-review", "--review-id", review_id, "--expected-head", expected,
                    pattern="head|HEAD|review|receipt",
                )

    def test_invalid_or_incomplete_dispositions_cannot_clear_blockers(self):
        review_id, original, proposal_path, _evidence = self.blocking_proposal()
        for mutation in ("missing", "addressed", "parked_without_owner", "changed_finding"):
            proposal = json.loads(json.dumps(original))
            if mutation == "missing":
                proposal["findings"].clear()
            elif mutation == "addressed":
                proposal["findings"][0]["response_disposition"] = "addressed"
            elif mutation == "parked_without_owner":
                proposal["findings"][0]["response_disposition"] = "parked"
            else:
                proposal["findings"][0]["raw_finding"]["summary"] = "rewritten raw finding"
            proposal_path.write_text(json.dumps(proposal))
            with self.subTest(mutation=mutation):
                self.refused(
                    "adjudicate", "--review-id", review_id, "--expected-head", self.head,
                    "--dispositions-file", str(proposal_path), pattern="finding|risk|disposition|owner",
                )

    def test_duplicate_blockers_require_separate_response_indices(self):
        review_id, proposal, proposal_path, _evidence = self.blocking_proposal(duplicate=True)
        self.assertEqual([row["index"] for row in proposal["findings"]], [1, 2])
        self.assertEqual(proposal["findings"][0]["finding_digest"], proposal["findings"][1]["finding_digest"])
        incomplete = json.loads(json.dumps(proposal))
        incomplete["findings"].pop()
        proposal_path.write_text(json.dumps(incomplete))
        self.refused(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path), pattern="finding|separate|disposition",
        )
        proposal_path.write_text(json.dumps(proposal))
        self.accept(review_id, proposal_path)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)


    def test_schema_drift_refuses_creation_dispatch_and_clearance(self):
        """A layout this adapter was not tested against stops every path.

        The guard has to sit on the read paths too. Enumeration alone would
        leave dispatch and clearance reading a table whose shape nothing
        checked, which is the case a schema change actually produces.
        """

        review_id = self.create()
        reviewer, calls = self.native_reviewer(review_id)
        self.success("review", "--review-id", review_id, reviewer=reviewer)
        drifted = dict(no_item.SCHEMA_CONTRACT, columns=(*no_item.SCHEMA_CONTRACT["columns"], "absent_column"))
        with patch.object(no_item, "SCHEMA_CONTRACT", drifted):
            for command in (
                ("review", "--create-record", "--assert-new-work"),
                ("review", "--review-id", review_id),
                ("verify-review", "--review-id", review_id, "--expected-head", self.head),
            ):
                with self.subTest(command=command[0]):
                    failure = self.refused(*command, pattern="layout|schema")
                    self.assertIn("absent_column", failure["error"])
        self.assertEqual(len(calls), 1)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)

    def test_a_failed_enumeration_query_is_never_an_empty_history(self):
        class FailingQueries:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, statement, *parameters):
                if "LIKE" in statement:
                    raise sqlite3.DatabaseError("fixture enumeration failure")
                return self.connection.execute(statement, *parameters)

            def __getattr__(self, name):
                return getattr(self.connection, name)

        def failing(database, *, write=True):
            return FailingQueries(connect(database, write=write))

        with patch("sd_db.database.connect", side_effect=failing):
            failure = self.refused(
                "review", "--create-record", "--assert-new-work", pattern="query failed|empty history"
            )
        self.assertIn("fixture enumeration failure", failure["error"])
        self.assertEqual(self.keys(), [])

    def test_a_malformed_no_item_record_refuses_dispatch_and_clearance(self):
        review_id = self.create()
        key, _record = self.record(review_id)
        self.connection.execute(
            "INSERT INTO state(kind,key,timestamp,body) VALUES ('checkpoint',?,?,?)",
            (key, "2026-09-18T00:00:00Z", "not JSON"),
        )
        self.connection.commit()
        # No reviewer is supplied, so any provider dispatch raises instead.
        self.refused("review", "--review-id", review_id, pattern="unreadable|malformed|receipt")
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="unreadable|malformed|receipt",
        )

    def test_a_forged_item_receipt_under_the_no_item_key_cannot_clear(self):
        """The expected key is not the authority. The bound identity is.

        A copy placed under the key this mode reads is the whole attack, so the
        forgery keeps a recomputed `proposal_digest`: the bookkeeping check
        passes and only the identity bindings stand in its way.
        """

        review_id, _proposal, proposal_path, _durable = self.blocking_proposal()
        self.accept(review_id, proposal_path)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        key = no_item.no_item_acceptance_key("fixture/repo", review_id)
        revision, receipt = receipts.read(self.connection, key)
        forged = json.loads(json.dumps(receipt))
        bindings = forged["proposal"]["bindings"]
        for name in ("identity_mode", "review_id", "identity_revision", "schema_version"):
            bindings.pop(name)
        bindings["item"] = 41
        forged["proposal_digest"] = ship.sd_ship_dispositions.digest(forged["proposal"])
        receipts.save(self.connection, key, revision, forged)
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="bind|identity|item",
        )

    def test_each_review_manifest_member_mutation_refuses_no_item_clearance(self):
        """The manifest guards both modes, so both modes are measured.

        Enumerated from the manifest rather than listed here, so a gate added
        to it is covered the moment it joins.
        """

        review_id = self.create()
        reviewer, calls = self.native_reviewer(review_id)
        self.success("review", "--review-id", review_id, reviewer=reviewer)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        original = pathlib.Path.read_bytes
        for name in bindings.REVIEW_TOOL_FILES:
            target = bindings.BIN / name

            def changed(path, target=target):
                return original(path) + (b"changed" if path == target else b"")

            with self.subTest(name=name), patch.object(pathlib.Path, "read_bytes", changed):
                self.refused(
                    "verify-review", "--review-id", review_id, "--expected-head", self.head,
                    pattern="tools or repository policy changed",
                )
        self.assertEqual(len(calls), 1)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)

    def test_relocated_durable_evidence_needs_its_bytes_back_or_a_new_approval(self):
        """A path is not the evidence. The bytes at that path are.

        Relocation is the ordinary accident: a cleanup moves a file. Clearance
        must refuse, the original approval must not carry over to the moved
        copy, and returning the exact bytes must restore it.
        """

        review_id, _proposal, proposal_path, durable = self.blocking_proposal()
        accepted = self.accept(review_id, proposal_path)
        moved = durable.with_name(durable.name + "-relocated")
        durable.rename(moved)
        self.refused(
            "verify-review", "--review-id", review_id, "--expected-head", self.head,
            pattern="evidence|archive|member|cannot be read",
        )
        self.refused(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path),
            "--accept-dispositions", accepted["acceptance_digest"],
            pattern="evidence|archive|member|cannot be read",
        )
        moved.rename(durable)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        # A readable copy with the right bytes is still not the durable archive,
        # so pointing the proposal at the relocated file cannot stand in for it.
        outside = self.directory / "relocated-evidence.txt"
        outside.write_bytes(durable.read_bytes())
        rewritten = json.loads(proposal_path.read_text())
        for row in rewritten["findings"]:
            for entry in row["evidence"]:
                entry["path"] = str(outside)
        relocated_file = self.directory / "relocated-dispositions.json"
        relocated_file.write_text(json.dumps(rewritten))
        self.refused(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(relocated_file), pattern="durable|archive|member",
        )

    def test_capacity_limits_refuse_actionably_and_keep_every_record_readable(self):
        """A limit refuses the operation. It never prunes to make room.

        Both limits are lowered rather than reached, because a test that writes
        five thousand receipts measures patience, not the refusal.
        """

        for item in (41, 42):
            receipts.save(
                self.connection, receipts.receipt_key("other/repo", f"topic-{item}", item), 0,
                {"repository": "other/repo", "branch": f"topic-{item}", "item": item, "passes": []},
            )
        for name, limit in (("RECEIPT_LIMIT", 1), ("INDEX_LIMIT", 0)):
            with self.subTest(limit=name), patch.object(no_item, name, limit):
                failure = self.refused(
                    "review", "--create-record", "--assert-new-work", pattern="limit|exceed|reached",
                )
                self.assertIn(str(limit), failure["error"])
                self.assertIn("readable", failure["error"])
        # Nothing was deleted or hidden: allocation still works, and the
        # unrelated receipts still read exactly as they were written.
        review_id = self.create()
        _key, (_revision, state) = self.record(review_id)
        self.assertEqual(state["review_id"], review_id)
        for item in (41, 42):
            key = receipts.receipt_key("other/repo", f"topic-{item}", item)
            self.assertEqual(receipts.read(self.connection, key)[1]["item"], item)

    def test_accepted_clearance_rejects_every_mutation_of_imported_history(self):
        """Imported records cannot be added, dropped, reordered or rewritten.

        Each forgery recomputes the stored combined digest, so the cheap
        self-consistency guard cannot be what refuses. Three separate bindings
        do: the native request's exact combined prior history, the full-branch
        coverage digest, and each retained report's own SHA256. Removing any
        one of the three still refuses every mutation here except a reordering,
        which the first binding alone catches.
        """

        review_id, _manifest = self.import_history(2)
        _key, (_revision, state) = self.record(review_id)
        reviewer, calls = self.native_reviewer(review_id, imported=2)
        self.success(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--review-history-digest", state["history_digest"],
            "--request-reason", "fixture continuation assertion", reviewer=reviewer,
        )
        self.assertEqual(len(calls), 1)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        key, (_revision, original) = self.record(review_id)
        for mutation in ("added", "removed", "reordered", "content"):
            forged = json.loads(json.dumps(original))
            records = forged["historical_passes"]
            if mutation == "added":
                records.append(json.loads(json.dumps(records[-1])))
            elif mutation == "removed":
                records.pop()
            elif mutation == "reordered":
                records.reverse()
            else:
                records[0]["report"]["sha256"] = "0" * 64
            forged["history_digest"] = no_item.combined_digest(forged)
            with self.subTest(mutation=mutation):
                receipts.save(self.connection, key, receipts.read(self.connection, key)[0], forged)
                self.refused(
                    "verify-review", "--review-id", review_id, "--expected-head", self.head,
                    pattern="history|coverage|SHA256|digest",
                )
                receipts.save(self.connection, key, receipts.read(self.connection, key)[0], original)
                self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)

    def test_a_native_only_record_verifies_its_fix_and_clears_a_requested_third_pass(self):
        """The control case with no imported history at all.

        Pass one is the code review, pass two the fix verification of the head
        it produced, and pass three an explicitly requested continuation. The
        third pass is where the record used to spend a paid review and then
        refuse its own clearance: the request carries the combined digest that
        `history_digest` writes, and the native-only reader compared it against
        the raw native prefix instead. The last two assertions are that
        mismatch, stated as the two formats that are not each other.
        """

        review_id = self.create()
        reviewer, calls = self.native_reviewer(review_id, blocking=True)
        code, value, diagnostic = self.cli("review", "--review-id", review_id, reviewer=reviewer)
        self.assertEqual(code, 3, diagnostic)
        self.assertIn("blocking", value["error"])

        reviewed = self.commit_fix("fix.py", "value = 2\n")

        def verification(report, state, argv):
            self.assertIn("--verify-report", argv)
            self.assertEqual(argv[argv.index("--base") + 1], reviewed)
            report["subject"]["base"] = reviewed
            report["verification_report_digest"] = ship.digest(state["passes"][0]["report"])

        reviewer, verify_calls = self.native_reviewer(review_id, shape=verification)
        self.success("review", "--review-id", review_id, reviewer=reviewer)
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)

        # Two passes are spent, so a third head needs an explicit request, and
        # the renewal digest belongs to the fourth pass onwards.
        self.commit_fix("more.py", "value = 3\n")
        self.refused("review", "--review-id", review_id, pattern="spent|explicit new request")
        _key, (_revision, state) = self.record(review_id)
        self.refused(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--request-reason", "fixture continuation assertion",
            "--review-history-digest", state["history_digest"], pattern="renews only after",
        )
        reviewer, third_calls = self.native_reviewer(review_id, resume=True)
        self.success(
            "review", "--review-id", review_id, "--additional-review-for", self.head,
            "--request-reason", "fixture continuation assertion", reviewer=reviewer,
        )
        cleared = self.success("verify-review", "--review-id", review_id, "--expected-head", self.head)
        self.assertEqual([len(calls), len(verify_calls), len(third_calls)], [1, 1, 1])
        self.assertEqual(cleared["spent_passes"], 3)

        _key, (_revision, state) = self.record(review_id)
        passes = state["passes"]
        request = passes[2]["additional_review_request"]
        self.assertEqual(request["prior_history_digest"], no_item.combined_digest(state, passes[:2]))
        self.assertNotEqual(request["prior_history_digest"], ship.digest(passes[:2]))

    def test_a_linked_worktree_keeps_its_durable_evidence_in_the_common_git_directory(self):
        """A linked worktree's `.git` is a file, so no path can be built from it.

        Preparation asks Git where the repository is. The archive then lands in
        the directory every worktree of this repository shares, which is the
        scope the record itself has, and acceptance reads it from the worktree
        that wrote it.
        """

        linked = self.directory / "linked"
        _git(self.root, "worktree", "add", "-q", "-b", "linked", str(linked), "topic")
        self.addCleanup(_git, self.root, "worktree", "remove", "--force", str(linked))
        self.assertTrue((linked / ".git").is_file())

        review_id = self.success(
            "review", "--create-record", "--assert-new-work", root=linked
        )["review_id"]
        reviewer, calls = self.native_reviewer(review_id, blocking=True)
        code, value, diagnostic = self.cli("review", "--review-id", review_id, reviewer=reviewer, root=linked)
        self.assertEqual(code, 3, diagnostic)
        self.assertIn("blocking", value["error"])
        self.assertEqual(len(calls), 1)

        data = b"fixture evidence written from a linked worktree\n"
        source = self.directory / "linked-evidence.txt"
        source.write_bytes(data)
        template = self.success(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head, root=linked
        )["proposal"]
        template.update(operator="fixture operator", authority_context="fixture assertion; not authenticated approval")
        for row in template["findings"]:
            row.update(
                response_disposition="rebutted", reason="fixture evidence contradicts this claim",
                owner="", trigger="", evidence=[{"path": str(source), "sha256": hashlib.sha256(data).hexdigest()}],
            )
        proposal_path = self.directory / "linked-dispositions.json"
        proposal_path.write_text(json.dumps(template))
        prepared = self.success(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path), "--prepare-evidence", root=linked,
        )["proposal"]
        proposal_path.write_text(json.dumps(prepared))

        common = self.root / ".git" / "sd-review-evidence" / review_id
        archive = pathlib.Path(prepared["bindings"]["evidence_archive"]["path"])
        member = pathlib.Path(prepared["findings"][0]["evidence"][0]["path"])
        for path in (archive, member):
            self.assertTrue(path.is_relative_to(common), path)
            self.assertFalse(path.is_relative_to(linked), path)
            self.assertEqual(path.resolve(strict=True), path)
        self.assertEqual(member.read_bytes(), data)
        # The evidence is inside the Git directory, so the worktree that wrote
        # it stays clean and acceptance can still read the exact same bytes.
        self.assertEqual(_git(linked, "status", "--porcelain", "--untracked-files=all"), "")
        validated = self.success(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path), root=linked,
        )
        self.success(
            "adjudicate", "--review-id", review_id, "--expected-head", self.head,
            "--dispositions-file", str(proposal_path),
            "--accept-dispositions", validated["acceptance_digest"], root=linked,
        )
        self.success("verify-review", "--review-id", review_id, "--expected-head", self.head, root=linked)

    def test_a_merged_record_closes_and_releases_the_branch_it_no_longer_needs(self):
        """A record outlives its branch diff, and closing it is how it ends.

        Once the work reaches the refreshed default branch, `base..head` is
        empty. That is the allocation and dispatch rule, and it used to run
        during identity lookup, which left a completed record permanently
        active and holding its branch alias against every later record.
        """

        review_id = self.create()
        branch_index = no_item.index_key("fixture/repo", "branch", "topic")
        self.assertEqual(receipts.read(self.connection, branch_index)[1]["review_id"], review_id)
        _git(self.remote.path, "update-ref", "refs/heads/main", self.head)

        # The eligibility rule itself is unchanged: no diff, no new record and
        # no further review of this one.
        self.refused("review", "--create-record", "--assert-new-work", pattern="committed diff")
        self.refused("review", "--review-id", review_id, pattern="committed diff")
        self.success("review", "--review-id", review_id, "--close-record", "fixture work merged")
        _key, (_revision, state) = self.record(review_id)
        self.assertEqual(state["lifecycle"], "closed")
        self.assertEqual(state["closed"]["reason"], "fixture work merged")
        self.assertIsNone(receipts.read(self.connection, branch_index)[1]["review_id"])
        self.success("review", "--review-id", review_id, "--reopen-record")
        self.assertEqual(receipts.read(self.connection, branch_index)[1]["review_id"], review_id)


if __name__ == "__main__":
    unittest.main()
