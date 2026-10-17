"""The `repo` table is what the enumeration is bounded by, so it must fill.

Criterion 6 enumerates `docs/work/*/prd.md` across "every repository the
`repo` table holds". Nothing in requirement 2 said how a row gets there, and
an empty table makes that criterion pass over nothing. These are the two ways
it fills and the one path it refuses.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from sd_db import connect, paths, ship
from sd_db.channels import ChannelRefusal
from sd_db.errors import SchemaTooOld, SdDbError
from sd_db.migrate import initialise, migrate
from sd_db.repos import (
    CI_MODES,
    ConfMissing,
    RepoRefusal,
    add,
    checkouts,
    clone_lines,
    conf_paths,
    github_issues,
    intake_issues,
    intake_repos,
    issue_sources,
    mail_aliases,
    mine_issues,
    read_conf,
    registered,
    repo_channels,
    repo_ci,
    seed,
    seed_clones,
    set_channels,
    set_ci,
    set_clones,
    set_dependabot,
    set_github_issues,
    set_lane_host,
    set_managed,
    set_runner_merge,
    worktrees_root,
)
from sd_db.schema import migrations
from sd_db.workflow import StaleItem
from sd_db.writes import upsert_repo

from . import support

#: Hold the ship lock as `sd-ship merge` does, say so, and keep it until killed.
HOLDER = """
import sys, time
from pathlib import Path
from sd_db import ship
with ship.repository_lock(Path(sys.argv[1]), sys.argv[2], holder={"command": "sd-ship merge --item 41", "item": 41}):
    print("held", flush=True)
    time.sleep(60)
"""


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkouts = self.root / "repos"
        self.checkouts.mkdir()
        database = self.root / "sd.db"
        initialise(database)
        self.connection = connect(database)
        self.addCleanup(self.connection.close)

    def conf(self, text: str) -> Path:
        path = self.root / "repos.personal.conf"
        path.write_text(text, encoding="utf-8")
        return path


class ReadingTheConf(RepoCase):
    def test_comments_and_blanks_are_skipped(self):
        path = self.conf("# a comment\n\nacme  example-org/anvil\nha  a/b\n")
        self.assertEqual(
            read_conf(path), [("acme", "example-org/anvil"), ("ha", "a/b")]
        )

    def test_a_comment_after_a_line_is_dropped_as_repo_sync_drops_it(self):
        """`repo-sync`'s conf reader cuts `#...` off every line (`sed -e 's/#.*//'`)."""
        path = self.conf("acme example-org/anvil  # daily\n  # indented\nha a/b#x\n")
        self.assertEqual(read_conf(path), [("acme", "example-org/anvil"), ("ha", "a/b")])

    def test_a_line_it_cannot_parse_is_a_refusal_and_not_a_skip(self):
        """A line nobody parses is a repository nobody syncs."""
        path = self.conf("acme example-org/anvil\nthis is not a line\n")
        with self.assertRaises(RepoRefusal) as caught:
            read_conf(path)
        self.assertIn("not a line", str(caught.exception))
        self.assertIn(":2:", str(caught.exception))


class Seeding(RepoCase):
    def setUp(self):
        super().setUp()
        (self.checkouts / "acme").mkdir()
        support.repository(self.checkouts / "acme" / "anvil")
        self.path = self.conf("acme  example-org/anvil\nacme  example-org/absent\n")

    def test_only_checkouts_that_exist_are_registered(self):
        result = seed(
            self.connection, self.path, root=self.checkouts, home=self.home
        )
        self.assertEqual(result.counts, {"registered": 1, "absent": 1})
        self.assertEqual(result.absent, ["example-org/absent"])
        rows = registered(self.connection)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["path"].endswith("/acme/anvil"))

    def test_a_second_seed_registers_the_same_set(self):
        first = seed(self.connection, self.path, root=self.checkouts, home=self.home)
        second = seed(self.connection, self.path, root=self.checkouts, home=self.home)
        self.assertEqual(first.registered, second.registered)
        self.assertEqual(len(registered(self.connection)), 1)

    def test_the_remote_is_recorded(self):
        """With no origin on the checkout, the conf's rendering is the answer."""
        seed(self.connection, self.path, root=self.checkouts, home=self.home)
        self.assertEqual(
            registered(self.connection)[0]["remote"],
            "https://github.com/example-org/anvil",
        )

    def test_a_checkouts_own_origin_outranks_the_confs_rendering(self):
        """The conf names a slug, so `Checkout.remote` can only ever render https.

        A machine that clones over ssh carries an ssh origin. Before sd:1436
        `same_remote` did not treat the two spellings as one repository, so
        letting the conf win left every seeded row unable to resolve its own
        checkout by origin. The row still records what the checkout says.
        """
        checkout = self.checkouts / "acme" / "ssh"
        support.repository(checkout, bare=self.root / "ssh.git")
        support.git(checkout, "remote", "set-url", "origin",
                    "git@github.com:example-org/ssh.git")
        path = self.conf("acme  example-org/anvil\nacme  example-org/ssh\n")
        seed(self.connection, path, root=self.checkouts, home=self.home)
        rows = {row["path"]: row["remote"] for row in registered(self.connection)}
        self.assertEqual(
            rows[str(checkout.resolve())], "git@github.com:example-org/ssh.git"
        )


    def test_a_checkout_whose_origin_names_another_repository_is_not_registered(self):
        """Failure table, row "`repo seed`: the path holds another repository"."""
        support.git(self.checkouts / "acme" / "anvil", "remote", "add", "origin",
                    "https://github.com/new-owner/anvil")
        result = seed(self.connection, self.path, root=self.checkouts, home=self.home)
        self.assertEqual(result.registered, [])
        self.assertEqual(len(result.mismatched), 1)
        self.assertIn("example-org/anvil", result.mismatched[0])
        self.assertIn("https://github.com/new-owner/anvil", result.mismatched[0])
        self.assertEqual(registered(self.connection), [])


class SeedingTheCommonConf(RepoCase):
    """`repo-sync` reads `repos.common.conf` plus the profile conf on personal.

    The seed read `repos.personal.conf` alone, so a checkout listed only in
    common -- `platypeeps/writing-pack`, `acme/web-supporting-files`
    -- was cloned every night and never registered.
    """

    def setUp(self):
        super().setUp()
        (self.checkouts / "platypeeps").mkdir()
        (self.checkouts / "acme").mkdir()
        support.repository(self.checkouts / "platypeeps" / "shared")
        support.repository(self.checkouts / "acme" / "anvil")
        self.personal = self.conf("acme  example-org/anvil\n")
        self.common = self.root / "repos.common.conf"
        self.common.write_text(
            "platypeeps  platypeeps/shared\nacme  example-org/anvil\n", encoding="utf-8"
        )

    def seed_default(self):
        with mock.patch("sd_db.repos.conf_path", return_value=self.personal):
            return seed(self.connection, None, root=self.checkouts, home=self.home)

    def test_the_default_seed_registers_a_checkout_only_common_names(self):
        result = self.seed_default()
        paths = sorted(Path(row["path"]).name for row in registered(self.connection))
        self.assertEqual(paths, ["anvil", "shared"])
        self.assertEqual(result.counts, {"registered": 2, "absent": 0})

    def test_an_entry_in_both_files_is_one_checkout(self):
        with mock.patch("sd_db.repos.conf_path", return_value=self.personal):
            slugs = [checkout.slug for checkout in checkouts(root=self.checkouts)]
        self.assertEqual(slugs, ["platypeeps/shared", "example-org/anvil"])

    def test_a_missing_common_conf_leaves_the_personal_one(self):
        self.common.unlink()
        self.assertEqual(self.seed_default().counts, {"registered": 1, "absent": 0})

    def test_a_named_conf_is_read_alone(self):
        """PIN: `repo seed <conf>` means that file, not that file plus common."""
        result = seed(self.connection, self.personal, root=self.checkouts, home=self.home)
        self.assertEqual(result.counts, {"registered": 1, "absent": 0})

    def test_the_personal_profile_reads_the_common_and_personal_pair(self):
        with mock.patch.dict(os.environ, {"SYSTEM_TOOLS_CONFIG": str(self.root / "cfg")}):
            os.environ.pop("REPO_SYNC_PROFILE", None)
            self.assertEqual(
                [path.name for path in conf_paths()],
                ["repos.common.conf", "repos.personal.conf"],
            )


