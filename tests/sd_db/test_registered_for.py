"""Which registered repository a checkout speaks for (`sd_db.repos`).

These cases pinned the resolver `work register` used. The verb is gone
(pack sd:7064); the resolver stays, since `sd_lib.registered_base` and the
runner resolve a clone or a worktree through it.
"""

import tempfile
import unittest
from pathlib import Path

from sd_db import connect, upsert_repo
from sd_db.migrate import initialise
from sd_db.repos import registered_for, remote_identity, same_remote


class RegisterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        path = self.root / "sd.db"
        initialise(path)
        self.db = connect(path)
        self.addCleanup(self.db.close)
        self.repo = "/Users/nobody/repos/system"
        upsert_repo(self.db, self.repo)


class WhichRepositoryACloneSpeaksFor(RegisterCase):
    """R10-D6 selects a repository by the working directory, not by its path.

    The runner clones a repository from its remote into a work path under
    `/Volumes/sd-work/worktrees/...` and runs there. Resolving by path alone
    refuses every run it makes -- and does so only after the command has been
    queued, dispatched and cloned, which is how it was found.
    """

    def setUp(self):
        super().setUp()
        upsert_repo(self.db, self.repo, remote="git@github.com:platypeeps/system.git")

    def test_a_registered_path_answers_for_itself(self):
        self.assertEqual(registered_for(self.db, self.repo, None), self.repo)

    def test_a_clone_resolves_to_the_repository_it_was_cloned_from(self):
        self.assertEqual(
            registered_for(self.db, "/Volumes/sd-work/worktrees/442/5-1-abc",
                           "git@github.com:platypeeps/system.git"),
            self.repo,
        )

    def test_a_clone_of_something_else_resolves_to_itself_and_is_refused_there(self):
        """Resolving to itself is what makes the caller's own refusal the message."""
        elsewhere = "/Volumes/sd-work/worktrees/9/1-def"
        self.assertEqual(
            registered_for(self.db, elsewhere, "git@github.com:platypeeps/other.git"),
            elsewhere,
        )

    def test_a_checkout_with_no_origin_resolves_to_itself(self):
        self.assertEqual(registered_for(self.db, "/tmp/loose", None), "/tmp/loose")

    def test_a_registered_path_wins_over_a_remote_match(self):
        """An ordinary checkout costs one indexed lookup and never scans."""
        upsert_repo(self.db, "/Users/nobody/repos/clone",
                    remote="git@github.com:platypeeps/system.git")
        self.assertEqual(
            registered_for(self.db, "/Users/nobody/repos/clone",
                           "git@github.com:platypeeps/system.git"),
            "/Users/nobody/repos/clone",
        )

    def test_an_origin_two_registered_paths_share_resolves_to_itself(self):
        """sd:1219 (941f61d80ffc, a09df0750b08): the first path in path order was a guess."""
        upsert_repo(self.db, "/srv/example.test/repos/clone",
                    remote="git@github.com:platypeeps/system.git")
        clone = "/Volumes/sd-work/worktrees/442/5-1-abc"
        self.assertEqual(registered_for(self.db, clone, "git@github.com:platypeeps/system.git"), clone)


