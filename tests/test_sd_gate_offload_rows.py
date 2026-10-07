"""The offload receipt, satellite side (sd:2704 step 3): a pass on a satellite writes a second row for the hub.

A satellite is a machine whose workflow database a hub serves over the wire.
Here the database is a local file and `served_by` is patched to name a hub for
it, as `SatellitePrepare` in `test_sd_ship_lane` does, so the rows land where
the test reads them. The pinned `sd_db` predates `repo.satellite_gate`, so the
opt-in is patched at its one reader, `sd_lib.repo_satellite_gate`, which has
its own tests below. No test starts `sd-check`: a stand-in run counts calls.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_gate_cache  # noqa: E402
import sd_gate_receipts  # noqa: E402
import sd_gate_run  # noqa: E402
import sd_gate_tools  # noqa: E402
import sd_lib  # noqa: E402

HUB = "hub.example.test:8769"
SLUG = "fixture/repo"
SATELLITE = {"hostname": "satellite.example.test", "login": "fixture@example.test", "address": "192.0.2.10"}
#: The one tool configuration under `HOME` an opted-in check still reads (sd:2879).
UV_CONFIG = sd_gate_receipts.OFFLOAD_HOME_FILES[0]


def no_real_tailscale(case: unittest.TestCase, scratch: pathlib.Path) -> None:
    """Name the satellite with fixture values, and fail `case` if anything still runs `tailscale` (sd:2775).

    The real `satellite_identity` asks `tailscale status --json`, and so wrote this machine's names into a row.
    A stand-in `tailscale` first on PATH leaves a mark; the check at cleanup fails on it.
    """
    programs, mark = scratch / "no-tailscale", scratch / "tailscale-ran"
    programs.mkdir()
    (programs / "tailscale").write_text(f'#!/bin/sh\necho "$*" >> "{mark}"\nexit 1\n', encoding="utf-8")
    (programs / "tailscale").chmod(0o755)
    case.addCleanup(lambda: case.assertFalse(mark.exists(), mark.exists() and f"the real tailscale ran: {mark.read_text()}"))
    for patcher in (mock.patch.object(sd_gate_receipts, "satellite_identity", lambda: dict(SATELLITE)),
                    mock.patch.dict(os.environ, {"PATH": f"{programs}{os.pathsep}{os.environ.get('PATH', '')}"})):
        patcher.start()
        case.addCleanup(patcher.stop)


def no_real_gate_cache(case: unittest.TestCase, scratch: pathlib.Path) -> None:
    """Point `SD_GATE_CACHE_DIR` into `scratch`, and fail `case` if a pinned tool folder lands outside it (sd:2921).

    `mock.patch.dict` keeps an inherited `SD_GATE_CACHE_DIR`, which outranks a scratch `XDG_CACHE_HOME`, so a gate
    would remove and write cargo subcommands in the real cache. Every pinning passes through `offload_pins`.
    The real `sd_gate_tools.PINS` name copies in that cache too, so this pins no tool (sd:2936).
    """
    pins, outside = sd_gate_receipts.offload_pins, []

    def isolated(environment):  # type: ignore[no-untyped-def]
        pinned = pins(environment)
        if not pathlib.Path(pinned["CARGO_HOME"]).resolve().is_relative_to(scratch.resolve()):
            outside.append(pinned["CARGO_HOME"])
        return pinned

    case.addCleanup(lambda: case.assertEqual(outside, [], "a test pinned the real gate cache"))
    for patcher in (mock.patch.object(sd_gate_receipts, "offload_pins", isolated), mock.patch.object(sd_gate_tools, "PINS", ()),
                    mock.patch.dict(os.environ, {sd_gate_cache.CACHE_VARIABLE: str(scratch / "gate-cache")})):
        patcher.start()
        case.addCleanup(patcher.stop)


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


class SatelliteFixture(unittest.TestCase):
    """A repository whose origin is `fixture/repo`, a workflow database a hub serves, and a counted stand-in run."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        git(self.root, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        (self.root / "Makefile").write_text("check:\n\ttrue\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")
        self.head = git(self.root, "rev-parse", "HEAD")
        from sd_db import initialise

        self.database = self.root.parent / "sd.db"
        initialise(self.database)
        no_real_tailscale(self, self.root.parent)
        no_real_gate_cache(self, self.root.parent)
        self.runs = 0
        self.hub: str | None = HUB
        self.opted = "accept"
        for patcher in (mock.patch("sd_db.database.served_by", self.served_by, create=True),
                        mock.patch.object(sd_lib, "repo_satellite_gate", lambda connection, root: self.opted)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def served_by(self, target, home=None):  # type: ignore[no-untyped-def]
        return self.hub if str(target) == str(self.database) else None

    def passing(self, argv, env, tree, timeout):  # type: ignore[no-untyped-def]
        self.runs += 1
        return 0, json.dumps({"status": "pass", "scope": {"mode": "full"}, "checks": []}), ""

    def gate(self) -> dict:
        return sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, run=self.passing)

    def row(self, key: str) -> dict:
        return sd_gate_receipts.read_offload(self.database, key)[1]

    def offload_row(self) -> dict:
        return self.row(sd_gate_receipts.offload_key(SLUG, self.head))

    def own_row(self) -> dict:
        return self.row(sd_gate_receipts.receipt_key(self.root, self.head))


