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

    # -- destructive cleanup: helpers ------------------------------------

    def supersede_stash(self, root: Path) -> str:
        """Land the stashed change as a commit so the stash is provably redundant.

        Returns the superseding commit oid whose tree equals ``stash@{0}``'s.
        """
        self.run_git(root, "stash", "apply")
        self.run_git(root, "commit", "-am", "land recovered work")
        return self.head(root)

    def stash_oids(self, root: Path) -> set[str]:
        out = self.git_output(root, "stash", "list", "--format=%H")
        return set(out.split()) if out else set()

    def worktree_paths(self, root: Path) -> set[str]:
        out = self.git_output(root, "worktree", "list", "--porcelain")
        return {
            str(Path(line[len("worktree ") :]).resolve())
            for line in out.splitlines()
            if line.startswith("worktree ")
        }

    def write_lock(self, root: Path, *, hostname: str, pid: int) -> Path:
        directory = self.receipt_dir(root)
        directory.mkdir(parents=True, exist_ok=True)
        lock = directory / self.mod.CLEANUP_LOCK_NAME
        lock.write_text(
            json.dumps({"host": hostname, "pid": pid, "token": "external", "createdAt": "2026-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        return lock

    def cleanup(self, root: Path, **kwargs):
        return self.mod.cleanup_repository(root, state_root=self.state_root, **kwargs)

    def redundant_stash_receipt(self, root: Path, *, live_owner: bool = False):
        oid = self.make_stash(root, "sd-ai-command-pack recovery: wip")
        superseded = self.supersede_stash(root)
        receipt = self.register_stash(
            root, oid, live_owner=live_owner, cleanup_predicate={"supersededBy": superseded}
        )
        return oid, receipt

    # -- destructive cleanup: stashes ------------------------------------

    def test_cleanup_owner_drops_redundant_stash(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        rid = receipt["artifactId"]

        report = self.cleanup(root, mode="owner", artifact_id=rid)

        self.assertEqual(report["actions"][0]["action"], "dropped-stash")
        self.assertNotIn(oid, self.stash_oids(root))
        self.assertFalse((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_preserves_unique_stash(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: wip")
        receipt = self.register_stash(root, oid, live_owner=False)
        rid = receipt["artifactId"]

        report = self.cleanup(root, mode="owner", artifact_id=rid)

        self.assertEqual(report["actions"][0]["action"], "skipped")
        self.assertEqual(report["actions"][0]["classification"], "needs-review")
        self.assertIn(oid, self.stash_oids(root))
        self.assertTrue((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_preserves_live_owner_stash(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root, live_owner=True)
        rid = receipt["artifactId"]

        report = self.cleanup(root, mode="owner", artifact_id=rid)

        self.assertEqual(report["actions"][0]["classification"], "active")
        self.assertIn(oid, self.stash_oids(root))
        self.assertTrue((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_drops_exact_stash_after_concurrent_renumber(self) -> None:
        # A second stash pushes the recorded one from stash@{0} to stash@{1};
        # cleanup must resolve by exact object identity and drop only that one.
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        (root / "file.txt").write_text("unrelated\n", encoding="utf-8")
        self.run_git(root, "stash", "push", "-m", "unrelated user stash")
        other = self.git_output(root, "rev-parse", "stash@{0}")
        self.assertNotEqual(other, oid)

        report = self.cleanup(root, mode="owner", artifact_id=receipt["artifactId"])

        self.assertEqual(report["actions"][0]["action"], "dropped-stash")
        self.assertNotIn(oid, self.stash_oids(root))
        self.assertIn(other, self.stash_oids(root))

    # -- destructive cleanup: worktrees ----------------------------------

    def test_cleanup_removes_clean_reachable_worktree(self) -> None:
        root = self.make_repo()
        wt = self.add_worktree(root, "wt-clean")
        receipt = self.register_worktree(root, wt, live_owner=False)
        rid = receipt["artifactId"]

        report = self.cleanup(root, mode="housekeeping")

        self.assertEqual(report["actions"][0]["action"], "removed-worktree")
        self.assertNotIn(str(wt.resolve()), self.worktree_paths(root))
        self.assertFalse(wt.exists())
        self.assertFalse((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_preserves_dirty_worktree(self) -> None:
        root = self.make_repo()
        wt = self.add_worktree(root, "wt-dirty", dirty=True)
        receipt = self.register_worktree(root, wt, live_owner=False)
        rid = receipt["artifactId"]

        report = self.cleanup(root, mode="housekeeping")

        self.assertEqual(report["actions"][0]["classification"], "needs-review")
        self.assertIn(str(wt.resolve()), self.worktree_paths(root))
        self.assertTrue((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_leaves_replaced_path_untouched(self) -> None:
        # The registered worktree is unlinked and a plain directory replaces it.
        # Housekeeping must never delete the replacement (it is not a worktree).
        root = self.make_repo()
        wt = self.add_worktree(root, "wt-replaced")
        receipt = self.register_worktree(root, wt, live_owner=False)
        rid = receipt["artifactId"]
        self.run_git(root, "worktree", "remove", str(wt))
        wt.mkdir(parents=True, exist_ok=True)
        (wt / "keep.txt").write_text("not a worktree\n", encoding="utf-8")

        report = self.cleanup(root, mode="housekeeping")

        self.assertEqual(report["actions"][0]["classification"], "missing-artifact")
        self.assertTrue((wt / "keep.txt").exists())
        # Housekeeping preserves the stale receipt for a read-only status decision.
        self.assertTrue((self.receipt_dir(root) / f"{rid}.json").exists())

    # -- destructive cleanup: reconciliation modes -----------------------

    def test_cleanup_owner_prunes_stale_receipt(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: wip")
        receipt = self.register_stash(root, oid, live_owner=False)
        rid = receipt["artifactId"]
        self.run_git(root, "stash", "drop", "stash@{0}")  # artifact gone out-of-band

        report = self.cleanup(root, mode="owner", artifact_id=rid)

        self.assertEqual(report["actions"][0]["action"], "pruned-receipt")
        self.assertFalse((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_housekeeping_keeps_stale_receipt(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: wip")
        receipt = self.register_stash(root, oid, live_owner=False)
        rid = receipt["artifactId"]
        self.run_git(root, "stash", "drop", "stash@{0}")

        report = self.cleanup(root, mode="housekeeping")

        self.assertEqual(report["actions"][0]["classification"], "missing-artifact")
        self.assertEqual(report["actions"][0]["action"], "skipped")
        self.assertTrue((self.receipt_dir(root) / f"{rid}.json").exists())

    def test_cleanup_dry_run_mutates_nothing(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        before_repo = self.repo_snapshot(root)
        before_state = self.state_snapshot()

        report = self.cleanup(root, mode="housekeeping", dry_run=True)

        self.assertEqual(report["actions"][0]["action"], "would-drop-stash")
        self.assertTrue(report["dryRun"])
        self.assertIn(oid, self.stash_oids(root))
        self.assertEqual(self.repo_snapshot(root), before_repo)
        self.assertEqual(self.state_snapshot(), before_state)

    def test_cleanup_persists_across_module_reload(self) -> None:
        # A fresh module instance (a restart) still retires the recorded artifact.
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        reloaded = self.load_module_from_path(MODULE_PATH, "sd_ai_command_pack_recovery_artifacts_reloaded")

        report = reloaded.cleanup_repository(
            root, mode="owner", artifact_id=receipt["artifactId"], state_root=self.state_root
        )

        self.assertEqual(report["actions"][0]["action"], "dropped-stash")
        self.assertNotIn(oid, self.stash_oids(root))

    # -- destructive cleanup: locking ------------------------------------

    def test_cleanup_skips_when_lock_held_by_live_owner(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        self.write_lock(root, hostname=socket.gethostname(), pid=os.getpid())  # alive

        with self.assertRaises(self.mod.RecoveryError):
            self.cleanup(root, mode="owner", artifact_id=receipt["artifactId"])

        self.assertIn(oid, self.stash_oids(root))  # nothing destroyed
        self.assertTrue((self.receipt_dir(root) / f"{receipt['artifactId']}.json").exists())

    def test_cleanup_reclaims_stale_same_host_lock(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        lock = self.write_lock(root, hostname=socket.gethostname(), pid=2147483646)  # dead pid

        report = self.cleanup(root, mode="owner", artifact_id=receipt["artifactId"])

        self.assertEqual(report["actions"][0]["action"], "dropped-stash")
        self.assertNotIn(oid, self.stash_oids(root))
        self.assertFalse(lock.exists())  # released after reclaim

    def test_cleanup_respects_foreign_host_lock(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        self.write_lock(root, hostname="other-host-xyz", pid=1)  # fresh mtime, not stale

        with self.assertRaises(self.mod.RecoveryError):
            self.cleanup(root, mode="owner", artifact_id=receipt["artifactId"])

        self.assertIn(oid, self.stash_oids(root))

    def test_cleanup_ignores_symlinked_receipt(self) -> None:
        root = self.make_repo()
        oid, receipt = self.redundant_stash_receipt(root)
        directory = self.receipt_dir(root)
        symlink = directory / "00000000dead.json"
        symlink.symlink_to(directory / f"{receipt['artifactId']}.json")

        report = self.cleanup(root, mode="housekeeping")

        # The real receipt is retired; the symlink is never followed or acted on.
        self.assertNotIn(oid, self.stash_oids(root))
        self.assertNotIn("00000000dead.json", {a.get("reference") for a in report["actions"]})

    def test_cleanup_rejects_unknown_mode(self) -> None:
        root = self.make_repo()
        with self.assertRaises(self.mod.RecoveryError):
            self.cleanup(root, mode="wipe-everything")

    # -- pure helpers: validation, resolution, and proofs ----------------

    def _valid_stash_receipt(self) -> dict:
        return {
            "schemaVersion": self.mod.SCHEMA_VERSION,
            "artifactId": "abcd1234",
            "type": "stash",
            "repository": {"digest": "d" * 64, "label": "repo"},
            "git": {"object": "abcdef1234", "subject": "s"},
            "originalHead": "abcdef1234",
        }

    def _valid_worktree_receipt(self) -> dict:
        return {
            "schemaVersion": self.mod.SCHEMA_VERSION,
            "artifactId": "abcd1234",
            "type": "worktree",
            "repository": {"digest": "d" * 64, "label": "repo"},
            "git": {"path": "/some/where", "head": "abcdef1234"},
            "originalHead": "abcdef1234",
        }

    def test_validate_receipt_accepts_valid_and_rejects_malformed(self) -> None:
        m = self.mod
        m.validate_receipt(self._valid_stash_receipt())  # no raise
        m.validate_receipt(self._valid_worktree_receipt())  # no raise
        stash_cases = [
            {"schemaVersion": 2},
            {"artifactId": "xyz"},
            {"artifactId": 123},
            {"type": "bomb"},
            {"repository": {"label": "x"}},
            {"repository": "nope"},
            {"git": "nope"},
            {"originalHead": "zz"},
            {"originalHead": 5},
            {"git": {"object": "nothex", "subject": "s"}},
            {"secretToken": "leak"},
        ]
        for override in stash_cases:
            receipt = self._valid_stash_receipt()
            receipt.update(override)
            with self.subTest(override=override), self.assertRaises(m.RecoveryError):
                m.validate_receipt(receipt)
        worktree_cases = [
            {"git": {"head": "abcdef1234"}},  # no path
            {"git": {"path": "/x", "head": "zz"}},  # bad head
        ]
        for override in worktree_cases:
            receipt = self._valid_worktree_receipt()
            receipt.update(override)
            with self.subTest(override=override), self.assertRaises(m.RecoveryError):
                m.validate_receipt(receipt)

    def test_validate_worktree_containment_rejects_unsafe_paths(self) -> None:
        root = self.make_repo()
        m = self.mod
        digest = m.repository_identity(root)["digest"]
        base = m.worktree_base(digest, self.state_root)
        base.mkdir(parents=True, exist_ok=True)
        # A receipt with no path is rejected outright.
        with self.assertRaises(m.RecoveryError):
            m.validate_worktree_containment({"git": {}}, digest=digest, state_root=self.state_root)
        # A path outside the pack recovery base escapes containment.
        outside = Path(tempfile.mkdtemp(dir=self._tmp.name, prefix="escape-"))
        with self.assertRaises(m.RecoveryError):
            m.validate_worktree_containment(
                {"git": {"path": str(outside)}}, digest=digest, state_root=self.state_root
            )
        # A symlink that resolves inside the base is still refused.
        target = base / "real"
        target.mkdir()
        link = base / "link"
        link.symlink_to(target)
        with self.assertRaises(m.RecoveryError):
            m.validate_worktree_containment(
                {"git": {"path": str(link)}}, digest=digest, state_root=self.state_root
            )

    def test_parse_utc_covers_all_branches(self) -> None:
        m = self.mod
        self.assertIsNone(m.parse_utc(None))
        self.assertIsNone(m.parse_utc(123))
        self.assertIsNone(m.parse_utc("   "))
        self.assertIsNone(m.parse_utc("not-a-timestamp"))
        self.assertEqual(m.parse_utc("2026-07-28T12:00:00Z").utcoffset().total_seconds(), 0)
        self.assertEqual(m.parse_utc("2026-07-28T12:00:00").utcoffset().total_seconds(), 0)
        self.assertEqual(m.parse_utc("2026-07-28T12:00:00+02:00").hour, 10)  # normalized to UTC

    def test_resolve_state_root_covers_platform_branches(self) -> None:
        m = self.mod
        env_key = m.STATE_HOME_ENV
        # Explicit absolute override wins and is returned as-is.
        self.assertEqual(m.resolve_state_root(environ={env_key: "/abs/state"}), Path("/abs/state"))
        # A relative override is rejected.
        with self.assertRaises(m.RecoveryError):
            m.resolve_state_root(environ={env_key: "rel/state"})
        # An absolute XDG_STATE_HOME gains the product subdirectory.
        self.assertEqual(
            m.resolve_state_root(environ={"XDG_STATE_HOME": "/xdg"}, home=Path("/home/u"), os_name="posix"),
            Path("/xdg/sd-ai-command-pack"),
        )
        # A relative XDG value is ignored and the home default is used.
        self.assertEqual(
            m.resolve_state_root(environ={"XDG_STATE_HOME": "rel"}, home=Path("/home/u"), os_name="posix"),
            Path("/home/u/.local/state/sd-ai-command-pack"),
        )
        # Windows uses LOCALAPPDATA when it is absolute.
        self.assertEqual(
            m.resolve_state_root(environ={"LOCALAPPDATA": "C:\\Users\\u\\AppData\\Local"}, os_name="nt"),
            Path("C:/Users/u/AppData/Local/sd-ai-command-pack/state"),
        )
        # A relative LOCALAPPDATA is ignored and the home default is used.
        self.assertEqual(
            m.resolve_state_root(environ={"LOCALAPPDATA": "rel"}, home=Path("/home/u"), os_name="nt"),
            Path("/home/u/.local/state/sd-ai-command-pack"),
        )
        # POSIX default location.
        self.assertEqual(
            m.resolve_state_root(environ={}, home=Path("/home/u"), os_name="posix"),
            Path("/home/u/.local/state/sd-ai-command-pack"),
        )
        # A non-absolute home directory is rejected.
        with self.assertRaises(m.RecoveryError):
            m.resolve_state_root(environ={}, home=Path("rel-home"), os_name="posix")

    def test_ensure_private_directory_rejects_symlink(self) -> None:
        target = Path(tempfile.mkdtemp(dir=self._tmp.name, prefix="pd-"))
        link = Path(self._tmp.name) / "pd-link"
        link.symlink_to(target)
        with self.assertRaises(self.mod.RecoveryError):
            self.mod.ensure_private_directory(link)

    def test_reject_secret_keys_recurses_into_lists(self) -> None:
        with self.assertRaises(self.mod.RecoveryError):
            self.mod._reject_secret_keys({"items": [{"nested": {"password": "x"}}]})
        # A list with no secret-like keys is accepted.
        self.mod._reject_secret_keys({"items": [{"ok": 1}, "plain"]})

    def test_worktree_proof_flags_missing_path(self) -> None:
        root = self.make_repo()
        receipt = {"git": {"head": self.head(root)}, "cleanupPredicate": {}}
        proof = self.mod.worktree_cleanup_proof(root, receipt, Path(self._tmp.name) / "gone-wt")
        self.assertFalse(proof["safe"])
        self.assertIn("missing", proof["detail"])

    def test_stash_proof_flags_absent_and_unique(self) -> None:
        root = self.make_repo()
        absent = self.mod.stash_cleanup_proof(
            root, {"git": {"object": "abcdef1234"}, "cleanupPredicate": {}}, stashes={}
        )
        self.assertFalse(absent["safe"])
        self.assertIn("no longer present", absent["detail"])
        # A present stash with unique content is preserve-only.
        oid = self.make_stash(root, "sd-ai-command-pack recovery: unique")
        present = self.mod.stash_cleanup_proof(
            root, {"git": {"object": oid}, "cleanupPredicate": {}}, stashes={oid: {"ref": "stash@{0}"}}
        )
        self.assertFalse(present["safe"])
        self.assertIn("not provably redundant", present["detail"])

    # -- CLI: worktree registration, predicates, and cleanup -------------

    def test_cli_register_worktree_then_classify(self) -> None:
        root = self.make_repo()
        wt = self.add_worktree(root, "cli-wt")
        head = self.git_output(wt, "rev-parse", "HEAD")
        code, out = self._cli(
            "--state-home", str(self.state_root),
            "register", "--repo", str(root), "--type", "worktree",
            "--worktree-path", str(wt), "--head", head,
            "--created-by", "sd-recover", "--run-id", "r-wt",
            "--purpose", "isolated repair", "--original-head", self.head(root),
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["type"], "worktree")

        code, out = self._cli("--state-home", str(self.state_root), "classify", "--repo", str(root))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual([r["type"] for r in report["receipts"]], ["worktree"])

    def test_cli_register_stash_with_predicate_flags(self) -> None:
        root = self.make_repo()
        oid = self.make_stash(root, "sd-ai-command-pack recovery: guard")
        superseding = self.head(root)
        code, out = self._cli(
            "--state-home", str(self.state_root),
            "register", "--repo", str(root), "--type", "stash",
            "--object", oid, "--created-by", "sd-recover", "--run-id", "r-pred",
            "--purpose", "wip", "--original-head", self.head(root),
            "--superseded-by", superseding, "--retain-commit",
        )
        self.assertEqual(code, 0)
        rid = json.loads(out)["registered"]
        stored = json.loads((self.receipt_dir(root) / f"{rid}.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["cleanupPredicate"]["supersededBy"], superseding)
        self.assertTrue(stored["cleanupPredicate"]["retainCommit"])

    def test_cli_cleanup_dry_run_reports_without_deleting(self) -> None:
        root = self.make_repo()
        oid, _ = self.redundant_stash_receipt(root)
        code, out = self._cli(
            "--state-home", str(self.state_root),
            "cleanup", "--repo", str(root), "--mode", "housekeeping", "--dry-run",
        )
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertTrue(report["dryRun"])
        self.assertIn(oid, self.stash_oids(root))  # nothing deleted

    def test_cli_cleanup_owner_requires_artifact_id(self) -> None:
        root = self.make_repo()
        code, _ = self._cli(
            "--state-home", str(self.state_root),
            "cleanup", "--repo", str(root), "--mode", "owner",
        )
        self.assertEqual(code, 2)  # RecoveryError -> exit 2


if __name__ == "__main__":
    unittest.main()
