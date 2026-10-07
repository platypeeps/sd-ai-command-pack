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
import shutil
import subprocess
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

    def gate_slots(self, **slots: int) -> None:
        """Each login's machine-wide `sd.gate_slots`."""
        for login, count in slots.items():
            config = self.home(login) / ".config" / "sd-ai-command-pack" / "config.json"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(f'{{"config": {{"sd": {{"gate_slots": {count}}}}}}}', encoding="utf-8")

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
        environment = sd_gate_receipts.offload_environment(sd_gate_run.gate_environment(self.tmp / "repo",
                                                                                          self.environ(login, **extra)))
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

    def test_only_path_order_and_the_slot_holders_settings_are_recorded(self) -> None:
        """sd:2879: of what the machines of sd:2844 differed in, these two decide nothing the check runs."""
        reordered = os.pathsep.join([str(self.shared), str(self.home("hub") / "bin")])
        theirs = self.view("sat", SD_GATE_POOL_SIZE="2")
        ours = self.view("hub", PATH=reordered, SD_NOTION_PRIVATE_FOLDER="/n")  # scrubbed: no check sees it
        self.assertEqual(self.recorded(theirs, ours), [("path", "~/bin"), ("variables", "SD_GATE_POOL_SIZE")])

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

    def test_a_tool_the_check_reaches_through_make_refuses(self) -> None:
        """sd:2879 finding 3: `make check` may run `npm ci`, `uv sync` or `git`, and `check_names` sees only `make`."""
        for name in ("git", "npm", "uv"):
            with self.subTest(name=name):
                self.tool(self.home("sat") / "bin" / name, f"{name} 1")
                self.tool(self.home("hub") / "bin" / name, f"{name} 2")
                self.assertEqual(sd_gate_receipts.offload_miss(self.view("sat"), self.view("hub"), ("make",)),
                                 {"part": "tools", "name": name})
                self.tool(self.home("hub") / "bin" / name, f"{name} 1")

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

    def test_an_opted_in_check_reads_no_home_tool_configuration(self) -> None:
        """sd:2879 finding 1: git, npm, pip and cargo read no file under `HOME` or the system's, whatever the caller set."""
        caller = self.environ("sat", CARGO_HOME="/elsewhere/.cargo", GIT_CONFIG_GLOBAL="/elsewhere/gitconfig",
                              PIP_CONFIG_FILE="/elsewhere/pip.conf", NPM_CONFIG_USERCONFIG="/elsewhere/npmrc")
        kept = sd_gate_receipts.offload_environment(sd_gate_run.gate_environment(self.tmp / "repo", caller))
        self.assertEqual({name: kept.get(name) for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "NPM_CONFIG_USERCONFIG",
                                                            "PIP_CONFIG_FILE")},
                         {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "NPM_CONFIG_USERCONFIG": os.devnull,
                          "PIP_CONFIG_FILE": os.devnull})
        gate_cache = self.home("sat") / ".cache" / "sd" / "gate"
        for name in ("CARGO_HOME", "NPM_CONFIG_GLOBALCONFIG"):  # the gate's own folder, which holds no configuration
            self.assertTrue(pathlib.Path(kept[name]).is_relative_to(gate_cache), kept[name])
        git = shutil.which("git")
        assert git is not None
        read = [subprocess.run([git, "config", "--get", "user.name"], env=env, cwd=self.tmp, text=True,
                               capture_output=True, check=False).stdout for env in (self.environ("sat"), kept)]
        self.assertEqual(read, ["t\n", ""])  # the fixture's `~/.gitconfig` names `t`

    def test_a_bound_cargo_subcommand_is_copied_for_the_gate_and_refuses(self) -> None:
        """sd:2921: cargo finds `cargo-nextest` in `$CARGO_HOME/bin`, and the pinned one holds none. The gate copies the
        caller's, `~/.cargo/bin` by default, into its own folder, and the view binds the copy's bytes."""
        views = {}
        for login, version in (("sat", "0.9.100"), ("hub", "0.9.101")):
            self.tool(self.home(login) / ".cargo" / "bin" / "cargo-nextest", f"cargo-nextest {version}")
            for caller in ("CARGO_HOME", "HOME"):
                with self.subTest(login=login, caller=caller):
                    tree = self.tmp / f"gate-{login}-{caller}" / "tree"
                    tree.mkdir(parents=True)
                    environ = {key: value for key, value in self.environ(login).items()
                               if not (caller == "HOME" and key == "CARGO_HOME")}
                    environment = sd_gate_receipts.offload_environment(environ)
                    sd_gate_receipts.cargo_subcommands(environ, tree, self.tmp / "repo", "offload")
                    copy = tree.parent / sd_gate_receipts.CARGO_SUBCOMMANDS / "cargo-nextest"
                    self.assertEqual(copy.read_bytes(), (self.home(login) / ".cargo" / "bin" / "cargo-nextest").read_bytes())
                    views[login] = sd_gate_receipts.offload_view(environment, (), tree)
                    self.assertEqual(views[login]["tools"]["cargo-nextest"], sd_gate_receipts._content_digest(copy))
        self.assertEqual(sd_gate_receipts.offload_miss(views["sat"], views["hub"]), {"part": "tools", "name": "cargo-nextest"})

    def test_a_check_that_runs_the_subcommand_itself_binds_the_gates_copy(self) -> None:
        """sd:2921 r4 review: `machine_binding` resolves the check's own names on the check's `PATH`, and names the
        copy by its place in the gate's folder, not by the temporary folder's random name."""
        self.tool(self.home("sat") / ".cargo" / "bin" / "cargo-nextest", "cargo-nextest 0.9.100")
        tree = self.tmp / "gate" / "tree"
        tree.mkdir(parents=True)
        environ = self.environ("sat")
        environment = sd_gate_receipts.offload_environment(environ)
        sd_gate_receipts.cargo_subcommands(environ, tree, self.tmp / "repo", "offload")
        bound = sd_gate_receipts.machine_binding(tree, [["cargo-nextest", "run"]], environment)["tools"]
        copy = tree.parent / sd_gate_receipts.CARGO_SUBCOMMANDS / "cargo-nextest"
        self.assertEqual(bound, [{"invocation": "cargo-nextest", "path": "subcommands:cargo-nextest",
                                  "sha256": sd_gate_receipts.sd_check_receipts.file_digest(copy)}])

    def test_a_check_that_runs_cargo_nextest_binds_the_gates_copy(self) -> None:
        """sd:2921 r6 review: `cargo nextest` runs the copy too, as the pinned `CARGO_HOME/bin` holds none; the view
        resolves the name on the check's `PATH`, which starts with the copy, not on the gate's `PATH`."""
        self.tool(self.home("sat") / ".cargo" / "bin" / "cargo-nextest", "cargo-nextest 0.9.100")
        self.tool(self.tmp / "decoy" / "cargo-nextest", "cargo-nextest decoy")
        tree = self.tmp / "gate" / "tree"
        tree.mkdir(parents=True)
        environ = self.environ("sat")
        environment = sd_gate_receipts.offload_environment(environ)
        environment["PATH"] = os.pathsep.join([str(self.tmp / "decoy"), environment["PATH"]])
        sd_gate_receipts.cargo_subcommands(environ, tree, self.tmp / "repo", "offload")
        copy = tree.parent / sd_gate_receipts.CARGO_SUBCOMMANDS / "cargo-nextest"
        self.assertIsNone(sd_gate_receipts.pinned_subcommands(environment, "offload"))
        self.assertEqual(sd_gate_receipts.view_tools(environment, (), tree)[0]["cargo-nextest"],
                         sd_gate_receipts._content_digest(copy))
        self.assertEqual(sd_gate_receipts.machine_binding(tree, [["cargo-nextest", "run"]], environment)["tools"][0]["path"],
                         "subcommands:cargo-nextest")

    def test_the_pins_hold_on_an_environment_they_already_pinned(self) -> None:
        """A pass under `offload_environment` reuses only when a second pinning changes nothing (sd:2921)."""
        once = sd_gate_receipts.offload_environment(self.environ("sat"))
        self.assertEqual(sd_gate_receipts.offload_environment(once), once)

    def test_an_isolated_home_file_is_not_bound(self) -> None:
        """No check reads `.gitconfig`, `.npmrc`, pip's or cargo's file, so two machines may differ in them (sd:2879)."""
        (self.home("hub") / ".gitconfig").write_text("[core]\n\thooksPath = /dev/null\n", encoding="utf-8")
        (self.home("sat") / ".npmrc").write_text("registry=https://registry.example.test/\n", encoding="utf-8")
        (self.home("sat") / ".cargo").mkdir()
        (self.home("sat") / ".cargo" / "config.toml").write_text("[build]\n", encoding="utf-8")
        self.assertEqual(sd_gate_receipts.offload_differences(self.view("sat"), self.view("hub")), [])

    def test_configuration_left_in_the_pinned_folders_refuses(self) -> None:
        """sd:2879 review: the pinned `CARGO_HOME` and npm global file persist, and an earlier check could leave a
        cargo `runner` there; the view binds their bytes, so one machine's leftover refuses."""
        environment = sd_gate_receipts.offload_environment(self.environ("hub"))
        for name, path in (("$CARGO_HOME/config.toml", pathlib.Path(environment["CARGO_HOME"], "config.toml")),
                           ("$CARGO_HOME/config", pathlib.Path(environment["CARGO_HOME"], "config")),
                           ("$NPM_CONFIG_GLOBALCONFIG", pathlib.Path(environment["NPM_CONFIG_GLOBALCONFIG"]))):
            with self.subTest(name=name):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('[target.aarch64-apple-darwin]\nrunner = "true"\n', encoding="utf-8")
                theirs, ours = self.view("sat"), self.view("hub")
                self.assertEqual(theirs["home_files"][name], "absent")
                self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "home_files", "name": name})
                path.unlink()

    def test_uvs_file_under_xdg_config_home_refuses(self) -> None:
        """uv reads `$XDG_CONFIG_HOME/uv/uv.toml` when the variable is set, not `~/.config/uv/uv.toml`."""
        config = self.tmp / "config"
        (config / "uv").mkdir(parents=True)
        theirs = self.view("sat", XDG_CONFIG_HOME=str(config))
        (config / "uv" / "uv.toml").write_text('index-url = "https://pypi.example.test/simple"\n', encoding="utf-8")
        ours = self.view("hub", XDG_CONFIG_HOME=str(config))
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "home_files", "name": "$XDG_CONFIG_HOME/uv/uv.toml"})

    def test_a_home_file_the_check_still_reads_refuses(self) -> None:
        """sd:2879 finding 1: `UV_NO_CONFIG` would skip the tree's own `uv.toml` too, so uv's user file is compared."""
        uv = self.home("hub") / ".config" / "uv" / "uv.toml"
        uv.parent.mkdir(parents=True)
        uv.write_text('index-url = "https://pypi.example.test/simple"\n', encoding="utf-8")
        theirs, ours = self.view("sat"), self.view("hub")
        self.assertEqual(theirs["home_files"][".config/uv/uv.toml"], "absent")
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "home_files", "name": ".config/uv/uv.toml"})

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

    def test_an_opted_in_check_runs_under_one_thread_cap_on_every_machine(self) -> None:
        """sd:2879 finding 2: 2 slots and 4 on 16 cores, and a caller's own lower caps, all run at `OFFLOAD_THREADS`."""
        self.gate_slots(sat=4, hub=2)
        with mock.patch.object(sd_gate_slots.os, "cpu_count", return_value=16):
            theirs = self.view("sat", RUST_TEST_THREADS="1", CARGO_BUILD_JOBS="2")
            ours = self.view("hub")
            child = sd_gate_slots.holder_environment(sd_gate_receipts.offload_environment(self.environ("hub")), 2)
        common = dict.fromkeys(sd_gate_slots.CPU_VARIABLES, sd_gate_receipts.OFFLOAD_THREADS)
        self.assertEqual((theirs["threads"], ours["threads"]), (common, common))
        self.assertEqual({name: child[name] for name in sd_gate_slots.CPU_VARIABLES}, common)  # what `sd-check` hands make
        self.assertEqual(sd_gate_receipts.offload_differences(theirs, ours), [])

    def test_a_machine_whose_share_is_below_the_common_cap_refuses(self) -> None:
        """sd:2879 finding 2: 16 slots on 16 cores run each check on one thread; a suite can pass there and fail on four."""
        self.gate_slots(sat=16, hub=2)
        with mock.patch.object(sd_gate_slots.os, "cpu_count", return_value=16):
            theirs, ours = self.view("sat"), self.view("hub")
        self.assertEqual((theirs["threads"]["RUST_TEST_THREADS"], ours["threads"]["RUST_TEST_THREADS"]),
                         ("1", sd_gate_receipts.OFFLOAD_THREADS))
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "threads", "name": "CARGO_BUILD_JOBS"})

    def test_another_thread_variable_refuses(self) -> None:
        """A row whose check saw another `RUST_TEST_THREADS` ran at other concurrency (sd:2879)."""
        ours = self.view("hub")
        theirs = {**ours, "variables": {**ours["variables"], "RUST_TEST_THREADS": "0" * 64}}
        self.assertEqual(sd_gate_receipts.offload_miss(theirs, ours), {"part": "variables", "name": "RUST_TEST_THREADS"})

    def test_a_view_written_before_threads_were_bound_refuses(self) -> None:
        ours = self.view("hub")
        old = {name: part for name, part in ours.items() if name != "threads"}
        self.assertEqual(sd_gate_receipts.offload_miss(old, ours), {"part": "threads", "name": None})

    def test_a_view_that_is_not_one_misses(self) -> None:
        ours = self.view("hub")
        self.assertEqual(sd_gate_receipts.offload_miss(None, ours), {"part": "view", "name": None})
        self.assertEqual(sd_gate_receipts.offload_miss({**ours, "tools": []}, ours), {"part": "tools", "name": None})