class OffloadRows(SatelliteFixture):
    def test_a_satellite_pass_writes_its_own_receipt_and_the_offload_row(self) -> None:
        result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertIn("receipt_revision", result)
        self.assertEqual((result["offload"]["hub"], result["offload"]["written"]), (HUB, True))
        row, own = self.offload_row(), self.own_row()
        self.assertEqual(row["writer"], "sd-satellite-gate")
        self.assertEqual((row["hub"], row["head"], row["reading"]["status"]), (HUB, self.head, "success"))
        self.assertEqual(row["satellite"], SATELLITE)
        self.assertEqual(row["binding"], own["binding"])
        self.assertEqual(row["pack_bin"], sd_gate_receipts.pack_bin())
        self.assertEqual(row["local_block"], sd_gate_receipts.sd_lib.local_policy_digest(None))
        self.assertIn("make", row["offload_view"]["tools"])
        self.assertEqual(row["offload_view"]["python"], {
            "sha256": sd_gate_receipts._content_digest(pathlib.Path(sys.executable).resolve()), "version": sys.version})
        self.assertNotIn("receipt_revision", row["reading"])

    def test_the_offload_row_holds_no_variable_off_the_allowlist(self) -> None:
        """sd:2782 L6: a credential the gate environment keeps reaches the hub's database neither as a value nor as a digest."""
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic-secret-0001", "LANG": "C"}):
            self.gate()
        stored = json.dumps(self.offload_row())
        self.assertIn('"LANG"', stored)
        for text in ("GITHUB_TOKEN", "synthetic-secret-0001", hashlib.sha256(b"synthetic-secret-0001").hexdigest()):
            self.assertNotIn(text, stored)

    def test_a_hub_run_writes_no_offload_row(self) -> None:
        self.hub = None
        result = self.gate()
        self.assertIn("receipt_revision", result)
        self.assertFalse({"offload", "offload_error", "offload_skipped"} & set(result))
        self.assertEqual(self.offload_row(), {})

    def test_a_repository_that_did_not_opt_in_writes_no_offload_row(self) -> None:
        self.opted = "off"
        result = self.gate()
        self.assertEqual(result["offload_skipped"], "repo.satellite_gate is not accept for this repository")
        self.assertEqual(self.offload_row(), {})

    def unwritten(self) -> dict:
        """A pass whose offload row never reached the hub (sd:2782: an opted-out pass runs otherwise, so is not reused)."""
        with mock.patch.object(sd_gate_receipts, "record_offload", lambda *args, **kwargs: {}):
            return self.gate()

    def test_a_reuse_writes_the_missing_row_with_the_original_time(self) -> None:
        self.unwritten()
        reused = self.gate()
        self.assertEqual(self.runs, 1)
        self.assertIn("reused", reused)
        self.assertEqual(reused["offload"]["written"], True)
        row = self.offload_row()
        self.assertEqual(row["recorded_at"], self.own_row()["recorded_at"])
        self.assertEqual(row["reading"]["summary"], "sd-check pass ()")
        # The row now stands, so a later reuse leaves it alone.
        self.assertEqual(self.gate()["offload"]["written"], False)
        self.assertEqual(sd_gate_receipts.read_offload(self.database, reused["offload"]["key"])[0],
                         reused["offload"]["revision"])

    def test_a_reuse_replaces_a_row_another_pass_left(self) -> None:
        """A row the hub would refuse (another pass's time, inputs or pack, another writer, a failure, another view) does not stand: the reuse writes its own."""
        from contextlib import closing

        from sd_db import connect, ship

        self.gate()
        self.gate()  # the reuse's own row: the reused pass's binding and pack, at its receipt's time
        key, current = sd_gate_receipts.offload_key(SLUG, self.head), self.offload_row()
        for fields in ({"recorded_at": current["recorded_at"] - 60}, {"binding": {**current["binding"], "inputs": "0" * 12}},
                       {"pack_bin": "0" * 64}, {"writer": "sd-lane"}, {"reading": {**current["reading"], "status": "failure"}},
                       {"offload_view": {**current["offload_view"], "tools": {}}}):
            with self.subTest(fields=sorted(fields)):
                with closing(connect(self.database)) as connection:
                    ship.save(connection, key, ship.read(connection, key)[0], {**current, **fields})
                self.assertEqual(self.gate()["offload"]["written"], True)
                self.assertEqual({name: self.offload_row()[name] for name in fields}, {name: current[name] for name in fields})
        self.assertEqual((self.runs, self.gate()["offload"]["written"]), (1, False))

    def home(self) -> pathlib.Path:
        """A `HOME` of the test's own: `gate_binding` does not hash its files, the offload view does."""
        home = self.root.parent / "home"
        home.mkdir(exist_ok=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        return home

    def test_a_reuse_writes_the_view_its_pass_kept_not_one_taken_now(self) -> None:
        """A home file that changed after the pass does not bind the old pass on the hub."""
        home = self.home()
        self.unwritten()
        (home / UV_CONFIG).parent.mkdir(parents=True)
        (home / UV_CONFIG).write_text('index-url = "https://pypi.example.test/simple"\n', encoding="utf-8")
        reused = self.gate()
        self.assertEqual((self.runs, reused["offload"]["written"]), (1, True))
        self.assertEqual(self.offload_row()["offload_view"]["home_files"][UV_CONFIG], "absent")

    def test_a_local_pass_is_not_exported_the_offloaded_run_runs_again(self) -> None:
        """sd:2782: a pass under the whole environment kept no view; the offloaded run's environment binds otherwise."""
        self.hub = None
        self.gate()
        self.hub = HUB
        result = self.gate()
        self.assertEqual((self.runs, result["offload"]["written"]), (2, True))

    def test_a_view_that_moves_during_the_run_writes_no_row(self) -> None:
        home = self.home()

        def moving(argv, env, tree, timeout):  # type: ignore[no-untyped-def]
            (home / UV_CONFIG).parent.mkdir(parents=True)
            (home / UV_CONFIG).write_text('index-url = "https://pypi.example.test/simple"\n', encoding="utf-8")
            return self.passing(argv, env, tree, timeout)

        result = sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, run=moving)
        self.assertEqual(result["offload_error"], f"the offload view moved during the run: home_files {UV_CONFIG}")
        self.assertIn("receipt_revision", result)
        self.assertEqual(self.offload_row(), {})
        # The receipt keeps no view it did not hold through the run, so a reuse cannot export it.
        reused = self.gate()
        self.assertEqual(self.runs, 1)
        self.assertIn("kept no offload view", reused["offload_error"])
        self.assertEqual(self.offload_row(), {})

    def test_an_unreachable_hub_still_runs_the_check_and_reports_offload_error(self) -> None:
        with mock.patch.object(sd_gate_receipts, "_connect", side_effect=ConnectionError("HubUnreachable: no answer")):
            result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertIn("HubUnreachable", result["offload_error"])
        self.assertIn("receipt_error", result)

    def test_a_malformed_hub_configuration_still_passes_and_reports_offload_error(self) -> None:
        """sd:2776: a fault in `served_by` reaches neither the run nor the receipt; the result names it."""
        fault = ValueError("malformed hub configuration")
        with mock.patch("sd_db.database.served_by", side_effect=fault, create=True):
            result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertEqual(result["offload_error"], "ValueError: malformed hub configuration")
        self.assertIn("receipt_revision", result)
        self.assertEqual(self.offload_row(), {})

    def test_a_differing_published_pack_digest_warns_before_the_run(self) -> None:
        from contextlib import closing

        from sd_db import connect, ship

        with closing(connect(self.database)) as connection:
            ship.save(connection, sd_gate_receipts.PACK_PREFIX + SLUG, 0,
                      {"writer": "sd-lane", "pack_bin": "0" * 64, "pack_rev": "1" * 40, "published_at": "now"})
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.gate()
        self.assertEqual(self.runs, 1)
        self.assertIn("satellite_pack_mismatch", result["pack_warning"])
        self.assertIn("is not the hub's 000000000000", stderr.getvalue())

    def test_an_equal_published_pack_digest_warns_of_nothing(self) -> None:
        from contextlib import closing

        from sd_db import connect, ship

        with closing(connect(self.database)) as connection:
            ship.save(connection, sd_gate_receipts.PACK_PREFIX + SLUG, 0,
                      {"writer": "sd-lane", "pack_bin": sd_gate_receipts.pack_bin(), "published_at": "now"})
        self.assertNotIn("pack_warning", self.gate())

    def test_the_warning_compares_the_published_digest_under_the_heads_own_scope(self) -> None:
        """sd:2823: the hub publishes a digest per scope; `pack_bin`, under its main's scope, is not this head's."""
        from contextlib import closing

        from sd_db import connect, ship

        key, other = sd_gate_receipts.PACK_PREFIX + SLUG, "0" * 64
        for closure in (False, True):
            ours = sd_gate_receipts.pack_bin(False, closure)
            scope, wrong = ("closure", "every") if closure else ("every", "closure")
            for bins, warns in (({scope: ours, wrong: other}, False), ({scope: other, wrong: ours}, True)):
                with self.subTest(closure=closure, warns=warns), \
                        mock.patch.object(sd_gate_receipts, "pack_scope", lambda root, head, closure=closure: closure), \
                        contextlib.redirect_stderr(io.StringIO()):
                    with closing(connect(self.database)) as connection:
                        revision, _ = ship.read(connection, key)
                        # `pack_bin` holds the other scope's digest, as a hub whose main differs in scope publishes.
                        ship.save(connection, key, revision, {"writer": "sd-lane", "pack_bin": bins[wrong],
                                                              "pack_bins": bins, "published_at": "now"})
                    warning = sd_gate_receipts.pack_warning(self.database, self.root, self.head, False)
                    self.assertEqual(warning is not None, warns, warning)

    def test_a_publication_that_is_not_an_object_warns_of_nothing_and_the_check_runs(self) -> None:
        from sd_db import ship

        real = ship.read

        def read(connection, key):  # type: ignore[no-untyped-def]
            # `ship.save` writes objects only; a body written by other means can be anything.
            return (1, ["not", "an", "object"]) if key == sd_gate_receipts.PACK_PREFIX + SLUG else real(connection, key)

        with mock.patch.object(ship, "read", read):
            result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertNotIn("pack_warning", result)


