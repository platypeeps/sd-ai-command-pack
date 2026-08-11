"""Fixtures for the shipped resweep's four-bucket rule.

Every case here is one of step 3's checks in `implement.md`. They are fixtures
rather than measurements on purpose: the eight real consumers exercise a
handful of these paths and no consumer exercises several of them at all, which
is exactly why a measured count cannot stand in for them.

The removal set is derived from the receipt each fixture writes, so a fixture
declares what a conversion would remove by listing it -- the same way a real
consumer does.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTITION = ROOT / "docs/fleet/surface-partition.json"

# A machine-scope Claude target the conversion deletes, and a repo-native one
# it keeps. Both are read from the partition rather than assumed, so a
# repartition moves the fixtures instead of silently invalidating them.
REMOVED = ".claude/commands/sd/check.md"
KEPT = ".agent/skills/sd-check/SKILL.md"
CONSUMER_PLATFORMS = frozenset({"claude", "github"})
# The whole `scripts/sd-ai-command-pack-*.sh` population, read from the
# partition rather than listed by hand: the glob fixture's premise is that
# every member is removed and none survives, so a member added to the pack
# later must join the fixture instead of quietly weakening it.
SHELL_HELPERS = tuple(
    sorted(
        entry["target"]
        for entry in json.loads(PARTITION.read_text(encoding="utf-8"))["files"]
        if entry["target"].startswith("scripts/sd-ai-command-pack-")
        and entry["target"].endswith(".sh")
    )
)


def load_resweep():
    """Import the shipped script by path; its name is not a module name."""
    path = ROOT / "scripts/sd-ai-command-pack-thin-resweep.py"
    spec = importlib.util.spec_from_file_location("thin_resweep", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


resweep = load_resweep()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


class ResweepFixture(unittest.TestCase):
    """One disposable consumer per test, built from a file map."""

    def make_consumer(
        self,
        files: dict[str, str],
        *,
        receipt: list[str] | None = None,
        platforms: frozenset[str] = CONSUMER_PLATFORMS,
        commit: bool = True,
    ) -> Path:
        import tempfile

        repo = Path(tempfile.mkdtemp(prefix="sd-resweep-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(repo, ignore_errors=True))

        entries = [REMOVED, KEPT] if receipt is None else receipt
        payload = {
            ".sd-ai-command-pack/installed-targets.txt": "\n".join(entries) + "\n",
            ".sd-ai-command-pack/manifest.json": json.dumps({"files": []}) + "\n",
            ".sd-ai-command-pack/provenance.json": json.dumps(
                {"pack": "sd-ai-command-pack", "version": "0.0.0", "files": {}}
            )
            + "\n",
            **files,
        }
        for relative, content in payload.items():
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")

        git(repo, "init", "-q")
        git(repo, "config", "user.email", "fixture@example.invalid")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "add", "-A")
        if commit:
            git(repo, "commit", "-qm", "fixture")
        self.platforms = platforms
        return repo

    def scan(self, repo: Path, platforms: frozenset[str] | None = None) -> dict:
        return resweep.scan(
            "fixture",
            repo,
            self.platforms if platforms is None else platforms,
            PARTITION,
        )

    def buckets_for(self, result: dict, relative: str) -> dict[str, list[dict]]:
        return {
            bucket: [entry for entry in result[bucket] if entry["file"] == relative]
            for bucket in ("blockers", "packDefects", "scheduled", "advisories")
        }

    def only_bucket(self, result: dict, relative: str) -> str:
        occupied = {
            bucket: entries
            for bucket, entries in self.buckets_for(result, relative).items()
            if entries
        }
        self.assertEqual(
            len(occupied), 1, f"{relative} landed in {sorted(occupied)}: {occupied}"
        )
        return next(iter(occupied))


class CitationBucketTests(ResweepFixture):
    def test_a_workflow_invoking_a_removed_path_blocks(self) -> None:
        repo = self.make_consumer(
            {".github/workflows/ci.yml": f"jobs:\n  run:\n    x: ./{REMOVED}\n"}
        )
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".github/workflows/ci.yml"), "blockers")

    def test_two_citations_in_two_files_produce_two_scheduled_free_entries(self) -> None:
        # Step 3: the four-bucket claim is per citation, not per removed file.
        # The research scanner records one entry per removed file, which is
        # right for a summary and wrong for a verdict.
        repo = self.make_consumer(
            {
                "docs/one.md": f"see {REMOVED}\n",
                "docs/two.md": f"see {REMOVED}\n",
            }
        )
        result = self.scan(repo)
        advisories = [
            entry
            for entry in result["advisories"]
            if entry["file"] in {"docs/one.md", "docs/two.md"}
        ]
        self.assertEqual(len(advisories), 2, advisories)

    def test_a_glob_naming_a_wholly_removed_population_blocks(self) -> None:
        # W-3, measured on the real fleet: `loadsmith/.github/workflows/ci.yml`
        # addresses the deleted scripts as `scripts/sd-ai-command-pack-*.sh`
        # and names no exact path and no basename, so exact-and-suffix matching
        # alone reports this consumer `clear` and the conversion breaks its CI.
        #
        # The glob qualifies only because its whole population is removed: the
        # matcher requires at least one removed entry and no surviving one, so
        # a glob that straddles the boundary stays out of every bucket rather
        # than blocking on a guess.
        repo = self.make_consumer(
            {
                ".github/workflows/ci.yml": (
                    "jobs:\n  run:\n    x: bash scripts/sd-ai-command-pack-*.sh\n"
                )
            },
            receipt=[REMOVED, KEPT, *SHELL_HELPERS],
        )
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".github/workflows/ci.yml"), "blockers")

    def test_a_citation_from_a_nested_scripts_directory_blocks(self) -> None:
        # Round 6's missed class: a runnable file nested well below any known
        # top level. This is the criterion's own shape,
        # `templates/**/scripts/*.py`, and it is classified by the `.py`
        # suffix -- the depth costs it nothing, which is the point. The
        # directory-segment rule is what covers the same nesting for a file
        # whose name carries no such signal; `test_a_citation_from_a_nested_
        # scripts_directory_blocks_without_a_runnable_suffix` isolates it.
        repo = self.make_consumer(
            {"templates/consumer/scripts/deploy.py": f"subprocess.run(['./{REMOVED}'])\n"}
        )
        result = self.scan(repo)
        self.assertEqual(
            self.only_bucket(result, "templates/consumer/scripts/deploy.py"), "blockers"
        )

    def test_a_citation_from_a_nested_scripts_directory_blocks_without_a_runnable_suffix(
        self,
    ) -> None:
        # The discriminator for the segment rule itself, and it takes two
        # subtractions to reach. A `.py` under `scripts/` is classified by its
        # suffix alone, so the fixture above passes with `EXECUTABLE_SEGMENTS`
        # disabled entirely. Removing the suffix is not enough either: a
        # citation in command position blocks whether or not the file is an
        # executable surface, so `./path` on its own line passes too.
        #
        # A bare mention inside an extensionless nested helper is the only
        # shape left where `executable` is the sole route to `blockers` -- with
        # the segment rule disabled this same fixture is an advisory.
        repo = self.make_consumer(
            {"templates/consumer/scripts/deploy": f"# superseded by {REMOVED}\n"}
        )
        result = self.scan(repo)
        self.assertEqual(
            self.only_bucket(result, "templates/consumer/scripts/deploy"), "blockers"
        )

    def test_a_citation_from_an_agent_prompt_blocks(self) -> None:
        # An agent prompt executes by being read: `.prompt.md` is instructions
        # a model acts on, so a removed path inside one is a broken
        # instruction, not prose about one. Classified by both the
        # `.github/prompts/` prefix and the `.prompt.md` suffix, because a
        # consumer may keep prompts outside that directory.
        repo = self.make_consumer(
            {".github/prompts/sd-one.prompt.md": f"Run ./{REMOVED} before review.\n"}
        )
        result = self.scan(repo)
        self.assertEqual(
            self.only_bucket(result, ".github/prompts/sd-one.prompt.md"), "blockers"
        )

    def test_prose_mentioning_a_removed_script_is_only_advisory(self) -> None:
        repo = self.make_consumer({"README.md": f"We used to run {REMOVED}.\n"})
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, "README.md"), "advisories")

    def test_a_test_asserting_on_the_kept_provenance_path_is_not_a_hit(self) -> None:
        repo = self.make_consumer(
            {
                "test/receipts.test.js": (
                    "assert(fs.existsSync('.sd-ai-command-pack/provenance.json'));\n"
                )
            }
        )
        result = self.scan(repo)
        self.assertEqual(self.buckets_for(result, "test/receipts.test.js"),
                         {"blockers": [], "packDefects": [], "scheduled": [],
                          "advisories": []})

    def test_a_citation_of_a_surviving_path_is_in_no_bucket(self) -> None:
        # A kept path is not something the conversion removes, so recording it
        # as `scheduled` would misreport the conversion's own plan.
        repo = self.make_consumer({".github/workflows/ci.yml": f"run: ./{KEPT}\n"})
        result = self.scan(repo)
        self.assertEqual(
            self.buckets_for(result, ".github/workflows/ci.yml"),
            {"blockers": [], "packDefects": [], "scheduled": [], "advisories": []},
        )

    def test_a_removed_file_still_present_is_scheduled_with_a_null_line(self) -> None:
        repo = self.make_consumer({REMOVED: "# the file itself\n"})
        result = self.scan(repo)
        entries = self.buckets_for(result, REMOVED)["scheduled"]
        self.assertEqual([entry["line"] for entry in entries], [None])


class VerdictTests(ResweepFixture):
    def test_a_clean_fixture_with_no_citations_is_clear(self) -> None:
        repo = self.make_consumer({"src/main.py": "print('hello')\n"})
        result = self.scan(repo)
        verdict, reasons = resweep.decide(result)
        self.assertEqual((verdict, reasons), ("clear", ()))

    def test_a_dirty_worktree_blocks_even_with_no_citations(self) -> None:
        # The research scanner deliberately does not gate on this; the shipped
        # tool must (prd.md:62), because converting a dirty tree mixes the
        # conversion's deletions with uncommitted work.
        repo = self.make_consumer({"src/main.py": "print('hello')\n"})
        (repo / "src/main.py").write_text("print('edited')\n", encoding="utf-8")
        result = self.scan(repo)
        verdict, reasons = resweep.decide(result)
        self.assertEqual(verdict, "blocked")
        self.assertIn("worktree is dirty; commit or stash before converting", reasons)

    def test_every_blocking_reason_is_named_not_just_the_first(self) -> None:
        result = {
            "blockers": [{"file": "a"}],
            "packDefects": [{"file": "b"}],
            "missingFiles": ["c"],
            "worktreeClean": False,
        }
        _, reasons = resweep.decide(result)
        self.assertEqual(len(reasons), 4, reasons)


class ClassifierDigestTests(unittest.TestCase):
    """Step 3's closing check: the digest must bind what decides a conversion."""

    def setUp(self) -> None:
        import shutil
        import tempfile

        self.root = Path(tempfile.mkdtemp(prefix="sd-digest-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for relative in (
            "docs/fleet/surface-partition.json",
            ".claude-plugin/marketplace.json",
            "plugins/sd/.claude-plugin/plugin.json",
            "installer/removal.py",
            "installer/registry.py",
            "installer/conversion.py",
            "installer/manifest.py",
            "manifest.json",
            "scripts/sd-ai-command-pack-thin-resweep.py",
            *__import__("installer.conversion", fromlist=["x"])
            .force_preserved_template_sources(ROOT),
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        self.entry = {"name": "fixture", "platforms": ["claude"]}

    def digest(self) -> str:
        from installer import conversion

        return conversion.classifier_digest(self.root, self.entry)

    def assert_digest_moves(self, relative: str, appended: str) -> None:
        before = self.digest()
        path = self.root / relative
        path.write_text(path.read_text(encoding="utf-8") + appended, encoding="utf-8")
        self.assertNotEqual(before, self.digest(), f"editing {relative} did not move it")

    def test_editing_a_force_preserved_template_moves_the_digest(self) -> None:
        # The ownership proof compares a consumer's file against these bytes,
        # so a changed template flips .github/PULL_REQUEST_TEMPLATE.md between
        # packDefects and blockers while every other input stays identical.
        self.assert_digest_moves("templates/.github/PULL_REQUEST_TEMPLATE.md", "\n- x\n")

    def test_editing_the_resweep_rule_moves_the_digest(self) -> None:
        self.assert_digest_moves("scripts/sd-ai-command-pack-thin-resweep.py", "\n# x\n")

    def test_editing_the_manifest_moves_the_digest(self) -> None:
        self.assert_digest_moves("manifest.json", "\n")

    def test_editing_the_manifest_reader_moves_the_digest(self) -> None:
        self.assert_digest_moves("installer/manifest.py", "\n# x\n")

    def test_the_consumer_entry_is_bound_too(self) -> None:
        before = self.digest()
        self.entry = {**self.entry, "platforms": ["claude", "codex"]}
        self.assertNotEqual(before, self.digest())


class ShippingBoundaryTests(unittest.TestCase):
    def test_the_resweep_is_not_a_shipped_target(self) -> None:
        # A manifest row would ship classification data into every consumer,
        # and the consumer has no surface-partition.json to classify against.
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        sources = {row.get("source") for row in manifest["files"]}
        targets = {row.get("target") for row in manifest["files"]}
        self.assertNotIn("scripts/sd-ai-command-pack-thin-resweep.py", sources)
        self.assertNotIn("scripts/sd-ai-command-pack-thin-resweep.py", targets)

    def test_the_resweep_has_no_templates_twin(self) -> None:
        self.assertFalse(
            (ROOT / "templates/scripts/sd-ai-command-pack-thin-resweep.py").exists()
        )


class PlatformMarkerTests(ResweepFixture):
    """Four markers, each asserted separately (step 3, prd.md:19)."""

    def test_a_populated_codex_directory_blocks_when_undeclared(self) -> None:
        repo = self.make_consumer({".codex/prompts/x.md": "do a thing\n"})
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".codex"), "blockers")

    def test_an_empty_codex_directory_is_not_usage(self) -> None:
        # R14-C1: Git cannot track an empty directory, and an empty one is not
        # evidence anybody runs the platform. Blocking on it would refuse a
        # conversion over a leftover mkdir.
        repo = self.make_consumer({"src/main.py": "x = 1\n"})
        (repo / ".codex").mkdir()
        result = self.scan(repo)
        self.assertEqual(self.buckets_for(result, ".codex"),
                         {"blockers": [], "packDefects": [], "scheduled": [],
                          "advisories": []})

    def test_declaring_the_platform_clears_the_same_directory(self) -> None:
        repo = self.make_consumer({".codex/prompts/x.md": "do a thing\n"})
        result = self.scan(repo, platforms=CONSUMER_PLATFORMS | {"codex"})
        self.assertEqual(self.buckets_for(result, ".codex")["blockers"], [])

    def test_a_pi_adapter_file_blocks_when_undeclared(self) -> None:
        # The fourth marker, and the one a combined case would have hidden:
        # `MARKER_PLATFORMS` carries `pi` alongside `codex`, and the criterion
        # exists because three markers can pass while the fourth was never
        # wired. It matters for the same reason codex does -- `retainVendoredFor`
        # intersects the *declared* platforms, so an undeclared pi user has the
        # `.agents/**` their adapter reads deleted out from under them.
        #
        # R13 also found the exclusion broken specifically for pi: patterns
        # ending in `/` were compared with a literal `startswith`, so
        # `.pi/skills/trellis-*/` never matched the glob it contains.
        repo = self.make_consumer({".pi/skills/sd-check/SKILL.md": "do a thing\n"})
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".pi"), "blockers")

    def test_declaring_pi_clears_the_same_adapter(self) -> None:
        repo = self.make_consumer({".pi/skills/sd-check/SKILL.md": "do a thing\n"})
        result = self.scan(repo, platforms=CONSUMER_PLATFORMS | {"pi"})
        self.assertEqual(self.buckets_for(result, ".pi")["blockers"], [])

    def test_an_empty_pi_directory_is_not_usage(self) -> None:
        # The permissive direction, asserted for pi as well as codex: R14-C1's
        # rule is that a directory marker requires at least one file, and a
        # rule implemented once per platform is a rule that holds for one.
        repo = self.make_consumer({"src/main.py": "x = 1\n"})
        (repo / ".pi").mkdir()
        result = self.scan(repo)
        self.assertEqual(self.buckets_for(result, ".pi")["blockers"], [])

    def test_a_codex_home_reference_blocks_when_undeclared(self) -> None:
        repo = self.make_consumer({"scripts/setup.sh": 'echo "$CODEX_HOME"\n'})
        result = self.scan(repo)
        # The marker's subject is the platform, not the citing file: one
        # undeclared platform is one finding however many files evidence it.
        # The file survives in `detail`, which is what a reader acts on.
        marker = self.buckets_for(result, "$CODEX_HOME")["blockers"]
        self.assertEqual(len(marker), 1, result["blockers"])
        self.assertIn("scripts/setup.sh", marker[0]["detail"])

    def test_the_codex_cli_in_command_position_blocks_when_undeclared(self) -> None:
        repo = self.make_consumer({"scripts/run.sh": "#!/bin/sh\ncodex exec --help\n"})
        result = self.scan(repo)
        marker = self.buckets_for(result, "codex")["blockers"]
        self.assertEqual(len(marker), 1, result["blockers"])
        self.assertIn("scripts/run.sh", marker[0]["detail"])

    def test_prose_naming_the_codex_command_does_not_block(self) -> None:
        # R16-C2: "we evaluated codex last year" is a sentence, not a call.
        repo = self.make_consumer({"docs/history.md": "We evaluated codex last year.\n"})
        result = self.scan(repo)
        self.assertEqual(self.buckets_for(result, "docs/history.md")["blockers"], [])


