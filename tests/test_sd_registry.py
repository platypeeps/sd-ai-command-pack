"""The provider registry, read two ways.

`bin/sd_registry.py` answers through `sd_db.registry` when the library is
installed and from the file alone when it is not. Criterion 32 is the reason
both are allowed to exist and the only thing that keeps them honest: they must
return the same reviewer order from the same `providers.yaml`.

So the comparison below does not skip when the library is missing. A skip
there would leave the one test that pins two implementations together passing
on one of them, which is the failure it exists to catch. `make setup`
provisions the library and CI checks the sibling repository out; where neither
has happened this file says so and fails.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_registry  # noqa: E402

SHIPPED = sd_registry.shipped_path(REPO_ROOT)

#: A whole registry in four lines, for the refusal cases. Each test edits one
#: thing, so the line it changes is the reason it fails.
MINIMAL = """\
bills:
  free: { cost: local }
providers:
  one: { url: "http://localhost:1/v1", vendor: alpha, roles: [author] }
  two: { url: "http://localhost:2/v1", vendor: beta, roles: [reviewer] }
roles:
  author: [one]
  reviewer: [two]
"""


def written(text: str) -> pathlib.Path:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    with handle:
        handle.write(text)
    return pathlib.Path(handle.name)


class TheShippedRegistry(unittest.TestCase):
    """What the pack ships, read as a checkout with no database reads it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = sd_registry.read_file(SHIPPED)

    def test_it_is_at_the_root_of_the_checkout(self) -> None:
        self.assertTrue(SHIPPED.is_file(), f"no registry at {SHIPPED}")
        self.assertEqual(SHIPPED.name, sd_registry.REGISTRY_NAME)

    def test_the_two_roles_resolve_to_different_providers(self) -> None:
        """Criterion 6. A review by the author is not a review."""
        author = self.registry.resolve("author")
        reviewer = self.registry.resolve("reviewer")
        self.assertNotEqual(author.name, reviewer.name)
        self.assertNotEqual(author.vendor, reviewer.vendor)

    def test_every_entry_carries_a_vendor(self) -> None:
        """Criterion 6: an entry whose vendor matches the author's is skipped,
        which needs every entry to have one."""
        for name, provider in self.registry.providers.items():
            with self.subTest(provider=name):
                self.assertTrue(provider.vendor, f"{name} has no vendor")

    def test_no_start_entry_sits_on_a_capped_bill(self) -> None:
        for name, provider in self.registry.providers.items():
            with self.subTest(provider=name):
                if self.registry.bills[provider.bill].capped:
                    self.assertEqual(provider.kind, "url")

    def test_a_disabled_entry_carries_its_reason_and_never_resolves(self) -> None:
        disabled = [
            provider for provider in self.registry.providers.values()
            if not provider.enabled
        ]
        self.assertTrue(disabled, "the shipped registry has no disabled entry")
        for provider in disabled:
            with self.subTest(provider=provider.name):
                self.assertTrue(provider.reason, "disabled with no reason")
        resolved = {
            provider.name
            for role in sd_registry.ROLES
            for provider in self.registry.order(role)
        }
        self.assertEqual(resolved & {provider.name for provider in disabled}, set())

    def test_the_registry_names_no_backend_the_review_lane_used_to_carry(self) -> None:
        """`prism` and `gito` pointed at the same endpoint and added limits of
        their own. The registry is the only list of providers, so their absence
        here is what removes them."""
        self.assertEqual(
            {"prism", "gito"} & set(self.registry.providers), set()
        )


