"""The offload view (sd:2704 step 2a): a gate's environment as a hub compares it with a satellite's.

Two logins on two machines differ in `HOME`, `USER` and the home prefix of
every `PATH` entry, so the local `environment_sha256` never matches across
them. `offload_view` leaves those out and binds what they select instead;
`offload_miss` names the first part that differs. Every `HOME`, tool and
`PATH` entry here is a temporary folder, so nothing reads the real home.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_receipts  # noqa: E402
import sd_gate_run  # noqa: E402


class OffloadView(unittest.TestCase):
    """A satellite login (`sat`) and a hub login (`hub`), each with `~/bin` ahead of one shared folder."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)  # unresolved, as a real HOME may be; the gate resolves PATH entries
        self.shared = self.tmp / "usr" / "bin"
        self.shared.mkdir(parents=True)
        self.tool(self.shared / "sh", "shared sh")
        for login in ("sat", "hub"):
            self.tool(self.home(login) / "bin" / "make", "make 4.4")
            (self.home(login) / ".gitconfig").write_text("[user]\n\tname = t\n", encoding="utf-8")

    def home(self, login: str) -> pathlib.Path:
        return self.tmp / "Users" / login

    @staticmethod
    def tool(path: pathlib.Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!/bin/sh\n# {text}\n", encoding="utf-8")
        path.chmod(0o755)

    def environ(self, login: str, **extra: str) -> dict[str, str]:
        home = self.home(login)
        return {"HOME": str(home), "USER": login, "LANG": "C", "CARGO_HOME": str(home / ".cargo"),
                "PATH": os.pathsep.join([str(home / "bin"), str(self.shared)]), **extra}

    def view(self, login: str, names: tuple[str, ...] = (), **extra: str) -> dict:
        environment = sd_gate_run.gate_environment(self.tmp / "repo", self.environ(login, **extra))
        view = sd_gate_receipts.offload_view(environment, names)
        self.assertIsNotNone(view)
        return view

    def test_two_logins_that_differ_only_in_home_user_and_the_path_prefix_compare_equal(self) -> None:
        theirs, ours = self.view("sat"), self.view("hub")
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours))
        self.assertEqual(theirs["path"][0], "~/bin")
        self.assertEqual(theirs["variables"]["CARGO_HOME"], ours["variables"]["CARGO_HOME"])
        self.assertNotIn("HOME", theirs["variables"])
        self.assertNotIn("USER", theirs["variables"])
        self.assertIsNotNone(theirs["tools"]["make"])

    def test_another_path_order_misses_on_path(self) -> None:
        reordered = os.pathsep.join([str(self.shared), str(self.home("hub") / "bin")])
        miss = sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", PATH=reordered))
        self.assertEqual(miss, {"part": "path", "name": "~/bin"})

    def test_a_home_prefix_needs_a_folder_boundary(self) -> None:
        """`/Users/hubber` is not under `/Users/hub`."""
        self.tool(self.tmp / "Users" / "hubber" / "bin" / "make", "make 4.4")
        other = self.tmp / "Users" / "hubber" / "bin"
        view = self.view("hub", PATH=os.pathsep.join([str(other), str(self.shared)]))
        self.assertEqual(view["path"][0], str(other.resolve()))

    def test_a_named_tool_with_other_bytes_misses_on_tools(self) -> None:
        self.tool(self.home("hub") / "bin" / "make", "make 3.81")
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub")),
                         {"part": "tools", "name": "make"})

    def test_a_tool_the_hub_cannot_resolve_is_recorded_not_compared(self) -> None:
        self.tool(self.home("sat") / "bin" / "cargo", "cargo 1.90")
        theirs, ours = self.view("sat"), self.view("hub")
        self.assertEqual((theirs["tools"]["cargo"] is None, ours["tools"]["cargo"]), (False, None))
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours))

    def test_a_tool_only_the_hub_resolves_misses(self) -> None:
        self.tool(self.home("hub") / "bin" / "cargo", "cargo 1.90")
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub")),
                         {"part": "tools", "name": "cargo"})

    def test_the_checks_own_tool_is_bound_and_one_in_the_tree_is_left_to_inputs(self) -> None:
        self.tool(self.home("sat") / "bin" / "just", "just 1")
        self.tool(self.home("hub") / "bin" / "just", "just 2")
        names = ("just", "scripts/check")
        theirs, ours = self.view("sat", names), self.view("hub", names)
        self.assertNotIn("scripts/check", theirs["tools"])
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "tools", "name": "just"})

    def test_a_named_home_file_with_other_bytes_misses_on_home_files(self) -> None:
        (self.home("hub") / ".gitconfig").write_text("[core]\n\thooksPath = /dev/null\n", encoding="utf-8")
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub")),
                         {"part": "home_files", "name": ".gitconfig"})

    def test_a_named_home_file_on_one_side_only_misses(self) -> None:
        (self.home("sat") / ".npmrc").write_text("registry=https://registry.example.test/\n", encoding="utf-8")
        theirs, ours = self.view("sat"), self.view("hub")
        self.assertEqual(ours["home_files"][".npmrc"], "absent")
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "home_files", "name": ".npmrc"})

    def test_another_variable_value_misses_on_variables(self) -> None:
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", LANG="en_US.UTF-8")),
                         {"part": "variables", "name": "LANG"})

    def test_a_variable_on_one_side_only_misses(self) -> None:
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", MAKEFLAGS="-j8")),
                         {"part": "variables", "name": "MAKEFLAGS"})

    def test_a_view_that_is_not_one_misses(self) -> None:
        ours = self.view("hub")
        self.assertEqual(sd_gate_receipts.offload_miss(None, ours), {"part": "view", "name": None})
        self.assertEqual(sd_gate_receipts.offload_miss({**ours, "tools": []}, ours), {"part": "tools", "name": None})


if __name__ == "__main__":
    unittest.main()