class CommandLineTests(ResweepFixture):
    """The CLI surface: exit codes, output forms, and its two refusals."""

    def registry_name(self) -> str:
        return next(iter(resweep.load_registry()))

    def test_an_unregistered_consumer_is_refused_by_name(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            resweep.resolve_consumer("not-a-consumer", None)
        self.assertIn("not a registered consumer", str(raised.exception))

    def test_a_path_that_is_not_a_checkout_is_refused(self) -> None:
        import tempfile

        with self.assertRaises(SystemExit) as raised:
            resweep.resolve_consumer(
                self.registry_name(), Path(tempfile.mkdtemp(prefix="sd-not-git-"))
            )
        self.assertIn("is not a Git checkout", str(raised.exception))

    def test_a_clear_fixture_exits_zero_and_a_blocked_one_does_not(self) -> None:
        import contextlib
        import io

        clear = self.make_consumer({"src/main.py": "print('hello')\n"})
        blocked = self.make_consumer(
            {".github/workflows/ci.yml": f"run: ./{REMOVED}\n"}
        )
        name = self.registry_name()
        for repo, expected in ((clear, 0), (blocked, 1)):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = resweep.main([name, "--repo", str(repo)])
            self.assertEqual(code, expected, stdout.getvalue())
            self.assertIn("clear" if expected == 0 else "blocked", stdout.getvalue())

    def test_the_json_form_is_written_and_carries_its_bindings(self) -> None:
        import contextlib
        import io

        repo = self.make_consumer({"src/main.py": "print('hello')\n"})
        out = repo / "verdict.json"
        with contextlib.redirect_stdout(io.StringIO()):
            resweep.main([self.registry_name(), "--repo", str(repo), "--json",
                          "--out", str(out)])
        document = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(document["schemaVersion"], resweep.SCHEMA_VERSION)
        self.assertEqual(document["kind"], "thin-resweep-verdict")
        for binding in (
            "head",
            "indexDigest",
            "indexFlagsDigest",
            "hiddenBytesDigest",
            "symlinkTargetsDigest",
            "platformMarkerDigest",
            "scannedBytesDigest",
            "worktreeDigest",
            "worktreeClean",
            "receiptOccupancyDigest",
            "executableBitsDigest",
            "binaryFiles",
            "missingFiles",
            "classifierDigest",
        ):
            self.assertIn(binding, document, binding)

    def test_the_rendered_summary_names_the_dirty_tree(self) -> None:
        repo = self.make_consumer({"src/main.py": "print('hello')\n"})
        (repo / "src/main.py").write_text("print('edited')\n", encoding="utf-8")
        document = resweep.resweep_consumer(self.registry_name(), repo)
        self.assertIn("(dirty)", resweep.render(document))


if __name__ == "__main__":
    unittest.main()
