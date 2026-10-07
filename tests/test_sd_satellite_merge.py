"""The hub's acceptance of a satellite's gate, and the satellite's status post (sd:2704 steps 4 and 5).

The trust rule of design.md has eight clauses. Clauses 3 to 7 are the offload
mode of `check_in_worktree`, tested in `GateCompare` below with the stand-in
run of `test_sd_gate_offload_rows`. Clauses 1, 2 and 8 are `sd-ship merge`'s,
tested in `SatelliteMerge` on the `test_sd_ship` rig. Every refusal asserts its
code and that no `sd-check` ran. The pinned `sd_db` predates
`repo.satellite_gate`, so the opt-in is patched at its one reader.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import unittest
from unittest.mock import patch

from tests import test_sd_gate_offload_rows as rows
from tests import test_sd_ship as fixture

ship = fixture.ship
sd_gate_receipts = rows.sd_gate_receipts
sd_gate_run = rows.sd_gate_run
sd_lib = rows.sd_lib


def rewrite(database: pathlib.Path, key: str, **fields: object) -> None:
    """Change `fields` of the row at `key`, as a broken or hostile satellite would."""
    from contextlib import closing

    from sd_db import ship as store

    with closing(sd_gate_receipts._connect(database, write=True)) as connection:
        revision, row = store.read(connection, key)
        store.save(connection, key, revision, {**row, **fields})


class GateCompare(rows.SatelliteFixture):
    """Clauses 3 to 7: `check_in_worktree(offload="require")` on the hub compares and never runs."""

    def setUp(self) -> None:
        super().setUp()
        self.gate()  # the satellite's pass, which writes the offload row
        self.hub = None
        self.key = sd_gate_receipts.offload_key(rows.SLUG, self.head)

    def compare(self, offload: str = "require") -> dict:
        return sd_gate_run.check_in_worktree(self.root, self.head, database=self.database, run=self.passing,
                                             record=False, offload=offload)

    def refused(self, code: str) -> dict:
        result = self.compare()
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["offload_refused"]["code"], code)
        self.assertEqual(self.runs, 1, "the hub ran the check")
        return result

    def test_a_valid_receipt_is_accepted_and_nothing_runs(self) -> None:
        result = self.compare()
        self.assertEqual((result["status"], result["head"], self.runs), ("success", self.head, 1))
        self.assertEqual(result["satellite"]["hostname"], rows.SATELLITE["hostname"])
        self.assertIn("(satellite ", result["summary"])
        self.assertEqual(result["satellite"]["unresolved_tools"], [])

    def test_clause_3_no_row_refuses_as_missing(self) -> None:
        rows.git(self.root, "commit", "-q", "--allow-empty", "-m", "moved")
        self.head = rows.git(self.root, "rev-parse", "HEAD")
        self.refused("satellite_receipt_missing")

    def test_clause_4_another_writer_or_a_failure_refuses_as_invalid(self) -> None:
        rewrite(self.database, self.key, writer="sd-check")
        self.refused("satellite_receipt_invalid")
        rewrite(self.database, self.key, writer=sd_gate_receipts.OFFLOAD_WRITER, reading={"status": "failure"})
        self.refused("satellite_receipt_invalid")

    def test_clause_4_a_satellite_with_no_tailnet_identity_refuses_as_unidentified(self) -> None:
        """sd:2782 L4: `satellite_identity` keeps `hostname` when the tailnet lookup fails; that row names no node."""
        rewrite(self.database, self.key, satellite={"hostname": rows.SATELLITE["hostname"],
                                                    "error": "TailnetError: Tailscale is not running"})
        self.assertIn("Tailscale is not running", self.refused("satellite_unidentified")["offload_refused"]["reason"])

    def test_clause_5_records_what_two_machines_differ_in_and_accepts(self) -> None:
        """sd:2862: thread caps, `PATH` order, `HOME` files, `git` and the pack's own settings differ on every pair of
        machines; the hub accepts and names each. A row from before the caps were bound names the part."""
        view = self.row(self.key)["offload_view"]
        rewrite(self.database, self.key, offload_view={
            **view, "threads": {"RUST_TEST_THREADS": "1"}, "path": ["/elsewhere", *view["path"]],
            "home_files": {**view["home_files"], ".npmrc": "0" * 64}, "tools": {**view["tools"], "git": "0" * 64},
            "variables": {**view["variables"], "SD_GATE_POOL_SIZE": "0" * 64}})
        result = self.compare()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        found = [(miss["part"], miss["name"]) for miss in result["satellite"]["view_differences"]]
        self.assertEqual([miss for miss in found if miss[0] != "threads"], [
            ("path", "/elsewhere"), ("tools", "git"), ("home_files", ".npmrc"), ("variables", "SD_GATE_POOL_SIZE")])
        self.assertIn(("threads", "RUST_TEST_THREADS"), found)
        rewrite(self.database, self.key, offload_view={name: part for name, part in view.items() if name != "threads"})
        self.assertIn({"part": "threads", "name": None}, self.compare()["satellite"]["view_differences"])

    def test_clause_5_a_toolchain_tool_or_the_checks_own_tool_refuses_as_binding(self) -> None:
        """sd:2862: what decides the result still refuses: `sh` from the toolchain, and `make`, the check's own."""
        view = self.row(self.key)["offload_view"]
        for name in ("sh", "make"):
            with self.subTest(name=name):
                rewrite(self.database, self.key, offload_view={**view, "tools": {**view["tools"], name: "0" * 64}})
                self.assertIn(f"part tools at {name}", self.refused("satellite_binding")["offload_refused"]["reason"])

    def test_clause_5_an_opt_in_read_fault_then_a_good_receipt_read_does_not_accept(self) -> None:
        """sd:2782: the fault ran the hub's gate under the whole environment; that gate never stands on a satellite's pass."""
        connect = sd_gate_receipts._connect
        for offload in ("require", "fallback"):
            with self.subTest(offload=offload):
                self.runs = 1
                calls = []

                def first_faults(database, *, write, calls=calls):  # type: ignore[no-untyped-def]
                    calls.append(write)
                    if len(calls) == 1:
                        raise OSError("hub database unreachable")
                    return connect(database, write=write)

                with patch.object(sd_gate_receipts, "_connect", first_faults):
                    result = self.compare(offload)
                self.assertNotIn("satellite", result)
                if offload == "require":
                    self.assertEqual((result["status"], result["offload_refused"]["code"]), ("refused", "satellite_binding"))
                    self.assertIn("whole environment", result["offload_refused"]["reason"])
                    self.assertEqual(self.runs, 1, "the hub ran the check")
                else:
                    self.assertIn("whole environment", result["reuse_miss"]["offload"]["reason"])
                    self.assertEqual((result["status"], self.runs), ("success", 2))

    def test_clause_5_a_receipt_that_binds_no_offload_mode_refuses_as_binding(self) -> None:
        row = self.row(self.key)
        self.assertEqual(row["binding"]["environment_mode"], "offload")
        for mode in ("allowlist", "whole", None):
            with self.subTest(mode=mode):
                rewrite(self.database, self.key, binding={**row["binding"], "environment_mode": mode})
                self.assertIn(f"environment_mode {mode}, not offload", self.refused("satellite_binding")["offload_refused"]["reason"])

    def test_clause_5_a_tree_field_or_the_offload_view_refuses_as_binding(self) -> None:
        row = self.row(self.key)
        rewrite(self.database, self.key, binding={**row["binding"], "inputs": "0" * 64})
        self.assertIn("inputs", self.refused("satellite_binding")["offload_refused"]["reason"])
        view = row["offload_view"]
        rewrite(self.database, self.key, binding=row["binding"],
                offload_view={**view, "variables": {**view["variables"], "LANG": "xx_XX.UTF-8"}})
        self.assertIn("LANG", self.refused("satellite_binding")["offload_refused"]["reason"])

    def test_clause_5_another_interpreter_running_sd_check_refuses_as_binding(self) -> None:
        """The view binds the interpreter that runs `sd-check` (`sys.executable`), not only `PATH`'s `python3`."""
        view = self.row(self.key)["offload_view"]
        rewrite(self.database, self.key, offload_view={**view, "python": {**view.get("python", {}), "sha256": "0" * 64}})
        self.assertIn("python at sha256", self.refused("satellite_binding")["offload_refused"]["reason"])
        rewrite(self.database, self.key, offload_view={name: part for name, part in view.items() if name != "python"})
        self.assertIn("part python", self.refused("satellite_binding")["offload_refused"]["reason"])

    def test_clause_5_reads_the_parsed_local_block_not_its_bytes(self) -> None:
        """sd:2854. The pass ran with no `CLAUDE.local.md`; notes and comments match it, a key does not."""
        local = self.root / "CLAUDE.local.md"
        start, end = sd_lib.LOCAL_BLOCK_START, sd_lib.LOCAL_BLOCK_END
        local.write_text(f"a note outside the block\n{start}\n# a comment\n{end}\n")
        self.assertEqual(self.compare()["status"], "success")
        local.write_text(f"{start}\nmode: minimal\n{end}\n")
        self.assertIn("binding fields inputs", self.refused("satellite_binding")["offload_refused"]["reason"])

    def test_clause_6_another_pack_refuses_as_pack_mismatch(self) -> None:
        rewrite(self.database, self.key, pack_bin="0" * 64)
        self.refused("satellite_pack_mismatch")

    def test_clause_7_an_old_or_future_row_refuses_as_expired(self) -> None:
        recorded = self.row(self.key)["recorded_at"]
        rewrite(self.database, self.key, recorded_at=recorded - sd_gate_receipts.OFFLOAD_WINDOW_SECONDS - 60)
        self.refused("satellite_receipt_expired")
        rewrite(self.database, self.key, recorded_at=recorded + sd_gate_receipts.OFFLOAD_SKEW_SECONDS + 60)
        self.refused("satellite_receipt_expired")

    def test_the_machine_part_is_never_compared(self) -> None:
        """C-17: a satellite's own environment digest and python differ from the hub's, and the receipt stands."""
        row = self.row(self.key)
        rewrite(self.database, self.key, binding={**row["binding"], "environment_sha256": "0" * 64,
                                                  "python": "/elsewhere/python3", "threads": {"RUST_TEST_THREADS": "1"}})
        self.assertEqual(self.compare()["status"], "success")

    def test_a_hub_path_that_lacks_the_repositorys_tool_still_accepts(self) -> None:
        real = shutil.which
        with patch.object(sd_gate_receipts.shutil, "which",
                          lambda name, path=None, **_: None if name == "make" else real(name, path=path)):
            result = self.compare()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertEqual(result["satellite"]["unresolved_tools"], ["make"])

    def test_fallback_runs_the_check_on_a_miss_and_names_it(self) -> None:
        rewrite(self.database, self.key, pack_bin="0" * 64)
        with patch.object(sd_gate_receipts, "examine", lambda *_: (None, {"reason": "no receipt"})):
            result = self.compare("fallback")
        self.assertEqual((result["status"], self.runs), ("success", 2))
        self.assertEqual(result["reuse_miss"]["offload"]["code"], "satellite_pack_mismatch")
        self.assertEqual(result["reuse_miss"]["reason"], "no receipt")


