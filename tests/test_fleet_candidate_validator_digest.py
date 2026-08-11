from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

mock = _support.mock
tempfile = _support.tempfile
Path = _support.Path
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

FLEET_LIB = PACK_ROOT / "scripts/sd_ai_command_pack_fleet_lib.py"
RELEASE_IDENTITY = PACK_ROOT / ".github/scripts/release_identity.py"


class CandidateValidatorDigestTests(InstallTestCase):
    """The digest that lets release-prep see a changed candidate validator.

    The payload digest reads only manifest-declared sources, and
    `scripts/sd-ai-command-pack-fleet-candidate-check.py` has no manifest row.
    Without this digest the candidate ledger stays current across an edit to
    the validator, so release-prep skips the very check the edit changed.
    """

    def load_fleet(self, suffix: str = ""):
        return self.load_module_from_path(
            FLEET_LIB,
            f"validator_digest_fleet_lib{suffix}",
        )

    def load_identity(self):
        return self.load_module_from_path(
            RELEASE_IDENTITY,
            "validator_digest_release_identity",
        )

    def write_sources(self, root: Path, contents: dict[str, str]) -> None:
        for source, text in contents.items():
            path = root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def make_tree(self, fleet, contents: dict[str, str] | None = None) -> Path:
        root = Path(self.make_temp_dir())
        sources = {
            source: f"# {source}\n" for source in fleet.CANDIDATE_VALIDATOR_SOURCES
        }
        self.write_sources(root, contents if contents is not None else sources)
        return root

    def make_temp_dir(self) -> str:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-validator-digest-")
        self.addCleanup(tempdir.cleanup)
        return tempdir.name

    # --- digest properties -------------------------------------------------

    def test_digest_is_stable_across_repeated_reads(self) -> None:
        fleet = self.load_fleet()
        root = self.make_tree(fleet)

        first = fleet.filesystem_candidate_validator_digest(root)
        second = fleet.filesystem_candidate_validator_digest(root)

        self.assertEqual(first, second)
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")

    def test_digest_changes_when_a_source_changes(self) -> None:
        fleet = self.load_fleet()
        root = self.make_tree(fleet)
        before = fleet.filesystem_candidate_validator_digest(root)

        source = root / fleet.CANDIDATE_VALIDATOR_SOURCES[0]
        source.write_text(source.read_text(encoding="utf-8") + "# edit\n", encoding="utf-8")

        self.assertNotEqual(before, fleet.filesystem_candidate_validator_digest(root))

    def test_digest_is_path_qualified(self) -> None:
        """Swapping two sources' contents must not preserve the digest.

        The digest feeds each path's bytes before its content hash for exactly
        this case: a rename that exchanges two files would otherwise produce an
        identical digest over an unchanged multiset of contents.
        """
        fleet = self.load_fleet()
        sources = ("scripts/first.py", "scripts/second.py")
        root = self.make_tree(fleet, {sources[0]: "alpha\n", sources[1]: "beta\n"})
        swapped = self.make_tree(fleet, {sources[0]: "beta\n", sources[1]: "alpha\n"})

        with mock.patch.object(fleet, "CANDIDATE_VALIDATOR_SOURCES", sources):
            original = fleet.filesystem_candidate_validator_digest(root)
            exchanged = fleet.filesystem_candidate_validator_digest(swapped)

        self.assertNotEqual(original, exchanged)

    def test_digest_ignores_the_executable_bit(self) -> None:
        """The deliberate departure from `payload_digest`.

        The validator is invoked as `sys.executable <path>`, never as a bare
        executable, so its permission bit changes no behavior. Hashing it would
        make `chmod +x` invalidate a ledger whose validator is byte-identical.
        """
        fleet = self.load_fleet()
        root = self.make_tree(fleet)
        before = fleet.filesystem_candidate_validator_digest(root)

        source = root / fleet.CANDIDATE_VALIDATOR_SOURCES[0]
        source.chmod(0o755)

        self.assertEqual(before, fleet.filesystem_candidate_validator_digest(root))

    def test_digest_resolves_a_symlinked_root(self) -> None:
        """A symlinked prefix is containment-legal, not an escape.

        macOS hands every temporary directory out under `/var`, itself a
        symlink to `/private/var`. Comparing a resolved source path against an
        unresolved root would reject every such tree.
        """
        fleet = self.load_fleet()
        root = self.make_tree(fleet)
        link = Path(self.make_temp_dir()) / "link"
        link.symlink_to(root, target_is_directory=True)

        self.assertEqual(
            fleet.filesystem_candidate_validator_digest(root),
            fleet.filesystem_candidate_validator_digest(link),
        )

    # --- error matrix ------------------------------------------------------

    def test_working_tree_source_absent_fails_closed(self) -> None:
        fleet = self.load_fleet()
        root = self.make_tree(fleet)
        (root / fleet.CANDIDATE_VALIDATOR_SOURCES[0]).unlink()

        with self.assertRaises(fleet.FleetConfigError) as raised:
            fleet.filesystem_candidate_validator_digest(root)

        self.assertIn("candidate validator source", str(raised.exception))
        self.assertIn(fleet.CANDIDATE_VALIDATOR_SOURCES[0], str(raised.exception))

    def test_source_escaping_the_root_fails_closed(self) -> None:
        fleet = self.load_fleet()
        outside = Path(self.make_temp_dir()) / "outside.py"
        outside.write_text("# outside\n", encoding="utf-8")
        root = self.make_tree(fleet, {})
        escape = root / "scripts/escape.py"
        escape.parent.mkdir(parents=True, exist_ok=True)
        escape.symlink_to(outside)

        with mock.patch.object(
            fleet, "CANDIDATE_VALIDATOR_SOURCES", ("scripts/escape.py",)
        ):
            with self.assertRaises(fleet.FleetConfigError) as raised:
                fleet.filesystem_candidate_validator_digest(root)

        self.assertIn("candidate validator source", str(raised.exception))

    def ledger(self, **overrides):
        payload = {
            "schemaVersion": 3,
            "validatedAt": "2026-08-11T00:00:00Z",
            "packVersion": "1.0.0",
            "payloadDigest": "sha256:payload",
            "fleetManifestDigest": "sha256:fleet",
            "validatorDigest": "sha256:validator",
            "consumers": [],
        }
        payload.update(overrides)
        return payload

    def validate(self, fleet, ledger):
        return fleet.validate_candidate_ledger(
            ledger,
            expected_version="1.0.0",
            expected_payload_digest="sha256:payload",
            expected_fleet_digest="sha256:fleet",
            expected_validator_digest="sha256:validator",
            consumers=[],
        )

    def test_matching_ledger_reports_no_errors(self) -> None:
        """The documented skip stands when all four fields agree."""
        fleet = self.load_fleet()

        self.assertEqual(self.validate(fleet, self.ledger()), [])

    def test_previous_schema_version_is_stale(self) -> None:
        fleet = self.load_fleet()
        ledger = self.ledger(schemaVersion=2)
        ledger.pop("validatorDigest")

        errors = self.validate(fleet, ledger)

        self.assertTrue(any("schemaVersion must be 3" in error for error in errors), errors)

    def test_absent_validator_digest_is_stale(self) -> None:
        fleet = self.load_fleet()
        ledger = self.ledger()
        ledger.pop("validatorDigest")

        errors = self.validate(fleet, ledger)

        self.assertTrue(any("validatorDigest is None" in error for error in errors), errors)

    def test_differing_validator_digest_is_stale(self) -> None:
        fleet = self.load_fleet()

        errors = self.validate(fleet, self.ledger(validatorDigest="sha256:other"))

        self.assertTrue(any("validatorDigest" in error for error in errors), errors)

    # --- commit-scoped loader ----------------------------------------------

    def make_validator_repo(self, fleet) -> tuple[Path, str]:
        root = self.make_git_repo_without_trellis()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.write_sources(
            root,
            {source: f"# {source}\n" for source in fleet.CANDIDATE_VALIDATOR_SOURCES},
        )
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "validator baseline")
        return root, self.git_output(root, "rev-parse", "HEAD")

    def test_commit_digest_reads_the_commit_not_the_working_tree(self) -> None:
        """PRD criterion 3.

        `verify_candidate_ledger_at_commit` reads its ledger from a commit, so
        its expected digest must come from the same commit. Digesting the
        working tree instead would report an ordinary post-release edit to the
        validator as tampered release evidence.
        """
        fleet = self.load_fleet()
        identity = self.load_identity()
        root, commit = self.make_validator_repo(fleet)
        committed = fleet.filesystem_candidate_validator_digest(root)

        source = root / fleet.CANDIDATE_VALIDATOR_SOURCES[0]
        source.write_text("# edited after the release\n", encoding="utf-8")
        working_tree = fleet.filesystem_candidate_validator_digest(root)

        at_commit = identity.candidate_validator_digest_at_commit(root, commit)

        self.assertNotEqual(committed, working_tree)
        self.assertEqual(at_commit, committed)

    def test_commit_digest_fails_closed_on_a_source_absent_at_the_commit(self) -> None:
        """Never fall back to the working tree for a source the commit lacks."""
        fleet = self.load_fleet()
        identity = self.load_identity()
        root, _commit = self.make_validator_repo(fleet)
        self.run_git(root, "rm", "-q", fleet.CANDIDATE_VALIDATOR_SOURCES[0])
        self.run_git(root, "commit", "-m", "drop the validator")
        without = self.git_output(root, "rev-parse", "HEAD")

        # The working tree of the *checkout* still has no source either, but the
        # point is the diagnostic: it must name the validator, not a manifest row
        # that has never existed.
        with self.assertRaises(identity.ReleaseIdentityError) as raised:
            identity.candidate_validator_digest_at_commit(root, without)

        message = str(raised.exception)
        self.assertIn("candidate validator source is absent", message)
        self.assertIn(fleet.CANDIDATE_VALIDATOR_SOURCES[0], message)

    def test_commit_digest_keeps_a_non_absent_reason_for_the_validator(self) -> None:
        """Absence is one of six ways the load fails; the other five survive.

        The loader is shared with the payload digest, so its subject is renamed
        rather than its exception re-wrapped. Wrapping at the call site could
        only assert one reason for all of them, and reporting a path that is
        occupied by a file as "absent" sends a reader looking for the wrong
        defect entirely.
        """
        fleet = self.load_fleet()
        identity = self.load_identity()
        root, _commit = self.make_validator_repo(fleet)
        source = fleet.CANDIDATE_VALIDATOR_SOURCES[0]
        directory = source.split("/", 1)[0]

        # Occupy the validator's parent directory with a regular file, so the
        # source exists as a path prefix but cannot be traversed.
        self.run_git(root, "rm", "-r", "-q", directory)
        (root / directory).write_text("not a directory\n", encoding="utf-8")
        self.run_git(root, "add", directory)
        self.run_git(root, "commit", "-m", "occupy the validator's directory")
        occupied = self.git_output(root, "rev-parse", "HEAD")

        with self.assertRaises(identity.ReleaseIdentityError) as raised:
            identity.candidate_validator_digest_at_commit(root, occupied)

        message = str(raised.exception)
        self.assertIn("candidate validator source traverses a non-directory", message)
        self.assertNotIn("is absent", message)
        self.assertNotIn("pack manifest source", message)
        self.assertIn(source, message)


if __name__ == "__main__":
    unittest.main()