class OffloadedEnvironment(SatelliteFixture):
    """sd:2782: in an opted-in repository every gate runs its check under only what the hub compares.

    The fixture's `make check` records its environment, and fails as an integration test would when
    `RUN_INTEGRATION` is set. Each run has a scratch `HOME` and no gate slot, so it touches no real config.
    """

    def setUp(self) -> None:
        super().setUp()
        self.record = self.root.parent / "check-env.txt"
        (self.root / "Makefile").write_text(
            f"check:\n\t@env > {self.record}\n\t@if [ -n \"$$RUN_INTEGRATION\" ]; then echo integration-ran; exit 1; fi\n",
            encoding="utf-8")
        git(self.root, "commit", "-q", "-am", "record the environment")
        self.head = git(self.root, "rev-parse", "HEAD")
        home = self.root.parent / "home"
        home.mkdir()
        self.extra = {"SKIP_TESTS": "1", "GOFLAGS": "-run=Smoke", "RUN_INTEGRATION": "1", "RUSTFLAGS": "-Dwarnings",
                      "GITHUB_TOKEN": "synthetic-secret-0003", "CARGO_REGISTRY_TOKEN": "synthetic-secret-0004"}
        self.scratch = {"HOME": str(home), "SD_GATE_SLOTS": "0", "XDG_CONFIG_HOME": str(home / ".config"),
                        "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".state"),
                        "SD_GATE_CACHE_DIR": str(home / ".cache" / "sd" / "gate")}

    def seen(self) -> tuple[str, dict[str, str]]:
        """The gate's status, and the environment its check saw."""
        with mock.patch.dict(os.environ, {**self.extra, **self.scratch}):
            result = sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, reuse=False)
        return result["status"], dict(line.split("=", 1) for line in self.record.read_text(encoding="utf-8").splitlines()
                                      if "=" in line)

    def test_an_opted_in_check_sees_no_variable_off_the_allowlist(self) -> None:
        status, seen = self.seen()
        self.assertEqual(status, "success")
        self.assertFalse({"SKIP_TESTS", "GOFLAGS", "RUN_INTEGRATION"} & set(seen))
        self.assertEqual((seen["RUSTFLAGS"], seen["SD_LOCAL_GATE"], seen["HOME"]), ("-Dwarnings", "1", self.scratch["HOME"]))
        self.assertTrue({"HOME", "PATH"} <= set(seen))
        self.assertEqual(self.offload_row()["writer"], "sd-satellite-gate")

    def test_an_opted_in_check_sees_one_tool_configuration_and_thread_cap(self) -> None:
        """sd:2879: the caller's own git and cargo configuration and thread counts never reach the check."""
        self.extra.update(GIT_CONFIG_GLOBAL="/elsewhere/gitconfig", CARGO_HOME="/elsewhere/cargo", RUST_TEST_THREADS="1")
        status, seen = self.seen()
        self.assertEqual(status, "success")
        pins = sd_gate_receipts.offload_pins({**os.environ, **self.scratch})
        del pins["PATH"]  # `gate_environment` cuts the caller's PATH first; `PinnedTools` checks the pinned entries
        self.assertEqual({name: seen.get(name) for name in pins}, pins)
        self.assertEqual((seen["GIT_CONFIG_GLOBAL"], seen["RUST_TEST_THREADS"]), (os.devnull, sd_gate_receipts.OFFLOAD_THREADS))
        self.assertTrue(pathlib.Path(seen["CARGO_HOME"]).is_relative_to(self.scratch["XDG_CACHE_HOME"]), seen["CARGO_HOME"])

    def test_an_opted_in_check_sees_no_credential(self) -> None:
        status, seen = self.seen()
        self.assertFalse({"GITHUB_TOKEN", "CARGO_REGISTRY_TOKEN"} & set(seen))
        self.assertNotIn("synthetic-secret", self.record.read_text(encoding="utf-8"))

    def test_the_hub_and_the_satellite_run_the_same_check(self) -> None:
        """The ship review's repro: `RUN_INTEGRATION=1` ran the integration test on the hub only."""
        runs = {}
        for hub in (None, HUB):
            self.hub = hub
            status, seen = self.seen()
            runs[hub] = (status, "RUN_INTEGRATION" in seen)
        self.assertEqual(runs, {None: ("success", False), HUB: ("success", False)})

    def test_a_repository_that_did_not_opt_in_passes_the_whole_environment(self) -> None:
        self.opted = "off"
        for hub in (None, HUB):
            with self.subTest(hub=hub):
                self.hub = hub
                status, seen = self.seen()
                self.assertEqual({name: seen.get(name) for name in self.extra}, self.extra)
                self.assertEqual(status, "failure")