class SatelliteMerge(unittest.TestCase):
    """Clauses 1, 2 and 8, the merge's `--satellite-gate`, and the satellite prepare's status (step 5)."""

    HUB = "hub.example.test:8769"
    args, operation, prepare = fixture.ShipCase.args, fixture.ShipCase.operation, fixture.ShipCase.prepare
    declare, commit, head, puts = (fixture.DeclaredGapCase.declare, fixture.DeclaredGapCase.commit,
                                   fixture.DeclaredGapCase.head, fixture.DeclaredGapCase.puts)
    check, local_ci, gate_posts, local_green = (fixture.DeclaredGapCase.check, fixture.DeclaredGapCase.local_ci,
                                                fixture.DeclaredGapCase.gate_posts, fixture.DeclaredGapCase.local_green)
    TESTS, ROUTE, DECLARATION = (fixture.DeclaredGapCase.TESTS, fixture.DeclaredGapCase.ROUTE,
                                 fixture.DeclaredGapCase.DECLARATION)

    def setUp(self) -> None:
        fixture.DeclaredGapCase.setUp(self)
        rows.no_real_tailscale(self, self.directory)
        self.runs = 0
        self.opted = "accept"
        self.served: str | None = None
        for patcher in (patch.object(sd_lib, "repo_satellite_gate", lambda connection, root: self.opted),
                        patch.object(sd_gate_run, "run_child", self.passing),
                        patch("sd_db.database.served_by", self.served_by, create=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.declare()
        self.local_ci()
        self.local_green()
        self.inputs = sd_gate_run.gate_inputs(self.root, self.head())
        # Prepare's own pass would answer the merge first; these tests are about the satellite's.
        rewrite(self.database, sd_gate_receipts.receipt_key(self.root, self.head()), binding=None)

    def served_by(self, target, home=None):  # type: ignore[no-untyped-def]
        return self.served if str(target) == str(self.database) else None

    def passing(self, argv, env, tree, timeout):  # type: ignore[no-untyped-def]
        self.runs += 1
        return 0, json.dumps({"status": "pass", "scope": {"mode": "full"}, "checks": []}), ""

    def satellite_pass(self) -> str:
        """The satellite's `sd gate check`: its offload row lands in the hub's database; its own receipt stays home."""
        self.served = self.HUB
        try:
            with patch.object(sd_gate_receipts, "record_unless_moved", lambda *_: None):
                result = sd_gate_run.check_in_worktree(self.root, self.head(), base=sd_gate_run.base_ref("main"),
                                                       database=self.database)
        finally:
            self.served = None
        self.runs = 0
        return result["offload"]["key"]

    def status(self, description: str, login: str = "fixture") -> None:
        self.double.statuses = [{"context": "sd/local-gate", "state": "success", "sha": self.head(),
                                 "creator": {"login": login}, "description": description}]

    def satellite_status(self) -> None:
        self.status(f"{self.head()[:12]} inputs {self.inputs}: sat satellite.example.test: sd-check pass")

    def merge(self, *extra: str) -> dict:
        return self.operation("merge", "--manual", "--expected-head", self.head(), *extra).merge()

    def merged_gate(self) -> dict:
        return self.operation("merge", "--manual", "--expected-head", self.head()).state["local_gate"]

    def refuse(self, code: str, *extra: str) -> ship.Refusal:
        with self.assertRaises(ship.Refusal) as caught:
            self.merge(*extra)
        self.assertEqual(caught.exception.workflow["blocker"]["code"], code)
        self.assertEqual((self.puts(), self.runs), (0, 0))
        return caught.exception

    def test_the_satellite_gate_merges_with_no_check_and_no_status_post(self) -> None:
        self.satellite_pass()
        self.satellite_status()
        self.merge("--satellite-gate")
        self.assertEqual((self.puts(), self.runs, self.gate_posts()), (1, 0, []))
        gate = self.merged_gate()
        self.assertEqual(gate["satellite"]["hub"], self.HUB)
        self.assertIn("(satellite ", gate["summary"])
        self.assertEqual(gate["satellite"]["view_differences"], [])  # sd:2862: what the machines differ in, by name

    def test_a_self_gating_pack_merges_from_a_satellite_with_another_installed_pack(self) -> None:
        """Clause 8 under sd:2613: the row binds the tree, so the status inputs leave the installed `bin/` out."""
        with patch.object(sd_gate_receipts, "gates_itself", lambda *_: True):
            self.satellite_pass()
            posted = self.satellite_prepare()["offload_status"]["description"]
            with patch.object(sd_gate_receipts, "pack_files", lambda folder, closure=False: []):  # the hub's installed pack differs
                self.merge("--satellite-gate")
        self.assertTrue(posted.startswith(f"{self.head()[:12]} inputs {sd_gate_run.gate_inputs(self.root, self.head(), own=True)}:"))
        self.assertEqual((self.puts(), self.runs), (1, 0))

    def test_clause_1_a_repository_not_opted_in_refuses_as_satellite_gate_off(self) -> None:
        self.satellite_pass()
        self.satellite_status()
        self.opted = "off"
        refusal = self.refuse("satellite_gate_off", "--satellite-gate")
        self.assertIn("satellite-gate <path> accept", refusal.workflow["next_action"])

    def test_clause_2_a_branch_behind_the_base_refuses_as_base_moved_and_hands_back(self) -> None:
        self.satellite_pass()
        self.satellite_status()
        next(iter(self.remote.pull_requests.values())).merge_state_status = "BEHIND"
        refusal = self.refuse("base_moved", "--satellite-gate")
        self.assertIn("On the satellite: git merge origin/main", refusal.workflow["next_action"])

    def test_clause_8_no_status_refuses_as_satellite_status_missing(self) -> None:
        self.satellite_pass()
        self.refuse("satellite_status_missing", "--satellite-gate")

    def test_clause_8_a_status_at_other_inputs_refuses_as_satellite_status_missing(self) -> None:
        self.satellite_pass()
        self.status(f"{self.head()[:12]} inputs {'0' * 64}: sat satellite.example.test: sd-check pass")
        self.refuse("satellite_status_missing", "--satellite-gate")

    def test_clause_8_another_accounts_status_refuses_as_local_gate_foreign(self) -> None:
        self.satellite_pass()
        self.status(f"{self.head()[:12]} inputs {self.inputs}: sat satellite.example.test: pass", login="someone-else")
        self.refuse("local_gate_foreign", "--satellite-gate")

    def test_clause_8_a_longer_inputs_token_refuses_as_satellite_status_missing(self) -> None:
        self.satellite_pass()
        self.status(f"{self.head()[:12]} inputs {self.inputs}EXTRA: sat satellite.example.test: sd-check pass")
        self.refuse("satellite_status_missing", "--satellite-gate")

    def test_a_refused_receipt_refuses_the_flagged_merge_with_its_code(self) -> None:
        rewrite(self.database, self.satellite_pass(), pack_bin="0" * 64)
        self.satellite_status()
        refusal = self.refuse("satellite_pack_mismatch", "--satellite-gate")
        self.assertIn("pack checkout to the hub's revision", refusal.workflow["next_action"])

    def test_a_plain_merge_takes_a_valid_offload_receipt_and_runs_nothing(self) -> None:
        self.satellite_pass()
        self.satellite_status()
        self.merge()
        self.assertEqual((self.puts(), self.runs, self.gate_posts()), (1, 0, []))

    def test_a_plain_merge_with_a_broken_offload_receipt_runs_and_names_the_miss(self) -> None:
        rewrite(self.database, self.satellite_pass(), pack_bin="0" * 64)
        self.merge()
        self.assertEqual((self.puts(), self.runs), (1, 1))
        [post] = self.gate_posts()
        self.assertEqual(post.body["state"], "success")
        miss = self.merged_gate()["reuse_miss"]
        self.assertEqual(miss["offload"]["code"], "satellite_pack_mismatch")

    # -- sd:2854: both bindings read the parsed `CLAUDE.local.md` block, not its bytes --

    def hub_copy(self, old: str, new: str) -> None:
        """The satellite's pass and status, then the hub's own copy of the untracked file, `old` replaced by `new`."""
        self.satellite_pass()
        self.satellite_status()
        local = self.root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace(old, new))

    def test_a_hub_copy_that_differs_outside_the_block_merges_on_the_satellite_gate(self) -> None:
        """Clause 5 compares `inputs`, clause 8 the status's, and the review its binding: none moves."""
        self.hub_copy("mode: full\n", "# the hub's copy\n\nmode: full  # a comment\n")
        with (self.root / "CLAUDE.local.md").open("a") as stream:
            stream.write("reviewers: a line outside the block\n")
        self.merge("--satellite-gate")
        self.assertEqual((self.puts(), self.runs), (1, 0))

    def test_a_key_that_differs_in_the_block_refuses_with_or_without_the_satellite_gate(self) -> None:
        self.hub_copy("mode: full", "mode: minimal")
        for extra in (("--satellite-gate",), ()):
            with self.subTest(extra=extra):
                refusal = self.refuse("review_binding_moved", *extra)
                self.assertTrue(str(refusal).endswith(": CLAUDE.local.md (policy)"), str(refusal))

    def test_the_satellite_gate_still_binds_the_tracked_review_policy(self) -> None:
        self.hub_copy("mode: full", "mode: full")
        with (self.root / ".git/info/exclude").open("a") as stream:  # a clean checkout, so the binding decides
            stream.write("\n.github/sd-review.json\n")
        (self.root / ".github" / "sd-review.json").write_text("{}")
        refusal = self.refuse("review_binding_moved", "--satellite-gate")
        self.assertTrue(str(refusal).endswith(": .github/sd-review.json (policy)"), str(refusal))

    def test_a_repository_not_opted_in_merges_as_before(self) -> None:
        self.satellite_pass()
        self.satellite_status()
        self.opted = "off"
        self.merge()
        self.assertEqual((self.puts(), self.runs, len(self.gate_posts())), (1, 1, 1))

    # -- step 5: the satellite's prepare posts the status the hub's clause 8 reads --

    def satellite_prepare(self) -> dict:
        operation = self.operation("prepare")
        operation.served_by = self.HUB
        return operation.prepare()

    def test_a_satellite_prepare_posts_one_status_from_its_offload_row(self) -> None:
        self.satellite_pass()
        before = len(self.gate_posts())
        result = self.satellite_prepare()
        posts = self.gate_posts()
        self.assertEqual(len(posts) - before, 1)
        description = posts[-1].body["description"]
        self.assertTrue(description.startswith(f"{self.head()[:12]} inputs {self.inputs}: sat "), description)
        self.assertEqual(result["offload_status"]["description"], description)
        self.merge("--satellite-gate")
        self.assertEqual((self.puts(), self.runs), (1, 0))

    def test_a_satellite_prepare_with_no_row_posts_nothing_and_says_why(self) -> None:
        result = self.satellite_prepare()
        self.assertEqual(self.gate_posts(), [])
        self.assertIn("no standing offload receipt", result["offload_error"])

    def test_a_satellite_prepare_posts_nothing_from_a_row_that_no_longer_stands(self) -> None:
        """Expired, another pack, or other inputs (a changed `CLAUDE.local.md`): no status names inputs nobody checked."""
        key = self.satellite_pass()
        row = rows.sd_gate_receipts.read_offload(self.database, key)[1]
        broken = {"outside": {"recorded_at": row["recorded_at"] - sd_gate_receipts.OFFLOAD_WINDOW_SECONDS - 60},
                  "not the hub's": {"pack_bin": "0" * 64},
                  "not this checkout's": {"binding": {**row["binding"], "inputs": "0" * 12}}}
        for reason, fields in broken.items():
            with self.subTest(reason=reason):
                rewrite(self.database, key, **fields)
                self.assertIn(reason, self.satellite_prepare()["offload_error"])
                self.assertEqual(self.gate_posts(), [])
                rewrite(self.database, key, **{name: row[name] for name in fields})

    def test_a_hub_prepare_posts_nothing_new(self) -> None:
        self.satellite_pass()
        result = self.operation("prepare").prepare()
        self.assertEqual(self.gate_posts(), [])
        self.assertFalse({"offload_status", "offload_error"} & set(result))



if __name__ == "__main__":
    unittest.main()
