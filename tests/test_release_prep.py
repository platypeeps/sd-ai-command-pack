from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACK_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACK_ROOT / ".github/scripts/prepare-release.py"
SPEC = importlib.util.spec_from_file_location("prepare_release", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
release_prep = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_prep
SPEC.loader.exec_module(release_prep)


def surface_report(
    *,
    stale: bool = False,
    changed_paths: list[str] | None = None,
    base_ref: str | None = None,
) -> dict[str, object]:
    finding = {
        "code": "provenance.candidate-stale",
        "path": "docs/fleet/candidate-validation.json",
        "relation": "requires-release-evidence",
        "message": "candidate ledger is stale",
        "ownerCommand": "python3 scripts/sd-ai-command-pack-fleet-candidate-check.py",
    }
    return {
        "schemaVersion": 1,
        "status": "failed" if stale else "clean",
        "baseRef": base_ref,
        "changedPaths": changed_paths or [],
        "findingCount": 1 if stale else 0,
        "findingCounts": {"provenance.candidate-stale": 1} if stale else {},
        "findingsTruncated": False,
        "findings": [finding] if stale else [],
    }


def completed(
    command: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class ReleasePrepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="release-prep-")
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.write_plugin_versions("1.0.0", "1.0.0")

    def write_plugin_versions(self, pack: str, plugin: str) -> None:
        (self.root / "manifest.json").write_text(
            json.dumps({"version": pack}), encoding="utf-8"
        )
        plugin_manifest = self.root / release_prep.PLUGIN_MANIFEST
        plugin_manifest.parent.mkdir(parents=True, exist_ok=True)
        plugin_manifest.write_text(
            json.dumps({"name": "sd", "version": plugin}), encoding="utf-8"
        )

    def command_responses(self, reports: list[dict[str, object]]):
        remaining = iter(reports)

        def run(command, **_kwargs):
            argv = list(command)
            if argv[-2:] == [release_prep.SURFACE_CHECK, "--json"]:
                report = next(remaining)
                return completed(
                    argv,
                    returncode=0 if report["status"] == "clean" else 1,
                    stdout=json.dumps(report),
                )
            return completed(argv)

        return run

    def test_clean_candidate_runs_ordered_prep_and_skips_fleet(self) -> None:
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            side_effect=self.command_responses([surface_report()]),
        ) as runner:
            release_prep.prepare_release(self.root, "/venv/python")

        commands = [list(call.args[0]) for call in runner.call_args_list]
        self.assertEqual(
            commands,
            [
                ["/venv/python", ".github/scripts/generate-command-surfaces.py"],
                ["/venv/python", ".github/scripts/partition-surfaces.py"],
                ["/venv/python", ".github/scripts/generate-plugin.py"],
                [
                    "/venv/python",
                    ".github/scripts/generate-provider-config-history.py",
                ],
                ["/venv/python", "install.py", ".", "--force"],
                ["/venv/python", "scripts/sd-ai-command-pack-update-spec-kb.py"],
                ["/venv/python", release_prep.SURFACE_CHECK, "--json"],
            ],
        )

    def test_stale_candidate_runs_fleet_once_then_requires_clean_closure(self) -> None:
        reports = [surface_report(stale=True), surface_report()]
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            side_effect=self.command_responses(reports),
        ) as runner:
            release_prep.prepare_release(self.root, "/venv/python")

        commands = [list(call.args[0]) for call in runner.call_args_list]
        self.assertEqual(
            commands,
            [
                ["/venv/python", ".github/scripts/generate-command-surfaces.py"],
                ["/venv/python", ".github/scripts/partition-surfaces.py"],
                ["/venv/python", ".github/scripts/generate-plugin.py"],
                [
                    "/venv/python",
                    ".github/scripts/generate-provider-config-history.py",
                ],
                ["/venv/python", "install.py", ".", "--force"],
                ["/venv/python", "scripts/sd-ai-command-pack-update-spec-kb.py"],
                ["/venv/python", release_prep.SURFACE_CHECK, "--json"],
                ["/venv/python", release_prep.CANDIDATE_CHECK],
                ["/venv/python", release_prep.SURFACE_CHECK, "--json"],
            ],
        )

    def test_candidate_failure_stops_before_final_closure(self) -> None:
        stale = surface_report(stale=True)

        def run(command, **_kwargs):
            argv = list(command)
            if argv[-2:] == [release_prep.SURFACE_CHECK, "--json"]:
                return completed(argv, returncode=1, stdout=json.dumps(stale))
            if argv[-1:] == [release_prep.CANDIDATE_CHECK]:
                return completed(argv, returncode=5)
            return completed(argv)

        with mock.patch.object(release_prep.subprocess, "run", side_effect=run) as runner:
            with self.assertRaisesRegex(release_prep.ReleasePrepError, "exit 5"):
                release_prep.prepare_release(self.root, "/venv/python")

        surface_calls = [
            call
            for call in runner.call_args_list
            if list(call.args[0])[-2:] == [release_prep.SURFACE_CHECK, "--json"]
        ]
        self.assertEqual(len(surface_calls), 1)

    def test_candidate_must_produce_clean_final_closure(self) -> None:
        reports = [surface_report(stale=True), surface_report(stale=True)]
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            side_effect=self.command_responses(reports),
        ):
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "ledger remains stale"
            ):
                release_prep.prepare_release(self.root, "/venv/python")

    def test_failed_step_stops_before_later_work(self) -> None:
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            return_value=completed(["generator"], returncode=7),
        ) as runner:
            with self.assertRaisesRegex(release_prep.ReleasePrepError, "exit 7"):
                release_prep.prepare_release(self.root, "/venv/python")

        self.assertEqual(runner.call_count, 1)

    def test_missing_or_timed_out_command_is_controlled(self) -> None:
        failures = [
            FileNotFoundError("missing"),
            subprocess.TimeoutExpired(["generator"], 300),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(
                    release_prep.subprocess, "run", side_effect=failure
                ):
                    with self.assertRaisesRegex(
                        release_prep.ReleasePrepError, "could not complete"
                    ):
                        release_prep.prepare_release(self.root, "/venv/python")

    def test_extra_surface_finding_stops_before_fleet(self) -> None:
        report = surface_report(stale=True)
        report["findingCount"] = 2
        report["findingCounts"] = {
            "mirror.stale": 1,
            "provenance.candidate-stale": 1,
        }
        report["findings"] = [
            *report["findings"],
            {
                "code": "mirror.stale",
                "path": "scripts/example.py",
                "relation": "mirrors",
            },
        ]
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            side_effect=self.command_responses([report]),
        ) as runner:
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "clean except for stale candidate"
            ):
                release_prep.prepare_release(self.root, "/venv/python")

        commands = [list(call.args[0]) for call in runner.call_args_list]
        self.assertNotIn(["/venv/python", release_prep.CANDIDATE_CHECK], commands)

    def test_plugin_version_mismatch_stops_before_self_sync(self) -> None:
        self.write_plugin_versions("1.1.0", "1.0.0")
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            side_effect=self.command_responses([surface_report()]),
        ) as runner:
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "does not match manifest.json version"
            ):
                release_prep.prepare_release(self.root, "/venv/python")

        commands = [list(call.args[0]) for call in runner.call_args_list]
        self.assertEqual(
            commands,
            [
                ["/venv/python", ".github/scripts/generate-command-surfaces.py"],
                ["/venv/python", ".github/scripts/partition-surfaces.py"],
                ["/venv/python", ".github/scripts/generate-plugin.py"],
            ],
        )

    def test_missing_plugin_manifest_is_controlled(self) -> None:
        (self.root / release_prep.PLUGIN_MANIFEST).unlink()
        with mock.patch.object(
            release_prep.subprocess,
            "run",
            side_effect=self.command_responses([surface_report()]),
        ):
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "cannot read plugin manifest"
            ):
                release_prep.prepare_release(self.root, "/venv/python")

    def test_plugin_surfaces_count_as_shipped_payload(self) -> None:
        for path in (
            "plugins/sd/skills/sd-help/SKILL.md",
            "plugins/sd/bin/sd-ai-command-pack-review.py",
            ".claude-plugin/marketplace.json",
            ".github/scripts/generate-plugin.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(release_prep._is_payload_path(path))
        for path in (".github/workflows/tests.yml", "tests/test_generate_plugin.py"):
            with self.subTest(path=path):
                self.assertFalse(release_prep._is_payload_path(path))

    def test_plugin_payload_change_requires_version_bump(self) -> None:
        self.write_release_files("1.0.0", "## 1.0.0 - 2026-08-09\n")
        report = surface_report(
            stale=True,
            changed_paths=["plugins/sd/.claude-plugin/plugin.json"],
            base_ref="origin/main",
        )
        with mock.patch.object(
            release_prep, "_git_text", return_value=json.dumps({"version": "1.0.0"})
        ):
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "without a manifest version bump"
            ):
                release_prep._validate_release_prerequisites(self.root, report)

    def write_release_files(self, version: str, heading: str) -> None:
        (self.root / "manifest.json").write_text(
            json.dumps({"version": version}), encoding="utf-8"
        )
        (self.root / "CHANGELOG.md").write_text(heading, encoding="utf-8")

    def test_payload_change_requires_version_bump_before_fleet(self) -> None:
        self.write_release_files("1.0.0", "## 1.0.0 - 2026-07-27\n")
        report = surface_report(
            stale=True,
            changed_paths=["templates/example.txt"],
            base_ref="origin/main",
        )
        with mock.patch.object(
            release_prep, "_git_text", return_value=json.dumps({"version": "1.0.0"})
        ):
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "without a manifest version bump"
            ):
                release_prep._validate_release_prerequisites(self.root, report)

    def test_payload_change_requires_matching_top_changelog_heading(self) -> None:
        self.write_release_files("1.1.0", "## 1.0.0 - 2026-07-27\n")
        report = surface_report(
            stale=True,
            changed_paths=["manifest.json"],
            base_ref="origin/main",
        )
        with mock.patch.object(
            release_prep, "_git_text", return_value=json.dumps({"version": "1.0.0"})
        ):
            with self.assertRaisesRegex(
                release_prep.ReleasePrepError, "requires top CHANGELOG"
            ):
                release_prep._validate_release_prerequisites(self.root, report)

    def test_payload_change_accepts_version_bump_and_matching_changelog(self) -> None:
        self.write_release_files("1.1.0", "## 1.1.0 - 2026-07-27\n")
        report = surface_report(
            stale=True,
            changed_paths=["manifest.json", "templates/example.txt"],
            base_ref="origin/main",
        )
        with mock.patch.object(
            release_prep, "_git_text", return_value=json.dumps({"version": "1.0.0"})
        ):
            release_prep._validate_release_prerequisites(self.root, report)

    def test_payload_change_requires_resolved_base(self) -> None:
        report = surface_report(
            stale=True,
            changed_paths=["templates/example.txt"],
        )

        with self.assertRaisesRegex(release_prep.ReleasePrepError, "no comparison base"):
            release_prep._validate_release_prerequisites(self.root, report)

    def test_candidate_report_must_match_exact_transitional_finding(self) -> None:
        report = surface_report(stale=True)
        report["findings"][0]["path"] = "other.json"

        with self.assertRaisesRegex(
            release_prep.ReleasePrepError, "unexpected candidate evidence"
        ):
            release_prep._candidate_refresh_required(report)

    def test_surface_report_rejects_boolean_integer_fields(self) -> None:
        for field, value in (
            ("schemaVersion", True),
            ("findingCount", False),
        ):
            report = surface_report()
            report[field] = value
            with self.subTest(field=field):
                with self.assertRaises(release_prep.ReleasePrepError):
                    release_prep._candidate_refresh_required(report)

        report = surface_report(stale=True)
        report["findingCounts"] = {"provenance.candidate-stale": True}
        with self.assertRaisesRegex(
            release_prep.ReleasePrepError, "non-candidate finding"
        ):
            release_prep._candidate_refresh_required(report)

    def test_surface_check_rejects_malformed_json(self) -> None:
        result = completed(["surface"], stdout="{not-json")
        with mock.patch.object(release_prep.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(release_prep.ReleasePrepError, "invalid JSON"):
                release_prep._run_surface_check(self.root, "/venv/python")

    def test_release_input_rejects_symlink_and_oversized_file(self) -> None:
        regular = self.root / "regular"
        regular.write_text("content", encoding="utf-8")
        symlink = self.root / "link"
        symlink.symlink_to(regular)
        with self.assertRaisesRegex(release_prep.ReleasePrepError, "regular file"):
            release_prep._regular_bytes(symlink, label="fixture")

        oversized = self.root / "oversized"
        oversized.write_bytes(b"x" * (release_prep.MAX_INPUT_BYTES + 1))
        with self.assertRaisesRegex(release_prep.ReleasePrepError, "exceeds"):
            release_prep._regular_bytes(oversized, label="fixture")

    def test_make_target_runs_final_check_after_preparation(self) -> None:
        makefile = (PACK_ROOT / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("release-prep:\n", 1)[1].split("\n\n", 1)[0]

        self.assertIn(
            '"$(VENV_PYTHON)" .github/scripts/prepare-release.py', target
        )
        self.assertIn("$(MAKE) check", target)
        self.assertLess(target.index("prepare-release.py"), target.index("$(MAKE) check"))


if __name__ == "__main__":
    unittest.main()