class CargoSubcommands(SatelliteFixture):
    """sd:2921: what cargo runs for `cargo nextest` in an opted-in check is the caller's, and the offload row binds it.

    The stand-in run finds `cargo-nextest` as cargo does: `$CARGO_HOME/bin`, then the check's `PATH`. Each
    test names one way the run and the view could part, as the table in the offload design lists them.
    """

    def setUp(self) -> None:
        super().setUp()
        home = self.root.parent / "home"
        home.mkdir()
        self.scratch = {"HOME": str(home), "SD_GATE_SLOTS": "0", "XDG_CONFIG_HOME": str(home / ".config"),
                        "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".state"),
                        "SD_GATE_CACHE_DIR": str(home / ".cache" / "sd" / "gate")}
        self.cargo = self.root.parent / "cargo-a"
        self.tool(self.cargo / "bin" / "cargo-nextest", "cargo-nextest a")
        self.tool(self.cargo / "bin" / "cargo-llvm-cov", "cargo-llvm-cov")
        self.during: Any = None
        self.seen: dict[str, Any] = {}

    @staticmethod
    def tool(path: pathlib.Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!/bin/sh\n# {text}\n", encoding="utf-8")
        path.chmod(0o755)

    @staticmethod
    def found(env: dict[str, str], name: str) -> str | None:
        return shutil.which(name, path=os.pathsep.join([os.path.join(env["CARGO_HOME"], "bin"), env["PATH"]]))

    def stand_in(self, argv, env, tree, timeout):  # type: ignore[no-untyped-def]
        if self.during is not None:
            during, self.during = self.during, None
            during()
        folder = pathlib.Path(tree).parent / sd_gate_receipts.CARGO_SUBCOMMANDS
        nextest = self.found(env, "cargo-nextest")
        self.seen = {"nextest": nextest and sd_gate_receipts._content_digest(nextest),
                     "llvm-cov": self.found(env, "cargo-llvm-cov"), "folder": folder,
                     "listing": sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []}
        return self.passing(argv, env, tree, timeout)

    def gate(self, cargo_home: str | None = None, reuse: bool = False) -> dict:  # type: ignore[override]
        with mock.patch.dict(os.environ, {**self.scratch, "CARGO_HOME": cargo_home or str(self.cargo)}):
            return sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, run=self.stand_in, reuse=reuse)

    def caller(self, cargo: pathlib.Path | None = None) -> str:
        return sd_gate_receipts._content_digest((cargo or self.cargo) / "bin" / "cargo-nextest")

    def bound(self) -> str | None:
        return self.offload_row()["offload_view"]["tools"]["cargo-nextest"]

    def test_the_check_runs_the_callers_subcommand_and_the_row_binds_it(self) -> None:
        result = self.gate()
        self.assertEqual(result["status"], "success")
        self.assertNotIn("offload_error", result)
        self.assertEqual((self.seen["nextest"], self.bound()), (self.caller(), self.caller()))

    def test_a_gate_that_did_not_opt_in_copies_and_refuses_nothing(self) -> None:
        """Its `CARGO_HOME` is the caller's own, whose `bin` holds `cargo-nextest`: no copy, and no refusal."""
        self.opted = "off"
        self.assertEqual(self.gate()["status"], "success")
        self.assertTrue((self.cargo / "bin" / "cargo-nextest").is_file())
        self.assertEqual(self.seen["listing"], [])

    def test_a_changed_subcommand_moves_the_local_binding(self) -> None:
        """sd:2921 r4 review: local reuse never reads the view, so the binding itself must hold the copy's bytes."""
        self.gate(reuse=True)
        self.tool(self.cargo / "bin" / "cargo-nextest", "cargo-nextest changed")
        result = self.gate(reuse=True)
        self.assertEqual((self.runs, result["reuse_miss"]), (2, {"reason": "binding", "fields": ["offload_tools"]}))

    def test_an_unchanged_subcommand_reuses_the_pass(self) -> None:
        """The binding names no temporary folder, so a second gate of the same tools reuses the first one's pass."""
        self.gate(reuse=True)
        self.assertIn("reused", self.gate(reuse=True))
        self.assertEqual(self.runs, 1)

    def test_a_concurrent_gate_of_another_caller_changes_nothing_this_one_runs(self) -> None:
        other = self.root.parent / "cargo-b"
        self.tool(other / "bin" / "cargo-nextest", "cargo-nextest b")
        self.during = lambda: self.gate(str(other))
        self.gate()
        self.assertEqual((self.seen["nextest"], self.bound()), (self.caller(), self.caller()))

    def refused(self, pinned: pathlib.Path, cargo_home: str | None = None) -> None:
        """The gate refuses before it runs, names the file, and leaves it as it was."""
        before = os.readlink(pinned / "cargo-nextest") if os.path.islink(pinned / "cargo-nextest") else (pinned / "cargo-nextest").read_bytes()
        result = self.gate(cargo_home)
        self.assertEqual((result["status"], self.runs, self.own_row(), self.offload_row()), ("failure", 0, {}, {}))
        self.assertIn(f"pinned CARGO_HOME holds {pinned / 'cargo-nextest'}", result["stderr"])
        self.assertEqual(os.readlink(pinned / "cargo-nextest") if os.path.islink(pinned / "cargo-nextest")
                         else (pinned / "cargo-nextest").read_bytes(), before)

    def test_a_file_in_the_pinned_cargo_home_refuses_the_gate(self) -> None:
        """sd:2921 r6 review: cargo runs it before the copy, so no gate runs or binds; a caller whose `CARGO_HOME`
        is the pinned one keeps its install."""
        pinned = pathlib.Path(sd_gate_receipts.offload_pins(self.scratch)["CARGO_HOME"], "bin")
        self.tool(pinned / "cargo-nextest", "cargo-nextest installed")
        for cargo_home in (None, str(pinned.parent)):
            with self.subTest(cargo_home=cargo_home):
                self.refused(pinned, cargo_home)

    def test_a_link_in_the_pinned_cargo_home_refuses_the_gate(self) -> None:
        """A link to another install, such as one an unmerged round of sd:2921 left, refuses and stays."""
        pinned = pathlib.Path(sd_gate_receipts.offload_pins(self.scratch)["CARGO_HOME"], "bin")
        self.tool(self.root.parent / "elsewhere" / "cargo-nextest", "cargo-nextest elsewhere")
        pinned.mkdir(parents=True)
        (pinned / "cargo-nextest").symlink_to(self.root.parent / "elsewhere" / "cargo-nextest")
        self.refused(pinned)

    def test_a_subcommand_written_to_the_pinned_cargo_home_during_the_run_keeps_no_receipt(self) -> None:
        """A check's `cargo install` writes the shared pinned `CARGO_HOME/bin`, which cargo reads first; the gate
        looks there again after the run, so neither a local receipt nor an offload row is kept."""
        pinned = pathlib.Path(sd_gate_receipts.offload_pins(self.scratch)["CARGO_HOME"], "bin")
        self.during = lambda: self.tool(pinned / "cargo-nextest", "cargo-nextest installed")
        result = self.gate()
        self.assertIn(f"moved during the run: the gate's pinned CARGO_HOME holds {pinned / 'cargo-nextest'}",
                      result["receipt_skipped"])
        self.assertEqual((self.own_row(), self.offload_row()), ({}, {}))

    def test_a_caller_binary_changed_during_the_run_changes_nothing_it_runs(self) -> None:
        before = self.caller()
        self.during = lambda: self.tool(self.cargo / "bin" / "cargo-nextest", "cargo-nextest changed")
        result = self.gate()
        self.assertNotIn("offload_error", result)
        self.assertEqual((self.seen["nextest"], self.bound()), (before, before))

    def test_a_caller_without_the_subcommand_does_not_run_another_callers(self) -> None:
        self.gate()
        other = self.root.parent / "cargo-b"
        (other / "bin").mkdir(parents=True)
        self.gate(str(other))
        self.assertNotIn("cargo-nextest", self.seen["listing"])
        self.assertNotEqual(self.seen["nextest"], self.caller())
        self.assertEqual(self.seen["nextest"], self.bound())

    def test_a_cargo_bin_the_gate_path_drops_gives_nothing(self) -> None:
        """A relative `CARGO_HOME`, or one in the checkout, names a folder `gate_environment` drops from `PATH`."""
        inside = self.root / "tools" / "cargo"
        self.tool(inside / "bin" / "cargo-nextest", "cargo-nextest in the checkout")
        for cargo_home in ("tools/cargo", str(inside)):
            with self.subTest(cargo_home=cargo_home), contextlib.chdir(self.root):
                self.assertEqual(self.gate(cargo_home)["status"], "success")
                self.assertEqual(self.seen["listing"], [])
                self.assertEqual(self.seen["nextest"], self.bound())

    def test_an_unbound_subcommand_stays_unavailable_and_the_folder_goes_with_the_run(self) -> None:
        """sd:2921 lane review: `cargo llvm-cov` would run bytes no view binds."""
        self.gate()
        llvm = self.seen["llvm-cov"]
        self.assertFalse(llvm and pathlib.Path(llvm).resolve().is_relative_to(self.cargo.resolve()), llvm)
        self.assertEqual(self.seen["listing"], ["cargo-nextest"])
        self.assertFalse(self.seen["folder"].exists())


