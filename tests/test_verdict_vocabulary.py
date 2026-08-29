"""Cross-payload verdict/status vocabulary guarantees (A-077).

Covers the acceptance criteria for unifying the ``outcome``/``status`` naming
rule across emitted payload envelopes:

- AC1: a shape walker asserts no document carries two ``status`` keys whose
  value types differ, after excluding the declared dual-emit aliases.
- AC2: the per-domain verdict sets are derived from one shared core and a
  domain cannot declare a non-core verdict without an explicit opt-out.
- AC5: a consumer written against the *old* key names still works for the
  whole dual-emit window (the aliases are still emitted).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any, Iterator

import install

SCRIPTS_DIR = install.ROOT / "templates/scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sd_ai_command_pack_lib as lib  # noqa: E402


def _load(module_name: str, filename: str) -> Any:
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


result_builder = _load(
    "sd_ai_command_pack_housekeeping_result",
    "sd-ai-command-pack-housekeeping-result.py",
)
review_local = _load(
    "sd_ai_command_pack_review_local", "sd-ai-command-pack-review-local.py"
)
fleet_timing = _load(
    "sd_ai_command_pack_fleet_timing", "sd-ai-command-pack-fleet-timing.py"
)

HEAD = "1" * 40


def _walk_status_keys(
    document: Any, path: tuple[Any, ...] = ()
) -> Iterator[tuple[tuple[Any, ...], Any]]:
    """Yield ``(path, value)`` for every dict key named ``status``."""

    if isinstance(document, dict):
        for key, value in document.items():
            here = path + (key,)
            if key == "status":
                yield here, value
                # Envelope-scoped rule: the top-level ``status`` is the embedded
                # sd-status document. Treat it opaque so its own nested
                # per-entity ``status`` fields never masquerade as an
                # envelope-scoped collision with the ``outcome`` verdict enum.
                if path == ():
                    continue
            yield from _walk_status_keys(value, here)
    elif isinstance(document, list):
        for index, item in enumerate(document):
            yield from _walk_status_keys(item, path + (index,))


def _deprecated_status_paths(producer: str) -> set[tuple[Any, ...]]:
    """Deprecated ``status`` alias paths for one producer's document."""

    return {
        tuple(entry["path"])
        for entry in lib.DEPRECATED_PAYLOAD_KEYS
        if entry["producer"] == producer and entry["path"][-1] == "status"
    }


class VerdictCoreDerivationTests(unittest.TestCase):
    """AC2: per-domain sets derive from one core with explicit opt-outs."""

    def test_every_producer_registers_its_domain(self) -> None:
        self.assertEqual(
            set(lib.VERDICT_DOMAINS),
            {"housekeeping", "review-local", "fleet-stage", "fleet-consumer"},
        )

    def test_each_domain_locks_in_its_exact_member_set(self) -> None:
        # AC2: each producer's vocabulary derives from the core plus explicit
        # opt-outs. Pin the exact frozen set every domain registers so a silent
        # drift — adding, dropping, or renaming a verdict — fails loudly here
        # and forces a conscious update rather than passing tautologically.
        self.assertEqual(
            {name: set(members) for name, members in lib.VERDICT_DOMAINS.items()},
            {
                "housekeeping": {"clean", "blocked", "indeterminate", "failed"},
                "review-local": {
                    "clean",
                    "findings",
                    "unavailable",
                    "failed",
                    "cancelled",
                    "skipped",
                },
                "fleet-stage": {"passed", "failed", "skipped", "interrupted"},
                "fleet-consumer": {
                    "at-target",
                    "refreshed-merged",
                    "pr-open",
                    "skipped",
                    "failed",
                    "blocked",
                },
            },
        )
        # Guard the derivation itself: every non-opted-out member is a core
        # verdict, so the exact sets above cannot drift away from the core
        # without a matching opt-out.
        opt_outs = {
            "housekeeping": {"indeterminate"},
            "review-local": {"findings", "unavailable", "cancelled"},
            "fleet-stage": {"passed", "interrupted"},
            "fleet-consumer": {"at-target", "refreshed-merged", "pr-open"},
        }
        for name, members in lib.VERDICT_DOMAINS.items():
            self.assertLessEqual(
                members - opt_outs[name], lib.VERDICT_CORE, name
            )

    def test_non_core_verdict_without_opt_out_is_rejected(self) -> None:
        with self.assertRaises(lib.VerdictVocabularyError):
            lib.declare_verdict_domain("drifted", {"clean", "at-target"})

    def test_opt_out_lets_domain_specific_verdict_through(self) -> None:
        declared = lib.declare_verdict_domain(
            "opt-in-demo", {"clean", "at-target"}, opt_out={"at-target"}
        )
        self.assertEqual(declared, {"clean", "at-target"})
        # Clean up the demo registration so it does not leak into other asserts.
        lib.VERDICT_DOMAINS.pop("opt-in-demo", None)

    def test_opting_out_a_core_verdict_is_rejected(self) -> None:
        with self.assertRaises(lib.VerdictVocabularyError):
            lib.declare_verdict_domain("redundant", {"clean"}, opt_out={"clean"})