#: A fake `rustup`: `which <tool>` names the toolchain that the cwd's `rust-toolchain.toml` pins, under `HOME`.
FAKE_RUSTUP = """[ "$1" = which ] && [ -f rust-toolchain.toml ] || exit 1
while read -r key _ value; do [ "$key" = channel ] && channel=${value#\\"} && channel=${channel%\\"}; done < rust-toolchain.toml
[ -n "$channel" ] || exit 1
echo "$HOME/.rustup/toolchains/$channel/bin/$2"
"""
#: What Homebrew's rustup wrapper sets before it execs the proxy.
HOMEBREW_WRAPPER = "RUSTUP_OVERRIDE_UNIX_FALLBACK_SETTINGS=/opt/homebrew/etc/rustup/settings.toml "


def build(name: str, commit: str = "797e8a9bca276c1c", os_line: str = "Mac OS 27.0.1", suffix: str = "") -> str:
    """A toolchain binary's body: `-vV` prints its build lines and the machine's `os:` line, as `cargo -vV` does."""
    return (f'echo "{name} 1.98.1 ({commit[:9]} 2026-08-05){suffix}"\necho "release: 1.98.1"\n'
            f'echo "commit-hash: {commit}"\necho "host: aarch64-apple-darwin"\necho "os: {os_line}"\n')


