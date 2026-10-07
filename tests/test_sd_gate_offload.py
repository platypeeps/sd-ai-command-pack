"""The offload view (sd:2704 step 2a): a gate's environment as a hub compares it with a satellite's.

Two logins on two machines differ in `HOME`, `USER` and the home prefix of
every `PATH` entry, so the local `environment_sha256` never matches across
them. `offload_view` leaves those out and binds what they select instead;
`offload_miss` names the first difference that decides a check's result, and
`offload_differences` every difference (sd:2862). Every `HOME`, tool and
`PATH` entry here is a temporary folder, so nothing reads the real home.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_receipts  # noqa: E402
import sd_gate_run  # noqa: E402
import sd_gate_slots  # noqa: E402


class ViewFixture(unittest.TestCase):
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

    def view(self, login: str, names: tuple[str, ...] = (), tree: pathlib.Path | None = None, **extra: str) -> dict:
        environment = sd_gate_run.gate_environment(self.tmp / "repo", self.environ(login, **extra))
        view = sd_gate_receipts.offload_view(environment, names, tree)
        self.assertIsNotNone(view)
        return view


class OffloadView(ViewFixture):
    """Two logins' views compared: what is recorded and what refuses."""

    def test_two_logins_that_differ_only_in_home_user_and_the_path_prefix_compare_equal(self) -> None:
        theirs, ours = self.view("sat"), self.view("hub")
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours))
        self.assertEqual(theirs["path"][0], "~/bin")
        self.assertEqual(theirs["variables"]["CARGO_HOME"], ours["variables"]["CARGO_HOME"])
        self.assertNotIn("HOME", theirs["variables"])
        self.assertNotIn("USER", theirs["variables"])
        self.assertIsNotNone(theirs["tools"]["make"])

    def recorded(self, theirs: dict, ours: dict, names: tuple[str, ...] = ()) -> list:
        """Every difference, each recorded and none refusing: `offload_miss` answers None (sd:2862)."""
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours, names))
        found = sd_gate_receipts.offload_differences(theirs, ours, names)
        self.assertFalse([miss for miss in found if miss["refuses"]])
        return [(miss["part"], miss["name"]) for miss in found]

    def test_another_path_order_is_recorded_not_refused(self) -> None:
        """sd:2862: the hub's launchd job and the satellite's shell order `PATH` differently; the tools it picks compare by bytes."""
        reordered = os.pathsep.join([str(self.shared), str(self.home("hub") / "bin")])
        self.assertEqual(self.recorded(self.view("sat"), self.view("hub", PATH=reordered)), [("path", "~/bin")])

    def test_the_machines_of_sd_2844_differ_and_the_satellites_pass_stands(self) -> None:
        """sd:2862: the first satellite merge differed in all of these; each is recorded, none refuses."""
        for login, version in (("sat", "2.50"), ("hub", "2.51")):
            self.tool(self.home(login) / "bin" / "git", f"git {version}")
            self.tool(self.home(login) / "bin" / "uv", f"uv {version}")
        (self.home("hub") / ".gitconfig").write_text("[user]\n\tname = hub\n", encoding="utf-8")
        (self.home("sat") / ".cargo").mkdir()
        (self.home("sat") / ".cargo" / "config.toml").write_text("[build]\n", encoding="utf-8")
        theirs = self.view("sat", CARGO_BUILD_JOBS="4", NEXTEST_TEST_THREADS="4", SD_GATE_POOL_SIZE="2")
        ours = self.view("hub", SD_NOTION_PRIVATE_FOLDER="/n")  # scrubbed: no check sees it, so it is not compared
        self.assertEqual(self.recorded(theirs, ours), [
            ("tools", "git"), ("tools", "uv"), ("home_files", ".cargo/config.toml"), ("home_files", ".gitconfig"),
            ("variables", "CARGO_BUILD_JOBS"), ("variables", "NEXTEST_TEST_THREADS"), ("variables", "SD_GATE_POOL_SIZE")])

    def test_an_sd_variable_the_gate_does_not_set_never_reaches_the_check(self) -> None:
        """sd:2862 review: a check that reads `SD_SKIP_TESTS` could skip its tests on one machine only; it sees nothing."""
        kept = sd_gate_receipts.offload_environment(
            sd_gate_run.gate_environment(self.tmp / "repo", self.environ("sat", SD_SKIP_TESTS="1", SD_GATE_SLOTS="2")))
        self.assertNotIn("SD_SKIP_TESTS", kept)
        self.assertEqual((kept["SD_LOCAL_GATE"], kept["SD_GATE_SLOTS"]), ("1", "2"))

    def test_a_check_named_tool_outside_the_toolchain_refuses(self) -> None:
        """`npm test` decides its own result, so `npm` refuses when the check names it, and is recorded when not."""
        self.tool(self.home("sat") / "bin" / "npm", "npm 10")
        self.tool(self.home("hub") / "bin" / "npm", "npm 11")
        theirs, ours = self.view("sat", ("npm",)), self.view("hub", ("npm",))
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours, ("npm",)), {"part": "tools", "name": "npm"})
        self.assertEqual(self.recorded(theirs, ours), [("tools", "npm")])

    def test_the_runtime_behind_a_launcher_refuses(self) -> None:
        """sd:2862 review: `npm run check` names only `npm`, and equal `npm` bytes can run another `node`."""
        for login, version in (("sat", "22"), ("hub", "24")):
            self.tool(self.home(login) / "bin" / "npm", "npm 10")
            self.tool(self.home(login) / "bin" / "node", f"node {version}")
        theirs, ours = self.view("sat", ("npm",)), self.view("hub", ("npm",))
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours, ("npm",)), {"part": "tools", "name": "node"})

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
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours, names), {"part": "tools", "name": "just"})

    def test_a_named_home_file_with_other_bytes_is_recorded(self) -> None:
        (self.home("hub") / ".gitconfig").write_text("[core]\n\thooksPath = /dev/null\n", encoding="utf-8")
        self.assertEqual(self.recorded(self.view("sat"), self.view("hub")), [("home_files", ".gitconfig")])

    def test_a_named_home_file_on_one_side_only_is_recorded(self) -> None:
        (self.home("sat") / ".npmrc").write_text("registry=https://registry.example.test/\n", encoding="utf-8")
        theirs, ours = self.view("sat"), self.view("hub")
        self.assertEqual(ours["home_files"][".npmrc"], "absent")
        self.assertEqual(self.recorded(theirs, ours), [("home_files", ".npmrc")])

    def test_another_variable_value_misses_on_variables(self) -> None:
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", LANG="en_US.UTF-8")),
                         {"part": "variables", "name": "LANG"})

    def test_a_variable_on_one_side_only_misses(self) -> None:
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", MAKEFLAGS="-j8")),
                         {"part": "variables", "name": "MAKEFLAGS"})

    def test_per_login_and_per_session_variables_compare_equal(self) -> None:
        """sd:2782 M2: a builder shell and a cron job differ in these, and none chooses what a check runs."""
        theirs = self.view("sat", __CF_USER_TEXT_ENCODING="0x1F5:0:0", SSH_AUTH_SOCK="/private/tmp/a/Listeners",
                           TMPDIR="/var/folders/aa/T/", LOGNAME="sat", TERM_PROGRAM_VERSION="3.5", XPC_SERVICE_NAME="0")
        ours = self.view("hub", __CF_USER_TEXT_ENCODING="0x1F6:0:0", LOGNAME="hub", MAILTO="")
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours))
        self.assertNotIn("__CF_USER_TEXT_ENCODING", theirs["variables"])

    def test_an_allowlisted_variable_by_prefix_still_misses(self) -> None:
        self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", RUSTFLAGS="-Dwarnings")),
                         {"part": "variables", "name": "RUSTFLAGS"})

    def test_a_build_or_test_control_misses(self) -> None:
        """Review rounds 1 and 2: `CFLAGS=-DNDEBUG` or `PYTEST_ADDOPTS='-k smoke'` runs other tests."""
        for name, value in (("CC", "gcc-15"), ("CFLAGS", "-DNDEBUG"), ("LDFLAGS", "-L/opt/lib"), ("SDKROOT", "/sdk"),
                            ("PYTEST_ADDOPTS", "-k smoke"), ("COVERAGE_RCFILE", "/c"), ("TASK_TEMP_DIR", "/t"),
                            ("TZ", "UTC"), ("BASH_ENV", "/b"), ("LD_PRELOAD", "/l.so"), ("DYLD_INSERT_LIBRARIES", "/d"),
                            ("GIT_DIR", "/g")):
            with self.subTest(name=name):
                self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub", **{name: value})),
                                 {"part": "variables", "name": name})

    def test_a_credential_is_neither_compared_nor_stored(self) -> None:
        """sd:2782 L6: no digest of a credential reaches the view, even under an allowlisted prefix."""
        theirs = self.view("sat", GITHUB_TOKEN="x", CARGO_REGISTRY_TOKEN="y")
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, self.view("hub")))
        self.assertFalse({"GITHUB_TOKEN", "CARGO_REGISTRY_TOKEN"} & set(theirs["variables"]))

    def test_an_offloaded_run_keeps_git_command_scope_config(self) -> None:
        """`GIT_CONFIG_COUNT` without its `GIT_CONFIG_KEY_<n>` fails every git call; `KEY` there names no credential."""
        git_config = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0"}
        kept = sd_gate_receipts.offload_environment({**self.environ("sat"), **git_config, "API_KEY": "x"})
        self.assertEqual({name: kept.get(name) for name in git_config}, git_config)
        self.assertNotIn("API_KEY", kept)

    def test_other_thread_caps_are_recorded(self) -> None:
        """sd:2782 M1: `machine_binding` binds the caps locally; across machines they follow the core count (sd:2862)."""
        for login, slots in (("sat", 16), ("hub", 2)):
            config = self.home(login) / ".config" / "sd-ai-command-pack" / "config.json"
            config.parent.mkdir(parents=True)
            config.write_text(f'{{"config": {{"sd": {{"gate_slots": {slots}}}}}}}', encoding="utf-8")
        with mock.patch.object(sd_gate_slots.os, "cpu_count", return_value=16):
            theirs, ours = self.view("sat"), self.view("hub")
        self.assertEqual((theirs["threads"]["RUST_TEST_THREADS"], ours["threads"]["RUST_TEST_THREADS"]), ("1", "8"))
        self.assertEqual(self.recorded(theirs, ours), [("threads", name) for name in sorted(sd_gate_slots.CPU_VARIABLES)])

    def test_a_view_written_before_threads_were_bound_is_recorded(self) -> None:
        ours = self.view("hub")
        old = {name: part for name, part in ours.items() if name != "threads"}
        self.assertEqual(self.recorded(old, ours), [("threads", None)])

    def test_a_view_that_is_not_one_misses(self) -> None:
        ours = self.view("hub")
        self.assertEqual(sd_gate_receipts.offload_miss(None, ours), {"part": "view", "name": None})
        self.assertEqual(sd_gate_receipts.offload_miss({**ours, "tools": []}, ours), {"part": "tools", "name": None})


