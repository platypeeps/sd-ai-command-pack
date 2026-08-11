"""Every row of design.md's conversion argument matrix, as its own test.

The matrix exists because dispatch order silently picks a winner when two
mutators are passed. A row that merely "does something reasonable" is a
failure here: the point is that the behavior is specified, and an unspecified
row is how a destructive selector gets quietly ignored.
"""

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
unittest = _support.unittest
Path = _support.Path
install = _support.install
InstallTestCase = _support.InstallTestCase
conversion = install.conversion


def parse(*argv: str):
    return install.parse_args(list(argv))


def rejection(*argv: str) -> str:
    """Parse and return the error text, asserting the parse was refused."""
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        try:
            parse(*argv)
        except SystemExit as exit_code:
            assert exit_code.code != 0, f"{argv} was accepted"
            return stderr.getvalue()
    raise AssertionError(f"{argv} was accepted")


VERDICT = ("--resweep-verdict", "verdict.json")


class RejectedRowTests(unittest.TestCase):
    def assert_names_both(self, message: str, *flags: str) -> None:
        for flag in flags:
            self.assertIn(flag, message, f"{flag} missing from: {message}")

    def test_opposing_mutators(self) -> None:
        message = rejection("target", "--thin", "--revert-thin", *VERDICT)
        self.assert_names_both(message, "--thin", "--revert-thin")

    def test_each_direction_rejects_remove(self) -> None:
        for direction, extra in (("--thin", VERDICT), ("--revert-thin", ())):
            message = rejection("target", direction, "--remove", *extra)
            self.assert_names_both(message, direction, "--remove")

    def test_each_direction_rejects_machine_scope(self) -> None:
        for direction, extra in (("--thin", VERDICT), ("--revert-thin", ())):
            message = rejection("target", direction, "--machine", *extra)
            self.assert_names_both(message, direction, "--machine")

    def test_each_direction_rejects_inspection(self) -> None:
        for direction, extra in (("--thin", VERDICT), ("--revert-thin", ())):
            for inspection in ("--status", "--check"):
                message = rejection("target", direction, inspection, *extra)
                self.assert_names_both(message, direction, inspection)

    def test_each_direction_rejects_configure_fleet(self) -> None:
        for direction, extra in (("--thin", VERDICT), ("--revert-thin", ())):
            message = rejection("target", direction, "--configure-fleet", *extra)
            self.assert_names_both(message, direction, "--configure-fleet")

    def test_each_direction_rejects_every_payload_selector(self) -> None:
        # Both directions, deliberately: the payload is derived from the
        # receipt and the partition, so a selector could only disagree with it.
        for direction, extra in (("--thin", VERDICT), ("--revert-thin", ())):
            for selector in (
                ("--platform", "claude"),
                ("--all",),
                ("--local-only",),
            ):
                message = rejection("target", direction, *selector, *extra)
                self.assert_names_both(message, direction, selector[0])

    def test_thin_without_a_verdict_is_refused(self) -> None:
        message = rejection("target", "--thin")
        self.assert_names_both(message, "--thin", "--resweep-verdict")

    def test_a_verdict_without_thin_is_refused(self) -> None:
        message = rejection("target", "--resweep-verdict", "verdict.json")
        self.assert_names_both(message, "--resweep-verdict", "--thin")

    def test_force_on_revert_is_refused(self) -> None:
        message = rejection("target", "--revert-thin", "--force")
        self.assert_names_both(message, "--force", "--revert-thin")

    def test_consumer_outside_a_conversion_is_refused(self) -> None:
        for extra in ((), ("--remove",), ("--machine",), ("--check",), ("--status",)):
            message = rejection("target", "--consumer", "demo", *extra)
            self.assert_names_both(message, "--consumer")


class AllowedRowTests(unittest.TestCase):
    def test_thin_with_a_verdict_parses(self) -> None:
        args = parse("target", "--thin", *VERDICT)
        self.assertTrue(args.thin)
        self.assertEqual(args.resweep_verdict.name, "verdict.json")

    def test_revert_parses_alone(self) -> None:
        self.assertTrue(parse("target", "--revert-thin").revert_thin)

    def test_consumer_is_allowed_with_either_direction(self) -> None:
        self.assertEqual(parse("target", "--thin", *VERDICT,
                               "--consumer", "demo").consumer, "demo")
        self.assertEqual(parse("target", "--revert-thin",
                               "--consumer", "demo").consumer, "demo")

    def test_dry_run_and_backup_are_allowed_in_both_directions(self) -> None:
        for direction, extra in (("--thin", VERDICT), ("--revert-thin", ())):
            args = parse("target", direction, "--dry-run", "--backup", *extra)
            self.assertTrue(args.dry_run and args.backup)

    def test_force_is_allowed_with_thin(self) -> None:
        self.assertTrue(parse("target", "--thin", *VERDICT, "--force").force)


class ConvertedFixtureTests(InstallTestCase):
    """The matrix above is about argv. This is about a tree on disk.

    Round 18's probe ran `--remove` against a converted consumer and found
    three things false that everyone assumed were true: it exited zero, it
    rewrote `.claude/settings.json`, and it deleted the provenance that was
    the only record the consumer had ever been thin. A parse-level refusal
    cannot assert any of them, because `--remove` alone is a legal argv --
    the refusal is a property of the target, not of the arguments.
    """

    SETTINGS = '{"hooks": {"kept": "by the consumer"}}\n'

    def make_thin_consumer(self) -> Path:
        root = self.make_repo(".claude")
        self.assertEqual(self.run_install(root).returncode, 0)
        # Written by the fixture, not by the installer: today's `install.py`
        # never touches `settings.json` at all. Step 6's conversion is the
        # first code that will, so the byte-equality assertion below is a
        # guard registered ahead of the mutator that can break it, not a
        # claim about a merge that exists now.
        (root / ".claude/settings.json").write_text(self.SETTINGS, encoding="utf-8")
        provenance = root / install.PROVENANCE_FILE
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        payload["mode"] = conversion.THIN_MODE
        provenance.write_text(json.dumps(payload), encoding="utf-8")
        return root

    def test_remove_on_a_converted_consumer_changes_nothing(self) -> None:
        root = self.make_thin_consumer()
        settings = root / ".claude/settings.json"
        before = settings.read_bytes()
        provenance = root / install.PROVENANCE_FILE

        result = self.run_install(root, "--remove")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(
            settings.read_bytes(),
            before,
            "--remove refused and rewrote settings.json anyway",
        )
        self.assertTrue(
            provenance.is_file(),
            "--remove refused and deleted the receipt that proves it was thin",
        )

    def test_the_same_removal_on_a_fat_consumer_still_works(self) -> None:
        # Without this, the test above passes on an installer that refuses
        # every `--remove`. The refusal has to be about the pin, not about
        # the command.
        root = self.make_thin_consumer()
        provenance = root / install.PROVENANCE_FILE
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        del payload["mode"]
        provenance.write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(self.run_install(root, "--remove").returncode, 0)
        self.assertFalse(provenance.exists())

    def test_the_refusal_points_at_the_undo(self) -> None:
        # A refusal with no way forward is how an operator reaches for
        # `--force`, which is the one thing that must not work here.
        result = self.run_install(self.make_thin_consumer(), "--remove")
        self.assertIn("--revert-thin", result.stdout)


if __name__ == "__main__":
    unittest.main()