class EnvironmentMode(SatelliteFixture):
    """sd:2782: a pass under the whole environment never stands for an opted-in gate, nor the reverse.

    The environment holds only allowlisted names and the pins (sd:2879), so the two modes give one
    `environment_sha256`: only `environment_mode` tells the passes apart.
    """

    def gate(self, reuse: bool = True) -> dict:
        allowlisted = {name: os.environ[name] for name in ("HOME", "USER", "PATH", "SD_GATE_CACHE_DIR") if name in os.environ}
        allowlisted.update(sd_gate_receipts.offload_pins(allowlisted))
        return sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, run=self.passing,
                                             environ=allowlisted, reuse=reuse)

    def test_a_pass_under_one_mode_is_not_reused_under_the_other(self) -> None:
        self.hub = None
        for first, second in (("off", "accept"), ("accept", "off")):
            with self.subTest(first=first, second=second):
                self.runs = 0
                self.opted = first
                self.gate(reuse=False)
                self.opted = second
                result = self.gate()
                self.assertEqual(self.runs, 2)
                self.assertEqual(result["reuse_miss"], {"reason": "binding", "fields": ["environment_mode"]})

    def test_a_pass_under_one_mode_is_reused_under_the_same(self) -> None:
        self.hub = None
        for opted in ("off", "accept"):
            with self.subTest(opted=opted):
                self.runs = 0
                self.opted = opted
                self.gate()
                self.assertIn("reused", self.gate())
                self.assertEqual(self.runs, 1)


