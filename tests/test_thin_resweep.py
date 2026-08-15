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
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# `load_resweep()` below reaches the script by file path, so nothing here has
# needed the repo on `sys.path` until now. The identity assertion in
# `RepointedScanTests` compares the installer function the resweep imported
# against the one this file imports, and that comparison is only meaningful if
# both resolve through the same package.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from installer import thin  # noqa: E402

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

    def write_partition(self, data: dict) -> Path:
        """A partition file of this fixture's own, for disposition variants."""
        import tempfile

        directory = Path(tempfile.mkdtemp(prefix="sd-resweep-partition-")).resolve()
        self.addCleanup(
            lambda: __import__("shutil").rmtree(directory, ignore_errors=True)
        )
        path = directory / "surface-partition.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def scan(
        self,
        repo: Path,
        platforms: frozenset[str] | None = None,
        partition: Path | None = None,
    ) -> dict:
        return resweep.scan(
            "fixture",
            repo,
            self.platforms if platforms is None else platforms,
            PARTITION if partition is None else partition,
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


RESOLVER_VENDORED = "scripts/sd-ai-command-pack-review-layout.py"
RESOLVER_KEPT = ".sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py"


class LayoutResolverReferenceTests(ResweepFixture):
    """The reference that asks *where the pack is* must not itself block.

    Both directions from one fixture shape. A one-directional test would pass
    on a rule that never fires -- classifying every citation as harmless looks
    identical to classifying this one correctly -- so the same consumer file,
    the same scan, and the same receipt are used for each, changing only which
    of the two resolver paths the file names.
    """

    def consumer_citing(self, cited: str) -> Path:
        return self.make_consumer(
            {"scripts/guard.sh": f'python3 "{cited}" --resolve x\n'},
            receipt=[RESOLVER_VENDORED, RESOLVER_KEPT, KEPT],
        )

    def test_citing_the_vendored_copy_blocks(self) -> None:
        result = self.scan(self.consumer_citing(RESOLVER_VENDORED))
        self.assertEqual(self.only_bucket(result, "scripts/guard.sh"), "blockers")

    def test_citing_the_consumer_config_copy_does_not_block(self) -> None:
        result = self.scan(self.consumer_citing(RESOLVER_KEPT))
        self.assertEqual(
            [entry for entry in result["blockers"] if entry["file"] == "scripts/guard.sh"],
            [],
        )
        verdict, reasons = resweep.decide(result)
        self.assertEqual((verdict, reasons), ("clear", ()))

    def test_the_two_copies_are_classified_oppositely_by_the_partition(self) -> None:
        # The scan results above are only meaningful if the partition really
        # does split these two, so assert the premise rather than trusting the
        # bucket to have been decided for the reason claimed.
        rows = {
            entry["target"]: entry["category"]
            for entry in json.loads(PARTITION.read_text(encoding="utf-8"))["files"]
        }
        self.assertEqual(rows[RESOLVER_VENDORED], "machine-claude")
        self.assertEqual(rows[RESOLVER_KEPT], "consumer-config")


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

    def test_a_populated_codex_directory_advises_when_undeclared(self) -> None:
        # Detected, recorded, and no longer blocking. `codex` left the
        # partition's `retainVendoredFor` on executed probe evidence, so
        # declaring it retains nothing and the blocker would be demanding a
        # declaration that changes nothing -- the same R14-C1 standard that
        # already exempts an empty directory, now reaching every codex marker.
        repo = self.make_consumer({".codex/prompts/x.md": "do a thing\n"})
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".codex"), "advisories")

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
        # Every bucket, not just `blockers`: with the marker demoted to an
        # advisory, asserting only the empty blockers list would pass on a
        # build that never suppressed a declared platform's marker at all.
        repo = self.make_consumer({".codex/prompts/x.md": "do a thing\n"})
        result = self.scan(repo, platforms=CONSUMER_PLATFORMS | {"codex"})
        self.assertEqual(self.buckets_for(result, ".codex"),
                         {"blockers": [], "packDefects": [], "scheduled": [],
                          "advisories": []})

    def test_a_pack_owned_codex_directory_is_still_a_pack_defect(self) -> None:
        # The demotion is scoped to the consumer's own usage. A `.codex/` the
        # pack installed for a platform the registry omits is a defect in the
        # pack whatever codex retains, so `marker_bucket` must leave the
        # non-consumer dispositions alone.
        import hashlib

        body = "do a thing\n"
        digest = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
        repo = self.make_consumer(
            {
                ".codex/prompts/x.md": body,
                # Ownership is receipt membership plus a matching recorded
                # digest, so the fixture has to supply both to be pack-owned.
                ".sd-ai-command-pack/provenance.json": json.dumps(
                    {
                        "pack": "sd-ai-command-pack",
                        "version": "0.0.0",
                        "files": {".codex/prompts/x.md": digest},
                    }
                )
                + "\n",
            },
            receipt=[REMOVED, KEPT, ".codex/prompts/x.md"],
        )
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".codex"), "packDefects")

    def test_an_undeclared_pi_marker_still_blocks_beside_the_codex_advisory(
        self,
    ) -> None:
        # The two platforms in one scan. Separately each could pass on a build
        # that routed every consumer marker to one bucket; together they pin
        # the split to the platform, which is the whole change.
        repo = self.make_consumer(
            {
                ".codex/prompts/x.md": "do a thing\n",
                ".pi/skills/sd-check/SKILL.md": "do a thing\n",
            }
        )
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, ".codex"), "advisories")
        self.assertEqual(self.only_bucket(result, ".pi"), "blockers")

    def test_the_blocking_set_is_read_from_the_partition(self) -> None:
        # The demotion is a consequence of `retainVendoredFor`, not a codex
        # special case: hand the scanner a partition that retains for codex and
        # the same marker blocks again. A hard-coded advisory list would pass
        # every other test here and fail this one.
        repo = self.make_consumer({".codex/prompts/x.md": "do a thing\n"})
        partition = json.loads(PARTITION.read_text(encoding="utf-8"))
        retained = partition["platforms"]["shared"]["retainVendoredFor"]
        self.assertNotIn("codex", retained, "the real partition already retains codex")
        partition["platforms"]["shared"]["retainVendoredFor"] = sorted(
            [*retained, "codex"]
        )
        result = self.scan(repo, partition=self.write_partition(partition))
        self.assertEqual(self.only_bucket(result, ".codex"), "blockers")

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

    def test_a_codex_home_reference_advises_when_undeclared(self) -> None:
        repo = self.make_consumer({"scripts/setup.sh": 'echo "$CODEX_HOME"\n'})
        result = self.scan(repo)
        # The marker's subject is the platform, not the citing file: one
        # undeclared platform is one finding however many files evidence it.
        # The file survives in `detail`, which is what a reader acts on.
        # Recorded, not blocking: `codex` retains nothing.
        marker = self.buckets_for(result, "$CODEX_HOME")["advisories"]
        self.assertEqual(len(marker), 1, result["advisories"])
        self.assertIn("scripts/setup.sh", marker[0]["detail"])

    def test_the_codex_cli_in_command_position_advises_when_undeclared(self) -> None:
        repo = self.make_consumer({"scripts/run.sh": "#!/bin/sh\ncodex exec --help\n"})
        result = self.scan(repo)
        marker = self.buckets_for(result, "codex")["advisories"]
        self.assertEqual(len(marker), 1, result["advisories"])
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


