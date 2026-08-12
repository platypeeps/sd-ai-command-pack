from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

hashlib = _support.hashlib
json = _support.json
subprocess = _support.subprocess
sys = _support.sys
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
install = _support.install
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

providerhistory = install.fileops.providerhistory if hasattr(
    install.fileops, "providerhistory"
) else __import__("installer.providerhistory", fromlist=["providerhistory"])

GITO_TARGET = ".gito/config.toml"
PRISM_TARGET = ".prism/rules.json"
OLD_DEFAULT = b"# a default this pack shipped once\n"


def history_for(**targets: bytes) -> providerhistory.ProviderConfigHistory:
    """A history claiming the pack shipped exactly these bytes per target."""

    return providerhistory.ProviderConfigHistory(
        digests_by_target={
            target: frozenset({hashlib.sha256(content).hexdigest()})
            for target, content in targets.items()
        }
    )


class ShippedDefaultPredicateTests(InstallTestCase):
    """The one question the installer could not previously answer: did *we*
    write these bytes, or did the consumer?"""

    def pack_file(self, target: str) -> object:
        _, files = install.load_manifest()
        return next(file for file in files if file.target.as_posix() == target)

    def test_bytes_the_pack_shipped_are_not_a_local_decision(self) -> None:
        file = self.pack_file(GITO_TARGET)
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=history_for(**{GITO_TARGET: OLD_DEFAULT}),
        ):
            self.assertTrue(
                install.fileops.is_previously_shipped_default(
                    file,
                    OLD_DEFAULT,
                    source=file.source,
                    installed_content=file.source.read_bytes(),
                )
            )

    def test_bytes_matching_no_shipped_digest_are_left_alone(self) -> None:
        # The whole population this policy exists for. Six of eight consumers'
        # .prism/rules.json were in exactly this state when the feature was
        # written -- their own `required` rules, not a stale copy of ours.
        file = self.pack_file(PRISM_TARGET)
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=history_for(**{PRISM_TARGET: OLD_DEFAULT}),
        ):
            self.assertFalse(
                install.fileops.is_previously_shipped_default(
                    file,
                    OLD_DEFAULT + b"a rule this team wrote\n",
                    source=file.source,
                    installed_content=file.source.read_bytes(),
                )
            )

    def test_force_preserved_membership_does_not_veto_a_shipped_default(self) -> None:
        # Both configs are in FORCE_PRESERVED_TARGETS *and* carry
        # `if-not-exists`. Reading that membership as an extra exclusion makes
        # this feature inert for its entire population, which is exactly what
        # the first draft did.
        file = self.pack_file(GITO_TARGET)
        self.assertIn(file.target, install.FORCE_PRESERVED_TARGETS)
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=history_for(**{GITO_TARGET: OLD_DEFAULT}),
        ):
            self.assertTrue(
                install.fileops.is_previously_shipped_default(
                    file,
                    OLD_DEFAULT,
                    source=file.source,
                    installed_content=file.source.read_bytes(),
                )
            )

    def test_a_force_preserved_target_without_the_policy_stays_preserved(self) -> None:
        file = self.pack_file(".github/PULL_REQUEST_TEMPLATE.md")
        self.assertIn(file.target, install.FORCE_PRESERVED_TARGETS)
        self.assertNotEqual(file.install, install.IF_NOT_EXISTS)
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=history_for(
                **{".github/PULL_REQUEST_TEMPLATE.md": OLD_DEFAULT}
            ),
        ):
            self.assertFalse(
                install.fileops.is_previously_shipped_default(
                    file,
                    OLD_DEFAULT,
                    source=file.source,
                    installed_content=file.source.read_bytes(),
                )
            )

    def test_an_unavailable_history_preserves_rather_than_guesses(self) -> None:
        file = self.pack_file(GITO_TARGET)
        unavailable = providerhistory.ProviderConfigHistory(
            digests_by_target={},
            unavailable_reason="history is missing",
        )
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=unavailable,
        ):
            self.assertFalse(
                install.fileops.is_previously_shipped_default(
                    file,
                    OLD_DEFAULT,
                    source=file.source,
                    installed_content=file.source.read_bytes(),
                )
            )

    def test_a_rewritten_payload_is_not_compared_against_template_digests(self) -> None:
        # The history stores template digests. If a mode rewrites this file's
        # bytes, what a past release installed is not what was recorded, and a
        # rewritten digest cannot be derived from a stored one. Neither config
        # is rewritten today; this keeps the day one gains a `scripts/`
        # citation from silently comparing the wrong bytes.
        file = self.pack_file(GITO_TARGET)
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=history_for(**{GITO_TARGET: OLD_DEFAULT}),
        ):
            self.assertFalse(
                install.fileops.is_previously_shipped_default(
                    file,
                    OLD_DEFAULT,
                    source=file.source,
                    installed_content=file.source.read_bytes() + b"# rewritten\n",
                )
            )

    def test_neither_config_is_rewritten_by_the_thin_payload_today(self) -> None:
        # The measurement the branch above is insurance for. If this fails, the
        # feature has gone inert for thin consumers and the insurance is what
        # made that silent -- fix the history, not this assertion.
        for target in (GITO_TARGET, PRISM_TARGET):
            with self.subTest(target=target):
                file = self.pack_file(target)
                self.assertEqual(
                    install.fileops.payload_source_bytes(
                        file, file.source, is_thin=True
                    ),
                    file.source.read_bytes(),
                )