class PackDigest(unittest.TestCase):
    def test_pack_bin_hashes_the_files_gate_inputs_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            pack = pathlib.Path(folder)
            (pack / "sd-x").write_text("one\n", encoding="utf-8")
            (pack / "notes.txt").write_text("not a pack file\n", encoding="utf-8")
            with mock.patch.object(sd_gate_run, "BIN", pack):
                first = sd_gate_receipts.pack_bin()
                (pack / "notes.txt").write_text("still not\n", encoding="utf-8")
                self.assertEqual(sd_gate_receipts.pack_bin(), first)
                (pack / "sd-x").write_text("two\n", encoding="utf-8")
                self.assertNotEqual(sd_gate_receipts.pack_bin(), first)
        self.assertEqual(sd_gate_receipts.pack_bin(own=True), "tree")

    def test_the_offload_key_is_the_same_for_any_checkout_of_one_slug(self) -> None:
        keys = []
        with tempfile.TemporaryDirectory() as folder:
            for name, origin in (("https", f"https://github.com/{SLUG}.git"), ("ssh", "git@github.com:Fixture/Repo.git")):
                checkout = pathlib.Path(folder) / name
                checkout.mkdir()
                git(checkout, "init", "-q")
                git(checkout, "remote", "add", "origin", origin)
                keys.append(sd_gate_receipts.offload_key(sd_gate_receipts.repository_slug(checkout) or "", "a" * 40))
        self.assertEqual(keys, [sd_gate_receipts.offload_key(SLUG, "a" * 40)] * 2)
        self.assertNotEqual(sd_gate_receipts.offload_key(SLUG, "a" * 40), sd_gate_receipts.offload_key(SLUG, "b" * 40))
        self.assertNotEqual(sd_gate_receipts.offload_key(SLUG, "a" * 40, "c" * 40),
                            sd_gate_receipts.offload_key(SLUG, "a" * 40))


