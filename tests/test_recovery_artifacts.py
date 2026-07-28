from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

hashlib = _support.hashlib
json = _support.json
os = _support.os
socket = __import__("socket")
io = __import__("io")
contextlib = __import__("contextlib")
subprocess = _support.subprocess
tempfile = _support.tempfile
unittest = _support.unittest
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

MODULE_PATH = PACK_ROOT / "templates/scripts/sd-ai-command-pack-recovery-artifacts.py"


class RecoveryArtifactTests(InstallTestCase):
    """Commit 1: registry + read-only classification (no destructive Git ops)."""

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix="sd-recovery-")
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.cache_root = base / "cache"
        self.cache_root.mkdir()
        self.state_root = base / "state"
        self.state_root.mkdir()
        self._prev_cache = os.environ.get("SD_AI_COMMAND_PACK_CACHE_ROOT")
        os.environ["SD_AI_COMMAND_PACK_CACHE_ROOT"] = str(self.cache_root)
        self.addCleanup(self._restore_cache)
        self.mod = self.load_module_from_path(MODULE_PATH, "sd_ai_command_pack_recovery_artifacts")

    def _restore_cache(self) -> None:
        if self._prev_cache is None:
            os.environ.pop("SD_AI_COMMAND_PACK_CACHE_ROOT", None)
        else:
            os.environ["SD_AI_COMMAND_PACK_CACHE_ROOT"] = self._prev_cache

    # -- fixtures ---------------------------------------------------------

    def make_repo(self, *, with_remote: bool = False) -> Path:
        root = Path(tempfile.mkdtemp(dir=self._tmp.name, prefix="repo-"))
        self.run_git(root, "init", "--initial-branch=main")
        self.run_git(root, "config", "user.name", "Recovery Test")
        self.run_git(root, "config", "user.email", "rec@example.com")
        (root / "file.txt").write_text("one\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "seed")
        if with_remote:
            remote = Path(tempfile.mkdtemp(dir=self._tmp.name, prefix="remote-")) / "origin.git"
            self.run_git(remote.parent, "init", "--bare", str(remote))
            self.run_git(root, "remote", "add", "origin", str(remote))
        return root

    def head(self, root: Path) -> str:
        return self.git_output(root, "rev-parse", "HEAD")

    def make_stash(self, root: Path, message: str) -> str:
        (root / "file.txt").write_text("changed\n", encoding="utf-8")
        self.run_git(root, "stash", "push", "-m", message)
        return self.git_output(root, "rev-parse", "stash@{0}")

    def add_worktree(self, root: Path, name: str, *, dirty: bool = False) -> Path:
        digest = self.mod.repository_identity(root)["digest"]
        wt_base = self.mod.worktree_base(digest, self.state_root)
        wt_base.mkdir(parents=True, exist_ok=True)
        wt = wt_base / name
        self.run_git(root, "worktree", "add", "--detach", str(wt))
        if dirty:
            (wt / "scratch.txt").write_text("wip\n", encoding="utf-8")
        return wt

    def register_stash(self, root: Path, oid: str, *, live_owner: bool, **overrides):
        run = (
            {"runId": "r-live", "hostname": socket.gethostname(), "pid": os.getpid()}
            if live_owner
            else {"runId": "r-dead", "hostname": "not-this-host-xyz", "pid": 4242}
        )
        params = dict(
            repo=root,
            artifact_type="stash",
            git_identity={"object": oid, "subject": "recovery stash"},
            created_by="sd-recover",
            run=run,
            purpose="protect wip",
            original_head=self.head(root),
            expected_outcome="restored",
            state_root=self.state_root,
        )
        params.update(overrides)
        return self.mod.register(**params)

    def register_worktree(self, root: Path, wt: Path, *, live_owner: bool):
        run = (
            {"runId": "r-live", "hostname": socket.gethostname(), "pid": os.getpid()}
            if live_owner
            else {"runId": "r-dead", "hostname": "not-this-host-xyz", "pid": 4242}
        )
        return self.mod.register(
            repo=root,
            artifact_type="worktree",
            git_identity={"path": str(wt), "head": self.git_output(wt, "rev-parse", "HEAD")},
            created_by="sd-recover",
            run=run,
            purpose="isolated repair",
            original_head=self.head(root),
            expected_outcome="removed",
            state_root=self.state_root,
        )

    def receipt_dir(self, root: Path) -> Path:
        digest = self.mod.repository_identity(root)["digest"]
        return self.mod.receipts_dir(digest, self.state_root)

    def state_snapshot(self) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in sorted(self.state_root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                snapshot[str(path.relative_to(self.state_root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return snapshot

    def repo_snapshot(self, root: Path) -> dict[str, str]:
        return {
            "stashes": self.git_output(root, "stash", "list"),
            "refs": self.git_output(root, "for-each-ref", "--format=%(refname) %(objectname)"),
            "status": self._git(root, "status", "--porcelain").stdout,
        }

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
        )

    # -- register ---------------------------------------------------------

    def test_register_stash_writes_private_receipt(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        receipt = self.register_stash(root, oid, live_owner=False)

        path = self.receipt_dir(root) / f"{receipt['artifactId']}.json"
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.receipt_dir(root).stat().st_mode & 0o777, 0o700)

        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["schemaVersion"], 1)
        self.assertEqual(stored["type"], "stash")
        self.assertEqual(stored["git"]["object"], oid)
        self.assertEqual(set(stored["repository"]), {"digest", "label"})

    def test_receipt_never_embeds_raw_path_or_remote(self) -> None:
        root = self.make_repo(with_remote=True)
        remote_url = self.git_output(root, "remote", "get-url", "origin")
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        receipt = self.register_stash(root, oid, live_owner=False)

        serialized = json.dumps(receipt)
        self.assertNotIn(str(root), serialized)
        self.assertNotIn(remote_url, serialized)

    def test_register_rejects_phantom_stash(self) -> None:
        root = self.make_repo()
        with self.assertRaises(self.mod.RecoveryError):
            self.register_stash(root, "0" * 40, live_owner=False)

    def test_register_rejects_worktree_outside_pack_base(self) -> None:
        root = self.make_repo()
        outside = Path(tempfile.mkdtemp(dir=self._tmp.name, prefix="evil-"))
        with self.assertRaises(self.mod.RecoveryError):
            self.mod.register(
                repo=root,
                artifact_type="worktree",
                git_identity={"path": str(outside), "head": self.head(root)},
                created_by="sd-recover",
                run={"runId": "r", "hostname": "h", "pid": 1},
                purpose="p",
                original_head=self.head(root),
                expected_outcome="removed",
                state_root=self.state_root,
            )

    def test_register_rejects_duplicate_identity(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        self.register_stash(root, oid, live_owner=False)
        with self.assertRaises(self.mod.RecoveryError):
            self.register_stash(root, oid, live_owner=False)

    def test_reject_secret_keys(self) -> None:
        with self.assertRaises(self.mod.RecoveryError):
            self.mod._reject_secret_keys({"apiKey": "value"})
        # A benign structure must not raise.
        self.mod._reject_secret_keys({"purpose": "protect", "run": {"pid": 1}})

    # -- classify (read-only) --------------------------------------------

    def test_classify_empty_state_is_all_zero(self) -> None:
        root = self.make_repo()
        report = self.mod.classify_repository(root, state_root=self.state_root)
        self.assertEqual(report["receipts"], [])
        self.assertEqual(report["unowned"], [])
        self.assertEqual(report["corrupt"], [])
        self.assertEqual(set(report["counts"].values()), {0})

    def test_classify_active_when_owner_live(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        self.register_stash(root, oid, live_owner=True)
        report = self.mod.classify_repository(root, state_root=self.state_root)
        self.assertEqual(len(report["receipts"]), 1)
        self.assertEqual(report["receipts"][0]["classification"], self.mod.CLASS_ACTIVE)
        self.assertTrue(report["receipts"][0]["ownerLive"])

    def test_classify_missing_when_stash_dropped(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        self.register_stash(root, oid, live_owner=False)
        self.run_git(root, "stash", "drop", "stash@{0}")
        report = self.mod.classify_repository(root, state_root=self.state_root)
        self.assertEqual(report["receipts"][0]["classification"], self.mod.CLASS_MISSING_ARTIFACT)

    def test_classify_safe_cleanable_worktree(self) -> None:
        root = self.make_repo()
        wt = self.add_worktree(root, "wt-clean")
        self.register_worktree(root, wt, live_owner=False)
        report = self.mod.classify_repository(root, state_root=self.state_root)
        item = next(r for r in report["receipts"] if r["type"] == "worktree")
        self.assertEqual(item["classification"], self.mod.CLASS_SAFE_CLEANABLE)

    def test_classify_needs_review_when_worktree_dirty(self) -> None:
        root = self.make_repo()
        wt = self.add_worktree(root, "wt-dirty", dirty=True)
        self.register_worktree(root, wt, live_owner=False)
        report = self.mod.classify_repository(root, state_root=self.state_root)
        item = next(r for r in report["receipts"] if r["type"] == "worktree")
        self.assertEqual(item["classification"], self.mod.CLASS_NEEDS_REVIEW)

    def test_classify_reports_pack_shaped_unowned_stash(self) -> None:
        root = self.make_repo()
        self.make_stash(root, "sd-ai-command-pack recovery: orphan")
        report = self.mod.classify_repository(root, state_root=self.state_root)
        self.assertEqual(report["receipts"], [])
        self.assertEqual(len(report["unowned"]), 1)
        self.assertEqual(report["unowned"][0]["type"], "stash")

    def test_classify_ignores_genuine_user_stash(self) -> None:
        root = self.make_repo()
        self.make_stash(root, "my personal work in progress")
        report = self.mod.classify_repository(root, state_root=self.state_root)
        self.assertEqual(report["unowned"], [])

    def test_classify_surfaces_corrupt_receipt(self) -> None:
        root = self.make_repo()
        directory = self.receipt_dir(root)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "broken.json").write_text("{ not valid json", encoding="utf-8")
        report = self.mod.classify_repository(root, state_root=self.state_root)
        self.assertEqual(len(report["corrupt"]), 1)
        self.assertEqual(report["receipts"], [])

    def test_classify_is_deterministic_and_read_only(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        self.register_stash(root, oid, live_owner=False)
        wt = self.add_worktree(root, "wt-clean")
        self.register_worktree(root, wt, live_owner=False)

        state_before = self.state_snapshot()
        repo_before = self.repo_snapshot(root)

        first = self.mod.classify_repository(root, state_root=self.state_root)
        second = self.mod.classify_repository(root, state_root=self.state_root)

        self.assertEqual(first, second)
        self.assertEqual(self.state_snapshot(), state_before)
        self.assertEqual(self.repo_snapshot(root), repo_before)

    def test_repository_identity_digest_is_stable(self) -> None:
        root = self.make_repo()
        self.assertEqual(
            self.mod.repository_identity(root)["digest"],
            self.mod.repository_identity(root)["digest"],
        )

    # -- CLI --------------------------------------------------------------

    def _cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.mod.main(list(argv))
        return code, buffer.getvalue()

    def test_cli_register_then_classify(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        head = self.head(root)

        code, out = self._cli(
            "--state-home", str(self.state_root),
            "register", "--repo", str(root), "--type", "stash",
            "--object", oid, "--subject", "recovery stash",
            "--created-by", "sd-recover", "--run-id", "r-cli",
            "--purpose", "protect wip", "--original-head", head,
        )
        self.assertEqual(code, 0)
        registered = json.loads(out)
        self.assertEqual(registered["type"], "stash")

        code, out = self._cli("--state-home", str(self.state_root), "classify", "--repo", str(root))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(len(report["receipts"]), 1)
        self.assertEqual(report["receipts"][0]["artifactId"], registered["registered"])

    def test_cli_register_rejects_relative_state_home(self) -> None:
        root = self.make_repo()
        code, _ = self._cli(
            "--state-home", "relative/path",
            "classify", "--repo", str(root),
        )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