class RefreshInstallTests(InstallTestCase):
    """End to end: the correction reaches an unmodified consumer and stops at
    a modified one, in the same run."""

    def install_with_history(self, root: Path, **shipped: bytes):
        with mock.patch.object(
            install.fileops,
            "load_provider_config_history",
            return_value=history_for(**shipped),
        ):
            return self.run_install_inproc(root)

    def seed(self, root: Path, target: str, content: bytes) -> Path:
        destination = root / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    def test_a_previously_shipped_default_is_replaced_and_reported(self) -> None:
        root = self.make_repo()
        destination = self.seed(root, GITO_TARGET, OLD_DEFAULT)
        template = (PACK_ROOT / "templates/.gito/config.toml").read_bytes()

        result = self.install_with_history(root, **{GITO_TARGET: OLD_DEFAULT})

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(destination.read_bytes(), template)
        self.assertIn("refreshed", result.stdout)
        self.assertIn(GITO_TARGET, result.stdout)

    def test_a_customized_config_survives_the_same_run(self) -> None:
        root = self.make_repo()
        customized = OLD_DEFAULT + b'"local-rule"\n'
        gito = self.seed(root, GITO_TARGET, OLD_DEFAULT)
        prism = self.seed(root, PRISM_TARGET, customized)

        result = self.install_with_history(
            root,
            **{GITO_TARGET: OLD_DEFAULT, PRISM_TARGET: OLD_DEFAULT},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(prism.read_bytes(), customized)
        self.assertNotEqual(gito.read_bytes(), OLD_DEFAULT)
        self.assertIn("preserved", result.stdout)

    def test_a_refresh_is_not_repeated_on_the_next_run(self) -> None:
        root = self.make_repo()
        self.seed(root, GITO_TARGET, OLD_DEFAULT)

        self.install_with_history(root, **{GITO_TARGET: OLD_DEFAULT})
        second = self.install_with_history(root, **{GITO_TARGET: OLD_DEFAULT})

        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertNotIn("refreshed", second.stdout)

    def test_a_refreshed_target_is_vouched_like_any_written_file(self) -> None:
        # A written file the provenance record does not vouch makes the next
        # `install.py --check` report drift for a file this run wrote itself.
        self.assertIn(
            install.InstallStatus.REFRESHED,
            install.fileops.VOUCHABLE_STATUSES,
        )


class HistoryArtifactTests(InstallTestCase):
    """Reading the record. Every unreadable shape resolves to `preserved`."""

    def load(self, root: Path):
        providerhistory.load_provider_config_history.cache_clear()
        try:
            return providerhistory.load_provider_config_history(root)
        finally:
            providerhistory.load_provider_config_history.cache_clear()

    def write_history(self, root: Path, payload: object) -> None:
        path = root / providerhistory.HISTORY_SOURCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )

    def test_a_missing_artifact_reports_why_instead_of_matching_nothing(self) -> None:
        history = self.load(self.make_repo())
        self.assertIsNotNone(history.unavailable_reason)
        self.assertIn("missing", history.unavailable_reason)

    def test_an_unknown_schema_version_is_refused(self) -> None:
        root = self.make_repo()
        self.write_history(root, {"schemaVersion": 99, "sources": {}})
        history = self.load(root)
        self.assertIsNotNone(history.unavailable_reason)
        self.assertIn("schemaVersion", history.unavailable_reason)

    def test_invalid_utf8_is_refused_rather_than_raised(self) -> None:
        # `JSONDecodeError` does not cover this: the decode fails before the
        # parser runs, and an uncaught error here would abort the install
        # instead of preserving.
        root = self.make_repo()
        path = root / providerhistory.HISTORY_SOURCE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{"schemaVersion": 1, "sources": {"\xff": {}}}')
        history = self.load(root)
        self.assertIsNotNone(history.unavailable_reason)
        self.assertIn("unreadable", history.unavailable_reason)

    def test_malformed_json_is_refused(self) -> None:
        root = self.make_repo()
        self.write_history(root, "{not json")
        history = self.load(root)
        self.assertIsNotNone(history.unavailable_reason)

    def test_every_malformed_shape_is_refused_with_a_reason(self) -> None:
        # Each shape resolves to `preserved`, so a reader that treats "no
        # reason" as "checked and clean" is never handed a silent empty
        # history.
        shapes = {
            "not an object": [],
            "sources is not an object": {"schemaVersion": 1, "sources": []},
            "entry is not an object": {"schemaVersion": 1, "sources": {"t": 5}},
            "target is not a string": {
                "schemaVersion": 1,
                "sources": {"t": {"target": 1, "digests": []}},
            },
            "no sources at all": {"schemaVersion": 1, "sources": {}},
        }
        for label, payload in shapes.items():
            with self.subTest(shape=label):
                root = self.make_repo()
                self.write_history(root, payload)
                history = self.load(root)
                self.assertIsNotNone(history.unavailable_reason)
                self.assertEqual(history.digests_by_target, {})

    def test_a_malformed_source_entry_is_refused_whole(self) -> None:
        root = self.make_repo()
        self.write_history(
            root,
            {
                "schemaVersion": 1,
                "sources": {"templates/x": {"target": ".x", "digests": [7]}},
            },
        )
        history = self.load(root)
        self.assertIsNotNone(history.unavailable_reason)

    def test_the_shipped_artifact_covers_every_if_not_exists_target(self) -> None:
        history = self.load(PACK_ROOT)
        self.assertIsNone(history.unavailable_reason)
        _, files = install.load_manifest()
        for file in files:
            if file.install != install.IF_NOT_EXISTS:
                continue
            with self.subTest(target=file.target.as_posix()):
                current = install.fileops.source_digest(file.source.read_bytes())
                self.assertTrue(
                    history.shipped(file.target, current),
                    "the current template must be recorded as shipped, or the "
                    "next release refreshes consumers back onto it",
                )