class LoginVariables(unittest.TestCase):
    """Decision 2026-10-05 10:02 MDT: `LOGNAME` and `TMPDIR` name the login; off the allowlist (sd:2782), a view leaves them out."""

    def view(self, **extra: str) -> dict:
        environment = {"HOME": "/Users/sat", "USER": "sat", "LOGNAME": "sat", "TMPDIR": "/var/folders/aa/T/",
                       "LANG": "C", "PATH": "/usr/bin", **extra}
        view = sd_gate_receipts.offload_view(environment)
        assert view is not None
        return view

    def test_another_logname_and_tmpdir_compare_equal(self) -> None:
        theirs = self.view()
        ours = self.view(HOME="/Users/hub", USER="hub", LOGNAME="hub", TMPDIR="/var/folders/bb/T/")
        self.assertIsNone(sd_gate_receipts.offload_miss(theirs, ours))
        self.assertFalse({"LOGNAME", "TMPDIR"} & set(theirs["variables"]))

    def test_any_other_differing_variable_still_misses(self) -> None:
        ours = self.view(LOGNAME="hub", TMPDIR="/var/folders/bb/T/", LANG="en_US.UTF-8")
        self.assertEqual(sd_gate_receipts.offload_miss(self.view(), ours), {"part": "variables", "name": "LANG"})