#: A fake `rustup`: `which <tool>` names the toolchain a path in `RUSTUP_TOOLCHAIN` or the cwd's `rust-toolchain.toml` pins.
FAKE_RUSTUP = """[ "$1" = which ] || exit 1
[ -n "$RUSTUP_TOOLCHAIN" ] && echo "$RUSTUP_TOOLCHAIN/bin/$2" && exit
[ -f rust-toolchain.toml ] || exit 1
while read -r key _ value; do [ "$key" = channel ] && channel=${value#\\"} && channel=${channel%\\"}; done < rust-toolchain.toml
[ -n "$channel" ] || exit 1
echo "$HOME/.rustup/toolchains/$channel/bin/$2"
"""


def part(mode: str = "full", tools: list[str] | None = None) -> dict:
    """A tree part as `tree_binding` writes it, for a `make check` repository in `mode`'s scope, declaring `tools`."""
    return {"schema": 2, "reuse": "head", "head": "a" * 40, "fork": None, "tree": "t" * 40, "inputs": "i" * 12,
            "scope": {"mode": mode, "fork": None, "command": ["make", "docs-gate"] if mode == "docs-only" else [],
                      **({"tools": tools} if tools is not None else {})},
            "detection": {"source": "Makefile", "commands": {"check": ["make", "check"]}}}


