"""Fixtures for bin/sd-handoff-restore: the SessionStart hook half of the lane.

The hook must be silent and cheap when there is nothing to do, must verify the
packet's recorded identity against the repository actually sitting at this
path before it injects anything, and must never break session startup. Every
test runs the real executable in a subprocess against a real `git init`
repository, with HOME redirected away from the operator's `~/.local/state`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HANDOFF = REPO_ROOT / "bin" / "sd-handoff"
RESTORE = REPO_ROOT / "bin" / "sd-handoff-restore"

GIT_IDENTITY = (
    "-c",
    "user.email=handoff@example.invalid",
    "-c",
    "user.name=Handoff Fixture",
    "-c",
    "commit.gpgsign=false",
)


def git(cwd: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *GIT_IDENTITY, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )
    return completed.stdout


class RestoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = pathlib.Path(os.path.realpath(self._temp.name))
        self.home = self.base / "home"
        self.home.mkdir()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main", ".")
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        git(self.repo, "add", "a.txt")
        git(self.repo, "commit", "-qm", "first")

    # -- plumbing ---------------------------------------------------------

    def env(self, cwd: pathlib.Path, **extra: str) -> dict[str, str]:
        environment = dict(os.environ)
        for key in ("XDG_STATE_HOME", "CLAUDE_PROJECT_DIR", "SD_HANDOFF_RESTORE"):
            environment.pop(key, None)
        environment["HOME"] = str(self.home)
        environment["PWD"] = str(cwd)
        environment.update(extra)
        return environment

    def packet_path(self, root: pathlib.Path) -> pathlib.Path:
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        return (
            self.home
            / ".local"
            / "state"
            / "sd-ai-command-pack"
            / "handoff"
            / f"{digest}.json"
        )

    def packet(self, root: pathlib.Path | None = None) -> dict:
        return json.loads(
            self.packet_path(root or self.repo).read_text(encoding="utf-8")
        )

    def rewrite(self, changes: dict, root: pathlib.Path | None = None) -> None:
        path = self.packet_path(root or self.repo)
        packet = json.loads(path.read_text(encoding="utf-8"))
        packet.update(changes)
        path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    def write_packet(
        self, *args: str, cwd: pathlib.Path | None = None, **extra: str
    ) -> None:
        where = cwd or self.repo
        result = subprocess.run(
            [str(HANDOFF), *args],
            cwd=str(where),
            env=self.env(where, **extra),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def restore(
        self,
        cwd: pathlib.Path | None = None,
        source: str = "clear",
        payload_cwd: pathlib.Path | None | bool = None,
        **extra: str,
    ) -> subprocess.CompletedProcess[str]:
        where = cwd or self.repo
        payload: dict[str, str] = {"hook_event_name": "SessionStart", "source": source}
        if payload_cwd is not False:
            payload["cwd"] = str(payload_cwd or where)
        return subprocess.run(
            [str(RESTORE)],
            cwd=str(where),
            env=self.env(where, **extra),
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def context(self, result: subprocess.CompletedProcess[str]) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), "hook emitted nothing")
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"], "SessionStart"
        )
        return payload["hookSpecificOutput"]["additionalContext"]

    def assert_silent(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


class RoundTripTests(RestoreFixture):
    def test_write_then_restore(self) -> None:
        (self.repo / "a.txt").write_text("changed\n", encoding="utf-8")
        self.write_packet(
            "--summary",
            "the tokenizer rewrite is half done",
            "--next",
            "finish the string case",
            "--dont",
            "do not reach for a regex again",
            "--question",
            "does the caller expect bytes or str",
            "--item",
            "docs/work/2026-08-29-tokenizer",
        )
        context = self.context(self.restore())
        for expected in (
            "the tokenizer rewrite is half done",
            "finish the string case",
            "do not reach for a regex again",
            "does the caller expect bytes or str",
            "docs/work/2026-08-29-tokenizer",
            "a.txt",
            str(self.repo),
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, context)

    def test_the_injected_context_carries_an_age_stamp(self) -> None:
        self.write_packet("--summary", "fresh")
        self.assertIn("ago", self.context(self.restore()))

    def test_an_old_but_unexpired_packet_reports_its_age_in_days(self) -> None:
        self.write_packet("--summary", "stale but valid")
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=9)
        self.rewrite({"created": old.replace(microsecond=0).isoformat()})
        self.assertIn("written 9d ago", self.context(self.restore()))

    def test_restoring_marks_the_packet_consumed(self) -> None:
        self.write_packet("--summary", "once")
        self.context(self.restore())
        self.assertIsNotNone(self.packet()["consumed"])

    def test_a_packet_is_injected_exactly_once(self) -> None:
        self.write_packet("--summary", "once")
        self.context(self.restore())
        self.assert_silent(self.restore())

    def test_a_packet_with_no_work_item_still_restores(self) -> None:
        self.write_packet("--summary", "no item anywhere in sight")
        context = self.context(self.restore())
        self.assertIn("Work item: none", context)

    def test_a_subdirectory_session_finds_the_root_packet(self) -> None:
        nested = self.repo / "src"
        nested.mkdir()
        self.write_packet("--summary", "written at the root")
        context = self.context(self.restore(cwd=nested))
        self.assertIn("written at the root", context)

    def test_startup_restores_as_well_as_clear(self) -> None:
        self.write_packet("--summary", "restored at startup")
        context = self.context(self.restore(source="startup"))
        self.assertIn("restored at startup", context)


class SilenceTests(RestoreFixture):
    def test_no_packet_is_silent(self) -> None:
        self.assert_silent(self.restore())

    def test_the_opt_out_leaves_the_packet_untouched(self) -> None:
        self.write_packet("--summary", "not for the 3am cron job")
        before = self.packet_path(self.repo).read_bytes()
        self.assert_silent(self.restore(SD_HANDOFF_RESTORE="0"))
        self.assertEqual(self.packet_path(self.repo).read_bytes(), before)
        self.assertIsNone(self.packet()["consumed"])
        # And the packet is still there for the interactive session that wants it.
        self.assertIn("not for the 3am cron job", self.context(self.restore()))

    def test_an_unrelated_value_of_the_opt_out_does_not_disable_the_hook(self) -> None:
        self.write_packet("--summary", "still restored")
        self.assertIn(
            "still restored", self.context(self.restore(SD_HANDOFF_RESTORE="1"))
        )

    def test_a_consumed_packet_is_silent(self) -> None:
        self.write_packet("--summary", "already taken")
        self.rewrite({"consumed": "2026-08-29T00:00:00+00:00"})
        self.assert_silent(self.restore())

    def test_an_expired_packet_is_silent(self) -> None:
        self.write_packet("--summary", "too old to trust")
        past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        self.rewrite({"expires": past.replace(microsecond=0).isoformat()})
        self.assert_silent(self.restore())
        self.assertIsNone(self.packet()["consumed"])

    def test_a_corrupt_packet_exits_zero_and_says_nothing(self) -> None:
        self.write_packet("--summary", "about to be mangled")
        self.packet_path(self.repo).write_text("{ truncated", encoding="utf-8")
        result = self.restore()
        self.assert_silent(result)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_packet_that_is_not_an_object_exits_zero(self) -> None:
        self.write_packet("--summary", "about to become a list")
        self.packet_path(self.repo).write_text("[1, 2, 3]", encoding="utf-8")
        self.assert_silent(self.restore())

    def test_an_empty_payload_does_not_break_startup(self) -> None:
        self.write_packet("--summary", "payloadless")
        result = subprocess.run(
            [str(RESTORE)],
            cwd=str(self.repo),
            env=self.env(self.repo),
            input="",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        # $PWD carries the directory when the payload does not.
        self.assertIn("payloadless", self.context(result))

    def test_a_malformed_payload_does_not_break_startup(self) -> None:
        self.write_packet("--summary", "malformed payload")
        result = subprocess.run(
            [str(RESTORE)],
            cwd=str(self.repo),
            env=self.env(self.repo),
            input="not json at all",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertIn("malformed payload", self.context(result))


class IdentityTests(RestoreFixture):
    def test_a_reused_path_holding_a_different_project_is_refused(self) -> None:
        self.write_packet("--summary", "belongs to the project that used to be here")
        # The same path, a different project: delete the checkout and clone
        # something else into it. The packet's head_sha is no longer an object.
        for child in self.repo.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        git(self.repo, "init", "-q", "-b", "main", ".")
        (self.repo / "b.txt").write_text("other project\n", encoding="utf-8")
        git(self.repo, "add", "b.txt")
        git(self.repo, "commit", "-qm", "a different history")
        result = self.restore()
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("not an object in the repository now at this path", context)
        self.assertNotIn("belongs to the project that used to be here", context)
        # A refusal never consumes: the operator can still inspect it.
        self.assertIsNone(self.packet()["consumed"])

    def test_a_recorded_root_that_no_longer_exists_is_refused(self) -> None:
        self.write_packet("--summary", "written for a vanished root")
        self.rewrite({"repo": {**self.packet()["repo"], "root": str(self.base / "gone")}})
        context = json.loads(self.restore().stdout)["hookSpecificOutput"][
            "additionalContext"
        ]
        self.assertIn("no longer exists", context)
        self.assertNotIn("written for a vanished root", context)

    def test_a_recorded_root_that_does_not_contain_the_cwd_is_refused(self) -> None:
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        self.write_packet("--summary", "written for another tree")
        self.rewrite({"repo": {**self.packet()["repo"], "root": str(elsewhere)}})
        context = json.loads(self.restore().stdout)["hookSpecificOutput"][
            "additionalContext"
        ]
        self.assertIn("does not contain the current directory", context)

    def test_a_commit_after_the_packet_is_context_not_a_check(self) -> None:
        self.write_packet("--summary", "head has moved on since")
        (self.repo / "c.txt").write_text("more\n", encoding="utf-8")
        git(self.repo, "add", "c.txt")
        git(self.repo, "commit", "-qm", "second")
        context = self.context(self.restore())
        self.assertIn("head has moved on since", context)
        self.assertNotIn("WARNING", context)

    def test_switching_origin_to_a_fork_restores_with_a_warning(self) -> None:
        git(self.repo, "remote", "add", "origin", "git@github.com:upstream/thing.git")
        self.write_packet("--summary", "the fork-first flow must survive this")
        git(self.repo, "remote", "set-url", "origin", "git@github.com:me/thing.git")
        context = self.context(self.restore())
        self.assertIn("the fork-first flow must survive this", context)
        self.assertIn("WARNING", context)
        self.assertIn("git@github.com:upstream/thing", context)
        self.assertIn("git@github.com:me/thing", context)
        self.assertIsNotNone(self.packet()["consumed"])

    def test_an_unchanged_origin_injects_without_a_warning(self) -> None:
        git(self.repo, "remote", "add", "origin", "git@github.com:o/r.git")
        self.write_packet("--summary", "same remote as before")
        self.assertNotIn("WARNING", self.context(self.restore()))


class WorktreeTests(RestoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.linked = self.base / "linked"
        git(self.repo, "worktree", "add", "-q", "-b", "side", str(self.linked))

    def test_a_writer_and_a_restorer_in_one_worktree_meet_on_one_digest(self) -> None:
        self.write_packet("--summary", "work that lives in the linked worktree",
                          cwd=self.linked)
        self.assertTrue(self.packet_path(self.linked).is_file())
        self.assertFalse(self.packet_path(self.repo).exists())
        context = self.context(self.restore(cwd=self.linked))
        self.assertIn("work that lives in the linked worktree", context)
        self.assertIn(str(self.linked), context)

    def test_claude_project_dir_pointing_at_the_main_checkout_still_meets(self) -> None:
        # The env var is the session's launch directory and is fixed for the
        # session; both sides must resolve from the working directory instead.
        self.write_packet(
            "--summary",
            "written from the worktree with the env var elsewhere",
            cwd=self.linked,
            CLAUDE_PROJECT_DIR=str(self.repo),
        )
        context = self.context(
            self.restore(cwd=self.linked, CLAUDE_PROJECT_DIR=str(self.repo))
        )
        self.assertIn("written from the worktree with the env var elsewhere", context)

    def test_the_payload_cwd_outranks_the_environment(self) -> None:
        self.write_packet("--summary", "worktree packet", cwd=self.linked)
        # Process cwd and $PWD say the main checkout; the payload says the
        # worktree, and the payload wins.
        result = subprocess.run(
            [str(RESTORE)],
            cwd=str(self.repo),
            env=self.env(self.repo, CLAUDE_PROJECT_DIR=str(self.repo)),
            input=json.dumps({"cwd": str(self.linked), "source": "clear"}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertIn("worktree packet", self.context(result))

    def test_the_other_worktree_does_not_see_it(self) -> None:
        self.write_packet("--summary", "worktree only", cwd=self.linked)
        self.assert_silent(self.restore(cwd=self.repo))


class RaceTests(RestoreFixture):
    def test_two_concurrent_restores_and_only_one_wins(self) -> None:
        self.write_packet("--summary", "exactly one session gets this")
        payload = json.dumps({"cwd": str(self.repo), "source": "clear"})
        processes = [
            subprocess.Popen(
                [str(RESTORE)],
                cwd=str(self.repo),
                env=self.env(self.repo),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [process.communicate(payload) for process in processes]
        for process in processes:
            self.assertEqual(process.returncode, 0)
        winners = [stdout for stdout, _ in outputs if stdout.strip()]
        self.assertEqual(len(winners), 1, outputs)
        self.assertIn("exactly one session gets this", winners[0])
        self.assertIsNotNone(self.packet()["consumed"])

    def test_show_and_the_hook_cannot_both_claim_one_packet(self) -> None:
        self.write_packet("--summary", "claimed once, by whoever gets there first")
        shown = subprocess.run(
            [str(HANDOFF), "--show"],
            cwd=str(self.repo),
            env=self.env(self.repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assert_silent(self.restore())


class LoadLogTests(RestoreFixture):
    """R10-D3's deletion criterion needs a count and a median, from somewhere.

    "Fewer than 5 packets auto-loaded, or median packet age at load over 7
    days" reads as though the packets themselves answer it -- each one keeps
    `created` and, after a restore, `consumed`. They do not: there is one
    packet per directory and the next `sd-handoff` overwrites it, so the
    highest count the packets can report is the number of directories. These
    fixtures pin the log that makes the criterion answerable, and pin the two
    ways an unpinned log would quietly report the wrong number -- counting
    races instead of loads, and taking session startup down with it.
    """

    def log_path(self) -> pathlib.Path:
        return (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "handoff"
            / "loads.jsonl"
        )

    def entries(self) -> list[dict]:
        path = self.log_path()
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_a_restore_appends_one_entry_carrying_the_age_at_load(self) -> None:
        self.write_packet("--summary", "counted once")
        self.context(self.restore())
        entries = self.entries()
        self.assertEqual(len(entries), 1, entries)
        entry = entries[0]
        self.assertEqual(sorted(entry), ["age_seconds", "consumed", "created", "directory"])
        # The age is the criterion's second number; a packet written moments
        # ago must read as ~0 rather than as None or a negative.
        self.assertIsInstance(entry["age_seconds"], int)
        self.assertGreaterEqual(entry["age_seconds"], 0)
        self.assertLess(entry["age_seconds"], 300)

    def test_the_count_survives_the_packet_being_overwritten(self) -> None:
        """The whole reason the log exists, stated as a fixture.

        Two handoffs and two restores in one directory are two loads. The
        packet file can only ever report the last of them, so a criterion read
        off the packets would say 1 where the truth is 2 -- and would say 1 no
        matter how many restores happened.
        """

        for note in ("first", "second"):
            self.write_packet("--summary", f"{note} handoff")
            self.context(self.restore())
        self.assertEqual(len(self.entries()), 2, self.entries())
        self.assertEqual(json.loads(
            self.packet_path(self.repo).read_text(encoding="utf-8")
        )["summary"], "second handoff")

    def test_the_loser_of_a_race_logs_nothing(self) -> None:
        """One packet restored once is one load, however many hooks tried.

        What this observes is the outcome, not the ordering that produces it.
        Whether the second hook returns early on a `consumed` packet or reaches
        `claim` and loses the rename depends on how the two processes interleave,
        so moving `record_load` above the rename does not reliably fail this --
        the placement is argued in the source and not pinned here. What is
        pinned is the number that matters: two hooks, one restore, one entry.
        """

        self.write_packet("--summary", "exactly one session gets this")
        payload = json.dumps({"cwd": str(self.repo), "source": "clear"})
        processes = [
            subprocess.Popen(
                [str(RESTORE)],
                cwd=str(self.repo),
                env=self.env(self.repo),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [process.communicate(payload) for process in processes]
        self.assertEqual(len([o for o, _ in outputs if o.strip()]), 1, outputs)
        self.assertEqual(len(self.entries()), 1, self.entries())

    def test_show_is_the_manual_path_and_is_not_counted(self) -> None:
        """The criterion measures auto-loads against the manual read path."""

        self.write_packet("--summary", "read by hand")
        shown = subprocess.run(
            [str(HANDOFF), "--show"],
            cwd=str(self.repo),
            env=self.env(self.repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(self.entries(), [])

    def test_an_unwritable_log_does_not_cost_the_session_its_context(self) -> None:
        """Measuring the restore must never be able to prevent one.

        A read-only state directory is the realistic way this breaks -- a
        restored backup, a permissions sweep -- and a session losing its
        handoff because the counter could not be incremented would be a worse
        bug than the one the counter exists to fix.
        """

        self.write_packet("--summary", "context survives an unwritable log")
        # chmod the file and restore *that* file: an earlier draft saved the
        # directory's mode and handed it back instead, which left the log
        # read-only after the test and restored nothing that had changed.
        log = self.log_path()
        log.write_text("", encoding="utf-8")
        mode = log.stat().st_mode
        self.addCleanup(os.chmod, log, mode)
        os.chmod(log, 0o444)
        result = self.restore()
        self.assertIn("context survives an unwritable log", self.context(result))
        self.assertEqual(self.entries(), [])


class ShapeTests(RestoreFixture):
    def test_the_hook_is_executable_and_self_contained(self) -> None:
        self.assertTrue(os.access(RESTORE, os.X_OK))
        source = RESTORE.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/usr/bin/env python3\n"))
        for forbidden in ("sd_lib", "import requests", "from installer"):
            self.assertNotIn(forbidden, source)

    def test_the_docstring_records_why_compact_and_resume_are_excluded(self) -> None:
        # The reasoning is the design: a later reader who does not find it here
        # will "helpfully" add the matchers back.
        docstring = RESTORE.read_text(encoding="utf-8").split('"""')[1]
        for token in ("startup", "clear", "compact", "resume"):
            self.assertIn(token, docstring)
        self.assertIn("NOT `compact`", docstring)
        self.assertIn("NOT `resume`", docstring)


if __name__ == "__main__":
    unittest.main()