class BindingSplit(SatelliteFixture):
    """Step 4's split: `gate_binding` is the union of its tree part and its machine part, unchanged."""

    def test_gate_binding_is_its_tree_part_and_its_machine_part(self) -> None:
        tree = self.root
        env = sd_gate_run.gate_environment(self.root, dict(os.environ))
        whole = sd_gate_receipts.gate_binding(tree, self.head, "i" * 12, None, env)
        part = sd_gate_receipts.tree_binding(tree, self.head, "i" * 12, None)
        assert whole is not None and part is not None
        self.assertEqual(set(part), set(sd_gate_receipts.TREE_FIELDS))
        self.assertEqual(set(whole) - set(part), {"tools", "python", "environment_sha256", "threads", "machine",
                                                  "offload_tools", "environment_mode"})
        self.assertEqual({name: whole[name] for name in part}, part)

    def test_the_tree_part_needs_no_tool_on_path(self) -> None:
        env = {"PATH": str(self.root.parent / "empty")}
        self.assertIsNone(sd_gate_receipts.gate_binding(self.root, self.head, "i" * 12, None, env))
        self.assertIsNotNone(sd_gate_receipts.tree_binding(self.root, self.head, "i" * 12, None))


class SatelliteGateReader(unittest.TestCase):
    """`sd_lib.repo_satellite_gate` answers `off` on every doubt, as `repo_ci` answers `github`."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name).resolve()
        from sd_db import connect, initialise, upsert_repo

        database = home / "sd.db"
        initialise(database)
        self.connection = connect(database)
        self.addCleanup(self.connection.close)
        self.root = home / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        upsert_repo(self.connection, str(self.root), remote=None)

    def read(self, reader) -> str:  # type: ignore[no-untyped-def]
        import sd_db.repos

        with mock.patch.object(sd_db.repos, "repo_satellite_gate", reader, create=True):
            return sd_lib.repo_satellite_gate(self.connection, self.root)

    def test_the_librarys_accept_is_returned(self) -> None:
        self.assertEqual(self.read(lambda connection, path: "accept"), "accept")

    def test_an_unknown_value_or_a_failing_read_answers_off(self) -> None:
        def broken(connection, path):  # type: ignore[no-untyped-def]
            raise RuntimeError("no such column: satellite_gate")

        for reader in (lambda connection, path: "sometimes", broken):
            with self.subTest(reader=reader):
                self.assertEqual(self.read(reader), "off")

    def test_without_the_reader_the_column_is_read_when_present_and_off_when_absent(self) -> None:
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(repo)")}
        if "satellite_gate" in columns:  # a library newer than the pin
            self.connection.execute("ALTER TABLE repo DROP COLUMN satellite_gate")
        self.assertEqual(self.read(None), "off")
        self.connection.execute("ALTER TABLE repo ADD COLUMN satellite_gate TEXT NOT NULL DEFAULT 'off'")
        self.connection.execute("UPDATE repo SET satellite_gate = 'accept'")
        self.assertEqual(self.read(None), "accept")


if __name__ == "__main__":
    unittest.main()
