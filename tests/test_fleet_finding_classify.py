from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
io = _support.io
json = _support.json
Path = _support.Path
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

CLASSIFIER = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-finding-classify.py"


class FleetFindingClassifyTests(InstallTestCase):
    def load_classifier(self):
        return self.load_module_from_path(
            CLASSIFIER,
            f"sd_ai_command_pack_fleet_finding_classify_{id(self)}",
        )

    def finding(self, finding_id: str, family: str, **updates: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": finding_id,
            "contractFamily": family,
            "summary": f"Finding {finding_id}",
            "evidence": f"https://example.test/reviews/{finding_id}",
            "reviewer": "copilot",
            "path": "scripts/example.py",
            "line": 12,
        }
        payload.update(updates)
        return payload

    def payload(self, *findings: dict[str, object]) -> dict[str, object]:
        return {"schemaVersion": 1, "findings": list(findings)}

    def test_default_contract_families_have_expected_timing(self) -> None:
        classifier = self.load_classifier()
        findings = [
            self.finding(f"F-{index}", family, line=index)
            for index, family in enumerate(
                sorted(classifier.CONTRACT_FAMILIES),
                start=1,
            )
        ]

        result = classifier.classify_payload(self.payload(*findings))

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.decision, "pause-corrective-release")
        by_family = {
            owner.finding.contract_family: owner.final_disposition
            for owner in result.owners
        }
        for family in classifier.BLOCKING_FAMILIES:
            self.assertEqual(by_family[family], classifier.BLOCK)
        for family in classifier.DEFERRED_FAMILIES:
            self.assertEqual(by_family[family], classifier.DEFER)
        serialized = result.as_json()
        self.assertEqual(serialized["counts"]["blockers"], 4)
        self.assertEqual(serialized["counts"]["deferred"], 6)
        self.assertEqual(json.loads(json.dumps(serialized, sort_keys=True)), serialized)

    def test_follow_up_family_escalates_with_blocker_evidence(self) -> None:
        classifier = self.load_classifier()
        finding = self.finding(
            "DOC-1",
            "documentation",
            impact="blocker",
            impactEvidence="The published install command deletes consumer data.",
        )

        owner = classifier.classify_payload(self.payload(finding)).owners[0]

        self.assertEqual(owner.default_disposition, classifier.DEFER)
        self.assertEqual(owner.computed_disposition, classifier.BLOCK)
        self.assertEqual(owner.final_disposition, classifier.BLOCK)
        self.assertTrue(owner.escalated)
        self.assertIn("blocker impact evidence", owner.rationale)

    def test_operator_override_can_upgrade_or_downgrade_with_rationale(self) -> None:
        classifier = self.load_classifier()
        upgrade = self.finding(
            "STYLE-1",
            "style",
            line=1,
            overrideDisposition=classifier.BLOCK,
            overrideRationale="This formatting defect breaks the generated parser.",
        )
        downgrade = self.finding(
            "SEC-1",
            "security",
            line=2,
            overrideDisposition=classifier.DEFER,
            overrideRationale="Evidence proves the report belongs to unrelated test data.",
        )

        result = classifier.classify_payload(self.payload(upgrade, downgrade))

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(
            [owner.final_disposition for owner in result.owners],
            [classifier.BLOCK, classifier.DEFER],
        )
        self.assertTrue(all(owner.override_applied for owner in result.owners))
        self.assertEqual(result.as_json()["counts"]["overrides"], 2)

    def test_exact_duplicates_share_one_owner_and_disposition(self) -> None:
        classifier = self.load_classifier()
        owner = self.finding("F-1", "diagnostics", evidence="review one")
        duplicate = self.finding(
            "F-2",
            "diagnostics",
            summary="Finding F-1",
            evidence="review two",
        )

        result = classifier.classify_payload(self.payload(owner, duplicate))

        self.assertEqual(len(result.owners), 1)
        self.assertEqual(result.owners[0].observation_ids, ("F-1", "F-2"))
        self.assertEqual(result.as_json()["counts"]["duplicates"], 1)
        self.assertEqual(result.observations[1]["ownerId"], "F-1")
        self.assertTrue(result.observations[1]["duplicate"])
        self.assertEqual(result.observations[1]["finalDisposition"], classifier.DEFER)
        self.assertIn("diagnostics", result.observations[1]["rationale"])
        self.assertEqual(result.exit_code, 0)

    def test_exact_duplicate_policy_conflict_is_invalid(self) -> None:
        classifier = self.load_classifier()
        owner = self.finding("F-1", "documentation")
        conflict = self.finding("F-2", "correctness", summary="Finding F-1")

        with self.assertRaisesRegex(classifier.FleetFindingError, "conflicts with owner F-1"):
            classifier.classify_payload(self.payload(owner, conflict))

    def test_schema_and_boundary_validation_fail_closed(self) -> None:
        classifier = self.load_classifier()
        valid = self.finding("F-1", "documentation")
        cases: tuple[tuple[object, str], ...] = (
            ({"schemaVersion": 2, "findings": [valid]}, "schemaVersion"),
            ({"schemaVersion": True, "findings": [valid]}, "schemaVersion"),
            ({"schemaVersion": 1, "findings": []}, "non-empty array"),
            ({"schemaVersion": 1, "findings": [valid], "extra": True}, "unknown field"),
            (self.payload({**valid, "id": "-unsafe"}), "safe identifier"),
            (self.payload({**valid, "contractFamily": "unknown"}), "must be one of"),
            (self.payload({**valid, "path": "../outside.py"}), "path is unsafe"),
            (self.payload({**valid, "path": "C:\\outside.py"}), "path is unsafe"),
            (self.payload({**valid, "line": True}), "positive integer"),
            (self.payload({**valid, "evidence": ""}), "must not be empty"),
            (self.payload({**valid, "impact": "blocker"}), "requires impactEvidence"),
            (
                self.payload({**valid, "impactEvidence": "not paired"}),
                "requires impact 'blocker'",
            ),
            (
                self.payload({**valid, "overrideDisposition": classifier.DEFER}),
                "must appear together",
            ),
            (self.payload(valid, valid), "duplicate finding ids"),
        )

        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(classifier.FleetFindingError, message):
                    classifier.classify_payload(payload)

    def test_input_file_rejects_symlink_and_malformed_json(self) -> None:
        classifier = self.load_classifier()
        root = self.make_git_repo_without_trellis()
        target = root / "findings.json"
        target.write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(classifier.FleetFindingError, "cannot read"):
            classifier.load_payload(target)

        target.write_text(json.dumps(self.payload(self.finding("F-1", "style"))), encoding="utf-8")
        link = root / "findings-link.json"
        link.symlink_to(target.name)
        with self.assertRaisesRegex(classifier.FleetFindingError, "not a regular file"):
            classifier.load_payload(link)

    def test_main_returns_stable_json_and_exit_codes(self) -> None:
        classifier = self.load_classifier()
        root = self.make_git_repo_without_trellis()
        input_path = root / "findings.json"
        cases = (
            (self.payload(self.finding("F-1", "correctness")), 1, "pause-corrective-release"),
            (self.payload(self.finding("F-2", "style")), 0, "continue-with-follow-ups"),
            ({"schemaVersion": 1, "findings": []}, 2, "invalid-pause"),
        )

        for payload, expected_exit, decision in cases:
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with self.subTest(decision=decision), contextlib.redirect_stdout(output):
                exit_code = classifier.main(["--input", str(input_path), "--json"])
            self.assertEqual(exit_code, expected_exit)
            self.assertEqual(json.loads(output.getvalue())["decision"], decision)

    def test_human_output_lists_disposition_duplicates_and_overrides(self) -> None:
        classifier = self.load_classifier()
        owner = self.finding(
            "F-1",
            "diagnostics",
            overrideDisposition=classifier.DEFER,
            overrideRationale="Bounded follow-up is sufficient.",
        )
        duplicate = self.finding(
            "F-2",
            "diagnostics",
            summary="Finding F-1",
            evidence="second review URL",
            overrideDisposition=classifier.DEFER,
            overrideRationale="Bounded follow-up is sufficient.",
        )

        output = classifier.render_human(
            classifier.classify_payload(self.payload(owner, duplicate))
        )

        self.assertIn("continue-with-follow-ups", output)
        self.assertIn("duplicates: 1", output)
        self.assertIn("overrides: 1", output)
        self.assertIn("duplicates: F-2", output)
        self.assertIn("operator override", output)


if __name__ == "__main__":
    unittest.main()