class RustupResolution(ViewFixture):
    """sd:2881: the satellite's `cargo` is a Homebrew rustup wrapper, the hub's another proxy or Homebrew's own `cargo`.

    A proxy's bytes name no toolchain; the tree's `rust-toolchain.toml` does, through `rustup which`.
    """

    def setUp(self) -> None:
        super().setUp()
        self.tree = self.tmp / "tree"
        self.tree.mkdir()
        (self.tree / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.98.1"\n', encoding="utf-8")
        for login in ("sat", "hub"):
            self.script(self.home(login) / "bin" / "rustup", FAKE_RUSTUP)
            for name in ("cargo", "rustc"):
                self.script(self.home(login) / ".rustup" / "toolchains" / "1.98.1" / "bin" / name,
                            f'echo "{name} 1.98.1 (797e8a9bc 2026-08-05)"\n')
        self.proxy("sat", "RUSTUP_OVERRIDE_UNIX_FALLBACK_SETTINGS=/opt/homebrew/etc/rustup/settings.toml ")
        self.proxy("hub", "")

    @staticmethod
    def script(path: pathlib.Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def proxy(self, login: str, prefix: str) -> None:
        """`cargo` and `rustc` that run the toolchain `rustup which` names, each login's wrapper with its own bytes."""
        for name in ("cargo", "rustc"):
            self.script(self.home(login) / "bin" / name, f'{prefix}exec "$(rustup which {name})" "$@"\n')

    def mismatch(self, theirs: dict, ours: dict, mode: str = "full", tools: list[str] | None = None) -> dict | None:
        row = {"binding": {**part(mode, tools), "environment_mode": "offload"}, "offload_view": theirs}
        return sd_gate_receipts.binding_mismatch(row, part(mode, tools), ours, "offload")

    def test_two_proxies_hash_the_toolchain_the_tree_pins(self) -> None:
        theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
        self.assertEqual(theirs["resolution"], {"cargo": "rustup", "rustc": "rustup"})
        self.assertEqual(theirs["tools"]["cargo"], ours["tools"]["cargo"])
        self.assertIsNone(self.mismatch(theirs, ours))

    def test_a_gates_worktree_resolves_in_its_own_tree(self) -> None:
        """Both sides take the view through `Worktree.view`: the satellite when it writes the row, the hub when it compares."""
        environment = sd_gate_run.gate_environment(self.tmp / "repo", self.environ("sat"))
        gated = sd_gate_receipts.Worktree(self.tmp / "repo", self.tree, "a" * 40, None, environment, None, None, False, "i" * 12)
        self.assertEqual(gated.view(part())["resolution"], {"cargo": "rustup", "rustc": "rustup"})

    def test_a_row_from_before_the_resolution_refuses_and_says_it_recorded_none(self) -> None:
        """A 7801d8b8 view hashed the wrapper and has no `resolution`: it refuses on `tools.cargo` (its pack digest first)."""
        ours = self.view("hub", tree=self.tree)
        old = {name: value for name, value in self.view("sat").items() if name != "resolution"}
        self.assertIn("tools at cargo (satellite via unrecorded, hub via rustup)", self.mismatch(old, ours)["reason"])

    def test_a_cargo_that_is_no_proxy_keeps_its_own_bytes_and_refuses(self) -> None:
        """The hub's cron `PATH` finds Homebrew's `cargo` 1.99.0, which ignores the pin: the hub would run another compiler."""
        self.script(self.home("hub") / "bin" / "cargo", 'echo "cargo 1.99.0 (5f94df478 2026-08-27) (Homebrew)"\n')
        theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
        self.assertEqual(ours["resolution"], {"cargo": "path", "rustc": "rustup"})
        self.assertIn("tools at cargo (satellite via rustup, hub via path)", self.mismatch(theirs, ours)["reason"])

    def test_a_cargo_that_prints_the_pinned_version_but_is_no_proxy_keeps_its_own_bytes(self) -> None:
        """Review round 1: equal `--version` output proves no dispatch; neither does a wrapper that adds arguments."""
        for body in ('# another build\necho "cargo 1.98.1 (797e8a9bc 2026-08-05)"\n', 'exec "$(rustup which cargo)" --locked "$@"\n'):
            with self.subTest(body=body):
                self.script(self.home("hub") / "bin" / "cargo", body)
                theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
                self.assertEqual(ours["resolution"]["cargo"], "path")
                self.assertIn("tools at cargo (satellite via rustup, hub via path)", self.mismatch(theirs, ours)["reason"])

    def test_a_tree_that_pins_nothing_or_no_rustup_hashes_the_path_tool(self) -> None:
        for login in ("sat", "hub"):
            (self.home(login) / "bin" / "rustup").unlink()
        self.assertEqual(self.view("sat", tree=self.tree)["resolution"], {"cargo": "path", "rustc": "path"})
        self.assertEqual(self.view("sat", tree=self.tmp)["resolution"], {"cargo": "path", "rustc": "path"})

    def test_a_docs_only_scope_refuses_on_its_declared_tools_only(self) -> None:
        """`make docs-gate` may run `cargo doc`, so a compiler still refuses, unless `docs_tools` names what it reaches."""
        self.script(self.home("hub") / "bin" / "cargo", 'echo "cargo 1.99.0 (Homebrew)"\n')
        self.tool(self.home("hub") / "bin" / "cc", "clang 21")
        theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
        self.assertIn("tools at cargo", self.mismatch(theirs, ours, "docs-only")["reason"])
        self.assertIsNone(self.mismatch(theirs, ours, "docs-only", ["sh", "python3"]))
        self.tool(self.shared / "sh", "another sh")
        self.assertIn("tools at sh", self.mismatch(theirs, self.view("hub", tree=self.tree), "docs-only", ["sh"])["reason"])
        self.tool(self.home("hub") / "bin" / "make", "make 3.81")
        self.assertIn("tools at make", self.mismatch(theirs, self.view("hub", tree=self.tree), "docs-only", [])["reason"])

    def test_a_declared_docs_tool_outside_the_toolchain_is_bound(self) -> None:
        """`check_names` carries `docs_tools`, so the view hashes one that `OFFLOAD_TOOLS` does not name."""
        self.tool(self.home("sat") / "bin" / "markdownlint", "markdownlint 1")
        self.tool(self.home("hub") / "bin" / "markdownlint", "markdownlint 2")
        names = tuple(sd_gate_receipts.check_names(part("docs-only", ["markdownlint"])))
        theirs, ours = self.view("sat", names, tree=self.tree), self.view("hub", names, tree=self.tree)
        self.assertIn("tools at markdownlint", self.mismatch(theirs, ours, "docs-only", ["markdownlint"])["reason"])

if __name__ == "__main__":
    unittest.main()