def part(mode: str = "full", tools: list[str] | None = None) -> dict:
    """A tree part as `tree_binding` writes it, for a `make check` repository in `mode`'s scope, declaring `tools`."""
    return {"schema": 2, "reuse": "head", "head": "a" * 40, "fork": None, "tree": "t" * 40, "inputs": "i" * 12,
            "scope": {"mode": mode, "fork": None, "command": ["make", "docs-gate"] if mode == "docs-only" else [],
                      **({"tools": tools} if tools is not None else {})},
            "detection": {"source": "Makefile", "commands": {"check": ["make", "check"]}}}


class ToolVersion(ViewFixture):
    """sd:2881: the satellite's `cargo` is a Homebrew rustup wrapper, and the hub's the same or Homebrew's own `cargo`.

    A proxy's bytes name no toolchain; the tree's `rust-toolchain.toml` does, and `-vV` run as the gate runs it
    prints that toolchain's release and commit-hash. Both bind.
    """

    def setUp(self) -> None:
        super().setUp()
        self.tree = self.tmp / "tree"
        self.tree.mkdir()
        (self.tree / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.98.1"\n', encoding="utf-8")
        for login in ("sat", "hub"):
            self.script(self.home(login) / "bin" / "rustup", FAKE_RUSTUP)
            for name in ("cargo", "rustc"):
                self.toolchain(login, name, build(name))
            self.proxy(login, HOMEBREW_WRAPPER)

    @staticmethod
    def script(path: pathlib.Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def toolchain(self, login: str, name: str, body: str) -> None:
        self.script(self.home(login) / ".rustup" / "toolchains" / "1.98.1" / "bin" / name, body)

    def proxy(self, login: str, prefix: str) -> None:
        """`cargo` and `rustc` that run the toolchain `rustup which` names, through a wrapper that sets `prefix`."""
        for name in ("cargo", "rustc"):
            self.script(self.home(login) / "bin" / name, f'{prefix}exec "$(rustup which {name})" "$@"\n')

    def mismatch(self, theirs: dict, ours: dict, mode: str = "full", tools: list[str] | None = None) -> dict | None:
        row = {"binding": {**part(mode, tools), "environment_mode": "offload"}, "offload_view": theirs}
        return sd_gate_receipts.binding_mismatch(row, part(mode, tools), ours, "offload")

    def test_the_same_commit_hash_and_bytes_pass_on_two_machines(self) -> None:
        """Another macOS release changes `cargo -vV`'s `os:` line, which names the machine, not the compiler."""
        self.toolchain("hub", "cargo", build("cargo", os_line="Mac OS 26.4.0"))
        theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
        self.assertEqual(theirs["resolution"], {"cargo": "cargo 1.98.1 (797e8a9bc 2026-08-05)",
                                                "rustc": "rustc 1.98.1 (797e8a9bc 2026-08-05)"})
        self.assertIsNone(self.mismatch(theirs, ours))

    def test_another_commit_hash_behind_the_same_wrapper_refuses(self) -> None:
        self.toolchain("hub", "cargo", build("cargo", commit="48a229ceaefd4985"))
        theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
        self.assertIn("tools at cargo (satellite via cargo 1.98.1 (797e8a9bc 2026-08-05), "
                      "hub via cargo 1.98.1 (48a229cea 2026-08-05))", self.mismatch(theirs, ours)["reason"])

    def test_a_homebrew_cargo_ahead_of_the_proxy_refuses(self) -> None:
        """The hub's cron `PATH` found Homebrew's `cargo` 1.99.0, which ignores the pin: the hub would run another compiler."""
        self.script(self.home("hub") / "bin" / "cargo", build("cargo", "5f94df4789f005f9", suffix=" (Homebrew)"))
        theirs, ours = self.view("sat", tree=self.tree), self.view("hub", tree=self.tree)
        self.assertEqual(ours["resolution"]["cargo"], "cargo 1.98.1 (5f94df478 2026-08-05) (Homebrew)")
        self.assertIn("tools at cargo", self.mismatch(theirs, ours)["reason"])

    def test_another_wrapper_refuses_though_it_runs_the_same_toolchain(self) -> None:
        """A wrapper's bytes decide what it adds to a check's own arguments, which `-vV` does not show."""
        self.proxy("hub", "")
        self.assertIn("tools at cargo", self.mismatch(self.view("sat", tree=self.tree),
                                                      self.view("hub", tree=self.tree))["reason"])

    def test_a_tool_that_answers_no_version_binds_its_bytes_as_path(self) -> None:
        for login in ("sat", "hub"):
            (self.home(login) / "bin" / "rustup").unlink()
        theirs = self.view("sat", tree=self.tree)
        self.assertEqual(theirs["resolution"], {"cargo": "path", "rustc": "path"})
        self.assertIsNone(self.mismatch(theirs, self.view("hub", tree=self.tree)))

    def test_a_gates_worktree_runs_it_in_its_own_tree(self) -> None:
        """Both sides take the view through `Worktree.view`: the satellite when it writes the row, the hub when it compares."""
        environment = sd_gate_run.gate_environment(self.tmp / "repo", self.environ("sat"))
        gated = sd_gate_receipts.Worktree(self.tmp / "repo", self.tree, "a" * 40, None, environment, None, None, False, "i" * 12)
        self.assertEqual(gated.view(part())["resolution"]["cargo"], "cargo 1.98.1 (797e8a9bc 2026-08-05)")

    def test_a_row_from_before_the_resolution_refuses_and_says_it_recorded_none(self) -> None:
        """A 7801d8b8 view hashed the wrapper alone and has no `resolution`: it refuses on `tools.cargo` (its pack digest first)."""
        ours = self.view("hub", tree=self.tree)
        old = {name: value for name, value in self.view("sat").items() if name != "resolution"}
        self.assertIn("tools at cargo (satellite via unrecorded, hub via cargo 1.98.1", self.mismatch(old, ours)["reason"])

    def test_a_docs_only_scope_refuses_on_its_declared_tools_only(self) -> None:
        """`make docs-gate` may run `cargo doc`, so a compiler still refuses, unless `docs_tools` names what it reaches."""
        self.script(self.home("hub") / "bin" / "cargo", build("cargo", "5f94df4789f005f9", suffix=" (Homebrew)"))
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
