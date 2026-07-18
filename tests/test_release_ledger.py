from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
os = _support.os
subprocess = _support.subprocess
sys = _support.sys
unittest = _support.unittest
Path = _support.Path
yaml = _support.yaml
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

RELEASE_TAG_SCRIPT = PACK_ROOT / ".github/scripts/create-release-tag.py"
FLEET_LIB = PACK_ROOT / "scripts/sd_ai_command_pack_fleet_lib.py"


class ReleaseLedgerTests(InstallTestCase):
    def write_candidate_ledger(self, root: Path, version: str) -> None:
        fleet = self.load_module_from_path(FLEET_LIB, "release_test_fleet_lib")
        fleet_path = root / "docs/fleet/consumers.json"
        fleet_bytes = fleet_path.read_bytes()
        consumers = fleet.load_fleet_consumers(fleet_path)
        ledger = {
            "schemaVersion": fleet.CANDIDATE_LEDGER_SCHEMA_VERSION,
            "validatedAt": "2026-01-02T00:00:00Z",
            "packVersion": version,
            "payloadDigest": fleet.filesystem_payload_digest(root / "manifest.json"),
            "fleetManifestDigest": fleet.fleet_manifest_digest(fleet_bytes),
            "consumers": [
                {
                    "name": consumer.name,
                    "github": consumer.github,
                    "baseCommit": "0" * 40,
                    "status": "passed",
                    "prepares": [
                        list(command) for command in consumer.candidate_prepare
                    ],
                    "checks": [list(command) for command in consumer.candidate_checks],
                }
                for consumer in consumers
            ],
        }
        ledger_path = root / "docs/fleet/candidate-validation.json"
        ledger_path.write_text(
            json.dumps(ledger, indent=2) + "\n",
            encoding="utf-8",
        )

    def make_release_repo(self) -> Path:
        root = self.make_git_repo_without_trellis()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "manifest.json").write_text(
            json.dumps({"version": "1.0.0", "files": []}, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 1.0.0 - 2026-01-01\n\n- Baseline.\n",
            encoding="utf-8",
        )
        fleet_path = root / "docs/fleet/consumers.json"
        fleet_path.parent.mkdir(parents=True)
        fleet_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 3,
                    "consumers": [
                        {
                            "name": "fixture",
                            "github": "example/fixture",
                            "pathHint": "~/fixture",
                            "platforms": ["github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["node", "check.mjs"]],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_candidate_ledger(root, "1.0.0")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "release 1.0.0")
        return root

    def commit_release(
        self,
        root: Path,
        version: str,
        *,
        files: list[dict[str, str]] | None = None,
        top_heading: bool = True,
        update_candidate_ledger: bool = True,
    ) -> str:
        (root / "manifest.json").write_text(
            json.dumps({"version": version, "files": files or []}, indent=2) + "\n",
            encoding="utf-8",
        )
        heading = f"## {version} - 2026-01-02\n\n- Release fixture.\n"
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        if top_heading:
            changelog = changelog.replace("# Changelog\n", f"# Changelog\n\n{heading}", 1)
        else:
            changelog = f"{changelog.rstrip()}\n\n{heading}"
        (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        if update_candidate_ledger:
            self.write_candidate_ledger(root, version)
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", f"release {version}")
        return self.git_output(root, "rev-parse", "HEAD")

    def run_release_tag(
        self,
        root: Path,
        *args: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(RELEASE_TAG_SCRIPT), *args],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_release_tag_dry_run_skips_when_manifest_is_unchanged(self) -> None:
        root = self.make_release_repo()
        (root / "README.md").write_text("documentation only\n", encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "docs only")

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("manifest version unchanged; no tag needed", result.stdout)

    def test_release_tag_dry_run_plans_valid_manifest_version_tag(self) -> None:
        root = self.make_release_repo()
        head_sha = self.commit_release(root, "1.1.0")

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"would create v1.1.0 at {head_sha}", result.stdout)

    def test_release_tag_resolves_symlinked_manifest_source_from_commit(self) -> None:
        root = self.make_release_repo()
        templates = root / "templates"
        templates.mkdir()
        target = templates / "tool-real.sh"
        target.write_text("#!/bin/sh\necho tool\n", encoding="utf-8")
        target.chmod(0o755)
        (templates / "tool.sh").symlink_to(target.name)
        head_sha = self.commit_release(
            root,
            "1.1.0",
            files=[
                {
                    "platform": "shared",
                    "kind": "file",
                    "source": "templates/tool.sh",
                    "target": "scripts/tool.sh",
                }
            ],
        )

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"would create v1.1.0 at {head_sha}", result.stdout)

    def test_release_tag_rejects_matching_heading_below_older_release(self) -> None:
        root = self.make_release_repo()
        self.commit_release(root, "1.1.0", top_heading=False)

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("requires the top CHANGELOG.md release heading", result.stdout)
        self.assertIn("found '## 1.0.0 - 2026-01-01'", result.stdout)

    def test_release_tag_rejects_stale_candidate_ledger(self) -> None:
        root = self.make_release_repo()
        self.commit_release(root, "1.1.0", update_candidate_ledger=False)

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("candidate ledger is not release-ready", result.stdout)
        self.assertIn("packVersion", result.stdout)

    def test_release_tag_rejects_non_object_manifest_without_traceback(self) -> None:
        root = self.make_release_repo()
        (root / "manifest.json").write_text("[]\n", encoding="utf-8")
        self.run_git(root, "add", "manifest.json")
        self.run_git(root, "commit", "-m", "malformed release manifest")

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("manifest.json is not an object", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_release_tag_creates_ref_through_github_api(self) -> None:
        root = self.make_release_repo()
        head_sha = self.commit_release(root, "1.1.0")
        stub_bin = root / "stub-bin"
        stub_bin.mkdir()
        call_log = root / "gh-calls.jsonl"
        gh_stub = stub_bin / "gh"
        gh_stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['GH_CALL_LOG'], 'a', encoding='utf-8') as stream:\n"
            "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if 'matching-refs' in ' '.join(sys.argv[1:]):\n"
            "    print('[]')\n"
            "elif '--method' in sys.argv and 'POST' in sys.argv:\n"
            "    print('{}')\n"
            "else:\n"
            "    raise SystemExit(2)\n",
            encoding="utf-8",
        )
        gh_stub.chmod(0o755)

        result = self.run_release_tag(
            root,
            "--base",
            "HEAD^",
            "--head",
            "HEAD",
            "--repository",
            "platypeeps/sd-ai-command-pack",
            extra_env={
                "GH_CALL_LOG": str(call_log),
                "PATH": os.pathsep.join([str(stub_bin), os.environ["PATH"]]),
            },
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"created v1.1.0 at {head_sha}", result.stdout)
        calls = [json.loads(line) for line in call_log.read_text().splitlines()]
        self.assertEqual(len(calls), 2)
        self.assertIn(
            "repos/platypeeps/sd-ai-command-pack/git/matching-refs/tags/v1.1.0",
            calls[0],
        )
        self.assertIn("POST", calls[1])
        self.assertIn("ref=refs/tags/v1.1.0", calls[1])
        self.assertIn(f"sha={head_sha}", calls[1])

    def test_tests_workflow_runs_auto_tag_only_after_main_ci(self) -> None:
        workflow = yaml.load(
            (PACK_ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )

        job = workflow["jobs"]["auto-tag-release"]
        self.assertEqual(job["needs"], "ci-result")
        self.assertEqual(job["permissions"]["contents"], "write")
        self.assertIn("github.event_name == 'push'", job["if"])
        self.assertIn("github.ref == 'refs/heads/main'", job["if"])
        # Regression guard for the transitive-skip trap: without !cancelled()
        # the implicit success() sees the PR-only release-payload-gate as
        # skipped on main pushes and silently skips auto-tagging.
        self.assertIn("!cancelled()", job["if"])
        self.assertIn("needs.ci-result.result == 'success'", job["if"])
        run_step = job["steps"][1]
        self.assertIn(".github/scripts/create-release-tag.py", run_step["run"])
        self.assertEqual(run_step["env"]["BASE_SHA"], "${{ github.event.before }}")
        self.assertEqual(run_step["env"]["HEAD_SHA"], "${{ github.sha }}")

    def test_tests_workflow_runs_release_payload_gate_on_pull_requests(self) -> None:
        workflow = yaml.load(
            (PACK_ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )

        job = workflow["jobs"]["release-payload-gate"]
        self.assertEqual(job["name"], "Release payload gate")
        self.assertIn("github.event_name == 'pull_request'", job["if"])
        checkout_step = job["steps"][0]
        self.assertEqual(checkout_step["with"]["fetch-depth"], "0")
        run_step = job["steps"][1]
        self.assertEqual(
            run_step["env"]["BASE_SHA"],
            "${{ github.event.pull_request.base.sha }}",
        )
        self.assertIn('git cat-file -e "${BASE_SHA}^{commit}"', run_step["run"])
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_TEST_SOURCE=1", run_step["run"])
        self.assertIn(
            'SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF="${BASE_SHA}"',
            run_step["run"],
        )
        self.assertIn("run_pack_source_drift_gates", run_step["run"])

        aggregate = workflow["jobs"]["ci-result"]
        self.assertIn("release-payload-gate", aggregate["needs"])
        aggregate_run = aggregate["steps"][0]["run"]
        self.assertIn("RELEASE_PAYLOAD_GATE_RESULT", aggregate["steps"][0]["env"])
        self.assertIn("The release payload gate failed.", aggregate_run)


if __name__ == "__main__":
    unittest.main()