class AddingAProviderIsAnEntry(unittest.TestCase):
    """Criterion 6: a new provider with an OpenAI-compatible URL needs no code
    change, which is a property of having no table of known names."""

    def test_an_unknown_name_with_a_url_resolves(self) -> None:
        path = written(
            MINIMAL.replace(
                "roles:\n  author: [one]\n  reviewer: [two]\n",
                "roles:\n  author: [one]\n  reviewer: [exo, two]\n",
            ).replace(
                '  two: { url: "http://localhost:2/v1", vendor: beta, roles: [reviewer] }\n',
                '  two: { url: "http://localhost:2/v1", vendor: beta, roles: [reviewer] }\n'
                '  exo: { url: "http://localhost:52415/v1", model: pinned-3b, '
                "vendor: local, bill: free, roles: [reviewer] }\n",
            ).replace(
                '  one: { url: "http://localhost:1/v1", vendor: alpha, roles: [author] }',
                '  one: { url: "http://localhost:1/v1", vendor: alpha, bill: free, roles: [author] }',
            ).replace(
                '  two: { url: "http://localhost:2/v1", vendor: beta, roles: [reviewer] }',
                '  two: { url: "http://localhost:2/v1", vendor: beta, bill: free, roles: [reviewer] }',
            )
        )
        registry = sd_registry.read_file(path)
        self.assertEqual(registry.resolve("reviewer").name, "exo")
        self.assertEqual(registry.providers["exo"].model, "pinned-3b")


class TheTwoReadersAgree(unittest.TestCase):
    """Criterion 32, and the only reason a second reader is allowed here."""

    def test_the_library_is_installed_so_the_comparison_means_something(self) -> None:
        self.assertIsNotNone(
            sd_registry.library(),
            "sd_db is not installed in this virtualenv, so the two readers "
            "cannot be compared and this file would pass on one of them. Run "
            "`make setup`, which provisions the library from the `system` "
            "checkout.",
        )

    def test_the_same_file_gives_the_same_reviewer_order(self) -> None:
        by_file = sd_registry.read(SHIPPED, prefer_library=False)
        by_library = sd_registry.read(SHIPPED, prefer_library=True)
        self.assertEqual(
            [provider.name for provider in by_file.order("reviewer")],
            [provider.name for provider in by_library.order("reviewer")],
        )

    def test_the_same_file_gives_the_same_entry_for_every_field(self) -> None:
        by_file = sd_registry.read(SHIPPED, prefer_library=False)
        by_library = sd_registry.read(SHIPPED, prefer_library=True)
        self.assertEqual(by_file.providers, by_library.providers)
        self.assertEqual(by_file.bills, by_library.bills)

    def test_the_file_only_reader_refuses_a_connection_rather_than_ignoring_it(
        self,
    ) -> None:
        """A caller holding a connection and getting file-only answers would be
        reading a registry the dashboard has already changed."""
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.read(SHIPPED, connection=object(), prefer_library=False)
        self.assertIn("sd_db is not installed", str(caught.exception))


class TheRefusals(unittest.TestCase):
    """A registry that cannot mean anything never reaches a caller."""

    def refuse(self, text: str) -> str:
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.parse(text, "fixture.yaml")
        return str(caught.exception)

    def test_a_provider_with_both_start_and_url(self) -> None:
        message = self.refuse(
            MINIMAL.replace(
                '{ url: "http://localhost:1/v1", vendor: alpha, roles: [author] }',
                '{ url: "http://localhost:1/v1", start: "one -p", vendor: alpha, '
                "bill: free, roles: [author] }",
            )
        )
        self.assertIn("both", message)

    def test_a_provider_with_neither(self) -> None:
        message = self.refuse(
            MINIMAL.replace(
                '{ url: "http://localhost:1/v1", vendor: alpha, roles: [author] }',
                "{ vendor: alpha, bill: free, roles: [author] }",
            )
        )
        self.assertIn("neither", message)

    def test_a_start_entry_on_a_capped_bill(self) -> None:
        message = self.refuse(
            MINIMAL.replace("free: { cost: local }", "free: { cost: company }").replace(
                '{ url: "http://localhost:1/v1", vendor: alpha, roles: [author] }',
                '{ start: "one -p", vendor: alpha, bill: free, roles: [author] }',
            )
        )
        self.assertIn("nothing enforces", message)

    def test_a_bill_the_bills_section_does_not_name(self) -> None:
        message = self.refuse(
            MINIMAL.replace(
                '{ url: "http://localhost:1/v1", vendor: alpha, roles: [author] }',
                '{ url: "http://localhost:1/v1", vendor: alpha, bill: nosuch, '
                "roles: [author] }",
            )
        )
        self.assertIn("nosuch", message)

    def test_a_role_list_naming_a_provider_that_does_not_exist(self) -> None:
        message = self.refuse(self.filled().replace("reviewer: [two]", "reviewer: [two, three]"))
        self.assertIn("three", message)

    def test_a_role_list_naming_an_entry_that_does_not_declare_the_role(self) -> None:
        message = self.refuse(self.filled().replace("author: [one]", "author: [one, two]"))
        self.assertIn("may not add one", message)

    def test_one_provider_first_in_both_lists(self) -> None:
        message = self.refuse(
            self.filled()
            .replace("roles: [author]", "roles: [author, reviewer]")
            .replace("reviewer: [two]", "reviewer: [one, two]")
        )
        self.assertIn("a review would be by the author", message)

    def test_a_missing_section(self) -> None:
        # Split on the section header, not on `roles:`, which also opens each
        # entry's own role list -- cutting there truncates a flow value and
        # the refusal that follows is about the brace, not the section.
        without = self.filled().split("\nroles:\n")[0] + "\n"
        self.assertIn("'roles'", self.refuse(without))

    def test_a_tab(self) -> None:
        self.assertIn("a tab", self.refuse(self.filled().replace("  free:", "\tfree:")))

    def test_a_flow_value_that_never_closes(self) -> None:
        self.assertIn("never closed", self.refuse(self.filled().replace("cost: local }", "cost: local")))

    def test_an_unknown_role(self) -> None:
        self.assertIn("'auditor'", self.refuse(self.filled() + "  auditor: [two]\n"))

    def filled(self) -> str:
        """`MINIMAL` with the bill each entry needs, so a test that is not
        about the bill does not fail on it."""
        return MINIMAL.replace("vendor: alpha,", "vendor: alpha, bill: free,").replace(
            "vendor: beta,", "vendor: beta, bill: free,"
        )


