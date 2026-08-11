"""`install.py TARGET --thin` end to end, one refusal per row.

The resweep is doubled here, deliberately and narrowly. It has its own 27
fixture tests in `tests/test_thin_resweep.py`, and the verdict-binding rule
has its own in `tests/test_thin_plan.py`; what is under test in this file is
the *orchestration* -- that every refusal happens before the first byte, and
in the order that makes each one reachable.

There is a second reason, and it is a finding rather than a convenience: no
real consumer produces a `clear` verdict today. Round 20 measured all eight
as `blocked`, and a freshly installed fixture is blocked for the same reason
-- the pack's own surviving surfaces still cite paths a conversion removes.
Repointing them is the sibling task `08-10-thin-prompt-surface-repoint`.
Until it lands, an end-to-end conversion driven by the real resweep is not
reachable, and pretending otherwise by weakening the binding would remove
the check that makes the verdict mean anything.
"""

from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
mock = _support.mock
unittest = _support.unittest
Path = _support.Path
install = _support.install
InstallTestCase = _support.InstallTestCase

from installer import conversion, fileops, thin  # noqa: E402


class FakeResweep:
    """A resweep whose answers the test controls.

    Only three surfaces are used by the conversion path: `resolve_consumer`,
    `resweep_consumer`, and `SCHEMA_VERSION` through the document itself.
    """

    SCHEMA_VERSION = 1

    def __init__(self, checkout: Path, document: dict, *, entry: dict | None = None):
        self.checkout = checkout
        self.document = document
        self.entry = entry if entry is not None else {"platforms": ["claude"]}
        self.resolve_error: SystemExit | None = None

    def resolve_consumer(self, name, repo):
        if self.resolve_error is not None:
            raise self.resolve_error
        return self.entry, Path(repo)

    def resweep_consumer(self, name, repo=None):
        return dict(self.document)


def clear_document(**overrides) -> dict:
    document = {
        "schemaVersion": 1,
        "kind": "thin-resweep-verdict",
        "verdict": "clear",
        "reasons": [],
        "consumer": "demo",
        "repo": "/checkouts/demo",
        "head": "a" * 40,
        "indexDigest": "sha256:index",
        "worktreeClean": True,
        "classifierDigest": "sha256:classifier",
    }
    document.update(overrides)
    return document