class WhatCountsAsOneRemote(unittest.TestCase):
    def test_the_git_suffix_and_a_trailing_slash_are_not_differences(self):
        self.assertTrue(same_remote("git@github.com:platypeeps/system.git",
                                    "git@github.com:platypeeps/system"))
        self.assertTrue(same_remote("https://example.invalid/a/b/",
                                    "https://example.invalid/a/b"))

    def test_a_different_repository_is_a_difference(self):
        self.assertFalse(same_remote("git@github.com:platypeeps/system.git",
                                     "git@github.com:platypeeps/other.git"))

    def test_absent_remotes_are_never_equal(self):
        """Two repositories with no remote are not thereby the same repository."""
        self.assertFalse(same_remote(None, None))
        self.assertFalse(same_remote("", ""))
        self.assertFalse(same_remote(None, "git@github.com:platypeeps/system.git"))

    def test_an_ssh_and_an_https_url_for_one_repository_match(self):
        """sd:1436: a worktree cloned over ssh against an https row was refused."""
        self.assertTrue(same_remote("git@github.com:platypeeps/system.git",
                                    "https://github.com/platypeeps/system"))
        self.assertTrue(same_remote("https://github.com/platypeeps/system/",
                                    "git@github.com:platypeeps/system"))

    def test_the_ssh_url_form_matches_the_scp_and_https_forms(self):
        self.assertTrue(same_remote("ssh://git@github.com/platypeeps/system.git",
                                    "git@github.com:platypeeps/system.git"))
        self.assertTrue(same_remote("ssh://git@github.com:22/platypeeps/system",
                                    "https://github.com/platypeeps/system.git"))

    def test_the_host_is_compared_without_case(self):
        self.assertTrue(same_remote("https://GitHub.com/platypeeps/system",
                                    "git@github.com:platypeeps/system.git"))

    def test_a_different_repository_is_refused_across_url_forms(self):
        """Normalising the spelling must not merge two repositories."""
        self.assertFalse(same_remote("git@github.com:platypeeps/system.git",
                                     "https://github.com/platypeeps/other"))
        self.assertFalse(same_remote("ssh://git@github.com/platypeeps/system",
                                     "https://github.com/otherowner/system"))
        self.assertFalse(same_remote("git@github.com:platypeeps/system.git",
                                     "https://gitlab.com/platypeeps/system"))

    def test_the_identity_is_host_owner_and_name(self):
        """One normaliser: delivery verification and ship read this too."""
        for spelling in ("git@github.com:Platypeeps/System.git",
                         "ssh://git@github.com:22/platypeeps/system/",
                         "https://user@GITHUB.com/platypeeps/system.git"):
            self.assertEqual(remote_identity(spelling), "github.com/platypeeps/system")
        self.assertEqual(remote_identity(None), "")

    def test_another_host_is_compared_as_written_but_for_host_case_and_suffix(self):
        """Only github.com is known to serve one repository at every spelling."""
        self.assertTrue(same_remote("https://Git.Example.com/Team/Repo.git",
                                    "https://git.example.com/Team/Repo/"))
        self.assertFalse(same_remote("https://git.example.com/Team/Repo",
                                     "https://git.example.com/team/repo"))
        self.assertFalse(same_remote("https://git.example.com/team/repo",
                                     "git@git.example.com:team/repo"))

    def test_another_hosts_port_and_ssh_user_are_part_of_its_identity(self):
        """sd:1436 review: two ports can be two servers, two users two homes."""
        self.assertFalse(same_remote("ssh://git@host.example:2222/srv/repo.git",
                                     "ssh://git@host.example:2223/srv/repo.git"))
        self.assertFalse(same_remote("alice@host.example:repo.git",
                                     "bob@host.example:repo.git"))
        self.assertTrue(same_remote("alice@Host.Example:repo.git",
                                    "alice@host.example:repo"))

    def test_a_local_path_remote_still_compares_as_a_path(self):
        """Test fixtures clone from a bare directory; that is not a host."""
        self.assertTrue(same_remote("/tmp/x/bare.git", "/tmp/x/bare"))
        self.assertFalse(same_remote("/tmp/x/bare.git", "/tmp/y/bare.git"))


class ResolvingAnSshWorktreeAgainstAnHttpsRow(RegisterCase):
    def test_a_worktree_with_an_ssh_origin_resolves_to_the_https_row(self):
        """The exact refusal sd:1436 records, at the resolver."""
        upsert_repo(self.db, self.repo,
                    remote="https://github.com/platypeeps/system")
        worktree = f"{self.repo}/.claude/worktrees/agent-1"
        self.assertEqual(
            registered_for(self.db, worktree, "git@github.com:platypeeps/system.git"),
            self.repo,
        )