class TheHomeItLivesIn(unittest.TestCase):
    def test_the_registry_sits_beside_the_database(self) -> None:
        path = sd_registry.registry_path("/tmp/somewhere")
        self.assertEqual(
            path, pathlib.Path("/tmp/somewhere/.local/share/sd/providers.yaml")
        )

    def test_the_environment_home_is_honoured_when_none_is_given(self) -> None:
        path = sd_registry.registry_path(environ={"HOME": "/tmp/elsewhere"})
        self.assertEqual(
            path, pathlib.Path("/tmp/elsewhere/.local/share/sd/providers.yaml")
        )

    def test_a_missing_file_is_refused_by_path(self) -> None:
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.read_file("/tmp/no/such/providers.yaml")
        self.assertIn("/tmp/no/such/providers.yaml", str(caught.exception))


class TheConsentLine(unittest.TestCase):
    """`CLAUDE.local.md`'s `reviewers` key: who may receive this diff.

    The registry says who can review. This says who may be sent the change,
    from this repository, on this machine. Nothing derives it.
    """

    def test_no_line_at_all_refuses_and_names_the_key(self) -> None:
        with self.assertRaises(sd_registry.ConsentRefusal) as caught:
            sd_registry.parse_consent(None)
        self.assertIn("reviewers", str(caught.exception))

    def test_a_bare_name_is_refused_naming_the_form(self) -> None:
        """An entry is a name for a destination, not the destination."""
        with self.assertRaises(sd_registry.ConsentRefusal) as caught:
            sd_registry.parse_consent("codex, claude@claude")
        message = str(caught.exception)
        self.assertIn("bare name", message)
        self.assertIn("entry@host", message.replace("`", ""))

    def test_commas_and_spaces_separate_the_same_way(self) -> None:
        self.assertEqual(
            sd_registry.parse_consent("a@one, b@two"),
            sd_registry.parse_consent("a@one b@two"),
        )

    def test_a_start_entry_carries_its_executable_and_a_fingerprint(self) -> None:
        registry = sd_registry.read_file(SHIPPED)
        allowance = sd_registry.recipient(registry.providers["codex"])
        self.assertEqual(allowance.recipient, "codex")
        self.assertEqual(
            len(allowance.fingerprint), sd_registry.FINGERPRINT_LENGTH
        )

    def test_a_url_entry_carries_its_host(self) -> None:
        registry = sd_registry.read_file(SHIPPED)
        allowance = sd_registry.recipient(registry.providers["baseten"])
        self.assertEqual(allowance.recipient, "inference.baseten.co")
        self.assertIsNone(allowance.fingerprint)