class ThinCommandTests(InstallTestCase):
    def setUp(self) -> None:
        self.root = self.make_repo(".claude")
        self.assertEqual(self.run_install(self.root).returncode, 0)
        self.verdict = self.root / "verdict.json"
        self.write_verdict(clear_document())

    def write_verdict(self, document) -> None:
        self.verdict.write_text(
            document if isinstance(document, str) else json.dumps(document),
            encoding="utf-8",
        )

    def run_thin(self, *extra: str, resweep: FakeResweep | None = None):
        double = resweep or FakeResweep(self.root, clear_document())
        with mock.patch.object(thin, "load_resweep_module", return_value=double):
            return self.run_install_inproc(
                self.root,
                "--thin",
                "--resweep-verdict",
                str(self.verdict),
                *extra,
                skip_diff_check=False,
            )

    def assert_refused(self, result, fragment: str) -> None:
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("nothing was written", result.stdout)
        self.assertIn(fragment, result.stdout)
        self.assertEqual(
            conversion.thin_pin_state(self.root),
            conversion.PIN_STATE_FAT,
            "a refusal left the consumer converted",
        )

    # -- refusals -----------------------------------------------------------

    def test_an_unknown_consumer_is_refused(self) -> None:
        double = FakeResweep(self.root, clear_document())
        double.resolve_error = SystemExit("error: nobody is not a registered consumer")
        result = self.run_thin(resweep=double)
        self.assertEqual(result.returncode, 2)
        self.assertIn("not a registered consumer", result.stdout)

    def test_a_missing_verdict_is_refused(self) -> None:
        self.verdict.unlink()
        self.assert_refused(self.run_thin(), "run the thin resweep first")

    def test_an_unreadable_verdict_is_refused_distinctly(self) -> None:
        self.write_verdict("{truncated")
        self.assert_refused(self.run_thin(), "cannot be read as a verdict document")

    def test_a_blocked_verdict_is_refused(self) -> None:
        blocked = clear_document(verdict="blocked", reasons=["7 references"])
        self.write_verdict(blocked)
        self.assert_refused(
            self.run_thin(resweep=FakeResweep(self.root, blocked)), "7 references"
        )

    def test_a_verdict_that_no_longer_binds_is_refused(self) -> None:
        # The tree moved under an otherwise clear verdict.
        self.assert_refused(
            self.run_thin(
                resweep=FakeResweep(self.root, clear_document(head="b" * 40))
            ),
            "head changed since the resweep",
        )

    def test_a_settings_collision_is_refused_before_any_deletion(self) -> None:
        settings = self.root / thin.CLAUDE_SETTINGS_FILE
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(
            json.dumps({"enabledPlugins": {"sd@sd-ai-command-pack": False}}),
            encoding="utf-8",
        )
        before = settings.read_bytes()
        witness = self.root / ".claude/commands/sd/check.md"

        self.assert_refused(self.run_thin(), "enabledPlugins")
        self.assertEqual(settings.read_bytes(), before)
        self.assertTrue(witness.exists(), "a settings refusal deleted payload")

    def test_removal_drift_is_refused_and_force_overrides_it(self) -> None:
        drifted = self.root / ".claude/commands/sd/check.md"
        drifted.write_text("edited by the consumer\n", encoding="utf-8")

        self.assert_refused(self.run_thin(), "--force")
        self.assertEqual(
            drifted.read_text(encoding="utf-8"), "edited by the consumer\n"
        )

        forced = self.run_thin("--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        self.assertFalse(drifted.exists())

    def test_a_stale_consumer_is_refused_rather_than_topped_up(self) -> None:
        # A conversion that added the missing targets would be a partial
        # installer: a two-root command writing new files into a consumer
        # while deleting 179 others, in a PR whose reviewers were told it only
        # removes -- and the resweep verdict would not cover the additions.
        # Both receipts, kept consistent: editing one alone is a *different*
        # refusal (the receipts-disagree row below), and running only that one
        # would leave the staleness check itself untested.
        for receipt in (install.PROVENANCE_FILE, install.PACK_MANIFEST_FILE):
            path = self.root / receipt
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["version"] = "0.0.1"
            path.write_text(json.dumps(payload), encoding="utf-8")
        self.assert_refused(self.run_thin(), "install.py TARGET")

    def test_receipts_that_contradict_each_other_are_refused(self) -> None:
        # Found while writing the test above: a conversion rewrites all three
        # receipts from the state of these ones, so contradictory inputs
        # produce a thin receipt certifying a tree nobody measured.
        provenance = self.root / install.PROVENANCE_FILE
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        payload["version"] = "0.0.1"
        provenance.write_text(json.dumps(payload), encoding="utf-8")
        self.assert_refused(self.run_thin(), "versions do not match")

    def test_a_missing_receipt_is_refused(self) -> None:
        (self.root / install.INSTALLED_TARGETS_FILE).unlink()
        self.assert_refused(self.run_thin(), "installed-targets")

    def test_an_unclassifiable_installed_target_is_refused(self) -> None:
        receipt = self.root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            receipt.read_text(encoding="utf-8") + "docs/invented-by-hand.md\n",
            encoding="utf-8",
        )
        (self.root / "docs/invented-by-hand.md").write_text("x\n", encoding="utf-8")
        self.assert_refused(self.run_thin(), "no partition row")

    def test_an_unwritable_target_is_refused(self) -> None:
        self.root.chmod(0o500)
        self.addCleanup(self.root.chmod, 0o700)
        self.assert_refused(self.run_thin(), "not writable")

    def test_an_unwritable_pack_checkout_is_refused_before_the_target_is_touched(
        self,
    ) -> None:
        # Doubled rather than chmod'ed: the pack root here is this repository.
        # The probe itself has direct tests in `tests/test_thin_plan.py`; what
        # this row owns is that the *registry* root is probed at all, before
        # 166 consumer deletions rather than after them.
        def unwritable(root, label):
            return f"{label} {root} is not writable" if label == "pack root" else None

        witness = self.root / ".claude/commands/sd/check.md"
        with mock.patch.object(thin, "writability_reason", side_effect=unwritable):
            result = self.run_thin()
        self.assert_refused(result, "pack root")
        self.assertTrue(witness.exists())

    def test_a_pack_checkout_that_is_not_this_repository_is_refused(self) -> None:
        with mock.patch.object(
            install, "_origin_url", return_value="git@github.com:someone/else.git"
        ):
            self.assert_refused(self.run_thin(), "someone/else")

    def test_a_receipt_missing_a_retained_target_is_refused(self) -> None:
        # R19-C2's exact assertion, which the version comparison only
        # approximates: a consumer whose version matches but whose tree was
        # refreshed against a partially applied install. Converting it would
        # leave `--check` reporting refresh-required immediately, for a file
        # the conversion never had a chance to keep.
        receipt = self.root / install.INSTALLED_TARGETS_FILE
        entries = receipt.read_text(encoding="utf-8").split()
        kept = ".gito/config.toml"
        self.assertIn(kept, entries)
        receipt.write_text(
            "\n".join(entry for entry in entries if entry != kept) + "\n",
            encoding="utf-8",
        )
        self.assert_refused(self.run_thin(), kept)

    def test_a_tracked_pack_like_file_absent_from_the_receipt_is_refused(self) -> None:
        # Every other receipt check reads outward from the receipt and asks
        # whether each path it lists is accounted for. This file is the other
        # direction, and it is invisible to all of them: the plan is computed
        # *from* the receipt, so a pack-shaped file the receipt never listed is
        # in neither `keep` nor `delete`. Conversion walks past it, every
        # receipt comparison still passes, and it survives into the thin tree
        # as an orphan -- which is the whole reason the residual is supposed to
        # be enumerable.
        #
        # Tracked, not gitignored: the audit tolerates a gitignored local-only
        # adapter by policy, so an ignored file here would be a warning and
        # would prove the opposite of the criterion.
        stray = self.root / ".claude/skills/sd-ghost/SKILL.md"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("# not from any install\n", encoding="utf-8")
        self.run_git(self.root, "add", "-A")
        receipt = self.root / install.INSTALLED_TARGETS_FILE
        self.assertNotIn(
            ".claude/skills/sd-ghost/SKILL.md",
            receipt.read_text(encoding="utf-8").split(),
        )

        self.assert_refused(self.run_thin(), ".claude/skills/sd-ghost/SKILL.md")

    def test_the_structural_refusal_does_not_swallow_the_force_override(self) -> None:
        # The boundary this check has to respect. Folding the audit's
        # provenance half in here would refuse on per-file content drift, and
        # overriding that drift is exactly what `--force` is for -- so a
        # drifted tree with no structural damage must still convert under
        # `--force` rather than being refused by the new preflight.
        target = self.root / ".gito/config.toml"
        target.write_text("# edited by the consumer\n", encoding="utf-8")
        self.run_git(self.root, "add", "-A")

        result = self.run_thin("--force")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN)

    # -- the happy path -----------------------------------------------------

    def test_a_dry_run_writes_nothing_and_names_the_plan(self) -> None:
        result = self.run_thin("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("would-delete", result.stdout)
        self.assertEqual(conversion.thin_pin_state(self.root), conversion.PIN_STATE_FAT)
        self.assertFalse((self.root / thin.CLAUDE_SETTINGS_FILE).exists())

    def test_a_dry_run_over_an_existing_settings_file_announces_no_creation(
        self,
    ) -> None:
        # `createdFile` is what tells revert whether it may delete the file,
        # so the dry run has to distinguish "I will create this" from "I will
        # add keys to yours" -- and the fixture's default is the first.
        settings = self.root / thin.CLAUDE_SETTINGS_FILE
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        result = self.run_thin("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("would-create ", result.stdout)
        self.assertIn("would-set      enabledPlugins.", result.stdout)

    def test_a_retired_target_is_announced_in_its_own_category(self) -> None:
        # Retire is not delete: `retire_stale_targets` preserves a drifted
        # retired file and keeps going, so folding the two into one printed
        # category would hide the bucket whose failure mode is silent.
        retired = sorted(install.RETIRED_TARGETS)[0]
        path = self.root / retired
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("legacy\n", encoding="utf-8")
        receipt = self.root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            receipt.read_text(encoding="utf-8") + f"{retired}\n", encoding="utf-8"
        )
        # Vouched, so the row exercises the retire *category* rather than the
        # drift refusal that guards it -- which has its own row above.
        provenance = self.root / install.PROVENANCE_FILE
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        # `sha256_file`'s prefixed form, which is what removal compares
        # against -- `source_digest` returns the bare hex and would silently
        # never match.
        payload["files"][retired] = fileops.sha256_file(path)[0]
        provenance.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        result = self.run_thin("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"would-retire   {retired}", result.stdout)
        self.assertNotIn(f"would-delete   {retired}", result.stdout)

    def announced(self, stdout: str, prefix: str) -> set[str]:
        return {
            line.split(maxsplit=1)[1].strip()
            for line in stdout.splitlines()
            if line.startswith(prefix)
        }

    def test_the_dry_run_set_matches_the_executed_run_in_all_six_categories(
        self,
    ) -> None:
        # "The tree was unchanged" is satisfied by an empty or wrong printout,
        # and a delete-only comparison passes while the settings and registry
        # writes go unannounced. So each category is compared against what the
        # real run actually did.
        flips: list[tuple[str, str]] = []
        with mock.patch.object(
            thin,
            "flip_registry_mode",
            side_effect=lambda root, consumer, mode="thin": flips.append(
                (consumer, mode)
            ),
        ):
            dry = self.run_thin("--dry-run", "--consumer", "demo")
            self.assertEqual(dry.returncode, 0, dry.stdout)
            before = set(self.installed_paths())
            real = self.run_thin("--consumer", "demo")
        self.assertEqual(real.returncode, 0, real.stdout)

        removed = before - set(self.installed_paths())
        announced_removals = (
            self.announced(dry.stdout, "would-delete")
            | self.announced(dry.stdout, "would-retire")
        )
        self.assertTrue(announced_removals, "the dry run announced no removals")

        # A stripped file can also vanish, and `.gitignore` does here: the
        # managed block was its entire contents. So the strip category is
        # announced separately and its disappearances are accounted for
        # rather than swept into the delete comparison.
        strips = self.announced(dry.stdout, "would-strip")
        self.assertEqual(strips, {".gitignore"})
        emptied = {entry for entry in strips if not (self.root / entry).exists()}
        self.assertEqual(announced_removals | emptied, removed)
        self.assertEqual(
            self.announced(dry.stdout, "would-rewrite"),
            {
                install.PACK_MANIFEST_FILE.as_posix(),
                install.INSTALLED_TARGETS_FILE.as_posix(),
                install.PROVENANCE_FILE.as_posix(),
            },
        )
        settings = json.loads(
            (self.root / thin.CLAUDE_SETTINGS_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(
            self.announced(dry.stdout, "would-set"),
            {
                f"{container}.{key}"
                for container, entries in settings.items()
                for key in entries
            },
        )
        self.assertEqual(
            self.announced(dry.stdout, "would-create"),
            {thin.CLAUDE_SETTINGS_FILE.as_posix()},
        )
        self.assertEqual(self.announced(dry.stdout, "would-registry"), {"demo -> thin"})
        self.assertEqual(flips, [("demo", "thin")])

    def installed_paths(self) -> list[str]:
        return [
            path.relative_to(self.root).as_posix()
            for path in sorted(self.root.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(self.root).parts
        ]

    def test_a_conversion_converts(self) -> None:
        result = self.run_thin()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN)
        self.assertFalse((self.root / ".claude/commands/sd/check.md").exists())
        self.assertTrue((self.root / install.PROVENANCE_FILE).is_file())
        self.assertFalse((self.root / thin.REMOVAL_INVENTORY_FILE).exists())

    def test_a_registry_that_cannot_be_written_reports_which_half_landed(self) -> None:
        # Both roots are probed before either is touched, so reaching here
        # means something changed underneath a validated plan. There is no
        # rollback and inventing one would be worse than the skew -- but
        # exiting zero over it would be worse than both.
        with mock.patch.object(
            thin, "flip_registry_mode", side_effect=OSError("read-only file system")
        ):
            result = self.run_thin("--consumer", "demo")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("converted and the registry still reads fat", result.stdout)
        self.assertIn("nothing is rolled back", result.stdout)
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )
        self.assertFalse((self.root / ".claude/commands/sd/check.md").exists())

    def test_the_pin_conversion_writes_is_the_pin_later_commands_read(self) -> None:
        # The two halves meeting. Without this the pin is written and never
        # enforced. `--remove` is the reader that still refuses outright: it
        # has no thin form, and running it would leave a live plugin, no
        # receipts, and a registry saying `thin`. The ordinary install is the
        # reader that changed in step 9b -- it refreshes rather than refuses,
        # because a fleet sweep runs exactly that command -- and it is proved
        # here to read the same pin by leaving the machine payload deleted.
        self.assertEqual(self.run_thin().returncode, 0)

        refused = self.run_install(self.root, "--remove", "--skip-diff-check")
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("--revert-thin", refused.stdout)

        refreshed = self.run_install(self.root)
        self.assertEqual(refreshed.returncode, 0, refreshed.stdout)
        self.assertEqual(
            conversion.thin_pin_state(self.root), conversion.PIN_STATE_THIN
        )
        self.assertFalse((self.root / ".claude/commands/sd/check.md").exists())


if __name__ == "__main__":
    unittest.main()
