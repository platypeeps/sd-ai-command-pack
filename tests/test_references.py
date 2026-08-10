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

from installer import references
from installer.references import (
    MACHINE_PROFILE,
    PACK_DOC_REFERENCE,
    PLUGIN_PROFILE,
    ReferenceRewriteError,
    RewriteProfile,
)

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


if __name__ == "__main__":
    unittest.main()