class WhatConsentRefuses(unittest.TestCase):
    """Each refusal names both values, because the operator has to choose."""

    def setUp(self) -> None:
        self.registry = sd_registry.read_file(SHIPPED)

    def refusal(self, name: str, line: str) -> str:
        allowed = sd_registry.parse_consent(line).get(name)
        message = sd_registry.refuse_allowance(self.registry.providers[name], allowed)
        self.assertIsNotNone(message, f"{name} was allowed and should not be")
        return message or ""

    def test_an_entry_the_line_does_not_name(self) -> None:
        message = self.refusal("kimi", "codex@codex")
        self.assertIn("not on the repository's 'reviewers' line", message)

    def test_a_url_host_edited_to_another_host_names_both(self) -> None:
        message = self.refusal("baseten", "baseten@inference.baseten.co.evil")
        self.assertIn("inference.baseten.co.evil", message)
        self.assertIn("inference.baseten.co'", message)

    def test_a_start_executable_edited_to_another_names_both(self) -> None:
        message = self.refusal("codex", "codex@codex-wrapper")
        self.assertIn("codex-wrapper", message)
        self.assertIn("executable", message)

    def test_an_argument_added_with_the_executable_unchanged(self) -> None:
        """The fingerprint is what catches this; the executable did not move."""
        allowed = sd_registry.parse_consent("codex@codex+00000000")["codex"]
        message = sd_registry.refuse_allowance(self.registry.providers["codex"], allowed)
        self.assertIn("fingerprint", message or "")
        self.assertIn("same one", message or "")

    def test_a_second_entry_for_an_allowed_vendor_is_still_refused(self) -> None:
        """`baseten` allowed does not allow `baseten-openrouter`.

        The line names entries because the entry is the recipient. A second
        entry pointing the same model at another host is another recipient.
        """
        second = sd_registry.Provider(
            name="baseten-openrouter",
            vendor="deepseek",
            bill="local",
            url="https://openrouter.ai/api/v1",
        )
        message = sd_registry.refuse_allowance(second, None)
        self.assertIn("baseten-openrouter", message or "")

    def test_a_line_that_matches_allows_the_entry(self) -> None:
        allowed = sd_registry.recipient(self.registry.providers["baseten"])
        self.assertIsNone(
            sd_registry.refuse_allowance(self.registry.providers["baseten"], allowed)
        )

    def test_a_fingerprint_the_line_omits_is_not_required(self) -> None:
        """The shorter form is the weaker statement, and is allowed to be."""
        allowed = sd_registry.parse_consent("codex@codex")["codex"]
        self.assertIsNone(
            sd_registry.refuse_allowance(self.registry.providers["codex"], allowed)
        )

    def test_a_variable_whose_value_is_a_url_refuses_the_session(self) -> None:
        message = sd_registry.refuse_environment(
            self.registry.providers["codex"],
            {"OPENAI_API_KEY": "https://collector.example/ingest"},
        )
        self.assertIn("OPENAI_API_KEY", message or "")
        self.assertIn("No session was started", message or "")

    def test_the_refusal_prints_no_value(self) -> None:
        """The value is the destination; printing it logs what was refused."""
        secret = "https://collector.example/ingest"
        message = sd_registry.refuse_environment(
            self.registry.providers["codex"], {"OPENAI_API_KEY": secret}
        )
        self.assertNotIn(secret, message or "")

    def test_an_ordinary_key_is_not_a_url_and_passes(self) -> None:
        self.assertIsNone(
            sd_registry.refuse_environment(
                self.registry.providers["codex"], {"OPENAI_API_KEY": "sk-abc"}
            )
        )


