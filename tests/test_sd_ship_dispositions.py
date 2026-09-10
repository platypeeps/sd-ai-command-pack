"""Operator adjudication uses local evidence and keeps raw external reviews intact."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import unittest
from unittest.mock import patch

from tests import test_sd_ship as fixture

ship = fixture.ship


class DispositionTests(unittest.TestCase):
    setUp = fixture.ShipCase.setUp
    args = fixture.ShipCase.args
    operation = fixture.ShipCase.operation
    prepare = fixture.ShipCase.prepare
    merge = fixture.ShipCase.merge
    cli = fixture.ShipCase.cli

    def blocked(self):
        provider = self.programs / "review-fixture"
        payload = {
            "type": "result",
            "subtype": "success",
            "structured_output": {
                "findings": [
                    {
                        "path": "src.py",
                        "line": 1,
                        "severity": "high",
                        "family": "correctness",
                        "summary": "fixture disputed finding",
                    }
                ]
            },
        }
        provider.write_text(
            "#!/usr/bin/env python3\nprint(" + repr(json.dumps(payload)) + ")\n"
        )
        with self.assertRaises(ship.Refusal):
            self.prepare()
        self.head = fixture._git(self.root, "rev-parse", "HEAD")
        self.raw = json.loads(json.dumps(self.operation().state["passes"]))
        self.evidence = self.directory / "evidence.txt"
        self.evidence.write_text("source and regression evidence for this fixture")
        self.proposal_file = self.directory / "dispositions.json"

    def command(self, *extra):
        return self.cli("adjudicate", "--expected-head", self.head, *extra)

    def filled(self):
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        proposal = json.loads(result.stdout)["proposal"]
        proposal.update(
            operator="fixture operator",
            authority_context="explicit fixture acceptance; not authenticated",
        )
        for row in proposal["findings"]:
            row.update(
                response_disposition="rebutted",
                reason="the retained fixture evidence contradicts the claim",
                evidence=[
                    {
                        "path": str(self.evidence),
                        "sha256": hashlib.sha256(
                            self.evidence.read_bytes()
                        ).hexdigest(),
                    }
                ],
            )
        self.proposal_file.write_text(json.dumps(proposal))
        return proposal

    def accepted(self, proposal=None):
        proposal = self.filled() if proposal is None else proposal
        self.proposal_file.write_text(json.dumps(proposal))
        verified = self.command("--dispositions-file", str(self.proposal_file))
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        acceptance_digest = json.loads(verified.stdout)["acceptance_digest"]
        result = self.command(
            "--dispositions-file",
            str(self.proposal_file),
            "--accept-dispositions",
            acceptance_digest,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return proposal

    def rejected_proposal(self, proposal):
        self.proposal_file.write_text(json.dumps(proposal))
        before = list(self.connection.execute("SELECT * FROM state"))
        result = self.command("--dispositions-file", str(self.proposal_file))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(list(self.connection.execute("SELECT * FROM state")), before)

    def test_blank_template_missing_explicit_acceptance_and_wrong_digest_refuse(self):
        self.blocked()
        blank = json.loads(self.command().stdout)["proposal"]
        self.rejected_proposal(blank)
        self.filled()
        before = list(self.connection.execute("SELECT * FROM state"))
        for args in (
            ("--accept-dispositions", "0" * 64),
            (
                "--dispositions-file",
                str(self.proposal_file),
                "--accept-dispositions",
                "0" * 64,
            ),
            ("--additional-review-for", self.head),
        ):
            with self.subTest(args=args):
                result = self.command(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    list(self.connection.execute("SELECT * FROM state")), before
                )
        with (
            self.assertRaises(ship.Refusal),
            patch.object(
                ship,
                "review_process",
                side_effect=AssertionError("unaccepted dispatch"),
            ),
        ):
            self.prepare()

    def test_only_explicit_risk_with_owner_trigger_or_rebuttal_is_accepted(self):
        self.blocked()
        proposal = self.filled()
        for value in ("addressed", "unresolved", "", "accepted"):
            trial = json.loads(json.dumps(proposal))
            trial["findings"][0]["response_disposition"] = value
            self.rejected_proposal(trial)
        for row in proposal["findings"]:
            row.update(
                response_disposition="parked",
                owner="fixture owner",
                trigger="revisit on the named scope change",
            )
        for field in ("owner", "trigger"):
            trial = json.loads(json.dumps(proposal))
            trial["findings"][0][field] = ""
            self.rejected_proposal(trial)
        self.accepted(proposal)
        with patch.object(
            ship,
            "review_process",
            side_effect=AssertionError("risk acceptance dispatched"),
        ):
            self.prepare()

    def test_duplicate_occurrences_need_distinct_indices_and_unchanged_raw_findings(
        self,
    ):
        self.blocked()
        op = self.operation()
        first = op.state["passes"][-1]["report"]["findings"][0]
        op.state["passes"][-1]["report"]["findings"] = [first, dict(first)]
        op.save()
        proposal = self.filled()
        self.assertEqual([row["index"] for row in proposal["findings"]], [1, 2])
        self.assertEqual(
            proposal["findings"][0]["finding_digest"],
            proposal["findings"][1]["finding_digest"],
        )
        for kind in ("missing", "duplicate", "boolean", "raw", "digest"):
            trial = json.loads(json.dumps(proposal))
            if kind == "missing":
                trial["findings"].pop()
            elif kind == "duplicate":
                trial["findings"][1] = trial["findings"][0]
            elif kind == "boolean":
                trial["findings"][0]["index"] = True
            elif kind == "raw":
                trial["findings"][0]["raw_finding"]["summary"] = "rewritten"
            else:
                trial["findings"][0]["finding_digest"] = "0" * 64
            with self.subTest(kind=kind):
                self.rejected_proposal(trial)

    def test_incomplete_transport_counts_status_and_check_cannot_be_waived(self):
        self.blocked()
        original = self.operation().state
        for kind in (
            "depth",
            "false_count",
            "duplicate_backend",
            "reviewed_by",
            "check",
            "check_exit",
            "transport",
            "timeout",
            "status",
            "scope",
        ):
            state = json.loads(json.dumps(original))
            last = state["passes"][-1]
            report = last["report"]
            if kind == "depth":
                report["completed_reviews"] = 0
            elif kind == "false_count":
                report["outcomes"] = report["outcomes"][:1]
            elif kind == "duplicate_backend":
                report["outcomes"][1]["backend"] = report["outcomes"][0]["backend"]
            elif kind == "reviewed_by":
                report["reviewed_by"] = ["invented"]
            elif kind == "check":
                report["check"]["status"] = "fail"
            elif kind == "check_exit":
                report["check"]["exit_code"] = 1
            elif kind == "transport":
                last["exit_code"] = 3
            elif kind == "timeout":
                last["execution_error"] = {"kind": "watchdog_expired"}
            elif kind == "status":
                report["status"] = "unavailable"
            else:
                report["scope"] = "worktree"
            self.operation().save(**state)
            with self.subTest(kind=kind):
                self.assertEqual(self.command().returncode, 3)
        self.operation().save(**original)

    def test_failed_primary_with_real_completed_fallback_still_qualifies(self):
        self.blocked()
        op = self.operation()
        op.state["passes"][-1]["report"]["outcomes"].insert(
            0, {"backend": "primary", "status": "rate_limited"}
        )
        op.save()
        self.accepted()
        with patch.object(
            ship, "review_process", side_effect=AssertionError("fallback dispatched")
        ):
            self.prepare()

    def test_changed_head_and_dirty_tracked_source_refuse(self):
        self.blocked()
        self.accepted()
        (self.root / "src.py").write_text("changed after acceptance")
        with self.assertRaises(ship.Refusal):
            self.operation().check_review(self.head)
        fixture._git(self.root, "restore", "src.py")
        fixture._git(
            self.root,
            "commit",
            "--allow-empty",
            "-m",
            "changed head\n\nAuthored-with: human",
        )
        self.assertEqual(self.command().returncode, 3)

    def test_later_reportless_pass_and_changed_report_invalidate_acceptance(self):
        self.blocked()
        self.accepted()
        self.prepare()
        original = self.operation().state
        for kind in ("report", "history", "reportless"):
            changed = json.loads(json.dumps(original))
            if kind == "report":
                changed["passes"][-1]["report"]["findings"][0]["summary"] = (
                    "new finding"
                )
            elif kind == "history":
                changed["passes"][0]["started_at"] = "changed history"
            else:
                changed["passes"].append(
                    {"head": self.head, "started_at": "later", "base": None}
                )
            self.operation().save(**changed)
            with self.subTest(kind=kind), self.assertRaises(ship.Refusal):
                self.operation().check_review(self.head)
        self.operation().save(**original)

    def test_acceptance_is_separate_append_only_and_does_not_confuse_for_item(self):
        self.blocked()
        original = list(
            self.connection.execute(
                "SELECT id,body FROM state WHERE kind='checkpoint' ORDER BY id"
            )
        )
        self.accepted()
        current = list(
            self.connection.execute(
                "SELECT id,body FROM state WHERE kind='checkpoint' ORDER BY id"
            )
        )
        self.assertEqual(current[: len(original)], original)
        self.assertEqual(len(current), len(original) + 1)
        resolved = fixture.receipts.for_item(
            self.connection, self.remote.slug, self.item, "topic"
        )
        self.assertEqual(resolved[2]["passes"], self.raw)
        self.assertEqual(self.operation().state["passes"], self.raw)

    def test_reacceptance_requires_prepare_refresh_before_merge(self):
        self.blocked()
        proposal = self.accepted()
        self.prepare()
        previous = self.operation().state["review_clearance"]
        proposal["authority_context"] = "a new explicit fixture decision"
        self.accepted(proposal)
        with self.assertRaisesRegex(ship.Refusal, "prepare again"):
            self.merge()
        with patch.object(
            ship, "review_process", side_effect=AssertionError("refresh dispatched")
        ):
            self.prepare()
        self.assertNotEqual(self.operation().state["review_clearance"], previous)
        self.assertEqual(self.merge()["phase"], "merged")

    def test_preview_uses_readonly_connection_without_lock_or_write_transaction(self):
        from sd_db import database

        self.blocked()
        args = [
            "adjudicate",
            "--item",
            str(self.item),
            "--expected-head",
            self.head,
            "--database",
            str(self.database),
            "--json",
        ]
        with (
            patch.object(database, "connect", wraps=database.connect) as connect,
            patch.object(ship.sd_lib, "repo_root", return_value=self.root),
            patch.object(
                fixture.receipts,
                "repository_lock",
                side_effect=AssertionError("readonly lock"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(ship.main(args), 0)
        self.assertIs(connect.call_args.kwargs["write"], False)

    def test_acceptance_checks_source_cas_inside_the_write_transaction(self):
        self.blocked()
        self.filled()
        validated = json.loads(
            self.command("--dispositions-file", str(self.proposal_file)).stdout
        )["acceptance_digest"]
        op = self.operation(
            "adjudicate",
            "--expected-head",
            self.head,
            "--dispositions-file",
            str(self.proposal_file),
            "--accept-dispositions",
            validated,
        )
        original_read = fixture.receipts.read
        observations = []

        def watched(connection, key):
            if key == op.key:
                observations.append(connection.in_transaction)
            return original_read(connection, key)

        with patch.object(fixture.receipts, "read", side_effect=watched):
            op.adjudicate()
        self.assertEqual(observations, [True])
        stale = self.operation(
            "adjudicate",
            "--expected-head",
            self.head,
            "--dispositions-file",
            str(self.proposal_file),
            "--accept-dispositions",
            validated,
        )
        self.operation().save(warnings=["concurrent phase update"])
        before = list(self.connection.execute("SELECT * FROM state"))
        with self.assertRaisesRegex(ship.Refusal, "changed before"):
            stale.adjudicate()
        self.assertEqual(list(self.connection.execute("SELECT * FROM state")), before)

    def test_missing_changed_directory_symlink_and_hardlinked_evidence_refuse(self):
        self.blocked()
        proposal = self.filled()
        original = self.evidence.read_bytes()
        for kind in ("changed", "missing", "directory", "symlink", "hardlink"):
            self.evidence.unlink(missing_ok=True)
            if kind == "changed":
                self.evidence.write_text("changed")
            elif kind == "directory":
                self.evidence.mkdir()
            elif kind == "symlink":
                self.evidence.symlink_to(self.root / "src.py")
            elif kind == "hardlink":
                os.link(self.root / "src.py", self.evidence)
            with self.subTest(kind=kind):
                self.rejected_proposal(proposal)
            if self.evidence.is_dir():
                self.evidence.rmdir()
            else:
                self.evidence.unlink(missing_ok=True)
            self.evidence.write_bytes(original)

    def test_review_tool_adjudicator_tool_and_policy_changes_refuse(self):
        self.blocked()
        self.accepted()
        self.prepare()
        with patch.object(ship, "binding", return_value="different review tools"):
            with self.assertRaises(ship.Refusal):
                self.operation().check_review(self.head)
        original_read = pathlib.Path.read_bytes
        for name in (
            "sd-ship",
            "sd_ship_dispositions.py",
            "sd_ship_remote.py",
            "SKILL.md",
            "sd-planning-adversarial-review.md",
        ):

            def changed(path, name=name):
                value = original_read(path)
                return value + b"changed" if path.name == name else value

            with (
                self.subTest(name=name),
                patch.object(pathlib.Path, "read_bytes", changed),
                self.assertRaises(ship.Refusal),
            ):
                self.operation().check_review(self.head)

    def test_typed_json_identity_changes_refuse(self):
        self.blocked()
        proposal = self.filled()
        for field, value in (
            ("line", True),
            ("line", 1.0),
            ("item", float(self.item)),
            ("item", True),
        ):
            trial = json.loads(json.dumps(proposal))
            if field == "line":
                trial["findings"][0]["raw_finding"][field] = value
            else:
                trial["bindings"][field] = value
            with self.subTest(field=field, value=value):
                self.rejected_proposal(trial)

    def test_four_spent_passes_can_reuse_exact_complete_report_without_another_review(
        self,
    ):
        self.blocked()
        fixture._git(
            self.root,
            "commit",
            "--allow-empty",
            "-m",
            "fixture fix attempt\n\nAuthored-with: human",
        )
        self.head = fixture._git(self.root, "rev-parse", "HEAD")
        with self.assertRaises(ship.Refusal):
            self.prepare()
        for count in (2, 3):
            arguments = [
                "--additional-review-for",
                self.head,
                "--request-reason",
                "fixture explicit review",
            ]
            if count == 3:
                arguments += [
                    "--review-history-digest",
                    ship.digest(self.operation().state["passes"]),
                ]
            with self.assertRaises(ship.Refusal):
                self.prepare(*arguments)
        previous = json.loads(json.dumps(self.operation().state["passes"]))
        self.assertEqual(len(previous), 4)
        self.assertIsNone(self.operation().state["reviewed_head"])
        self.accepted()
        with patch.object(
            ship,
            "review_process",
            side_effect=AssertionError("fifth review dispatched"),
        ):
            self.prepare()
        self.assertEqual(self.operation().state["passes"], previous)

    def test_unreadable_oversized_and_raced_file_reads_refuse(self):
        evidence = self.directory / "read-evidence.txt"
        evidence.write_text("original evidence")
        read = ship.sd_ship_dispositions.read_file
        with self.assertRaisesRegex(ship.Refusal, "bounded input"):
            read(evidence, 4)
        with patch.object(
            os, "open", side_effect=PermissionError(13, "fixture denied")
        ):
            with self.assertRaisesRegex(ship.Refusal, "cannot be read"):
                read(evidence, 1024)
        original_stat = os.fstat
        calls = []

        def race(descriptor):
            calls.append(descriptor)
            if len(calls) == 2:
                evidence.write_text("changed during read")
            return original_stat(descriptor)

        with patch.object(os, "fstat", side_effect=race):
            with self.assertRaisesRegex(ship.Refusal, "changed during"):
                read(evidence, 1024)

    def test_duplicate_json_keys_and_oversized_proposals_refuse(self):
        self.blocked()
        proposal = self.filled()
        duplicate = json.dumps(proposal).replace(
            '"schema_version": 1', '"schema_version": 2, "schema_version": 1'
        )
        for data in (
            duplicate,
            "x" * (ship.sd_ship_dispositions.MAX_PROPOSAL_BYTES + 1),
        ):
            self.proposal_file.write_text(data)
            before = list(self.connection.execute("SELECT * FROM state"))
            result = self.command("--dispositions-file", str(self.proposal_file))
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertEqual(
                list(self.connection.execute("SELECT * FROM state")), before
            )

    def test_template_and_validation_do_not_write_receipts(self):
        self.blocked()
        before = list(self.connection.execute("SELECT * FROM state"))
        self.filled()
        result = self.command("--dispositions-file", str(self.proposal_file))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(
            json.loads(result.stdout)["acceptance_digest"], r"^[0-9a-f]{64}$"
        )
        self.assertEqual(list(self.connection.execute("SELECT * FROM state")), before)

    def test_explicit_acceptance_reuses_blocking_review_without_provider_dispatch(self):
        self.blocked()
        self.filled()
        verified = self.command("--dispositions-file", str(self.proposal_file))
        digest = json.loads(verified.stdout)["acceptance_digest"]
        result = self.command(
            "--dispositions-file",
            str(self.proposal_file),
            "--accept-dispositions",
            digest,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with patch.object(
            ship,
            "review_process",
            side_effect=AssertionError("provider dispatch after adjudication"),
        ):
            self.assertEqual(self.prepare()["phase"], "ready_to_send")
        self.assertEqual(self.operation().state["passes"], self.raw)
        self.assertEqual(
            self.operation().state["review_clearance"]["kind"], "adjudicated"
        )
        self.assertEqual(self.merge()["phase"], "merged")


if __name__ == "__main__":
    unittest.main()