class RepointedScanTests(ResweepFixture):
    """The verdict judges the bytes the conversion writes, not the ones it reads.

    `repoint_kept_references` (installer/thin.py) rewrites the kept files' path
    citations as part of every conversion. Scanning the pre-conversion text made
    the resweep report those rewrites as defects, and since `decide` blocks on a
    non-empty `packDefects` bucket and `--thin` refuses anything but `clear`, a
    fat consumer whose pack files correctly named the paths it currently had
    could never convert. Measured across the canary cohort on 2026-08-15: fifteen
    pack defects each, fourteen of them repointed, and nothing in the fleet
    convertible.
    """

    def cited_from_a_kept_pack_file(self, body: str) -> Path:
        """A kept, receipt-vouched `KEPT` whose text is `body`.

        Ownership is receipt membership plus a matching recorded digest, so both
        are supplied. The whole shell-helper population joins the receipt because
        the citation under test names one of them: a path the receipt omits is
        never removed, so nothing cites it and every bucket comes back empty --
        which is how the first draft of these tests passed against the unfixed
        scanner.
        """

        import hashlib

        digest = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
        return self.make_consumer(
            {
                KEPT: body,
                ".sd-ai-command-pack/provenance.json": json.dumps(
                    {
                        "pack": "sd-ai-command-pack",
                        "version": "0.0.0",
                        "files": {KEPT: digest},
                    }
                )
                + "\n",
            },
            receipt=[REMOVED, KEPT, *SHELL_HELPERS],
        )

    def test_a_citation_the_conversion_repoints_is_not_a_defect(self) -> None:
        # `THIN_PROFILE.script_template` rewrites this to `~/.agents/bin/`, so
        # the converted tree does not name the removed path and the pre-conversion
        # text does not describe a defect.
        repo = self.cited_from_a_kept_pack_file(
            f"Run `{SHELL_HELPERS[0]}` first.\n"
        )
        result = self.scan(repo)
        self.assertEqual(self.buckets_for(result, KEPT)["packDefects"], [])

    def test_a_citation_the_conversion_cannot_repoint_still_defects(self) -> None:
        # The other direction, and the reason it is not optional: a change that
        # simply stopped scanning kept files would pass the test above while
        # clearing every real defect with it. `REMOVED` is a command payload
        # path with no rewrite rule, so the repoint leaves it exactly as it is.
        repo = self.cited_from_a_kept_pack_file(f"See `{REMOVED}` for the steps.\n")
        result = self.scan(repo)
        self.assertEqual(self.only_bucket(result, KEPT), "packDefects")

    def test_the_rewrite_is_sourced_from_the_installer(self) -> None:
        # Not a duplicate of the two above: they would both pass against a
        # second, drifting copy of the rewrite rules living in the scanner.
        # What is pinned here is that there is only one implementation of
        # "what will the conversion write".
        self.assertIs(resweep.thin.planned_repoints, thin.planned_repoints)