class TheConfigDirectory(RepoCase):
    """repo-sync's lists live in `<config>/repo-sync/`, not in the checkout."""

    def setUp(self):
        super().setUp()
        self.config = self.root / "cfg"
        self.lists = self.config / "repo-sync"
        self.lists.mkdir(parents=True)
        support.repository(self.checkouts / "acme" / "anvil")
        support.repository(self.checkouts / "platypeeps" / "shared")
        patcher = mock.patch.dict(os.environ, {"SYSTEM_TOOLS_CONFIG": str(self.config)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("REPO_SYNC_PROFILE", None)

    def test_the_default_pair_is_read_from_the_config_directory(self):
        self.assertEqual(conf_paths(), [self.lists / "repos.common.conf",
                                        self.lists / "repos.personal.conf"])
        (self.lists / "repos.common.conf").write_text("platypeeps  platypeeps/shared\n")
        (self.lists / "repos.personal.conf").write_text("acme  example-org/anvil\n")
        result = seed(self.connection, None, root=self.checkouts, home=self.home)
        self.assertEqual(result.counts, {"registered": 2, "absent": 0})

    def test_the_profile_names_the_list(self):
        os.environ["REPO_SYNC_PROFILE"] = "work"
        self.assertEqual(conf_paths()[-1], self.lists / "repos.work.conf")
        os.environ["REPO_SYNC_PROFILE"] = "terra"
        self.assertEqual(conf_paths(), [self.lists / "repos.terra.conf"])

    def test_an_absent_profile_list_fails_naming_where_it_goes(self):
        with self.assertRaises(ConfMissing) as caught:
            seed(self.connection, None, root=self.checkouts, home=self.home)
        message = str(caught.exception)
        self.assertIn(str(self.lists / "repos.personal.conf"), message)
        self.assertIn("local-repo-sync/repos.personal.conf.example", message)
        self.assertIsInstance(caught.exception, FileNotFoundError)
        self.assertEqual(registered(self.connection), [])

    def test_the_command_reports_the_absent_list_and_exits_1(self):
        import contextlib
        import io

        from sd_db.jobs import cli
        err = io.StringIO()
        with mock.patch.object(cli, "_open_for_write", lambda: connect(self.root / "sd.db")), \
                mock.patch.object(cli, "_home", lambda: self.home), \
                contextlib.redirect_stderr(err):
            rc = cli.command_repo(["seed"])
        self.assertEqual(rc, 1)
        self.assertIn("repos.personal.conf is not set", err.getvalue())
        self.assertIn(str(self.lists / "repos.personal.conf"), err.getvalue())


class Adding(RepoCase):
    def test_a_checkout_is_registered_with_the_mode_read_from_it(self):
        checkout = support.repository(self.checkouts / "one")
        add(self.connection, checkout, home=self.home)
        row = registered(self.connection)[0]
        self.assertEqual(row["mode"], "work")

    def test_a_directory_that_is_not_a_checkout_is_refused(self):
        plain = self.checkouts / "plain"
        plain.mkdir()
        with self.assertRaises(RepoRefusal) as caught:
            add(self.connection, plain, home=self.home)
        self.assertIn("not a git checkout", str(caught.exception))

    def test_a_clone_under_the_worktrees_directory_is_refused(self):
        """A runner's clone is not a registered repository.

        Criterion 6's own test clones a registered repository under the
        worktrees directory and asserts the enumeration does not widen. It
        does not widen because the table is the bound; this refusal is what
        stops an operator putting one in the table by hand.
        """
        worktrees = worktrees_root(self.home)
        worktrees.mkdir(parents=True)
        clone = support.repository(worktrees / "item-clone")
        with self.assertRaises(RepoRefusal) as caught:
            add(self.connection, clone, home=self.home)
        self.assertIn("worktrees directory", str(caught.exception))
        self.assertEqual(registered(self.connection), [])


class TheManagedWriter(RepoCase):
    """sd:1619. `repo.managed` says the operator manages the repository.

    The writer mirrors `set_runner_merge`: it writes, it reports what it
    replaced, it refuses a value that is not a flag word, and it refuses a
    path no row holds rather than making one.
    """

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def _value(self, path: str) -> int:
        return self.connection.execute(
            "SELECT managed FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_it_sets_the_column_and_names_what_it_replaced(self):
        path = self._registered()
        self.assertEqual(self._value(path), 0)
        self.assertEqual(set_managed(self.connection, path, "yes"), (path, "no"))
        self.assertEqual(self._value(path), 1)
        self.assertEqual(set_managed(self.connection, path, "no"), (path, "yes"))
        self.assertEqual(self._value(path), 0)

    def test_it_changes_no_other_field_on_the_row(self):
        path = self._registered()
        before = dict(self.connection.execute(
            "SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_managed(self.connection, path, "yes")
        after = dict(self.connection.execute(
            "SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        moved = {key for key in before if before[key] != after[key]}
        self.assertEqual(moved - {"updated_at"}, {"managed"})

    def test_a_value_that_is_not_a_flag_word_is_refused_in_a_sentence(self):
        path = self._registered()
        for value in ("true", "1", "Yes", ""):
            with self.subTest(value=value), self.assertRaises(RepoRefusal) as caught:
                set_managed(self.connection, path, value)
            self.assertIn("yes or no", str(caught.exception))
        self.assertEqual(self._value(path), 0)

    def test_an_unregistered_path_is_refused_rather_than_registered(self):
        checkout = support.repository(self.checkouts / "two")
        with self.assertRaises(RepoRefusal) as caught:
            set_managed(self.connection, checkout, "yes")
        self.assertIn("not a registered repository", str(caught.exception))
        self.assertEqual(registered(self.connection), [])


if __name__ == "__main__":
    unittest.main()


class TheRunnerMergeWriter(RepoCase):
    """sd:1131. `repo.runner_merge` had four readers and no caller that set it.

    Every registered repository therefore kept the schema default forever, and
    the only way to change one was to import the library and call
    `upsert_repo` by hand. These are the writer's four behaviours: it writes,
    it reports what it replaced, it refuses a value the CHECK would reject,
    and it refuses a path no row holds rather than making one.
    """

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def _value(self, path: str) -> str:
        return self.connection.execute(
            "SELECT runner_merge FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_it_sets_the_column_and_names_what_it_replaced(self):
        path = self._registered()
        self.assertEqual(self._value(path), "manual")
        self.assertEqual(set_runner_merge(self.connection, path, "auto"), (path, "manual"))
        self.assertEqual(self._value(path), "auto")
        self.assertEqual(set_runner_merge(self.connection, path, "manual"), (path, "auto"))
        self.assertEqual(self._value(path), "manual")

    def test_it_changes_no_other_field_on_the_row(self):
        path = self._registered()
        before = dict(self.connection.execute(
            "SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_runner_merge(self.connection, path, "auto")
        after = dict(self.connection.execute(
            "SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        moved = {key for key in before if before[key] != after[key]}
        self.assertEqual(moved - {"updated_at"}, {"runner_merge"})

    def test_a_value_the_check_would_reject_is_refused_in_a_sentence(self):
        path = self._registered()
        with self.assertRaises(RepoRefusal) as caught:
            set_runner_merge(self.connection, path, "automatic")
        self.assertIn("manual or auto", str(caught.exception))
        self.assertEqual(self._value(path), "manual")

    def test_an_unregistered_path_is_refused_rather_than_registered(self):
        checkout = support.repository(self.checkouts / "two")
        with self.assertRaises(RepoRefusal) as caught:
            set_runner_merge(self.connection, checkout, "auto")
        self.assertIn("not a registered repository", str(caught.exception))
        self.assertEqual(registered(self.connection), [])


class TheCiWriter(RepoCase):
    """sd:1843. `repo.ci` says whether a repository's checks run in GitHub
    Actions or as a local `sd-check`.

    The writer mirrors `set_runner_merge`; the reader answers `github` for a
    path the table does not hold, so a caller never treats an unregistered
    repository as switched to local checks.
    """

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def test_the_modes_are_the_two_the_check_lists_default_first(self):
        self.assertEqual(CI_MODES, ("github", "local"))

    def test_it_sets_the_column_names_what_it_replaced_and_reads_back(self):
        path = self._registered()
        self.assertEqual(repo_ci(self.connection, path), "github")
        self.assertEqual(set_ci(self.connection, path, "local"), (path, "github"))
        self.assertEqual(repo_ci(self.connection, path), "local")
        self.assertEqual(set_ci(self.connection, path, "github"), (path, "local"))
        self.assertEqual(repo_ci(self.connection, path), "github")

    def test_the_reader_resolves_an_absolute_checkout_path_to_its_row(self):
        checkout = support.repository(self.checkouts / "one")
        path = add(self.connection, checkout, home=self.home)
        set_ci(self.connection, path, "local")
        self.assertEqual(repo_ci(self.connection, checkout), "local")

    def test_it_changes_no_other_field_on_the_row(self):
        path = self._registered()
        before = dict(self.connection.execute(
            "SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_ci(self.connection, path, "local")
        after = dict(self.connection.execute(
            "SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        moved = {key for key in before if before[key] != after[key]}
        self.assertEqual(moved - {"updated_at"}, {"ci"})

    def test_a_value_the_check_would_reject_is_refused_in_a_sentence(self):
        path = self._registered()
        for value in ("actions", "GitHub", ""):
            with self.subTest(value=value), self.assertRaises(RepoRefusal) as caught:
                set_ci(self.connection, path, value)
            self.assertIn("github or local", str(caught.exception))
        self.assertEqual(repo_ci(self.connection, path), "github")

    def test_an_unregistered_path_is_refused_rather_than_registered(self):
        checkout = support.repository(self.checkouts / "two")
        with self.assertRaises(RepoRefusal) as caught:
            set_ci(self.connection, checkout, "local")
        self.assertIn("not a registered repository", str(caught.exception))
        self.assertEqual(registered(self.connection), [])

    def test_the_reader_answers_github_for_an_unregistered_path(self):
        checkout = support.repository(self.checkouts / "two")
        self.assertEqual(repo_ci(self.connection, checkout), "github")
        self.assertEqual(registered(self.connection), [])


class TheLaneHostWriter(RepoCase):
    """sd:3075. `set_lane_host` is the one writer of `repo.lane_host`: a
    host name, or `hub`, stored as NULL. It moves no other field.

    The class the review named: a lane move can overlap a ship holder on the
    old host. The move holds that host's ship flock, so this machine,
    `hub-mac`, moves only a lane it hosts.
    """

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch("sd_db.ship.this_host", return_value="hub-mac"))

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def _stored(self, path: str):
        return self.connection.execute("SELECT lane_host FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_a_host_is_stored_and_hub_stores_null_each_answering_the_value_before(self):
        path = self._registered()
        self.assertIsNone(self._stored(path))
        self.assertEqual(set_lane_host(self.connection, path, "hub-mac"), (path, "hub"))
        self.assertEqual(self._stored(path), "hub-mac")
        self.assertEqual(set_lane_host(self.connection, path, "hub"), (path, "hub-mac"))
        self.assertIsNone(self._stored(path))
        self.assertEqual(set_lane_host(self.connection, path, "build-2"), (path, "hub"))
        self.assertEqual(self._stored(path), "build-2")

    def test_it_changes_no_other_field_on_the_row(self):
        path = self._registered()
        before = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_lane_host(self.connection, path, "build-2")
        after = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        self.assertEqual({key for key in before if before[key] != after[key]} - {"updated_at"}, {"lane_host"})

    def test_a_bad_name_and_an_unregistered_path_are_refused(self):
        path = self._registered()
        for value in ("Build_2", "build.example.test", "", "build 2"):
            with self.subTest(value=value), self.assertRaises(RepoRefusal) as caught:
                set_lane_host(self.connection, path, value)
            self.assertIn("not a lane host", str(caught.exception))
        self.assertIsNone(self._stored(path))
        with self.assertRaises(RepoRefusal) as caught:
            set_lane_host(self.connection, support.repository(self.checkouts / "two"), "build-2")
        self.assertIn("not a registered repository", str(caught.exception))

    def _clones(self, *remotes: str) -> list[str]:
        made = []
        for index, remote in enumerate(remotes):
            path = add(self.connection, support.repository(self.checkouts / f"clone-{index}"), home=self.home)
            self.connection.execute("UPDATE repo SET remote = ? WHERE path = ?", (remote, path))
            made.append(path)
        return made

    def test_every_clone_of_the_remote_moves_and_no_other_repository(self):
        # Round 1: the lane belongs to the remote. Clones that disagree only between NULL and this machine unify.
        first, second, other = self._clones("git@github.com:example/one.git",
                                            "https://github.com/Example/One", "git@github.com:example/two.git")
        self.connection.execute("UPDATE repo SET lane_host = 'hub-mac' WHERE path = ?", (second,))
        self.assertEqual(set_lane_host(self.connection, first, "build-2"), (first, "hub"))
        self.assertEqual([self._stored(path) for path in (first, second, other)], ["build-2", "build-2", None])

    def test_a_lane_on_another_machine_refuses_the_move_and_takes_no_lock(self):
        # Its ship lock lives on that machine; part 1 cannot take it (sd:3003 part 2).
        first, second = self._clones("git@github.com:example/one.git", "git@github.com:example/one.git")
        self.connection.execute("UPDATE repo SET lane_host = 'build-2' WHERE path = ?", (second,))
        for value in ("hub", "build-3"):
            with self.subTest(value=value), self.assertRaises(RepoRefusal) as caught:
                set_lane_host(self.connection, first, value)
            self.assertIn("run the move on build-2 (sd:3003 part 2)", str(caught.exception))
        self.assertEqual([self._stored(first), self._stored(second)], [None, "build-2"])
        self.assertFalse((self.root / "ship-locks").exists())

    def test_a_ship_holding_the_lock_refuses_the_move_naming_it_whatever_the_case(self):
        # A hand-run sd-ship and a runner merge both hold this flock while they run.
        (path,) = self._clones("https://github.com/Example/One")
        child = subprocess.Popen([sys.executable, "-c", HOLDER, str(self.root / "sd.db"), "example/one"],
                                 stdout=subprocess.PIPE, text=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.addCleanup(child.stdout.close)
        self.assertEqual(child.stdout.readline().strip(), "held")
        with self.assertRaises(SdDbError) as caught:
            set_lane_host(self.connection, path, "build-2")
        self.assertIn("another ship operation owns this repository", str(caught.exception))
        self.assertIn("sd-ship merge --item 41", str(caught.exception))
        self.assertIsNone(self._stored(path))

    def test_the_lock_is_held_from_before_the_read_until_after_the_commit(self):
        (path,) = self._clones("git@github.com:example/one.git")
        events = []
        real = ship.repository_flock

        @contextmanager
        def watched(*args, **kwargs):
            with real(*args, **kwargs):
                events.append("held")
                yield
            events.append("released")

        self.connection.set_trace_callback(lambda sql: events.append(sql.split()[0]) if sql.split()[0] in (
            "BEGIN", "COMMIT", "UPDATE") else None)
        with mock.patch.object(ship, "repository_flock", watched):
            set_lane_host(self.connection, path, "build-2")
        self.connection.set_trace_callback(None)
        self.assertEqual(events, ["BEGIN", "held", "UPDATE", "COMMIT", "released"])

    def test_a_move_inside_an_open_transaction_refuses(self):
        # Its commit would come after the flock is released.
        path = self._registered()
        self.connection.execute("BEGIN IMMEDIATE")
        self.addCleanup(lambda: self.connection.in_transaction and self.connection.execute("ROLLBACK"))
        with self.assertRaisesRegex(RepoRefusal, "outside a transaction"):
            set_lane_host(self.connection, path, "build-2")

    def test_a_stale_before_refuses_and_writes_nothing(self):
        path = self._registered()
        with self.assertRaises(StaleItem):
            set_lane_host(self.connection, path, "build-2", before="build-3")
        self.assertIsNone(self._stored(path))


class TheChannelsWriter(RepoCase):
    """sd:3462, design sd:3471. `set_channels` is the one writer of
    `repo.channels`, shaped like `set_runner_merge`: it writes the canonical
    text, answers what it replaced, refuses a value the validator refuses and
    a path no row holds, and moves no other field. `None` clears to NULL.
    `before` is compared inside the write transaction, NULL included.
    """

    VALUE = {"obsidian": {"folder": "Briefs/x"}, "notion": {"folder": "Example"}, "drive": {}}
    TEXT = '{"drive":{},"notion":{"folder":"Example"},"obsidian":{"folder":"Briefs/x"}}'

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def _stored(self, path: str):
        return self.connection.execute("SELECT channels FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_it_sets_reads_back_and_clears_each_answering_the_value_before(self):
        path = self._registered()
        self.assertIsNone(repo_channels(self.connection, path))
        self.assertEqual(set_channels(self.connection, path, self.VALUE), (path, "none"))
        self.assertEqual(self._stored(path), self.TEXT)
        self.assertEqual(repo_channels(self.connection, path), self.VALUE)
        self.assertEqual(set_channels(self.connection, path, {"drive": {}}), (path, self.TEXT))
        self.assertEqual(set_channels(self.connection, path, None), (path, '{"drive":{}}'))
        self.assertIsNone(self._stored(path))
        self.assertIsNone(repo_channels(self.connection, path))

    def test_it_changes_no_other_field_on_the_row(self):
        path = self._registered()
        before = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_channels(self.connection, path, self.VALUE)
        after = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        self.assertEqual({key for key in before if before[key] != after[key]} - {"updated_at"}, {"channels"})

    def test_each_refusal_leaves_the_row_unchanged(self):
        path = self._registered()
        set_channels(self.connection, path, {"drive": {}})
        for value, named in (({"slack": {}}, "slack"), ({"notion": {"folder": "A/B"}}, "notion"), ({}, "none"),
                             ({"drive": {"folder": "/abs"}}, "drive")):
            with self.subTest(value=value), self.assertRaises(ChannelRefusal) as caught:
                set_channels(self.connection, path, value)
            self.assertIn(named, str(caught.exception))
            self.assertEqual(self._stored(path), '{"drive":{}}')

    def test_an_unregistered_path_is_refused_rather_than_registered(self):
        checkout = support.repository(self.checkouts / "two")
        with self.assertRaises(RepoRefusal) as caught:
            set_channels(self.connection, checkout, {"drive": {}})
        self.assertIn("not a registered repository", str(caught.exception))
        self.assertEqual(registered(self.connection), [])

    def test_a_set_keeps_the_half_it_does_not_name(self):
        """sd:3980 self-review: the dashboard form posts the outbound channels
        alone, and `feed=URL` names the feed alone. Each keeps the stored
        other half, so neither deletes what it never showed; `None` clears
        both."""
        path = self._registered()
        feed = {"url": "https://example.test/feed.xml"}
        set_channels(self.connection, path, {"feed": feed, "obsidian": {}})
        stored = self._stored(path)
        set_channels(self.connection, path, {"obsidian": {"folder": "Briefs/changed"}}, before=stored)
        self.assertEqual(self._stored(path), '{"feed":{"url":"https://example.test/feed.xml"},'
                                             '"obsidian":{"folder":"Briefs/changed"}}')
        set_channels(self.connection, path, {"feed": {"url": "https://example.test/other.xml"}})
        self.assertEqual(self._stored(path), '{"feed":{"url":"https://example.test/other.xml"},'
                                             '"obsidian":{"folder":"Briefs/changed"}}')
        set_channels(self.connection, path, None)
        self.assertIsNone(self._stored(path))

    def test_issue_sources_map_each_tracker_to_its_shadow_repo_and_keep_the_other_inbound_keys(self):
        """sd:3461: `jira` and `github` are inbound like `feed`, so a set of
        the outbound channels keeps them, and `issue_sources` answers the
        shadow `repo` value each tracker's rows carry."""
        path = self._registered()
        self.assertEqual(issue_sources(self.connection, path), {})
        set_channels(self.connection, path, {"jira": {"project": "EXAMPLE"}, "github": {"repo": "example/project"},
                                             "feed": {"url": "https://example.test/feed.xml"}})
        set_channels(self.connection, path, {"drive": {}})
        self.assertEqual(issue_sources(self.connection, path), {"jira": "EXAMPLE", "github": "example/project"})
        self.assertEqual(self._stored(path), '{"drive":{},"feed":{"url":"https://example.test/feed.xml"},'
                                             '"github":{"repo":"example/project"},"jira":{"project":"EXAMPLE"}}')

    def test_mine_issues_reads_the_open_assigned_and_filed_issues_of_each_repo_s_sources(self):
        """sd:4636: Today and Tasks show a repository's issues that are the
        operator's. A watched row, a row of unknown reason (synced before
        migration 34), a closed one, a pull request, and a row from another
        repository or tracker stay out; GitHub's `owner/name` matches in any case."""
        path = self._registered()
        self.assertEqual(mine_issues(self.connection), {})
        set_channels(self.connection, path, {"jira": {"project": "EXAMPLE"}, "github": {"repo": "example/project"}})
        rows = [("github", "Example/Project", "https://github.com/example/project/issues/1", "issue", "open", "assigned"),
                ("github", "example/project", "https://github.com/example/project/issues/2", "issue", "open", "filed"),
                ("github", "example/project", "https://github.com/example/project/issues/3", "issue", "open", "watched"),
                ("github", "example/project", "https://github.com/example/project/issues/4", "issue", "open", None),
                ("github", "example/project", "https://github.com/example/project/issues/5", "issue", "closed",
                 "assigned"),
                ("github", "example/project", "https://github.com/example/project/pull/6", "pull", "open", "filed"),
                ("github", "example/other", "https://github.com/example/other/issues/7", "issue", "open", "assigned"),
                ("jira", "EXAMPLE", "https://example.test/browse/EXAMPLE-8", "issue", "open", "filed"),
                ("jira", "example/project", "https://example.test/browse/EXAMPLE-9", "issue", "open", "assigned"),
                ("github", "EXAMPLE", "https://github.com/example/project/issues/10", "issue", "open", "assigned")]
        for number, (tracker, repo, url, kind, state, reason) in enumerate(rows, start=1):
            self.connection.execute(
                "INSERT INTO shadow (tracker, repo, url, number, kind, title, state, reason, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 't1', ?)",
                (tracker, repo, url, number, kind, f"issue {number}", state, reason, f"t{number:02d}"))
        found = mine_issues(self.connection)
        self.assertEqual(list(found), [path])
        self.assertEqual([(row["tracker"], row["number"], row["reason"]) for row in found[path]],
                         [("jira", 8, "filed"), ("github", 2, "filed"), ("github", 1, "assigned")])
        self.assertEqual(set(found[path][0]), {"tracker", "url", "number", "title", "state", "reason", "last_seen"})

    def test_mail_aliases_read_the_labels_and_ride_along_with_every_other_set(self):
        """sd:4191: `email` is inbound like `feed`, so a set of the outbound
        channels or of another source keeps it, and `mail_aliases` answers
        the labels, `[]` for none."""
        path = self._registered()
        self.assertEqual(mail_aliases(self.connection, path), [])
        set_channels(self.connection, path, {"email": {"aliases": ["committee", "board"]}})
        self.assertEqual(mail_aliases(self.connection, path), ["board", "committee"])
        set_channels(self.connection, path, {"drive": {}})
        set_channels(self.connection, path, {"jira": {"project": "EXAMPLE"}})
        self.assertEqual(self._stored(path), '{"drive":{},"email":{"aliases":["board","committee"]},'
                                             '"jira":{"project":"EXAMPLE"}}')
        self.assertEqual(mail_aliases(self.connection, path), ["board", "committee"])

    def test_mail_aliases_raise_on_what_the_setting_reader_cannot_read(self):
        """Unknown is not none: a stored value the validator refuses and an
        open restore raise, as `issue_sources` does; never `[]`."""
        path = self._registered()
        self.connection.execute(
            "UPDATE repo SET channels = '{\"email\": {\"aliases\": [\"a@example.test\"]}}' WHERE path = ?",
            (path,))
        with self.assertRaises(ChannelRefusal):
            mail_aliases(self.connection, path)
        set_channels(self.connection, path, None)
        set_channels(self.connection, path, {"email": {"aliases": ["board"]}})
        self.connection.execute(
            "INSERT INTO state (kind, key, timestamp, body) VALUES ('restore', '2026-10-14', 't', '{}')")
        with self.assertRaises(ChannelRefusal):
            mail_aliases(self.connection, path)

    INBOUND = {"feed": {"url": "https://example.test/feed.xml"}, "jira": {"project": "EXAMPLE"},
               "github": {"repo": "example/project"}, "email": {"aliases": ["board"]}}
    CHANGED = {"feed": {"url": "https://example.test/other.xml"}, "jira": {"project": "OTHER"},
               "github": {"repo": "example/other"}, "email": {"aliases": ["committee"]}}

    def test_a_set_of_one_inbound_key_keeps_the_other_inbound_keys_and_the_channels(self):
        """sd:3461 lane review: each inbound source is set on its own, so
        `feed=URL` never deletes Jira or GitHub, and `jira=KEY` never deletes
        the feed or GitHub. Each omitted inbound key keeps its stored value."""
        path = self._registered()
        for key in self.INBOUND:
            with self.subTest(key=key):
                set_channels(self.connection, path, {**self.INBOUND, "obsidian": {}})
                set_channels(self.connection, path, {key: self.CHANGED[key]})
                self.assertEqual(json.loads(self._stored(path)),
                                 {**self.INBOUND, key: self.CHANGED[key], "obsidian": {}})
                set_channels(self.connection, path, None)
                self.assertIsNone(self._stored(path))

    def test_a_set_of_the_channels_still_replaces_the_channels_and_keeps_every_inbound_key(self):
        """Outbound keys stay one replacement: a channel left out is off."""
        path = self._registered()
        set_channels(self.connection, path, {**self.INBOUND, "obsidian": {}, "drive": {}})
        set_channels(self.connection, path, {"notion": {"folder": "Example"}})
        self.assertEqual(json.loads(self._stored(path)), {**self.INBOUND, "notion": {"folder": "Example"}})

    def test_a_managed_repo_takes_no_github_source_and_reads_none_after_a_later_flip(self):
        """Managed repositories use no GitHub issues (sd:3461). A set naming
        `github` on one refuses and writes nothing; a source set before
        `repo managed PATH yes` reads as none, and still rides along when the
        dashboard sets the outbound channels, so that form keeps working."""
        path = self._registered()
        set_managed(self.connection, path, "yes")
        with self.assertRaises(RepoRefusal) as caught:
            set_channels(self.connection, path, {"github": {"repo": "example/project"}, "drive": {}})
        self.assertIn("managed", str(caught.exception))
        self.assertIsNone(self._stored(path))
        set_managed(self.connection, path, "no")
        set_channels(self.connection, path, {"github": {"repo": "example/project"}, "jira": {"project": "EXAMPLE"}})
        set_managed(self.connection, path, "yes")
        self.assertEqual(issue_sources(self.connection, path), {"jira": "EXAMPLE"})
        set_channels(self.connection, path, {"drive": {}})
        self.assertIn('"github":{"repo":"example/project"}', self._stored(path))

    def test_a_stale_before_refuses_and_writes_nothing_null_included(self):
        """Two forms both opened on a NULL row cannot both write."""
        path = self._registered()
        self.assertEqual(set_channels(self.connection, path, {"drive": {}}, before="none"), (path, "none"))
        with self.assertRaises(StaleItem) as caught:
            set_channels(self.connection, path, {"notion": {}}, before="none")
        self.assertIn('{"drive":{}}', str(caught.exception))
        self.assertEqual(self._stored(path), '{"drive":{}}')
        set_channels(self.connection, path, None)
        with self.assertRaises(StaleItem):
            set_channels(self.connection, path, {"notion": {}}, before='{"drive":{}}')
        self.assertIsNone(self._stored(path))

    def test_a_before_in_another_spelling_of_the_same_value_matches(self):
        path = self._registered()
        set_channels(self.connection, path, self.VALUE)
        spelled = '{"obsidian": {"folder": "Briefs/x"}, "notion": {"folder": "Example"}, "drive": {}}'
        self.assertEqual(set_channels(self.connection, path, None, before=spelled), (path, self.TEXT))

    def test_a_stored_value_the_validator_refuses_can_be_replaced(self):
        path = self._registered()
        self.connection.execute("UPDATE repo SET channels = '{\"slack\": {}}' WHERE path = ?", (path,))
        self.assertEqual(set_channels(self.connection, path, {"drive": {}}, before='{"slack":{}}'),
                         (path, '{"slack":{}}'))
        self.assertEqual(self._stored(path), '{"drive":{}}')

    def test_a_set_with_no_before_refuses_over_a_stored_value_it_cannot_read(self):
        """sd:4191 self-review: a stored value this build refuses may hold a
        key a newer build wrote. A set that never read it would replace it
        whole and lose the keys it does not name, so it refuses and writes
        nothing; `none` clears, and a set naming the value as `before` replaces."""
        path = self._registered()
        newer = '{"jira":{"project":"EXAMPLE"},"obsidian":{"folder":"Notes"},"slack":{}}'
        self.connection.execute("UPDATE repo SET channels = ? WHERE path = ?", (newer, path))
        with self.assertRaises(ChannelRefusal) as caught:
            set_channels(self.connection, path, {"drive": {}})
        self.assertIn("slack", str(caught.exception))
        self.assertIn("none", str(caught.exception))
        self.assertEqual(self._stored(path), newer)
        self.assertEqual(set_channels(self.connection, path, {"drive": {}}, before=newer), (path, newer))
        self.assertEqual(self._stored(path), '{"drive":{}}')

    def test_it_writes_while_a_restore_is_open(self):
        """Failure table, row "restore": the operator sets each repository's
        setting again before resolving the restore, so the writer does not refuse."""
        path = self._registered()
        self.connection.execute(
            "INSERT INTO state (kind, key, timestamp, body) VALUES ('restore', '2026-10-13', 't', '{}')")
        set_channels(self.connection, path, {"drive": {}})
        self.assertEqual(self._stored(path), '{"drive":{}}')


class TheChannelsVerb(RepoCase):
    """`sd-db repo channels PATH [obsidian=.. notion=.. drive=.. | none]`.

    No setting word prints the value, `none` clears it, and `channel=folder`
    words set it, `channel=` meaning the default folder. A read that fails
    exits 1 with the cause and never prints `none`.
    """

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def _run(self, *argv: str, database: Path | None = None) -> tuple[int, str, str]:
        import contextlib
        import io

        from sd_db.jobs import cli
        out, err = io.StringIO(), io.StringIO()
        target = database or self.root / "sd.db"
        with mock.patch.object(cli, "_open_for_write", lambda: connect(target)), \
                mock.patch.object(cli, "_home", lambda: self.home), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["repo", "channels", *argv])
        return rc, out.getvalue(), err.getvalue()

    def _stored(self, path: str):
        return self.connection.execute("SELECT channels FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_print_set_print_and_clear(self):
        path = self._registered()
        self.assertEqual(self._run(path), (0, "none\n", ""))
        rc, out, _ = self._run(path, "notion=Example", "drive=Research/Example")
        self.assertEqual(rc, 0)
        text = '{"drive":{"folder":"Research/Example"},"notion":{"folder":"Example"}}'
        self.assertIn(f"{path} channels none -> {text}", out)
        self.assertEqual(self._run(path), (0, f"{text}\n", ""))
        rc, out, _ = self._run(path, "obsidian=", "drive=")
        self.assertIn(f"channels {text} -> " + '{"drive":{},"obsidian":{}}', out)
        rc, out, _ = self._run(path, "none")
        self.assertEqual(rc, 0)
        self.assertIn('channels {"drive":{},"obsidian":{}} -> none', out)
        self.assertIsNone(self._stored(path))

    def test_a_feed_word_sets_the_repos_subscription(self):
        """sd:3980: `feed=URL` is the inbound subscription; a URL keeps its
        own `=` signs, and `feed=` with no URL refuses."""
        path = self._registered()
        rc, out, err = self._run(path, "feed=https://example.test/feed?a=b", "obsidian=")
        self.assertEqual(rc, 0, err)
        text = '{"feed":{"url":"https://example.test/feed?a=b"},"obsidian":{}}'
        self.assertEqual(self._stored(path), text)
        self.assertEqual(self._run(path), (0, f"{text}\n", ""))
        rc, out, err = self._run(path, "drive=")
        kept = '{"drive":{},"feed":{"url":"https://example.test/feed?a=b"}}'
        self.assertIn(f"channels {text} -> {kept}", out)
        text = kept
        rc, out, err = self._run(path, "feed=")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("feed", err)
        self.assertEqual(self._stored(path), text)

    def test_jira_and_github_words_set_the_issue_sources(self):
        """sd:3461: `jira=KEY github=owner/name`; an empty one refuses."""
        path = self._registered()
        rc, out, err = self._run(path, "jira=EXAMPLE", "github=example/project")
        self.assertEqual(rc, 0, err)
        text = '{"github":{"repo":"example/project"},"jira":{"project":"EXAMPLE"}}'
        self.assertIn(f"channels none -> {text}", out)
        for word in ("jira=", "github="):
            rc, out, err = self._run(path, word)
            self.assertEqual((rc, out), (1, ""))
            self.assertIn(word[:-1], err)
        self.assertEqual(self._stored(path), text)

    def test_an_email_word_sets_the_mail_alias_labels(self):
        """sd:4191: `email=board,committee` names the labels; `email=` and an
        address refuse naming `email` and change nothing."""
        path = self._registered()
        rc, out, err = self._run(path, "email=committee,board")
        self.assertEqual(rc, 0, err)
        text = '{"email":{"aliases":["board","committee"]}}'
        self.assertIn(f"channels none -> {text}", out)
        for word in ("email=", "email=a@example.test", "email=board,,committee", "email=board,board"):
            with self.subTest(word=word):
                rc, out, err = self._run(path, word)
                self.assertEqual((rc, out), (1, ""))
                self.assertIn("email", err)
                self.assertEqual(self._stored(path), text)

    def test_one_inbound_word_keeps_the_other_sources_and_prints_what_is_stored(self):
        """sd:3461 lane review: `feed=URL`, `jira=KEY` and `github=owner/name`
        each change one source; the others and the channels stay, and the
        verb prints them in `after`. `none` still clears all of it."""
        path = self._registered()
        rc, out, err = self._run(path, "feed=https://example.test/feed.xml", "jira=EXAMPLE",
                                 "github=example/project", "obsidian=")
        self.assertEqual(rc, 0, err)
        for word, key, value in (("feed=https://example.test/other.xml", "feed", {"url": "https://example.test/other.xml"}),
                                 ("jira=OTHER", "jira", {"project": "OTHER"}),
                                 ("github=example/other", "github", {"repo": "example/other"})):
            with self.subTest(word=word):
                before = json.loads(self._stored(path))
                rc, out, err = self._run(path, word)
                self.assertEqual(rc, 0, err)
                after = {**before, key: value}
                self.assertEqual(json.loads(self._stored(path)), after)
                self.assertIn(" -> " + json.dumps(after, sort_keys=True, separators=(",", ":")), out)
        rc, out, _ = self._run(path, "none")
        self.assertEqual(rc, 0)
        self.assertIsNone(self._stored(path))

    def test_a_change_names_the_render_that_publishes_it(self):
        """Failure table, row "set: the change takes effect"."""
        path = self._registered()
        for words in (["drive="], ["none"]):
            with self.subTest(words=words):
                rc, out, _ = self._run(path, *words)
                self.assertEqual(rc, 0)
                self.assertIn("sd-research-kit render", out)
                self.assertIn("next commit", out)

    def test_a_refused_value_names_the_channel_and_changes_nothing(self):
        path = self._registered()
        self._run(path, "drive=")
        for words, named in ((["notion=A/B"], "notion"), (["slack=x"], "slack"), (["obsidian=/abs"], "obsidian"),
                             (["drive"], "drive"), (["drive=", "drive=x"], "drive"), (["none", "drive="], "none"),
                             (["--force"], "--force")):
            with self.subTest(words=words):
                rc, out, err = self._run(path, *words)
                self.assertEqual(rc, 1, out + err)
                self.assertIn(named, err)
                self.assertEqual(out, "")
                self.assertEqual(self._stored(path), '{"drive":{}}')

    def test_a_read_during_an_open_restore_exits_1_and_a_write_still_works(self):
        """Review of b96428745: a drain reads the setting through this verb, so
        an open restore, whose row may be older than the operator's last edit,
        holds the read as it holds the render, and never prints a value.
        Setting it again is the restore's recovery, so a write still works."""
        path = self._registered()
        self._run(path, "drive=")
        self.connection.execute(
            "INSERT INTO state (kind, key, timestamp, body) VALUES ('restore', '2026-10-13', 't', '{}')")
        rc, out, err = self._run(path)
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("a restore is unresolved", err)
        self.assertEqual(self._run(path, "notion=")[0], 0)
        self.assertEqual(self._stored(path), '{"notion":{}}')

    def test_an_unregistered_path_refuses_a_write_and_prints_none_for_a_read(self):
        """No row is no setting, so a read answers `none` and says why on stderr."""
        checkout = support.repository(self.checkouts / "two")
        rc, out, err = self._run(str(checkout), "drive=")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("not a registered repository", err)
        self.assertEqual(registered(self.connection), [])
        rc, out, err = self._run(str(checkout))
        self.assertEqual((rc, out), (0, "none\n"))
        self.assertIn("not a registered repository", err)

    def test_a_stored_value_the_validator_refuses_exits_1_and_prints_no_none(self):
        """Failure table, row "drain: read the setting"."""
        path = self._registered()
        self.connection.execute("UPDATE repo SET channels = '{\"slack\": {}}' WHERE path = ?", (path,))
        rc, out, err = self._run(path)
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("slack", err)
        self.assertNotIn("none", out + err)

    def test_a_database_at_twenty_eight_exits_1_and_prints_no_none(self):
        """Failure table, row "drain: read the setting": the column is missing."""
        path = self._registered()
        old = self.root / "old.db"
        through = [m for m in migrations() if m[0] <= 28]
        with mock.patch("sd_db.migrate.migrations", return_value=through):
            migrate(old)
        raw = sqlite3.connect(old)
        raw.execute("INSERT INTO repo (path, created_at, updated_at) VALUES (?, 't', 't')", (path,))
        raw.commit()
        raw.close()
        rc, out, err = self._run(path, database=old)
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("schema version 28", err)
        self.assertNotIn("none", out)


class TheClonesWriter(RepoCase):
    """sd:4043. `repo.clone_profiles`: the machine kinds `repo-sync` clones a
    repository on, one spelling per set (design sd:3983)."""

    def _registered(self) -> str:
        checkout = support.repository(self.checkouts / "one")
        return add(self.connection, checkout, home=self.home)

    def _value(self, path: str):
        return self.connection.execute("SELECT clone_profiles FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_a_set_none_plus_and_minus_each_write_the_one_spelling(self):
        path = self._registered()
        for words, before, after in (("work,personal", "none", "personal,work"), ("+terra", "personal,work",
                                     "personal,work,terra"), ("-work", "personal,work,terra", "personal,terra"),
                                     ("+terra", "personal,terra", "personal,terra"), ("none", "personal,terra",
                                     "none"), ("-work", "none", "none"), ("work", "none", "work")):
            with self.subTest(words=words):
                self.assertEqual(set_clones(self.connection, path, words), (path, before, after))
        self.assertEqual(self._value(path), "work")

    def test_a_word_outside_the_profiles_is_refused_in_a_sentence_and_writes_nothing(self):
        path = self._registered()
        set_clones(self.connection, path, "personal")
        for words in ("laptop", "personal,personal", "", "+laptop", "+", "personal,", "none,work"):
            with self.subTest(words=words), self.assertRaises(RepoRefusal) as caught:
                set_clones(self.connection, path, words)
            self.assertIn("personal, work, terra", str(caught.exception))
        self.assertEqual(self._value(path), "personal")

    def test_it_changes_no_other_field_and_refuses_an_unregistered_path(self):
        path = self._registered()
        before = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_clones(self.connection, path, "+work")
        after = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        self.assertEqual({key for key in before if before[key] != after[key]} - {"updated_at"}, {"clone_profiles"})
        checkout = support.repository(self.checkouts / "two")
        with self.assertRaises(RepoRefusal) as caught:
            set_clones(self.connection, checkout, "work")
        self.assertIn("not a registered repository", str(caught.exception))
        self.assertEqual(len(registered(self.connection)), 1)

    def test_two_writers_on_one_row_both_land(self):
        """Failure table, row "`repo clones PATH -P` beside a dashboard write".

        Each writer reads, waits, then writes. Without one transaction around
        the read and the write, the second write is computed from the first
        read and drops the first writer's profile.
        """
        import threading

        from sd_db import repos

        path = self._registered()
        set_clones(self.connection, path, "personal")
        real = repos.clone_profiles

        def slow(words, held):
            value = real(words, held)
            time.sleep(0.3)
            return value

        errors = []

        def write(words):
            connection = connect(self.root / "sd.db")
            try:
                set_clones(connection, path, words)
            except Exception as error:  # noqa: BLE001 - reported below
                errors.append(error)
            finally:
                connection.close()

        with mock.patch("sd_db.repos.clone_profiles", slow):
            threads = [threading.Thread(target=write, args=(words,)) for words in ("+work", "+terra")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(self._value(path), "personal,work,terra")


class TheDependabotWriter(RepoCase):
    """sd:4043. `repo.dependabot`: the sweep's list outside its owner rule (design sd:3984)."""

    def test_it_sets_the_flag_names_what_it_replaced_and_refuses_in_a_sentence(self):
        checkout = support.repository(self.checkouts / "one")
        path = add(self.connection, checkout, home=self.home)
        self.assertEqual(set_dependabot(self.connection, path, "yes"), (path, "no"))
        self.assertEqual(set_dependabot(self.connection, path, "yes"), (path, "yes"))
        for value in ("true", "1", ""):
            with self.subTest(value=value), self.assertRaises(RepoRefusal) as caught:
                set_dependabot(self.connection, path, value)
            self.assertIn("yes or no", str(caught.exception))
        self.assertEqual(self.connection.execute("SELECT dependabot FROM repo").fetchone()[0], 1)
        self.assertEqual(set_dependabot(self.connection, path, "no"), (path, "yes"))
        with self.assertRaises(RepoRefusal):
            set_dependabot(self.connection, support.repository(self.checkouts / "two"), "yes")


class TheGithubIssuesSetting(RepoCase):
    """sd:4827. `repo.github_issues`: third-party GitHub issue intake, on or off per repo.

    The writer mirrors `set_runner_merge`; the reader answers False for no row,
    the column default, and raises on a store without the column rather than
    reading it as off.
    """

    def _registered(self) -> str:
        return add(self.connection, support.repository(self.checkouts / "one"), home=self.home)

    def _value(self, path: str) -> int:
        return self.connection.execute("SELECT github_issues FROM repo WHERE path = ?", (path,)).fetchone()[0]

    def test_it_sets_the_column_names_what_it_replaced_and_the_reader_follows(self):
        path = self._registered()
        self.assertEqual(self._value(path), 0)
        self.assertFalse(github_issues(self.connection, path))
        self.assertEqual(set_github_issues(self.connection, path, "on"), (path, "off"))
        self.assertEqual(self._value(path), 1)
        self.assertTrue(github_issues(self.connection, path))
        self.assertTrue(github_issues(self.connection, paths.expand(path)))
        self.assertEqual(set_github_issues(self.connection, path, "on"), (path, "on"))
        self.assertEqual(set_github_issues(self.connection, path, "off"), (path, "on"))
        self.assertFalse(github_issues(self.connection, path))

    def test_it_changes_no_other_field_on_the_row(self):
        path = self._registered()
        before = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        set_github_issues(self.connection, path, "on")
        after = dict(self.connection.execute("SELECT * FROM repo WHERE path = ?", (path,)).fetchone())
        self.assertEqual({key for key in before if before[key] != after[key]} - {"updated_at"}, {"github_issues"})

    def test_every_word_but_on_and_off_is_refused_and_writes_nothing(self):
        """Property over edge inputs: case, padding, other flag words, empty,
        control and non-ASCII text, and a seeded spread of random strings."""
        import random

        path = self._registered()
        set_github_issues(self.connection, path, "on")
        words = ["On", "ON", "oN", "Off", "OFF", " on", "on ", "on\n", "\ton", "yes", "no", "true", "false",
                 "1", "0", "", " ", "o", "onn", "of", "offf", "on,off", "auto", "manual", "\x00", "ón", "ｏｎ"]
        draw = random.Random(4827)
        alphabet = "onfON \t\n\x00-_,1é"
        words += ["".join(draw.choice(alphabet) for _ in range(draw.randrange(0, 6))) for _ in range(300)]
        for word in (word for word in words if word not in ("on", "off")):
            with self.subTest(word=word), self.assertRaises(RepoRefusal) as caught:
                set_github_issues(self.connection, path, word)
            self.assertIn("on or off", str(caught.exception))
        self.assertEqual(self._value(path), 1)

    def test_an_unregistered_path_is_refused_on_write_and_reads_off(self):
        self._registered()
        stranger = support.repository(self.checkouts / "two")
        for where in (stranger, self.checkouts / "absent", self.root):
            with self.subTest(where=where):
                with self.assertRaises(RepoRefusal) as caught:
                    set_github_issues(self.connection, where, "on")
                self.assertIn("not a registered repository", str(caught.exception))
                self.assertFalse(github_issues(self.connection, where))
        self.assertEqual(len(registered(self.connection)), 1)

    def test_a_store_before_35_raises_and_never_reads_as_off(self):
        """Older state: the new library over a store not yet migrated."""
        database = self.root / "old.db"
        with mock.patch("sd_db.migrate.migrations", return_value=[m for m in migrations() if m[0] < 35]):
            migrate(database)
        old = connect(database, write=False)
        self.addCleanup(old.close)
        with self.assertRaises(SchemaTooOld):
            github_issues(old, self.checkouts / "one")


class TheIntake(RepoCase):
    """sd:4880. A repository with `github_issues` on lists its open third-party
    issues that no sd item carries yet, for Today's intake (sd:4840)."""

    def _on(self, name: str, remote: str | None, *, on: bool = True) -> str:
        path = add(self.connection, support.repository(self.checkouts / name), home=self.home)
        upsert_repo(self.connection, path, remote=remote)
        set_github_issues(self.connection, path, "on" if on else "off")
        return path

    def _shadow(self, rows):
        for number, (tracker, repo, url, kind, state, reason) in enumerate(rows, start=1):
            self.connection.execute(
                "INSERT INTO shadow (tracker, repo, url, number, kind, title, state, author, reason, first_seen, "
                "last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, 'octocat', ?, 't1', ?)",
                (tracker, repo, url, number, kind, f"issue {number}", state, reason, f"t{number:02d}"))

    def _ref(self, ref: str) -> None:
        from sd_db.workflow import capture_task
        from sd_db.writes import set_item_fields

        item = capture_task(self.connection, title=f"mapped {ref}", who="test")["item"]["id"]
        set_item_fields(self.connection, item, source="task-ref", external_id=ref)

    def test_only_on_repositories_with_a_github_remote_are_intake_repositories(self):
        on = self._on("one", "git@github.com:Example/Project.git")
        self._on("two", "https://github.com/example/off", on=False)
        self._on("three", "https://example.test/example/elsewhere.git")
        self._on("four", None)
        self.assertEqual(intake_repos(self.connection), {on: "Example/Project"})

    def test_it_lists_open_third_party_issues_no_item_carries(self):
        """Filed (the operator's own), closed, pull, other repository, other
        tracker and mapped rows stay out; a watched, an assigned and an unknown
        row are third-party or may be. A ref for the same number in another
        repository maps nothing here; a ref matches in any letter case."""
        path = self._on("one", "https://github.com/example/project")
        self._on("two", "https://github.com/example/off", on=False)
        self.assertEqual(intake_issues(self.connection), {})
        base = "https://github.com/example/project"
        self._shadow([("github", "Example/Project", f"{base}/issues/1", "issue", "open", "watched"),
                      ("github", "example/project", f"{base}/issues/2", "issue", "open", "filed"),
                      ("github", "example/project", f"{base}/issues/3", "issue", "open", "assigned"),
                      ("github", "example/project", f"{base}/issues/4", "issue", "open", None),
                      ("github", "example/project", f"{base}/issues/5", "issue", "closed", "watched"),
                      ("github", "example/project", f"{base}/pull/6", "pull", "open", "watched"),
                      ("github", "example/off", "https://github.com/example/off/issues/7", "issue", "open", "watched"),
                      ("jira", "example/project", "https://example.test/browse/EXAMPLE-8", "issue", "open", None),
                      ("github", "example/project", f"{base}/issues/9", "issue", "open", "watched"),
                      ("github", "example/project", f"{base}/issues/10", "issue", "open", "watched")])
        self.connection.execute("UPDATE shadow SET author = 'operator' WHERE reason = 'filed'")
        self._ref("github:EXAMPLE/project#9")
        self._ref("github:example/other#10")
        found = intake_issues(self.connection)
        self.assertEqual(list(found), [path])
        self.assertEqual([row["number"] for row in found[path]], [10, 4, 3, 1])
        self.assertEqual(set(found[path][0]),
                         {"tracker", "repo", "url", "number", "title", "state", "reason", "author", "last_seen"})

    def test_an_issue_the_operator_opened_is_not_intake_whatever_its_reason(self):
        """`assigned` outranks `filed`, and a row only the sweep saw has no
        reason, so the reason cannot say who opened an issue. The author can:
        the operator's login is the author of every `filed` row."""
        path = self._on("one", "https://github.com/example/project")
        base = "https://github.com/example/project"
        self._shadow([("github", "example/project", f"{base}/issues/1", "issue", "open", "assigned"),
                      ("github", "example/project", f"{base}/issues/2", "issue", "open", None),
                      ("github", "example/project", f"{base}/issues/3", "issue", "open", None),
                      ("github", "example/elsewhere", "https://github.com/example/elsewhere/issues/4", "issue",
                       "closed", "filed")])
        self.connection.execute("UPDATE shadow SET author = 'Operator' WHERE number IN (1, 2)")
        self.connection.execute("UPDATE shadow SET author = 'operator' WHERE number = 4")
        self.assertEqual([row["number"] for row in intake_issues(self.connection)[path]], [3])
        self.connection.execute("UPDATE shadow SET author = NULL WHERE number = 3")
        self.assertEqual([row["number"] for row in intake_issues(self.connection)[path]], [3])

    def test_a_repository_switched_off_drops_out(self):
        path = self._on("one", "https://github.com/example/project")
        self._shadow([("github", "example/project", "https://github.com/example/project/issues/1", "issue",
                       "open", "watched")])
        self.assertEqual(list(intake_issues(self.connection)), [path])
        set_github_issues(self.connection, path, "off")
        self.assertEqual(intake_issues(self.connection), {})


class TheCloneLines(RepoCase):
    """sd:4043. `list --clones P` gives back `repo-sync`'s conf lines, whole or not at all."""

    def row(self, relative: str, remote: str | None, profiles: str | None) -> str:
        path = str(self.checkouts / relative)
        upsert_repo(self.connection, path, remote=remote)
        self.connection.execute("UPDATE repo SET clone_profiles = ? WHERE path = ?", (profiles, path))
        return path

    def test_each_row_on_the_profile_is_one_line_in_path_order(self):
        self.row("system", "git@github.com:platypeeps/system.git", "personal,work")
        self.row("ai/llama.cpp", "https://github.com/example-org/llama.cpp", "personal")
        self.row("platypeeps/pack", "ssh://git@github.com/platypeeps/pack", "work")
        self.row("other", "https://github.com/platypeeps/other", None)
        self.assertEqual(clone_lines(self.connection, "personal", root=self.checkouts),
                         ["ai example-org/llama.cpp", ". platypeeps/system"])
        self.assertEqual(clone_lines(self.connection, "work", root=self.checkouts),
                         ["platypeeps platypeeps/pack", ". platypeeps/system"])
        self.assertEqual(clone_lines(self.connection, "terra", root=self.checkouts), [])

    def test_a_row_that_is_not_a_conf_line_refuses_the_whole_list_naming_every_one(self):
        """Failure table, row "`list --clones P`: a row that is not a conf line"."""
        self.row("system", "git@github.com:platypeeps/system.git", "personal")
        bad = [self.row("a/b/deep", "https://github.com/platypeeps/deep", "personal"),
               self.row("local", "/srv/git/local.git", "personal"),
               self.row("none", None, "personal"),
               self.row("tools/renamed", "https://github.com/platypeeps/original", "personal")]
        outside = str(self.root / "elsewhere" / "x")
        upsert_repo(self.connection, outside, remote="https://github.com/platypeeps/x")
        self.connection.execute("UPDATE repo SET clone_profiles = 'personal' WHERE path = ?", (outside,))
        with self.assertRaises(RepoRefusal) as caught:
            clone_lines(self.connection, "personal", root=self.checkouts)
        for path in [*bad, outside]:
            self.assertIn(path, str(caught.exception))
        self.assertIn("5 row(s)", str(caught.exception))
        self.assertNotIn("/system ", str(caught.exception))

    def test_an_unknown_profile_is_refused(self):
        with self.assertRaises(RepoRefusal):
            clone_lines(self.connection, "laptop", root=self.checkouts)

    def test_a_database_before_the_columns_raises_and_never_answers_empty(self):
        old = self.root / "old.db"
        through = [m for m in migrations() if m[0] <= 32]
        with mock.patch("sd_db.migrate.migrations", return_value=through):
            migrate(old)
        raw = sqlite3.connect(old)
        self.addCleanup(raw.close)
        raw.row_factory = sqlite3.Row
        with self.assertRaises(SdDbError) as caught:
            clone_lines(raw, "personal", root=self.checkouts)
        self.assertIn("schema version 32", str(caught.exception))


class TheCloneSeed(RepoCase):
    """sd:4043. `seed --clones P` reads repo-sync's lists for P and only adds P to rows."""

    def setUp(self):
        super().setUp()
        self.config = self.root / "cfg"
        (self.config / "repo-sync").mkdir(parents=True)
        self.environ = {"SYSTEM_TOOLS_CONFIG": str(self.config), "REPO_SYNC_PROFILE": "personal"}
        for folder, origin in (("platypeeps/present", "https://github.com/platypeeps/present"),
                               ("platypeeps/listed", "git@github.com:platypeeps/listed.git"),
                               ("shared", "https://github.com/platypeeps/shared")):
            support.git(support.repository(self.checkouts / folder), "remote", "add", "origin", origin)
        # A row for a checkout this machine does not hold: another machine registered it.
        upsert_repo(self.connection, str((self.checkouts / "platypeeps" / "elsewhere").resolve()),
                    remote="https://github.com/platypeeps/elsewhere")
        self.listed = add(self.connection, self.checkouts / "platypeeps" / "listed",
                          remote="git@github.com:platypeeps/listed.git", home=self.home)
        self.connection.execute("UPDATE repo SET clone_profiles = 'terra' WHERE path = ?", (self.listed,))
        self.lists("repos.common.conf", ". platypeeps/shared\n")
        self.lists("repos.work.conf", "# work\nplatypeeps platypeeps/present\nplatypeeps platypeeps/listed\n"
                   "platypeeps platypeeps/elsewhere\nplatypeeps platypeeps/missing\n")
        self.lists("repos.personal.conf", "platypeeps platypeeps/listed\n")
        self.lists("repos.terra.conf", ". platypeeps/shared\n")

    def lists(self, name: str, text: str) -> None:
        (self.config / "repo-sync" / name).write_text(text, encoding="utf-8")

    def seed(self, profile: str = "work", connection=None):
        return seed_clones(connection or self.connection, profile, root=self.checkouts, environ=self.environ,
                           home=self.home)

    def state(self, connection=None):
        return sorted((Path(row["path"]).name, row["clone_profiles"]) for row in registered(connection or
                                                                                            self.connection))

    def test_it_registers_present_lines_adds_the_profile_and_names_the_line_it_cannot_place(self):
        result = self.seed()
        self.assertEqual(sorted(Path(path).name for path in result.registered), ["present", "shared"])
        self.assertEqual(sorted(Path(path).name for path in result.added), ["elsewhere", "listed", "present",
                                                                            "shared"])
        self.assertEqual(result.unplaced, ["platypeeps/missing"])
        # It only adds: the terra a row held stays beside work.
        self.assertEqual(self.state(), [("elsewhere", "work"), ("listed", "work,terra"), ("present", "work"),
                                        ("shared", "work")])

    def test_a_second_run_changes_nothing(self):
        self.seed()
        before = self.state()
        result = self.seed()
        self.assertEqual((result.registered, result.added, result.unplaced), ([], [], ["platypeeps/missing"]))
        self.assertEqual(len(result.held), 4)
        self.assertEqual(self.state(), before)

    def test_the_profile_is_the_argument_and_terra_reads_its_own_list_alone(self):
        """`REPO_SYNC_PROFILE` says personal here; the argument decides."""
        self.seed("terra")
        self.assertEqual(self.state(), [("elsewhere", None), ("listed", "terra"), ("shared", "terra")])

    def origin(self, folder: str, url: str | None) -> None:
        checkout = self.checkouts / "platypeeps" / folder
        support.git(checkout, "remote", "remove", "origin")
        if url is not None:
            support.git(checkout, "remote", "add", "origin", url)

    def test_a_line_whose_path_holds_another_repository_writes_nothing_and_names_both(self):
        """Failure table, rows "`seed --clones P`: the path holds another repository".

        The line names a repository; its path only says where `repo-sync` put
        it. A row's remote and a checkout's origin each name the repository
        at that path, and each must be the line's, or that line writes nothing.
        """
        self.connection.execute("UPDATE repo SET remote = 'https://github.com/new-owner/elsewhere' "
                                "WHERE path LIKE '%/elsewhere'")
        self.origin("present", "git@github.com:new-owner/present.git")
        self.origin("listed", "https://github.com/new-owner/listed")
        result = self.seed()
        self.assertEqual(len(result.mismatched), 3, result.mismatched)
        for slug, held in (("platypeeps/elsewhere", "https://github.com/new-owner/elsewhere"),
                           ("platypeeps/present", "git@github.com:new-owner/present.git"),
                           ("platypeeps/listed", "https://github.com/new-owner/listed")):
            named = next(line for line in result.mismatched if line.startswith(slug))
            self.assertIn(held, named)
        # The row the conf names by path keeps what it held; the new checkout gets no row; the line that agrees lands.
        self.assertEqual(self.state(), [("elsewhere", None), ("listed", "terra"), ("shared", "work")])
        self.assertEqual(result.unplaced, ["platypeeps/missing"])

    def test_a_checkout_with_no_origin_is_unknown_and_writes_nothing(self):
        """A probe that finds no origin cannot say which repository the path holds."""
        self.origin("present", None)
        result = self.seed()
        self.assertEqual([line.split(" ", 1)[0] for line in result.mismatched], ["platypeeps/present"])
        self.assertIn("no origin", result.mismatched[0])
        self.assertNotIn("present", [name for name, _ in self.state()])

    def test_an_agreeing_row_does_not_vouch_for_a_checkout_that_disagrees(self):
        """A plain `repo seed` can leave the conf's slug on a row; the checkout still decides."""
        self.origin("listed", "https://github.com/new-owner/listed")
        result = self.seed()
        self.assertEqual([line.split(" ", 1)[0] for line in result.mismatched], ["platypeeps/listed"])
        self.assertIn(("listed", "terra"), self.state())

    def test_a_run_stopped_at_any_line_is_finished_by_a_rerun(self):
        """Failure table, row "`seed --clones P`: stop after line k"."""
        from sd_db import repos

        def fresh(name):
            source, target = sqlite3.connect(self.root / "sd.db"), sqlite3.connect(self.root / name)
            source.backup(target)
            source.close()
            target.close()
            connection = connect(self.root / name)
            self.addCleanup(connection.close)
            return connection

        reference = fresh("clean.db")
        self.seed(connection=reference)
        real = repos.clone_profiles
        for stop in range(1, 5):
            with self.subTest(stop=stop):
                stopped = fresh(f"stopped-{stop}.db")
                calls: list[str] = []

                def failing(words, held, calls=calls, stop=stop):
                    calls.append(words)
                    if len(calls) == stop:
                        raise OSError("stopped")
                    return real(words, held)

                with mock.patch("sd_db.repos.clone_profiles", failing), self.assertRaises(OSError):
                    self.seed(connection=stopped)
                # Lines before `stop` stay committed; line `stop` left nothing, its new row included.
                # The placed lines in order: shared and present (no row yet), listed and elsewhere.
                held = [name for name, profiles in self.state(stopped) if profiles and "work" in profiles]
                self.assertEqual(len(held), stop - 1)
                self.assertEqual(len(self.state(stopped)), 2 + min(stop - 1, 2))
                self.seed(connection=stopped)
                self.assertEqual(self.state(stopped), self.state(reference))


class TheCloneVerbs(TheCloneSeed):
    """`sd-db repo clones`, `dependabot`, `list --clones` and `seed --clones`, as the operator types them."""

    def run_verb(self, *argv: str) -> tuple[int, str, str]:
        import contextlib
        import io

        from sd_db.jobs import cli
        out, err = io.StringIO(), io.StringIO()
        environ = {**self.environ, "SD_REPO_ROOT": str(self.checkouts)}
        with mock.patch.object(cli, "_open_for_write", lambda: connect(self.root / "sd.db")), \
                mock.patch.object(cli, "_home", lambda: self.home), mock.patch.dict(os.environ, environ), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["repo", *argv])
        return rc, out.getvalue(), err.getvalue()

    def test_seed_then_list_gives_the_lines_back_and_names_the_line_it_could_not_place(self):
        rc, out, err = self.run_verb("seed", "--clones", "work")
        self.assertEqual(rc, 1)
        self.assertIn("sd-db: work: registered 2, added to 4, already held by 0", out)
        self.assertIn("platypeeps/missing is not cloned here and has no row", err)
        rc, out, err = self.run_verb("list", "--clones", "work")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(out.splitlines(), ["platypeeps platypeeps/elsewhere", "platypeeps platypeeps/listed",
                                            "platypeeps platypeeps/present", ". platypeeps/shared"])
        self.lists("repos.work.conf", "platypeeps platypeeps/present\n")
        self.assertEqual(self.run_verb("seed", "--clones", "work")[0], 0)

    def test_both_seeds_exit_1_and_name_a_line_whose_path_holds_another_repository(self):
        support.git(self.checkouts / "platypeeps" / "listed", "remote", "set-url", "origin",
                    "https://github.com/new-owner/listed")
        for argv in (("seed", "--clones", "work"), ("seed",)):
            with self.subTest(argv=argv):
                rc, _, err = self.run_verb(*argv)
                self.assertEqual(rc, 1)
                self.assertIn("platypeeps/listed", err)
                self.assertIn("https://github.com/new-owner/listed", err)

    def test_a_row_that_is_not_a_line_exits_1_and_prints_nothing(self):
        self.run_verb("seed", "--clones", "work")
        self.connection.execute("UPDATE repo SET remote = '/srv/git/x.git' WHERE path = ?", (self.listed,))
        rc, out, err = self.run_verb("list", "--clones", "work")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn(self.listed, err)

    def test_clones_and_dependabot_print_before_and_after(self):
        rc, out, _ = self.run_verb("clones", self.listed, "+personal")
        self.assertEqual((rc, out), (0, f"sd-db: {self.listed} clone_profiles terra -> personal,terra\n"))
        rc, out, _ = self.run_verb("dependabot", self.listed, "yes")
        self.assertEqual((rc, out), (0, f"sd-db: {self.listed} dependabot no -> yes\n"))
        for argv in (("clones", self.listed), ("clones", self.listed, "laptop"), ("dependabot", self.listed),
                     ("dependabot", self.listed, "maybe"), ("list", "--clones"), ("list", "--clones", "laptop"),
                     ("seed", "--clones"), ("seed", "--clones", "work", "extra.conf")):
            with self.subTest(argv=argv):
                rc, out, err = self.run_verb(*argv)
                self.assertEqual((rc, out), (1, ""), err)
                self.assertTrue(err)

    def test_list_keeps_runner_merge_as_the_last_field(self):
        rc, out, _ = self.run_verb("list")
        self.assertEqual(rc, 0)
        for line in out.splitlines():
            self.assertTrue(line.endswith("  manual"), line)