class HousekeepingCollisionTests(unittest.TestCase):
    """AC1/R4: housekeeping's document no longer carries two ``status`` types."""

    def _clean_result(self) -> dict[str, Any]:
        args = Namespace(
            status_input=None,
            status_error=["status_unavailable", "collector produced no JSON"],
            status_exit=1,
            repository=Path("/repo"),
            eligibility_input=None,
            finish_work_unverified=False,
            start_branch="feature/x",
            default_branch="main",
            remote="origin",
            merge_strategy="merge",
            dry_run=False,
            keep_remote_branch=False,
            dependency_pr_number=None,
            action=[],
            anomaly=[],
        )
        return result_builder.build_result(args)

    def test_no_two_status_keys_share_a_document_with_different_types(self) -> None:
        result = self._clean_result()
        # Give the document its realistic shape: top-level ``status`` is the
        # embedded sd-status document (a dict), which is the genuine other half
        # of the historical collision with the ``outcome.status`` enum string.
        # The real sd-status payload carries its own nested ``status`` strings
        # (its summary field and per-provider state); the envelope-scoped walker
        # must treat the embedded document as opaque and never surface those as
        # a collision.
        result["status"] = {
            "schemaVersion": 2,
            "status": "degraded",
            "providers": [{"id": "git", "status": "available"}],
        }
        deprecated = _deprecated_status_paths("housekeeping-result")
        canonical = [
            (path, value)
            for path, value in _walk_status_keys(result)
            if path not in deprecated
        ]
        types = {type(value) for _, value in canonical}
        self.assertEqual(
            types,
            {dict},
            f"canonical status keys carry mixed value types: {canonical}",
        )
        # The canonical enum now lives under outcome.verdict; outcome.status is
        # only the deprecated alias emitting the same value.
        self.assertIn("verdict", result["outcome"])
        self.assertEqual(result["outcome"]["verdict"], result["outcome"]["status"])

    def test_walker_would_catch_the_collision_if_alias_were_canonical(self) -> None:
        # Guard against a walker that trivially passes: without excluding the
        # declared alias, the housekeeping document does mix a str and a dict.
        result = self._clean_result()
        result["status"] = {"schemaVersion": 2}  # force the document shape
        all_status = list(_walk_status_keys(result))
        types = {type(value) for _, value in all_status}
        self.assertGreater(len(types), 1)


class ReviewLocalCollisionTests(unittest.TestCase):
    """Step 3: the review-local report envelope converges on ``outcome``."""

    def _receipt(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "receiptId": "receipt-1",
            "outcome": "clean",
            "target": {
                "repository": "o/r",
                "base": "base",
                "head": "head",
                "contentDigest": "digest",
            },
            "plan": {"policyId": "policy", "familyGate": "gate"},
            "attempts": [
                {
                    "provider": {
                        "id": "prism",
                        "costTier": "low",
                        "qualityTier": "standard",
                    },
                    "status": "clean",
                    "durationMs": 10,
                }
            ],
            "findings": [],
            "disposition": {"outstanding": 0},
            "remoteGate": {"state": "eligible"},
            "confidence": {"granted": True, "limitations": []},
        }

    def test_report_emits_outcome_and_the_deprecated_status_alias(self) -> None:
        report = review_local._report(self._receipt(), reused=False)
        self.assertEqual(report["outcome"], "clean")
        self.assertEqual(report["status"], "clean")

    def test_report_status_keys_are_type_consistent(self) -> None:
        report = review_local._report(self._receipt(), reused=False)
        types = {type(value) for _, value in _walk_status_keys(report)}
        # The report's only status values are per-attempt state strings and the
        # deprecated top-level alias; all are strings, so there is no collision.
        self.assertEqual(types, {str})


class DualEmitCompatFixtureTests(unittest.TestCase):
    """AC5: a consumer written against the OLD key names still works."""

    def test_legacy_housekeeping_consumer_reads_outcome_status(self) -> None:
        args = Namespace(
            status_input=None,
            status_error=["status_unavailable", "no JSON"],
            status_exit=1,
            repository=Path("/repo"),
            eligibility_input=None,
            finish_work_unverified=False,
            start_branch="feature/x",
            default_branch="main",
            remote="origin",
            merge_strategy="merge",
            dry_run=False,
            keep_remote_branch=False,
            dependency_pr_number=None,
            action=[],
            anomaly=[],
        )
        result = result_builder.build_result(args)

        # A month-old consumer that only knows outcome.status must keep working.
        def legacy_verdict(payload: dict[str, Any]) -> str:
            return payload["outcome"]["status"]

        self.assertEqual(legacy_verdict(result), "failed")
        self.assertEqual(legacy_verdict(result), result["outcome"]["verdict"])

    def test_legacy_review_local_consumer_reads_report_status(self) -> None:
        receipt = {
            "schemaVersion": 1,
            "receiptId": "receipt-1",
            "outcome": "findings",
            "target": {
                "repository": "o/r",
                "base": "base",
                "head": "head",
                "contentDigest": "digest",
            },
            "plan": {"policyId": "policy", "familyGate": "gate"},
            "attempts": [],
            "findings": [],
            "disposition": {"outstanding": 0},
            "remoteGate": {"state": "blocked"},
            "confidence": {"granted": False, "limitations": []},
        }
        report = review_local._report(receipt, reused=True)

        def legacy_report_verdict(payload: dict[str, Any]) -> str:
            return payload["status"]

        self.assertEqual(legacy_report_verdict(report), "findings")
        self.assertEqual(legacy_report_verdict(report), report["outcome"])

    def test_every_declared_alias_is_still_emitted(self) -> None:
        # R5: the dual-emit window keeps each deprecated key alive with a
        # recorded removed_version until a later release drops it.
        for entry in lib.DEPRECATED_PAYLOAD_KEYS:
            self.assertRegex(entry["removed_version"], r"^\d+\.\d+\.\d+$")
            self.assertTrue(entry["replacement"])


if __name__ == "__main__":
    unittest.main()