class ConsumerConfigCitationTests(unittest.TestCase):
    """A kept target may not name a path the conversion removes.

    `repoint_kept_references` rewrites kept files during conversion, but only
    forms `THIN_PROFILE` recognises: a `scripts/<name>` path, the manual, the
    Copilot globs. A bare basename in prose matches none of them, and
    `cites_removed_path` reports basenames -- so a comment reading
    "already existed in ``sd-ai-command-pack-review-scope.sh``" is a permanent
    `packDefect` in every consumer that installs the file, unfixable by the
    conversion and blocking it outright.

    That is not hypothetical. 0.71.11 shipped
    `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` as the second
    `consumer-config` target, and its docstring and one inline comment cited two
    machine-scope scripts by name. The first refresh that installed it put two
    fresh pack defects into all three canaries at once, after the cohort had
    already measured zero.

    `consumer-config` is the category that needs the guard: `repo-native` files
    are the consumer's own, and machine-scope files do not survive to be read.
    """

    def test_no_consumer_config_source_names_a_removed_path(self) -> None:
        partition = json.loads(PARTITION.read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        sources = {entry["target"]: entry["source"] for entry in manifest["files"]}

        removed = frozenset(
            entry["target"]
            for entry in partition["files"]
            if entry["category"].startswith("machine-")
        )
        survivors = frozenset(
            entry["target"]
            for entry in partition["files"]
            if not entry["category"].startswith("machine-")
        )
        # The same two forms `cites_removed_path` reports for a plain
        # reference, and the same basename rule: `unambiguous_basenames` is
        # borrowed rather than restated, so this guard cannot drift stricter
        # than the check that produces the verdict. Restating it as "any
        # basename" was tried and flagged `design.md` and `review.md`, which
        # is exactly the ambiguity that rule exists to drop.
        names = resweep.unambiguous_basenames(removed, survivors) | removed
        self.assertIn("sd-ai-command-pack-review-scope.sh", names)

        kept = [
            entry["target"]
            for entry in partition["files"]
            if entry["category"] == "consumer-config"
        ]
        # Every consumer-config target must resolve to a manifest source.
        # Skipping the ones that do not would make the guard quietly
        # incomplete: a target added to the partition without a manifest entry
        # is exactly the case this is here to catch, and it would evade the
        # check by being unreadable rather than by being clean.
        unmapped = sorted(target for target in kept if target not in sources)
        self.assertEqual(
            unmapped,
            [],
            "a consumer-config target has no manifest source, so its text "
            "cannot be checked",
        )

        offenders = []
        for target in kept:
            source = sources[target]
            text = (ROOT / source).read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), start=1):
                for name in names:
                    if name in line:
                        offenders.append(f"{source}:{number} names {name}")

        self.assertEqual(
            offenders,
            [],
            "a kept consumer-config target names a path the conversion removes; "
            "the conversion cannot rewrite it, so it blocks every consumer",
        )


if __name__ == "__main__":
    unittest.main()