class GeneratorTests(InstallTestCase):
    """The artifact is generated, so an edit to a template cannot ship without
    its digest."""

    GENERATOR = PACK_ROOT / ".github/scripts/generate-provider-config-history.py"

    def run_generator(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.GENERATOR)],
            cwd=PACK_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_running_it_on_a_current_tree_changes_nothing(self) -> None:
        before = (PACK_ROOT / providerhistory.HISTORY_SOURCE).read_bytes()
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unchanged", result.stdout)
        self.assertEqual(
            (PACK_ROOT / providerhistory.HISTORY_SOURCE).read_bytes(),
            before,
        )

    def test_the_recorded_sources_are_exactly_the_manifest_population(self) -> None:
        # Keyed off the manifest rather than a hand-maintained list, so a third
        # `if-not-exists` file joins with no code edit.
        artifact = json.loads(
            (PACK_ROOT / providerhistory.HISTORY_SOURCE).read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (PACK_ROOT / "manifest.json").read_text(encoding="utf-8")
        )
        expected = {
            record["source"]
            for record in manifest["files"]
            if record.get("install") == install.IF_NOT_EXISTS
        }
        self.assertTrue(expected)
        self.assertTrue(expected.issubset(set(artifact["sources"])))


if __name__ == "__main__":
    unittest.main()
