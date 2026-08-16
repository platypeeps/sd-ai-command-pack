"""Relocated-resource rewriting shared by the plugin and machine payloads.

The two payloads move the same authored text to different places, so the
interesting failures are not substitutions but judgements:

* which occurrences are references at all — a hyperlink into the source
  repository on GitHub is not one, and rewriting it corrupts a link;
* which rewritten references name something the payload does not carry, which
  is how a payload ships an instruction that cannot possibly work;
* which repository-root literals survive on purpose, each with a written
  justification rather than a silently widened pattern.

The profiles are exercised side by side because the whole point of one
implementation is that a rule proven for one payload holds for the other.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from installer import references
from installer.references import (
    MACHINE_PROFILE,
    PACK_DOC_REFERENCE,
    PLUGIN_PROFILE,
    ReferenceRewriteError,
    RewriteProfile,
)

PACK_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = "sd-ai-command-pack-toolchain.sh"
DOC_TARGET = "~/.agents/docs/SD_AI_COMMAND_PACK.md"


def machine_profile_with(
    exemptions: dict[str, tuple[str, frozenset[str]]],
) -> RewriteProfile:
    """The machine profile with a test exemption table in place of its own."""

    return RewriteProfile(
        name=MACHINE_PROFILE.name,
        script_template=MACHINE_PROFILE.script_template,
        doc_template=MACHINE_PROFILE.doc_template,
        strip_node_prefix=MACHINE_PROFILE.strip_node_prefix,
        residue_advice=MACHINE_PROFILE.residue_advice,
        closure_subject=MACHINE_PROFILE.closure_subject,
        closure_advice=MACHINE_PROFILE.closure_advice,
        exemptions=exemptions,
    )


class RewriteTests(unittest.TestCase):
    """Where each payload points a reference, and what it leaves alone."""

    def test_plugin_rewrites_invocations_to_bare_commands(self) -> None:
        body = references.rewrite_text(
            f"bash scripts/{SCRIPT} doctor\n", profile=PLUGIN_PROFILE
        )

        self.assertEqual(body, f"bash {SCRIPT} doctor\n")

    def test_plugin_drops_the_node_runner_prefix(self) -> None:
        body = references.rewrite_text(
            "node scripts/sd-ai-command-pack-review-preflight.mjs\n",
            profile=PLUGIN_PROFILE,
        )

        self.assertEqual(body, "sd-ai-command-pack-review-preflight.mjs\n")

    def test_machine_rewrites_invocations_into_the_agents_bin(self) -> None:
        body = references.rewrite_text(
            f"bash scripts/{SCRIPT} doctor\n", profile=MACHINE_PROFILE
        )

        self.assertEqual(body, f"bash ~/.agents/bin/{SCRIPT} doctor\n")

    def test_machine_keeps_the_node_runner_prefix(self) -> None:
        """`node` takes a path, and the machine payload gives it one."""

        body = references.rewrite_text(
            "node scripts/sd-ai-command-pack-review-preflight.mjs\n",
            profile=MACHINE_PROFILE,
        )

        self.assertEqual(
            body, "node ~/.agents/bin/sd-ai-command-pack-review-preflight.mjs\n"
        )

    def test_machine_relocates_the_reference_manual(self) -> None:
        body = references.rewrite_text(
            f"See `{PACK_DOC_REFERENCE}` for the toggles.\n", profile=MACHINE_PROFILE
        )

        self.assertEqual(body, f"See `{DOC_TARGET}` for the toggles.\n")

    def test_plugin_leaves_the_reference_manual_alone(self) -> None:
        """The plugin does not carry the manual, so it may not claim to."""

        text = f"See `{PACK_DOC_REFERENCE}`.\n"

        self.assertEqual(references.rewrite_text(text, profile=PLUGIN_PROFILE), text)

    def test_a_hyperlink_is_not_a_repository_root_reference(self) -> None:
        text = f"[helper](https://github.com/o/r/blob/main/scripts/{SCRIPT})\n"

        for profile in (PLUGIN_PROFILE, MACHINE_PROFILE):
            with self.subTest(profile=profile.name):
                self.assertEqual(
                    references.rewrite_text(text, profile=profile), text
                )

    def test_a_template_path_is_not_a_repository_root_reference(self) -> None:
        text = f"the authored copy is templates/scripts/{SCRIPT}\n"

        self.assertEqual(references.rewrite_text(text, profile=MACHINE_PROFILE), text)

    def test_an_exempt_script_keeps_its_repository_path(self) -> None:
        profile = machine_profile_with(
            {"manual.md": ("source-only fleet tooling documented as such", frozenset({SCRIPT}))}
        )
        text = f"the source-only `scripts/{SCRIPT}` runs in the pack checkout\n"

        self.assertEqual(
            references.rewrite_text(text, profile=profile, key="manual.md"), text
        )

    def test_an_exempt_manual_reference_keeps_its_repository_path(self) -> None:
        profile = machine_profile_with(
            {
                "manual.md": (
                    "the manual describes its own repository location",
                    frozenset({PACK_DOC_REFERENCE}),
                )
            }
        )
        text = f"this file is `{PACK_DOC_REFERENCE}`\n"

        self.assertEqual(
            references.rewrite_text(text, profile=profile, key="manual.md"), text
        )

    def test_an_exemption_without_a_justification_fails(self) -> None:
        profile = machine_profile_with({"manual.md": ("", frozenset({SCRIPT}))})

        with self.assertRaisesRegex(
            ReferenceRewriteError, "exemption for manual.md has no justification"
        ):
            references.rewrite_text("text\n", profile=profile, key="manual.md")


class ResidueTests(unittest.TestCase):
    """Nothing may still name a repository-root pack resource after rewriting."""

    def test_clean_text_passes(self) -> None:
        references.check_text_residue(
            "skill.md", f"bash ~/.agents/bin/{SCRIPT}\n", profile=MACHINE_PROFILE
        )

    def test_a_surviving_script_path_fails(self) -> None:
        with self.assertRaisesRegex(
            ReferenceRewriteError, rf"rewrite residue in skill.md: scripts/{SCRIPT}"
        ):
            references.check_text_residue(
                "skill.md", f"see scripts/{SCRIPT}\n", profile=MACHINE_PROFILE
            )

    def test_a_surviving_manual_path_fails(self) -> None:
        with self.assertRaisesRegex(
            ReferenceRewriteError, rf"rewrite residue in skill.md: {PACK_DOC_REFERENCE}"
        ):
            references.check_text_residue(
                "skill.md", f"see {PACK_DOC_REFERENCE}\n", profile=MACHINE_PROFILE
            )

    def test_the_relocated_manual_is_not_its_own_residue(self) -> None:
        """`~/.agents/docs/...` contains the repository form as a substring."""

        references.check_text_residue(
            "skill.md", f"see `{DOC_TARGET}`\n", profile=MACHINE_PROFILE
        )

    def test_the_plugin_does_not_gate_the_manual_reference(self) -> None:
        references.check_text_residue(
            "skill.md", f"see {PACK_DOC_REFERENCE}\n", profile=PLUGIN_PROFILE
        )

    def test_an_exempt_literal_is_not_residue(self) -> None:
        profile = machine_profile_with(
            {"manual.md": ("source-only fleet tooling", frozenset({SCRIPT}))}
        )

        references.check_text_residue(
            "manual.md", f"see scripts/{SCRIPT}\n", profile=profile
        )

    def test_a_deliberately_unrewritten_form_is_still_reported(self) -> None:
        """The rewrite declines these; the residue gate is what refuses them."""

        for label, text in (
            ("relative", f"bash ./scripts/{SCRIPT}\n"),
            ("parent", f"see ../scripts/{SCRIPT}\n"),
            ("template", f"authored at templates/scripts/{SCRIPT}\n"),
            ("hyperlink", f"[helper](https://github.com/o/r/blob/main/scripts/{SCRIPT})\n"),
            ("glob", "the scripts/sd-ai-command-pack-*.sh helpers\n"),
        ):
            with self.subTest(label=label):
                body = references.rewrite_text(text, profile=MACHINE_PROFILE)
                with self.assertRaisesRegex(
                    ReferenceRewriteError, "rewrite residue in skill.md"
                ):
                    references.check_text_residue(
                        "skill.md", body, profile=MACHINE_PROFILE
                    )

    def test_a_wrapped_script_reference_is_reported(self) -> None:
        """Neither half is a reference on its own, so no other gate sees it."""

        for profile in (PLUGIN_PROFILE, MACHINE_PROFILE):
            with self.subTest(profile=profile.name):
                with self.assertRaisesRegex(
                    ReferenceRewriteError,
                    rf"line-wrapped reference in skill.md: scripts/ \+ {SCRIPT}",
                ):
                    references.check_text_residue(
                        "skill.md", f"run bash scripts/\n{SCRIPT} doctor\n", profile=profile
                    )

    def test_a_wrapped_manual_reference_is_reported(self) -> None:
        with self.assertRaisesRegex(
            ReferenceRewriteError, r"line-wrapped reference in skill.md: docs/ \+"
        ):
            references.check_text_residue(
                "skill.md",
                f"see the manual in docs/\n{references.PACK_DOC_NAME} for toggles\n",
                profile=MACHINE_PROFILE,
            )

    def test_the_plugin_does_not_gate_a_wrapped_manual_reference(self) -> None:
        """The plugin carries no manual, so the wrap names nothing it relocates."""

        references.check_text_residue(
            "skill.md",
            f"see the manual in docs/\n{references.PACK_DOC_NAME} for toggles\n",
            profile=PLUGIN_PROFILE,
        )

    def test_a_directory_listing_is_not_a_wrapped_reference(self) -> None:
        """A tree names a directory and its contents; it invokes nothing."""

        references.check_text_residue(
            "skill.md", f"scripts/\n  {SCRIPT}\n", profile=MACHINE_PROFILE
        )

    def test_a_wrapped_exempt_reference_is_still_reported(self) -> None:
        """The exemption names a script, and a wrap is where no gate sees one."""

        profile = machine_profile_with(
            {"manual.md": ("source-only fleet tooling documented as such", frozenset({SCRIPT}))}
        )

        with self.assertRaisesRegex(ReferenceRewriteError, "line-wrapped reference"):
            references.check_text_residue(
                "manual.md", f"the source-only scripts/\n{SCRIPT} runs here\n", profile=profile
            )

    def test_an_executable_keeps_only_allowlisted_literals(self) -> None:
        with self.assertRaisesRegex(
            ReferenceRewriteError, r"repository-root pack paths in bin/probe.sh"
        ):
            references.check_executable_residue(
                "bin/probe.sh",
                f"# runs scripts/{SCRIPT}\n",
                allowlist={},
                name="probe.sh",
            )

    def test_an_allowlisted_executable_literal_passes(self) -> None:
        references.check_executable_residue(
            "scripts/probe.sh",
            f"# audits scripts/{SCRIPT}\n",
            allowlist={"probe.sh": ("layout data about the audited repo", frozenset({f"scripts/{SCRIPT}"}))},
            name="probe.sh",
        )

    def test_an_executable_allowlist_needs_a_justification(self) -> None:
        with self.assertRaisesRegex(ReferenceRewriteError, "has no justification"):
            references.check_executable_residue(
                "scripts/probe.sh",
                f"# audits scripts/{SCRIPT}\n",
                allowlist={"probe.sh": ("", frozenset({f"scripts/{SCRIPT}"}))},
                name="probe.sh",
            )


class ClosureTests(unittest.TestCase):
    """Every relocated resource a text file names must travel with it."""

    def closure(self, text: str, **kwargs: object) -> None:
        arguments: dict[str, object] = {
            "profile": MACHINE_PROFILE,
            "shipped_commands": frozenset({SCRIPT}),
            "shipped_docs": frozenset({"SD_AI_COMMAND_PACK.md"}),
            "allowlist": {},
        }
        arguments.update(kwargs)
        references.check_closure("skill.md", text, **arguments)  # type: ignore[arg-type]

    def test_a_shipped_command_passes(self) -> None:
        self.closure(f"bash ~/.agents/bin/{SCRIPT}\n")

    def test_an_unshipped_command_fails(self) -> None:
        with self.assertRaisesRegex(
            ReferenceRewriteError,
            r"references sd-ai-command-pack-absent.py, which the machine payload",
        ):
            self.closure("run sd-ai-command-pack-absent.py\n")

    def test_a_justified_reference_passes(self) -> None:
        self.closure(
            "run sd-ai-command-pack-absent.py\n",
            allowlist={
                ("skill.md", "sd-ai-command-pack-absent.py"): (
                    "fleet-operator path: no manifest row, already absent today"
                )
            },
        )

    def test_an_allowlist_entry_without_a_justification_fails(self) -> None:
        with self.assertRaisesRegex(ReferenceRewriteError, "which the machine payload"):
            self.closure(
                "run sd-ai-command-pack-absent.py\n",
                allowlist={("skill.md", "sd-ai-command-pack-absent.py"): ""},
            )

    def test_an_exempt_command_passes(self) -> None:
        profile = machine_profile_with(
            {
                "skill.md": (
                    "source-only fleet tooling documented as such",
                    frozenset({"sd-ai-command-pack-absent.py"}),
                )
            }
        )

        self.closure("run sd-ai-command-pack-absent.py\n", profile=profile)

    def test_a_relocated_manual_reference_needs_the_manual(self) -> None:
        with self.assertRaisesRegex(
            ReferenceRewriteError, r"which the payload does not install"
        ):
            self.closure(f"see {DOC_TARGET}\n", shipped_docs=frozenset())

    def test_a_relocated_manual_reference_passes_when_shipped(self) -> None:
        self.closure(f"see {DOC_TARGET}\n")

    def test_the_plugin_profile_has_no_manual_closure(self) -> None:
        self.closure(
            f"see {DOC_TARGET}\n", profile=PLUGIN_PROFILE, shipped_docs=frozenset()
        )


class AllowlistShapeTests(unittest.TestCase):
    """The shipped allowlists must describe the payloads as they ship today."""

    def test_every_closure_justification_is_written_out(self) -> None:
        for allowlist in (
            references.PLUGIN_CLOSURE_ALLOWLIST,
            references.MACHINE_CLOSURE_ALLOWLIST,
        ):
            for key, justification in allowlist.items():
                with self.subTest(key=key):
                    self.assertGreater(len(justification.split()), 5)

    def test_every_reference_exemption_is_written_out(self) -> None:
        for key, (justification, names) in (
            references.MACHINE_REFERENCE_EXEMPTIONS.items()
        ):
            with self.subTest(key=key):
                self.assertGreater(len(justification.split()), 5)
                self.assertTrue(names)

    def test_both_payloads_excuse_the_same_reference(self) -> None:
        """The same broken skill line, recorded once per payload path shape."""

        self.assertEqual(
            {command for _path, command in references.PLUGIN_CLOSURE_ALLOWLIST},
            {command for _path, command in references.MACHINE_CLOSURE_ALLOWLIST},
        )


class ThinProfileTests(unittest.TestCase):
    """The third profile, whose output is read back by the thin resweep.

    Its constraint is not shared with the two payload profiles: a converted
    consumer's own files are scanned, so a rewritten reference has to survive
    `cites_removed_path` as well as be true.
    """

    def test_script_references_move_to_the_machine_bin_directory(self) -> None:
        rewritten = references.rewrite_text(
            "run `bash scripts/sd-ai-command-pack-housekeeping.sh` now",
            profile=references.THIN_PROFILE,
        )
        self.assertIn(
            "~/.agents/bin/sd-ai-command-pack-housekeeping.sh", rewritten
        )
        self.assertNotIn("scripts/sd-ai-command-pack-housekeeping.sh", rewritten)

    def test_the_doc_reference_avoids_the_removed_path_as_a_suffix(self) -> None:
        """The machine payload's own doc form would be reported as a citation.

        `cites_removed_path` matches path suffixes, so
        `~/.agents/docs/SD_AI_COMMAND_PACK.md` ends with the removed
        `docs/SD_AI_COMMAND_PACK.md`. The machine payload is never scanned and
        keeps the fuller form; this profile cannot.
        """

        rewritten = references.rewrite_text(
            "see docs/SD_AI_COMMAND_PACK.md", profile=references.THIN_PROFILE
        )
        self.assertNotIn("docs/SD_AI_COMMAND_PACK.md", rewritten)
        self.assertIn("~/.agents/docs", rewritten)
        self.assertNotEqual(
            references.THIN_PROFILE.doc_template,
            references.MACHINE_PROFILE.doc_template,
        )

    def test_the_doc_replacement_carries_no_markdown_of_its_own(self) -> None:
        """Every occurrence replaced already sits inside a code span."""

        self.assertNotIn("`", references.THIN_DOC_REFERENCE)

    def test_the_copilot_globs_are_rewritten_by_literal(self) -> None:
        """`SCRIPT_REFERENCE_RE` cannot see them: a glob has no script suffix."""

        source = (
            "- entry points: `.agents/skills/sd-*/SKILL.md`, and\n"
            "- `**/skills/trellis-*/**` and `**/skills/sd-*/**` under `.agents/`,\n"
            "- `scripts/sd-ai-command-pack-*`, legacy `scripts/trellis-*.sh`, and\n"
        )
        rewritten = references.rewrite_text(
            source, profile=references.THIN_PROFILE
        )
        self.assertIn("`~/.agents/skills`", rewritten)
        self.assertNotIn("`**/skills/sd-*/**`", rewritten)
        self.assertNotIn("`scripts/sd-ai-command-pack-*`", rewritten)
        # The Trellis glob beside it is not the pack's to repoint.
        self.assertIn("`**/skills/trellis-*/**`", rewritten)
        self.assertIn("`scripts/trellis-*.sh`", rewritten)

    def test_the_surviving_legacy_glob_keeps_a_narrow_globs_marker(self) -> None:
        """Trellis' gate reads the bullet only because the rewrite touched it.

        `check-narrow-globs.py` assembles paragraphs from the diff's added
        lines, so the marker has to arrive with the rewritten bullet: one in
        the template would be context and never reach the paragraph. Without
        it, `scripts/trellis-*.sh` -- legacy Trellis scripts most consumers
        never had -- becomes the line's first glob and fails the gate as a
        zero-match on the conversion PR.
        """

        source = (
            "  - `scripts/sd-ai-command-pack-*`, legacy `scripts/trellis-*.sh`, and\n"
            "    `scripts/update_repomix*`\n"
        )
        rewritten = references.rewrite_text(
            source, profile=references.THIN_PROFILE
        )

        self.assertEqual(
            rewritten,
            "  <!-- narrow-globs: skip - legacy Trellis script payloads may "
            "not exist in every repo. -->\n"
            "  - legacy `scripts/trellis-*.sh` and\n"
            "    `scripts/update_repomix*`\n",
        )

    def test_the_skills_reference_avoids_the_removed_path_as_a_suffix(self) -> None:
        """The same suffix trap as the doc case one test up, one family over.

        `~/.agents/skills/sd-*/SKILL.md` is where those files truly live, and it
        ends with the removed `.agents/skills/sd-*/SKILL.md`, so a resweep of the
        converted tree reads the relocated form as a citation of the path the
        rewrite just repointed away from. Measured on the canary cohort: it was
        the single surviving `packDefect` once the repoint simulation cleared the
        other fourteen. Naming the directory is what closes it, so no rewritten
        form may end with the glob.
        """

        rewritten = references.rewrite_text(
            "- entry points: `.agents/skills/sd-*/SKILL.md`, and\n",
            profile=references.THIN_PROFILE,
        )
        self.assertNotIn(".agents/skills/sd-*/SKILL.md", rewritten)
        self.assertIn("~/.agents/skills", rewritten)

    def test_the_payload_profiles_rewrite_no_literals(self) -> None:
        """The glob problem belongs to the converted repository alone."""

        for profile in (references.PLUGIN_PROFILE, references.MACHINE_PROFILE):
            with self.subTest(profile=profile.name):
                self.assertEqual(dict(profile.literal_rewrites), {})

    def test_text_naming_nothing_relocated_is_returned_unchanged(self) -> None:
        """Conversion offers every kept file, so a no-op has to stay a no-op."""

        source = "Nothing here names a pack resource at all.\n"
        self.assertEqual(
            references.rewrite_text(source, profile=references.THIN_PROFILE),
            source,
        )


class ThinRestoreTests(unittest.TestCase):
    """`restore_thin_text`, which `--revert-thin` uses to undo a repoint."""

    KEY = ".github/PULL_REQUEST_TEMPLATE.md"

    def assert_round_trips(self, source: str, key: str = "") -> str:
        rewritten = references.rewrite_text(
            source, profile=references.THIN_PROFILE, key=key
        )
        self.assertNotEqual(rewritten, source, "nothing was rewritten to undo")
        restored = references.restore_thin_text(rewritten)
        self.assertEqual(restored, source)
        return rewritten

    def test_every_shipped_kept_surface_round_trips(self) -> None:
        """The population, enumerated from the templates rather than listed.

        A test naming two files by hand passes for as long as nobody ships a
        third kept surface with a pack reference in it, and a revert that
        silently stops undoing one is exactly the defect this covers. So the
        candidate set comes off disk: every template whose text the thin
        rewrite changes at all.
        """

        templates = PACK_ROOT / "templates"
        checked = 0
        for path in sorted(templates.rglob("*")):
            if not path.is_file():
                continue
            try:
                source = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                continue
            key = path.relative_to(templates).as_posix()
            rewritten = references.rewrite_text(
                source, profile=references.THIN_PROFILE, key=key
            )
            if rewritten == source:
                continue
            with self.subTest(template=key):
                self.assertEqual(
                    references.restore_thin_text(rewritten), source
                )
            checked += 1
        self.assertGreater(checked, 0, "no template exercises the thin rewrite")

    def test_a_sentence_final_doc_reference_is_restored(self) -> None:
        """The bug the round trip found: `~/.agents/docs.` ends a sentence.

        The forward rule has a leading boundary and no trailing one, so it
        rewrites a reference that a period follows. An inverse that borrowed
        the forward boundary on the trailing side treated that period as part
        of a longer path and left the reference relocated -- through a full
        revert, exit zero, with the file still naming the machine.
        """

        self.assert_round_trips("as described in docs/SD_AI_COMMAND_PACK.md.\n")

    def test_the_machine_manual_path_is_not_read_as_the_thin_directory(self) -> None:
        """`~/.agents/docs/SD_AI_COMMAND_PACK.md` is a different profile's form.

        It starts with the thin directory reference, so an unbounded inverse
        turns it into `docs/SD_AI_COMMAND_PACK.md/SD_AI_COMMAND_PACK.md`.
        """

        source = "the machine payload writes ~/.agents/docs/SD_AI_COMMAND_PACK.md\n"
        self.assertEqual(references.restore_thin_text(source), source)

    def test_the_nested_skills_literal_survives_the_shorter_one(self) -> None:
        """Inversion order, and why it is reversed rather than insertion order.

        One literal's replacement contains the whole of another's, so undoing
        the short form first eats a substring of the long one and leaves a
        bullet neither rule can finish.
        """

        source = (
            "- `**/skills/trellis-*/**` and `**/skills/sd-*/**` under `.agents/`,\n"
            "- entry points: `.agents/skills/sd-*/SKILL.md`\n"
        )
        self.assert_round_trips(source)

    def test_text_naming_nothing_relocated_is_returned_unchanged(self) -> None:
        """Revert offers every kept file, so a no-op has to stay a no-op."""

        source = "Nothing here names a pack resource at all.\n"
        self.assertEqual(references.restore_thin_text(source), source)


if __name__ == "__main__":
    unittest.main()