class TheReviewerChain(unittest.TestCase):
    """Criterion 6's fallthrough, and what it says about what it passed over."""

    def setUp(self) -> None:
        self.registry = sd_registry.read_file(SHIPPED)
        self.all = sd_registry.parse_consent(
            " ".join(
                str(sd_registry.recipient(provider))
                for provider in self.registry.providers.values()
            )
        )

    def names(self, **kwargs) -> list[str]:
        return [
            candidate.provider.name
            for candidate in sd_registry.reviewer_chain(
                self.registry, consent=self.all, **kwargs
            )
            if candidate.eligible
        ]

    def test_with_everything_allowed_the_chain_is_the_registry_order(self) -> None:
        self.assertEqual(self.names(), ["codex", "claude", "minimax", "kimi", "baseten"])

    def test_an_entry_of_the_author_s_vendor_is_skipped(self) -> None:
        self.assertEqual(self.names(author_vendors=("openai",))[0], "claude")

    def test_a_bill_at_its_cap_is_passed_over(self) -> None:
        self.assertNotIn("baseten", self.names(capped_bills=("baseten",)))

    def test_the_chain_reports_every_entry_it_passed_over_and_why(self) -> None:
        """The interesting sentence is the one about what did not run."""
        chain = sd_registry.reviewer_chain(
            self.registry,
            consent=self.all,
            author_vendors=("openai",),
            capped_bills=("baseten",),
        )
        skipped = {c.provider.name: c.reason for c in chain if not c.eligible}
        self.assertIn("openai", skipped["codex"])
        self.assertIn("cap for the month", skipped["baseten"])
        self.assertEqual(len(chain), 5)

    def test_consent_bounds_the_chain_absolutely(self) -> None:
        """Two allowed, the author's vendor is one of them: one candidate, and
        the fallthrough does not reach a third entry it was never allowed."""
        two = sd_registry.parse_consent("claude@claude codex@codex")
        chain = [
            candidate.provider.name
            for candidate in sd_registry.reviewer_chain(
                self.registry, consent=two, author_vendors=("anthropic",)
            )
            if candidate.eligible
        ]
        self.assertEqual(chain, ["codex"])

    def test_a_disabled_entry_is_not_on_the_chain_at_all(self) -> None:
        self.assertNotIn("exo", [c.provider.name for c in sd_registry.reviewer_chain(
            self.registry, consent=self.all
        )])


class ThePick(unittest.TestCase):
    """`--provider <name>`: one entry for one run, refused by its own reason."""

    def setUp(self) -> None:
        self.registry = sd_registry.read_file(SHIPPED)
        self.all = sd_registry.parse_consent(
            " ".join(
                str(sd_registry.recipient(provider))
                for provider in self.registry.providers.values()
            )
        )

    def test_a_name_the_registry_does_not_carry(self) -> None:
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.pick(self.registry, "greptile", consent=self.all)
        self.assertIn("only list of providers", str(caught.exception))

    def test_a_disabled_entry_is_refused_by_its_reason(self) -> None:
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.pick(self.registry, "exo", consent=self.all)
        self.assertIn("model not pinned", str(caught.exception))

    def test_an_entry_that_does_not_hold_the_role(self) -> None:
        registry = sd_registry.read_file(SHIPPED)
        registry.providers["kimi"] = sd_registry.Provider(
            name="kimi", vendor="moonshot", bill="moonshot", url="http://x/v1",
            roles=("author",), ranks={"author": 9},
        )
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.pick(registry, "kimi", consent=self.all)
        self.assertIn("cannot review", str(caught.exception))

    def test_an_entry_on_no_reviewer_list_is_refused_for_that(self) -> None:
        registry = sd_registry.read_file(SHIPPED)
        registry.providers["kimi"] = sd_registry.Provider(
            name="kimi", vendor="moonshot", bill="moonshot", url="http://x/v1",
            roles=("reviewer",), ranks={},
        )
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.pick(registry, "kimi", consent=self.all)
        self.assertIn("on no reviewer list", str(caught.exception))

    def test_a_bill_at_its_cap_refuses_the_direct_pick_too(self) -> None:
        with self.assertRaises(sd_registry.ConsentRefusal) as caught:
            sd_registry.pick(
                self.registry, "baseten", consent=self.all, capped_bills=("baseten",)
            )
        self.assertIn("cap for the month", str(caught.exception))

    def test_an_allowed_enabled_entry_is_returned(self) -> None:
        self.assertEqual(
            sd_registry.pick(self.registry, "kimi", consent=self.all).name, "kimi"
        )


if __name__ == "__main__":
    unittest.main()
