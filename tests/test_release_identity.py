from __future__ import annotations

from unittest import mock

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
fleet_manifest = _support.fleet_manifest
Path = _support.Path
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

RELEASE_IDENTITY = PACK_ROOT / ".github/scripts/release_identity.py"
FLEET_LIB = PACK_ROOT / "scripts/sd_ai_command_pack_fleet_lib.py"


class ReleaseIdentityTests(InstallTestCase):
    def load_identity_module(self):
        return self.load_module_from_path(
            RELEASE_IDENTITY,
            "sd_ai_command_pack_release_identity_test",
        )

    def write_manifest(self, root: Path, version: str, content: str = "payload\n") -> None:
        template = root / "templates/tool.txt"
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text(content, encoding="utf-8")
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "files": [
                        {
                            "platform": "shared",
                            "kind": "file",
                            "source": "templates/tool.txt",
                            "target": "tool.txt",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_fleet(self, root: Path, *, extra_consumer: bool = False) -> None:
        consumers = [
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
        ]
        if extra_consumer:
            consumers.append(
                {
                    "name": "second",
                    "github": "example/second",
                    "pathHint": "~/second",
                    "platforms": ["github"],
                    "rolloutPriority": 20,
                    "candidateTimeoutSeconds": 60,
                    "candidatePrepare": [],
                    "candidateChecks": [["node", "check.mjs"]],
                }
            )
        path = root / "docs/fleet/consumers.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(fleet_manifest(consumers), indent=2)
            + "\n",
            encoding="utf-8",
        )

    def write_ledger(self, root: Path) -> None:
        fleet = self.load_module_from_path(
            FLEET_LIB,
            f"release_identity_fleet_lib_{id(root)}",
        )
        manifest_path = root / "manifest.json"
        fleet_path = root / "docs/fleet/consumers.json"
        version = fleet.pack_version(manifest_path)
        consumers = fleet.load_fleet_consumers(fleet_path)
        payload = {
            "schemaVersion": fleet.CANDIDATE_LEDGER_SCHEMA_VERSION,
            "validatedAt": "2026-07-20T00:00:00Z",
            "packVersion": version,
            "payloadDigest": fleet.filesystem_payload_digest(manifest_path),
            "fleetManifestDigest": fleet.fleet_manifest_digest(fleet_path.read_bytes()),
            "consumers": [
                {
                    "name": consumer.name,
                    "github": consumer.github,
                    "baseCommit": "0" * 40,
                    "status": "passed",
                    "prepares": [list(command) for command in consumer.candidate_prepare],
                    "checks": [list(command) for command in consumer.candidate_checks],
                }
                for consumer in consumers
            ],
        }
        ledger = root / "docs/fleet/candidate-validation.json"
        ledger.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def make_release_repo(self) -> tuple[Path, Path]:
        root = self.make_git_repo_without_trellis()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.write_manifest(root, "1.0.0")
        self.write_fleet(root)
        self.write_ledger(root)
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "release 1.0.0")
        self.run_git(root, "tag", "v1.0.0")

        remote = root.parent / f"{root.name}-origin.git"
        remote.mkdir()
        self.run_git(remote, "init", "--bare", "--initial-branch=main")
        self.run_git(root, "remote", "add", "origin", str(remote))
        self.run_git(root, "push", "origin", "HEAD:main", "refs/tags/v1.0.0")
        return root, remote

    def verify(self, identity, root: Path):
        return identity.verify_release_identity(
            root,
            manifest_path=root / "manifest.json",
            fleet_path=root / "docs/fleet/consumers.json",
            ledger_path=root / "docs/fleet/candidate-validation.json",
            remote="origin",
        )

    def test_run_git_bounds_subprocess_and_reports_launch_failure(self) -> None:
        identity = self.load_identity_module()
        root = self.make_git_repo_without_trellis()

        with mock.patch.object(
            identity.subprocess,
            "run",
            side_effect=OSError("git unavailable"),
        ) as runner:
            with self.assertRaisesRegex(
                identity.ReleaseIdentityError,
                "git command failed to start or timed out",
            ):
                identity.run_git(root, ["status"])

        self.assertEqual(
            runner.call_args.kwargs["timeout"],
            identity.GIT_TIMEOUT_SECONDS,
        )

    def test_option_like_remote_is_separated_from_git_options(self) -> None:
        identity = self.load_identity_module()
        root = self.make_git_repo_without_trellis()
        object_id = "a" * 40

        with mock.patch.object(
            identity,
            "git_text",
            return_value=f"{object_id}\trefs/tags/v1.0.0\n",
        ) as git_text:
            result = identity._remote_tag_object(
                root,
                "--upload-pack=unexpected",
                "v1.0.0",
            )

        self.assertEqual(result, object_id)
        git_text.assert_called_once_with(
            root,
            "ls-remote",
            "--refs",
            "--",
            "--upload-pack=unexpected",
            "refs/tags/v1.0.0",
        )

    def test_rejects_manifest_source_traversal_at_commit(self) -> None:
        identity = self.load_identity_module()

        with self.assertRaisesRegex(
            identity.ReleaseIdentityError,
            "resolves outside the repository",
        ):
            identity.normalize_tree_path(
                identity.PurePosixPath("../outside.txt"),
                "../outside.txt",
            )

    def test_verifies_release_and_allows_bookkeeping_commit(self) -> None:
        identity = self.load_identity_module()
        root, _remote = self.make_release_repo()
        (root / "README.md").write_text("bookkeeping\n", encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "docs after release")

        result = self.verify(identity, root)

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.version, "1.0.0")
        self.assertEqual(result.tag, "v1.0.0")
        self.assertEqual(result.commit_sha, self.git_output(root, "rev-parse", "v1.0.0"))
        self.assertTrue(result.payload_digest.startswith("sha256:"))

    def test_rejects_missing_local_tag(self) -> None:
        identity = self.load_identity_module()
        root, _remote = self.make_release_repo()
        self.run_git(root, "tag", "-d", "v1.0.0")

        with self.assertRaisesRegex(
            identity.ReleaseIdentityError,
            "local release tag refs/tags/v1.0.0 is missing",
        ):
            self.verify(identity, root)

    def test_rejects_rewritten_tag(self) -> None:
        identity = self.load_identity_module()
        root, _remote = self.make_release_repo()
        (root / "README.md").write_text("later\n", encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "later commit")
        self.run_git(root, "tag", "-f", "v1.0.0")

        with self.assertRaisesRegex(
            identity.ReleaseIdentityError,
            "release tag v1.0.0 was rewritten or does not match origin",
        ):
            self.verify(identity, root)

    def test_rejects_tagged_version_mismatch(self) -> None:
        identity = self.load_identity_module()
        root, remote = self.make_release_repo()
        self.write_manifest(root, "1.1.0")
        self.write_ledger(root)
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "prepare 1.1.0")
        baseline = self.git_output(root, "rev-parse", "v1.0.0")
        self.run_git(root, "tag", "v1.1.0", baseline)
        self.run_git(root, "push", str(remote), "refs/tags/v1.1.0")

        with self.assertRaisesRegex(
            identity.ReleaseIdentityError,
            "tag v1.1.0 contains pack version '1.0.0'",
        ):
            self.verify(identity, root)

    def test_rejects_payload_mismatch_under_same_version(self) -> None:
        identity = self.load_identity_module()
        root, _remote = self.make_release_repo()
        self.write_manifest(root, "1.0.0", content="changed payload\n")

        with self.assertRaisesRegex(
            identity.ReleaseIdentityError,
            "tag v1.0.0 payload does not match the current checkout",
        ):
            self.verify(identity, root)

    def test_rejects_stale_current_candidate_ledger(self) -> None:
        identity = self.load_identity_module()
        root, _remote = self.make_release_repo()
        self.write_fleet(root, extra_consumer=True)
        self.run_git(root, "add", "docs/fleet/consumers.json")
        self.run_git(root, "commit", "-m", "expand fleet without evidence")

        with self.assertRaisesRegex(
            identity.ReleaseIdentityError,
            "current candidate ledger is not release-ready",
        ):
            self.verify(identity, root)


if __name__ == "__main__":
    unittest.main()
