from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
mock = _support.mock
Path = _support.Path
subprocess = _support.subprocess
sys = _support.sys
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

ROUTER = PACK_ROOT / "scripts/sd-ai-command-pack-audit-route.py"
TEMPLATE_ROUTER = PACK_ROOT / "templates/scripts/sd-ai-command-pack-audit-route.py"


class AuditRoutingTests(InstallTestCase):
    def load_router(self):
        return self.load_module_from_path(
            ROUTER,
            f"sd_ai_command_pack_audit_route_{id(self)}",
        )

    def make_fixture(self, files: dict[str, str]):
        root = self.make_git_repo_without_trellis()
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    @staticmethod
    def charter_rows(report):
        return {row["id"]: row for row in report["charters"]}

    def test_bounded_evidence_is_deduplicated_sorted_and_capped(self) -> None:
        router = self.load_router()
        values = [f"path-{index:03d}" for index in reversed(range(40))]

        bounded = router._bounded([*values, *values])

        self.assertEqual(len(bounded), router.MAX_EVIDENCE)
        self.assertEqual(bounded, tuple(sorted(set(values))[: router.MAX_EVIDENCE]))

    def test_standard_keeps_core_and_dimensions_are_additive(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"main.py": "print('hello')\n"})

        report = router.build_report(root, "standard", ["improvements"])
        rows = self.charter_rows(report)

        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["routerVersion"], 1)
        self.assertEqual(report["classificationStatus"], "complete")
        self.assertFalse(report["fallbackToExhaustive"])
        for charter in router.MANDATORY_STANDARD:
            with self.subTest(charter=charter):
                self.assertEqual(rows[charter]["status"], "run")
                self.assertEqual(
                    rows[charter]["reasonCode"],
                    "mandatory-standard-core",
                )
        self.assertEqual(rows["improvements"]["status"], "run")
        self.assertEqual(rows["improvements"]["reasonCode"], "explicit-dimension")
        self.assertEqual(rows["bloat"]["status"], "not-selected")
        self.assertEqual(rows["accessibility-i18n"]["status"], "not-applicable")
        self.assertIn("not equivalent to exhaustive", report["warnings"][0])
        self.assertEqual(sum(report["summary"].values()), len(router.CHARTERS))

    def test_documentation_signal_requires_a_document_extension_or_directory(self) -> None:
        router = self.load_router()
        code_root = self.make_fixture({"src/architecture.py": "class Router: pass\n"})
        named_doc_root = self.make_fixture({"README": "fixture\n"})
        directory_doc_root = self.make_fixture(
            {"docs/examples/architecture.py": "# documented example\n"}
        )

        code_rows = self.charter_rows(router.build_report(code_root, "standard", []))
        named_doc_rows = self.charter_rows(
            router.build_report(named_doc_root, "standard", [])
        )
        directory_doc_rows = self.charter_rows(
            router.build_report(directory_doc_root, "standard", [])
        )

        self.assertEqual(code_rows["documentation"]["status"], "not-applicable")
        self.assertEqual(named_doc_rows["documentation"]["status"], "run")
        self.assertEqual(directory_doc_rows["documentation"]["status"], "run")

    def test_exhaustive_runs_every_charter(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"README.md": "fixture\n"})

        report = router.build_report(root, "exhaustive", [])

        self.assertEqual(report["summary"]["run"], len(router.CHARTERS))
        self.assertEqual(report["summary"]["not-applicable"], 0)
        self.assertEqual(report["summary"]["not-selected"], 0)
        self.assertEqual(report["warnings"], [])
        self.assertTrue(
            all(
                row["reasonCode"] == "exhaustive-mode"
                for row in report["charters"]
            )
        )

    def test_calibration_fixtures_route_seeded_material_findings(self) -> None:
        router = self.load_router()
        scenarios = (
            (
                "ui",
                {
                    "package.json": json.dumps(
                        {"name": "ui-fixture", "dependencies": {"react": "1"}}
                    ),
                    "src/App.tsx": "export const App = () => <main />;\n",
                },
                {"accessibility-i18n"},
            ),
            (
                "database",
                {
                    "requirements.txt": "sqlalchemy==2.0\n",
                    "db/migrations/001.sql": "create table fixture(id int);\n",
                    "src/main.py": "print('db')\n",
                },
                {"architecture", "performance", "dependencies"},
            ),
            (
                "api",
                {
                    "openapi.yaml": "openapi: 3.1.0\n",
                    "src/api/routes.py": "def route(): return {}\n",
                },
                {"design", "consumer-impact"},
            ),
            (
                "infrastructure",
                {
                    "main.tf": "terraform {}\n",
                    "Dockerfile": "FROM scratch\n",
                    "src/server.py": "print('server')\n",
                },
                {"architecture", "observability"},
            ),
            (
                "dependency",
                {"Cargo.toml": "[package]\nname = 'fixture'\nversion = '0.1.0'\n"},
                {"dependencies"},
            ),
            (
                "release",
                {"CHANGELOG.md": "# Changelog\n"},
                {"release-hygiene"},
            ),
        )

        for name, files, seeded_dimensions in scenarios:
            with self.subTest(scenario=name):
                root = self.make_fixture(files)
                standard = router.build_report(root, "standard", [])
                exhaustive = router.build_report(root, "exhaustive", [])
                standard_rows = self.charter_rows(standard)
                exhaustive_rows = self.charter_rows(exhaustive)
                self.assertTrue(
                    all(
                        standard_rows[dimension]["status"] == "run"
                        for dimension in seeded_dimensions
                    )
                )
                self.assertTrue(
                    all(row["status"] == "run" for row in exhaustive_rows.values())
                )
                self.assertLess(
                    standard["summary"]["run"],
                    exhaustive["summary"]["run"],
                )

    def test_unknown_inventory_falls_back_to_exhaustive(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"main.py": "print('fixture')\n"})

        with mock.patch.object(
            router,
            "_inventory_paths",
            side_effect=router.CommandError("synthetic inventory failure"),
        ):
            report = router.build_report(root, "standard", [])

        self.assertEqual(report["classificationStatus"], "fallback-exhaustive")
        self.assertTrue(report["fallbackToExhaustive"])
        self.assertEqual(report["summary"]["run"], len(router.CHARTERS))
        self.assertEqual(report["fingerprints"][0]["state"], "unknown")
        self.assertIn("synthetic inventory failure", report["warnings"][0])
        self.assertTrue(
            all(
                row["reasonCode"] == "classification-fallback-exhaustive"
                for row in report["charters"]
            )
        )

    def test_malformed_manifest_falls_back_instead_of_skipping(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"package.json": "{not json\n"})

        report = router.build_report(root, "standard", [])

        self.assertTrue(report["fallbackToExhaustive"])
        self.assertEqual(report["summary"]["run"], len(router.CHARTERS))
        self.assertIn("invalid JSON", report["warnings"][0])
        self.assertEqual(report["fingerprints"][0]["state"], "conflicting")

    def test_unknown_source_stack_falls_back_to_exhaustive(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"src/main.unknown-language": "fixture\n"})

        report = router.build_report(root, "standard", [])

        self.assertTrue(report["fallbackToExhaustive"])
        self.assertEqual(report["summary"]["run"], len(router.CHARTERS))
        self.assertEqual(report["fingerprints"][0]["state"], "unknown")
        self.assertIn("unrecognized source-language paths", report["warnings"][0])

    def test_symlinked_manifest_is_conflicting_and_not_followed(self) -> None:
        router = self.load_router()
        root = self.make_fixture({})
        outside = root.parent / "outside-package.json"
        outside.write_text('{"dependencies":{"react":"1"}}\n', encoding="utf-8")
        (root / "package.json").symlink_to(outside)

        report = router.build_report(root, "standard", [])

        self.assertTrue(report["fallbackToExhaustive"])
        self.assertEqual(report["fingerprints"][0]["state"], "conflicting")
        self.assertIn("not a regular file", report["warnings"][0])

    def test_oversized_manifest_falls_back_without_reading_it(self) -> None:
        router = self.load_router()
        root = self.make_fixture(
            {"package.json": "x" * (router.MAX_MANIFEST_BYTES + 1)}
        )

        report = router.build_report(root, "standard", [])

        self.assertTrue(report["fallbackToExhaustive"])
        self.assertIn("exceeds", report["warnings"][0])
        self.assertNotIn("xxx", report["warnings"][0])

    def test_manifest_identity_change_is_conflicting(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"package.json": '{"name":"fixture"}\n'}).resolve()
        original_fstat = router.os.fstat

        def changed_identity(file_descriptor):
            opened = original_fstat(file_descriptor)
            changed = mock.Mock()
            changed.st_mode = opened.st_mode
            changed.st_dev = opened.st_dev
            changed.st_ino = opened.st_ino + 1
            changed.st_size = opened.st_size
            return changed

        with mock.patch.object(router.os, "fstat", side_effect=changed_identity):
            report = router.build_report(root, "standard", [])

        self.assertTrue(report["fallbackToExhaustive"])
        self.assertIn("changed during inspection", report["warnings"][0])

    def test_manifest_os_error_does_not_expose_host_path(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"package.json": '{"name":"fixture"}\n'}).resolve()
        sensitive = "/Users/private/token-value"

        with mock.patch.object(
            router,
            "_open_without_following_symlinks",
            side_effect=OSError(5, sensitive),
        ):
            with self.assertRaises(router.FingerprintEvidenceError) as raised:
                router._read_manifest(root, "package.json")

        detail = str(raised.exception)
        self.assertIn("package.json", detail)
        self.assertIn("os-error-5", detail)
        self.assertNotIn(sensitive, detail)

    def test_inventory_rejects_control_characters_without_echoing_them(self) -> None:
        router = self.load_router()
        root = self.make_fixture({})
        inventory = mock.Mock(stdout="src/main.py\0src/private\nvalue.py\0")

        with mock.patch.object(router, "run_git", return_value=inventory):
            with self.assertRaisesRegex(
                router.CommandError,
                "repository path inventory contains an unsafe path",
            ) as raised:
                router._inventory_paths(root)

        self.assertNotIn("private", str(raised.exception))

    def test_build_report_rejects_wrong_structured_input_types(self) -> None:
        router = self.load_router()
        root = self.make_fixture({"main.py": "print('fixture')\n"})

        cases = (
            (".", "standard", [], "repository must be a path"),
            (root, None, [], "audit depth must be a string"),
            (root, "standard", "security", "sequence of strings"),
            (root, "standard", [True], "only strings"),
        )
        for repo, mode, dimensions, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(router.AuditRoutingError, expected):
                    router.build_report(repo, mode, dimensions)

    def test_cli_json_human_and_invalid_dimension(self) -> None:
        root = self.make_fixture({"README.md": "fixture\n"})

        json_result = subprocess.run(
            [sys.executable, str(ROUTER), "--repo", str(root), "--json"],
            check=False,
            text=True,
            capture_output=True,
        )
        human_result = subprocess.run(
            [sys.executable, str(ROUTER), "--repo", str(root)],
            check=False,
            text=True,
            capture_output=True,
        )
        invalid = subprocess.run(
            [
                sys.executable,
                str(ROUTER),
                "--repo",
                str(root),
                "--dimension",
                "unknown",
            ],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        self.assertEqual(json.loads(json_result.stdout)["schemaVersion"], 1)
        self.assertEqual(human_result.returncode, 0, human_result.stderr)
        self.assertIn("Charters:", human_result.stdout)
        self.assertIn("not-applicable", human_result.stdout)
        self.assertIn("Warnings:", human_result.stdout)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("unknown audit dimensions: unknown", invalid.stderr)
        self.assertNotIn("Traceback", invalid.stderr)

    def test_template_and_root_router_are_identical(self) -> None:
        self.assertEqual(ROUTER.read_bytes(), TEMPLATE_ROUTER.read_bytes())


if __name__ == "__main__":
    _support.unittest.main()
