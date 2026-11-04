"""Studio, slices 2 and 3 (sd:6920, sd:6921): the projects it lists, the files it serves, the ranges it answers, the
stage moves on a project's item and the pins and hides on its files.

The data comes later (fun-ai-stuff sd:6923), so every case builds its own `REPO_ROOT` with a registered repository and
its `project.json` files. The cases are the design's failure table rows for slice 2 (docs/work/2026-10-31-studio):
a bad file and an escaping root each list as a problem, the resolve cases run against a studio root, and each Range
header shape answers its status and bytes.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from sd_dashboard import studio, v2
from sd_db.testing import patience
from support import ScreenCase
from test_v2_read import READ_SHELL
from test_v2_registry import Registers
from test_v2_tasks import SHELL, STAND_IN
from test_v2_today import OSASCRIPT
from test_workflow_actions import BrowserSession

STATIC = Path(v2.__file__).resolve().parent / "static"

#: 1000 bytes of ASCII, so a slice of it says which bytes came back.
MEDIA = bytes(48 + i % 10 for i in range(1000))


def register(connection, path: Path) -> None:
    connection.execute("INSERT INTO repo (path, managed, created_at, updated_at) VALUES (?, 1, ?, ?)",
                       (str(path), "2026-11-01T00:00:00Z", "2026-11-01T00:00:00Z"))
    connection.commit()


def fixture(base: Path) -> tuple[Path, Path]:
    """`REPO_ROOT` with one registered-to-be repository of projects, and a folder outside it; (repo root, outside)."""
    root, outside = base / "repos", base / "outside"
    art = root / "example" / "art"
    cat = art / "shirts" / "cat"
    (cat / "candidates").mkdir(parents=True)
    (cat / "media").mkdir()
    (cat / "candidates" / "one.png").write_bytes(b"\x89PNG one")
    (cat / "candidates" / "notes.md").write_text("not media", encoding="utf-8")
    (cat / "candidates" / ".hidden.png").write_bytes(b"hidden")
    (cat / "media" / "clip.mp4").write_bytes(MEDIA)
    (cat / "media" / "take.wav").write_bytes(MEDIA)
    (cat / "stray.png").write_bytes(b"in the folder, in no root")
    outside.mkdir(parents=True)
    (outside / "secret.png").write_bytes(b"outside")
    (cat / "previews").symlink_to(outside, target_is_directory=True)
    # A file in a root that links out of it: to the project folder, and out of the repository.
    (cat / "candidates" / "link.png").symlink_to(cat / "stray.png")
    (cat / "candidates" / "out.png").symlink_to(outside / "secret.png")
    (cat / "project.json").write_text(json.dumps({
        "kind": "shirt", "title": "Cat shirt", "brief": "A cat on a shirt.", "item": "sd:42",
        "roots": {"candidates": "candidates", "media": "media", "previews": "previews", "print": "../escape", "poster": "candidates"},
    }), encoding="utf-8")
    (art / "songs" / "broken").mkdir(parents=True)
    (art / "songs" / "broken" / "project.json").write_text("{not json", encoding="utf-8")
    (art / "node_modules" / "dep").mkdir(parents=True)
    (art / "node_modules" / "dep" / "project.json").write_text("{}", encoding="utf-8")
    return root, outside


class TheProjects(ScreenCase):
    def setUp(self):
        super().setUp()
        self.root, self.outside = fixture(Path(self.tmp.name))
        register(self.connection, self.root / "example" / "art")

    def read(self):
        return studio.document(self.connection, now="2026-11-01T07:00:00Z", repo_root=self.root)

    def test_each_project_json_in_a_registered_repository_lists_and_build_output_is_skipped(self):
        doc = self.read()
        self.assertEqual([p["id"] for p in doc["projects"]], ["art/shirts/cat", "art/songs/broken"])
        cat = doc["projects"][0]
        self.assertEqual((cat["kind"], cat["title"], cat["brief"], cat["item"]), ("shirt", "Cat shirt", "A cat on a shirt.", 42))

    def test_a_project_json_with_no_kind_is_another_tools_and_is_not_listed(self):
        other = self.root / "example" / "art" / "tests" / "fixtures"
        other.mkdir(parents=True)
        (other / "project.json").write_text('{"name": "a fixture of another tool"}', encoding="utf-8")
        self.assertEqual([p["id"] for p in self.read()["projects"]], ["art/shirts/cat", "art/songs/broken"])

    def test_a_file_that_does_not_parse_lists_with_its_error(self):
        broken = self.read()["projects"][1]
        self.assertIn("project.json does not parse", broken["error"])
        self.assertEqual(broken["roots"], [])
        self.assertEqual(self.read()["attention"], {"state": "caution", "n": 2, "what": "projects whose project.json lists a problem"})

    def test_a_root_outside_its_folder_or_with_an_unknown_role_is_dropped_with_its_reason(self):
        cat = self.read()["projects"][0]
        self.assertEqual([r["role"] for r in cat["roots"]], ["candidates", "media"])
        problems = " | ".join(cat["problems"])
        self.assertIn("root previews previews leaves the project folder", problems)
        self.assertIn("root print '../escape' is not a folder name inside the project", problems)
        self.assertIn("root 'poster' is not a role", problems)

    def test_a_root_lists_its_media_from_disk_and_nothing_else(self):
        roots = {r["role"]: r for r in self.read()["projects"][0]["roots"]}
        self.assertEqual([f["path"] for f in roots["candidates"]["files"]], ["shirts/cat/candidates/one.png"])
        self.assertEqual([(f["name"], f["type"], f["ranged"], f["bytes"]) for f in roots["media"]["files"]],
                         [("clip.mp4", "video", True, 1000), ("take.wav", "audio", True, 1000)])

    def test_each_file_and_project_says_when_it_last_changed(self):
        # pack sd:7490: a file carries its mtime, and a project the newest of its files' and its project.json's.
        art = self.root / "example" / "art"
        for path, stamp in (("shirts/cat/project.json", 1_700_000_000), ("shirts/cat/candidates/one.png", 1_760_000_000),
                            ("shirts/cat/media/clip.mp4", 1_790_000_000), ("shirts/cat/media/take.wav", 1_710_000_000),
                            ("shirts/cat/stray.png", 1_800_000_000), ("songs/broken/project.json", 1_720_000_000)):
            os.utime(art / path, (stamp, stamp))
        cat, broken = self.read()["projects"]
        self.assertEqual({f["name"]: f["modified"] for r in cat["roots"] for f in r["files"]},
                         {"one.png": "2025-10-09T08:53:20Z", "clip.mp4": "2026-09-21T14:13:20Z", "take.wav": "2024-03-09T16:00:00Z"})
        # stray.png is newer, but in no root: the gallery does not serve it, so it does not count.
        self.assertEqual(cat["updated"], "2026-09-21T14:13:20Z")
        self.assertEqual(broken["updated"], "2024-07-03T09:46:40Z")

    def test_a_root_says_whether_it_holds_rendered_results_and_a_kind_names_its_render_verb(self):
        # pack sd:7490: reference and candidates are inputs and options; the other roles hold what was rendered.
        song = self.root / "example" / "art" / "songs" / "tune"
        (song / "media").mkdir(parents=True)
        (song / "project.json").write_text(json.dumps({"kind": "song", "title": "Tune", "roots": {"media": "media"}}), encoding="utf-8")
        cat, _, tune = self.read()["projects"]
        self.assertEqual([(r["role"], r["result"]) for r in cat["roots"]], [("candidates", False), ("media", True)])
        self.assertEqual((cat["render"], tune["render"]), ("", "assemble"))
        self.assertEqual(studio.RESULTS, ("selected", "print", "stickers", "previews", "media"))
        self.assertIn(studio.RENDER["song"], studio.SONG_VERBS)
        self.assertEqual(set(studio.RENDER), {"song"})

    def test_a_songs_final_video_lists_as_a_result_and_nothing_else_in_its_folder_does(self):
        # pack sd:7490 (decision #43036): song_pipeline.py assemble writes final-video.mp4 in the song folder, in no
        # root; it lists under the role "final", counts toward updated, and is the only file of the folder that does.
        song = self.root / "example" / "art" / "songs" / "tune"
        song.mkdir(parents=True)
        (song / "project.json").write_text(json.dumps({"kind": "song", "title": "Tune"}), encoding="utf-8")
        (song / "final-video.mp4").write_bytes(MEDIA)
        (song / "other.mp4").write_bytes(MEDIA)
        for path, stamp in (("project.json", 1_700_000_000), ("final-video.mp4", 1_790_000_000), ("other.mp4", 1_800_000_000)):
            os.utime(song / path, (stamp, stamp))
        tune = self.read()["projects"][2]
        self.assertEqual([(r["role"], r["result"], [f["path"] for f in r["files"]]) for r in tune["roots"]],
                         [("final", True, ["songs/tune/final-video.mp4"])])
        self.assertEqual(tune["updated"], "2026-09-21T14:13:20Z")
        self.assertEqual([r["role"] for r in self.read()["projects"][0]["roots"]], ["candidates", "media"], "a shirt has none")
        located = studio.located(self.connection, "art/songs/tune/final-video.mp4", self.root)
        self.assertEqual(located[0] if located else None, (song / "final-video.mp4").resolve())
        self.assertIsNone(studio.located(self.connection, "art/songs/tune/other.mp4", self.root))

    def test_a_final_video_that_links_out_of_its_folder_is_not_listed_or_served(self):
        song = self.root / "example" / "art" / "songs" / "tune"
        song.mkdir(parents=True)
        (song / "project.json").write_text(json.dumps({"kind": "song", "title": "Tune"}), encoding="utf-8")
        (self.outside / "film.mp4").write_bytes(MEDIA)
        (song / "final-video.mp4").symlink_to(self.outside / "film.mp4")
        self.assertEqual(self.read()["projects"][2]["roots"], [])
        self.assertIsNone(studio.located(self.connection, "art/songs/tune/final-video.mp4", self.root))

    def test_a_root_with_more_than_files_lists_the_first_and_says_it_was_cut(self):
        with mock.patch.object(studio, "FILES", 1):
            roots = {r["role"]: r for r in self.read()["projects"][0]["roots"]}
        self.assertEqual(([f["name"] for f in roots["media"]["files"]], roots["media"]["cut"]), (["clip.mp4"], True))
        self.assertEqual(([f["name"] for f in roots["candidates"]["files"]], roots["candidates"]["cut"]), (["one.png"], False))

    def test_a_repository_outside_repo_root_or_unregistered_lists_nothing(self):
        other = Path(self.tmp.name) / "elsewhere"
        (other / "p").mkdir(parents=True)
        (other / "p" / "project.json").write_text('{"kind": "song"}', encoding="utf-8")
        register(self.connection, other)
        unregistered = self.root / "example" / "loose" / "p"
        unregistered.mkdir(parents=True)
        (unregistered / "project.json").write_text('{"kind": "song"}', encoding="utf-8")
        self.assertEqual([p["repo"] for p in self.read()["projects"]], ["art", "art"])

    def test_a_machine_with_no_project_json_shows_an_empty_list(self):
        empty = Path(self.tmp.name) / "bare"
        (empty / "example" / "repo").mkdir(parents=True)
        doc = studio.document(self.connection, now="2026-11-01T07:00:00Z", repo_root=empty)
        self.assertEqual((doc["projects"], doc["problems"], doc["attention"]["state"]), ([], [], "ok"))

    def test_a_folder_the_scan_cannot_read_is_a_problem_not_an_empty_list(self):
        """sd:7151: os.walk skips a folder it cannot list unless asked; the scan says so instead of finding nothing."""
        locked = self.root / "example" / "art" / "songs"
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        doc = self.read()
        self.assertEqual([p["id"] for p in doc["projects"]], ["art/shirts/cat"])
        self.assertEqual(len(doc["problems"]), 1, doc["problems"])
        self.assertRegex(doc["problems"][0], r"^art: songs could not be read: .*Permission denied")
        self.assertEqual(doc["attention"]["state"], "caution")
        self.assertEqual(doc["repositories"], 1)

    def test_a_repo_root_that_does_not_resolve_is_a_problem_not_an_empty_list(self):
        missing = Path(self.tmp.name) / "no-such-root"
        doc = studio.document(self.connection, now="2026-11-01T07:00:00Z", repo_root=missing)
        self.assertEqual(doc["projects"], [])
        self.assertEqual(len(doc["problems"]), 1, doc["problems"])
        self.assertTrue(doc["problems"][0].startswith(f"REPO_ROOT {missing} does not resolve: "), doc["problems"])

    def test_two_registered_repositories_with_one_name_are_each_keyed_by_their_parent_and_read(self):
        """sd:7392: two checkouts named art under different parents are both read, each keyed parent-name."""
        twin = self.root / "other" / "art"
        (twin / "p" / "media").mkdir(parents=True)
        (twin / "p" / "media" / "a.mp3").write_bytes(MEDIA)
        (twin / "p" / "project.json").write_text('{"kind": "song", "roots": {"media": "media"}}', encoding="utf-8")
        register(self.connection, twin)
        doc = self.read()
        self.assertEqual(doc["problems"], [])
        self.assertEqual(doc["repositories"], 2)
        self.assertEqual([p["id"] for p in doc["projects"]], ["example-art/shirts/cat", "example-art/songs/broken", "other-art/p"])
        self.assertIsNotNone(studio.located(self.connection, "example-art/shirts/cat/candidates/one.png", self.root))
        self.assertIsNotNone(studio.located(self.connection, "other-art/p/media/a.mp3", self.root))
        self.assertIsNone(studio.located(self.connection, "art/shirts/cat/candidates/one.png", self.root))

    def test_a_qualified_key_that_still_clashes_is_neither_served_and_named(self):
        """sd:7392: example/art keys as example-art, which a checkout named example-art already holds: neither is served."""
        for path in (self.root / "other" / "art", self.root / "x" / "example-art"):
            (path / "p").mkdir(parents=True)
            (path / "p" / "project.json").write_text('{"kind": "song"}', encoding="utf-8")
            register(self.connection, path)
        doc = self.read()
        self.assertEqual(doc["problems"], ["Two registered repositories take the key example-art (example/art, x/example-art): "
                                           "neither is served."])
        self.assertEqual([p["id"] for p in doc["projects"]], ["other-art/p"])
        self.assertEqual(doc["repositories"], 1)
        self.assertIsNone(studio.located(self.connection, "example-art/shirts/cat/candidates/one.png", self.root))

    def test_a_qualified_key_that_is_no_name_is_not_served_and_named(self):
        """sd:7392: a twin under `_drafts` keys as `_drafts-art`, which no URL segment may be: it is named, not served."""
        twin = self.root / "_drafts" / "art"
        (twin / "p").mkdir(parents=True)
        (twin / "p" / "project.json").write_text('{"kind": "song"}', encoding="utf-8")
        register(self.connection, twin)
        doc = self.read()
        self.assertEqual(doc["problems"], ["The registered repository _drafts/art shares its name, and _drafts-art is no key: "
                                           "it is not served."])
        self.assertEqual(([p["id"] for p in doc["projects"]], doc["repositories"]),
                         (["example-art/shirts/cat", "example-art/songs/broken"], 1))

    def test_a_repository_whose_own_folder_does_not_list_is_not_counted_as_read(self):
        checkout = self.root / "example" / "art"
        checkout.chmod(0)
        self.addCleanup(checkout.chmod, 0o755)
        doc = self.read()
        self.assertEqual((doc["projects"], doc["repositories"]), ([], 0))
        self.assertRegex(doc["problems"][0], r"^art could not be read: .*Permission denied")

    def test_a_media_name_with_spaces_and_punctuation_lists_and_resolves(self):
        """sd:7395: a final render is named like a title; the gallery lists it and the file route finds it."""
        media = self.root / "example" / "art" / "shirts" / "cat" / "media"
        (media / "Song Title!.mp4").write_bytes(MEDIA)
        roots = {r["role"]: r for r in self.read()["projects"][0]["roots"]}
        self.assertIn("shirts/cat/media/Song Title!.mp4", [f["path"] for f in roots["media"]["files"]])
        found = studio.located(self.connection, "art/shirts/cat/media/Song%20Title%21.mp4", self.root)
        self.assertEqual(found, ((media / "Song Title!.mp4").resolve(), "video/mp4"))

    def test_a_name_with_undecodable_bytes_is_skipped_and_the_scan_goes_on(self):
        """sd:7406: os.walk yields 'bad\\udcff.png' on Linux; quote() raised and blanked the whole scan."""
        walk = os.walk

        def with_a_bad_name(*args, **kwargs):
            for current, folders, names in walk(*args, **kwargs):
                if current.endswith("media"):
                    names.append("bad\udcff.png")
                yield current, folders, names
        with mock.patch.object(studio.os, "walk", with_a_bad_name):
            doc = self.read()
        self.assertEqual(doc["problems"], [])
        listed = [f["name"] for r in doc["projects"][0]["roots"] for f in r["files"]]
        self.assertEqual(sorted(listed), ["clip.mp4", "one.png", "take.wav"])

    def test_a_view_request_for_an_undecodable_name_is_a_refusal_not_a_crash(self):
        """sd:7406: JSON carries a lone surrogate ('\\udcff'); quote() raised UnicodeEncodeError, not ValueError."""
        write = studio.view_request({"file": "art/shirts/cat/media/bad\udcff.png", "pinned": True})
        with self.assertRaisesRegex(ValueError, "No studio file"):
            write(self.connection)

    def test_a_dot_a_hidden_or_a_control_name_still_never_lists_or_resolves(self):
        """sd:7395: the looser last-segment rule still refuses '..', a leading dot, a control or format character."""
        media = self.root / "example" / "art" / "shirts" / "cat" / "media"
        for name in (".hidden.mp4", "bell\x07.mp4", "rtl\u202egnp.mp4"):
            (media / name).write_bytes(MEDIA)
        listed = [f["name"] for r in self.read()["projects"][0]["roots"] for f in r["files"]]
        self.assertEqual(sorted(listed), ["clip.mp4", "one.png", "take.wav"])
        for tail in ("art/shirts/cat/media/.hidden.mp4", "art/shirts/cat/media/bell%07.mp4", "art/shirts/cat/media/rtl%E2%80%AEgnp.mp4",
                     "art/shirts/cat/media/..", "art/shirts/cat/media/%2E%2E%2Fclip.mp4", "art/shirts/cat/media/..%2F..%2Fstray.png",
                     "art/shirts/cat/media/a%00.mp4"):
            with self.subTest(tail=tail):
                self.assertIsNone(studio.located(self.connection, tail, self.root))
        for name in ("..", ".", ".mp4", "a/b.mp4", "a\x00.mp4", "tab\t.mp4", "", "Song Title!.mp4"):
            with self.subTest(name=name):
                self.assertEqual(studio.file_name(name), name == "Song Title!.mp4")

def name_item(root: Path, item: int, folder: str = "shirts/cat") -> None:
    """The project at `folder` names `item` as its sd item."""
    manifest = root / "example" / "art" / folder / "project.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps({**data, "item": f"sd:{item}"}), encoding="utf-8")


class TheStage(ScreenCase):
    """The design's row "Move a stage": a stale revision and a skipped stage are each refused, and nothing is written."""

    def setUp(self):
        super().setUp()
        self.root, _ = fixture(Path(self.tmp.name))
        register(self.connection, self.root / "example" / "art")
        self.number = self.item("Cat shirt")
        name_item(self.root, self.number)

    def cat(self):
        return studio.document(self.connection, now="2026-11-01T07:00:00Z", repo_root=self.root)["projects"][0]

    def move(self, target, revision=None):
        from sd_db import workflow

        project = studio.naming(self.connection, self.number, self.root)
        revision = revision or workflow.item_state(self.connection, self.number)["revision"]
        return studio.move_stage(self.connection, self.number, project, target, who="dashboard", expected_revision=revision)

    def test_each_kind_has_its_strip_and_an_item_with_no_stage_starts_at_the_first(self):
        self.assertEqual(studio.STAGES["shirt"], ("brief", "candidates", "selected", "print_export", "approved", "ordered"))
        self.assertEqual(studio.STAGES["song"], ("lyrics", "suno", "selections", "film", "delivered"))
        self.assertEqual(studio.STAGES["episode"], ("idea", "outlined", "scripted", "in_production", "published"))
        self.assertEqual([studio.next_stage("song", s) for s in (None, "lyrics", "delivered", "drafting")], ["lyrics", "suno", None, None])

    def test_the_document_carries_the_items_stage_its_next_and_the_revision_a_move_posts(self):
        from sd_db import workflow

        cat = self.cat()
        self.assertEqual((cat["stage"], cat["next"], cat["strip"][0]), ("", "brief", "brief"))
        self.assertEqual(cat["revision"], workflow.item_state(self.connection, self.number)["revision"])
        self.move("brief")
        self.assertEqual((self.cat()["stage"], self.cat()["next"]), ("brief", "candidates"))

    def test_a_missing_item_or_a_stage_off_the_strip_lists_as_a_problem(self):
        name_item(self.root, 9999)
        self.assertIn("item sd:9999 does not exist", self.cat()["problems"])
        name_item(self.root, self.number)
        from sd_db.writes import set_item_fields

        set_item_fields(self.connection, self.number, stage="drafting")
        cat = self.cat()
        self.assertIn(f"item sd:{self.number} is at stage 'drafting', which is not on the shirt strip", cat["problems"])
        self.assertEqual(cat["next"], "")

    def test_a_move_to_the_next_stage_writes_the_stage_and_a_note(self):
        state = self.move("brief")
        self.assertEqual(state["item"]["stage"], "brief")
        self.assertEqual(self.move("candidates")["item"]["stage"], "candidates")
        notes = [n["body"] for n in state["notes"] if n["kind"] == "comment"]
        self.assertEqual(notes, ["Studio stage none -> brief by dashboard (art/shirts/cat)"])

    def test_a_stale_revision_is_refused_and_writes_nothing(self):
        from sd_db import workflow

        stale = workflow.item_state(self.connection, self.number)["revision"]
        self.move("brief")
        before = tuple(self.connection.iterdump())
        with self.assertRaises(workflow.StaleItem):
            self.move("candidates", revision=stale)
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_a_skipped_stage_a_step_back_or_one_off_the_strip_is_refused_and_writes_nothing(self):
        from sd_db import workflow
        from sd_db.writes import set_item_fields

        self.move("brief")
        for target in ("selected", "brief_x", "lyrics", "ordered"):
            before = tuple(self.connection.iterdump())
            with self.subTest(target=target), self.assertRaisesRegex(workflow.WorkflowError, "one stage at a time"):
                self.move(target)
            self.assertEqual(tuple(self.connection.iterdump()), before)
        self.move("candidates")
        with self.assertRaisesRegex(workflow.WorkflowError, "one stage at a time"):
            self.move("brief")
        set_item_fields(self.connection, self.number, stage="drafting")
        before = tuple(self.connection.iterdump())
        with self.assertRaisesRegex(workflow.WorkflowError, "not on the shirt strip"):
            self.move("brief")
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_a_note_that_fails_after_the_stage_leaves_the_stage_unmoved(self):
        """Steps: the stage and its note are one transaction; a failure between them undoes the stage."""
        from sd_db import writes

        before = tuple(self.connection.iterdump())
        with mock.patch.object(writes, "add_note", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.move("brief")
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_two_projects_naming_one_item_are_refused(self):
        song = self.root / "example" / "art" / "songs" / "two"
        song.mkdir(parents=True)
        (song / "project.json").write_text(json.dumps({"kind": "song", "item": f"sd:{self.number}"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, f"Two projects name sd:{self.number}"):
            studio.naming(self.connection, self.number, self.root)


#: A stand-in tool: prints its argv after its own name, and exits 0.
ECHO = "import sys\nprint(' '.join(sys.argv))\n"


class TheActions(ScreenCase):
    """Slice 4 (sd:6922): the `studio.*` rows of `run_actions.ACTIONS`. Each argv is fixed text, a project the server
    found and a verb from its list; nothing the page sends enters it otherwise."""

    def setUp(self):
        super().setUp()
        self.root, _ = fixture(Path(self.tmp.name))
        self.art = self.root / "example" / "art"
        register(self.connection, self.art)
        (self.art / "Makefile").write_text("check:\n\t@echo checked\n", encoding="utf-8")
        for folder, kind, tool in (("gang/episodes/door", "episode", "gang/tools/episode.py"),
                                   ("songs/tune", "song", "songs/tools/song_pipeline.py")):
            (self.art / folder).mkdir(parents=True)
            (self.art / folder / "project.json").write_text(json.dumps({"kind": kind, "title": folder}), encoding="utf-8")
            (self.art / tool).parent.mkdir(parents=True, exist_ok=True)
            (self.art / tool).write_text(ECHO, encoding="utf-8")
        patched = mock.patch.dict(os.environ, {"REPO_ROOT": str(self.root)})
        patched.start()
        self.addCleanup(patched.stop)

    def run_action(self, **values):
        from sd_dashboard import run_actions

        return run_actions.request(values)(self.connection)

    def test_check_runs_make_check_in_the_projects_checkout(self):
        status, answer = self.run_action(action="studio.check", project="art/shirts/cat")
        self.assertEqual((status, answer["exit"], answer["line"]), (200, 0, f"cd {self.art.resolve()} && make check"))
        self.assertEqual(answer["output"], "checked")

    def test_an_unknown_project_or_an_extra_field_runs_nothing(self):
        for values in ({"project": "art/shirts/dog"}, {"project": "art/shirts/cat", "argv": "rm -rf /"}, {}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.run_action(action="studio.check", **values)

    def test_episode_runs_the_tool_above_the_project_with_its_folder(self):
        status, answer = self.run_action(action="studio.episode", project="art/gang/episodes/door", verb="check")
        folder = (self.art / "gang" / "episodes" / "door").resolve()
        self.assertEqual((status, answer["exit"]), (200, 0), answer)
        self.assertEqual(answer["output"], f"{(self.art / 'gang' / 'tools' / 'episode.py').resolve()} check {folder}")

    def test_song_runs_the_pipeline_with_the_song_alone(self):
        status, answer = self.run_action(action="studio.song", project="art/songs/tune", verb="validate")
        self.assertEqual((status, answer["output"].split()[1:]), (200, ["validate", "tune"]), answer)

    def test_song_assemble_replaces_the_last_render_and_the_tool_keeps_its_backup(self):
        # pack sd:7490 (decision #43036): assemble refuses while final-video.mp4 exists unless --replace, which keeps
        # the old render in media/final-backups; Re-render and Song assemble both pass it.
        status, answer = self.run_action(action="studio.song", project="art/songs/tune", verb="assemble")
        self.assertEqual((status, answer["output"].split()[1:]), (200, ["assemble", "--replace", "tune"]), answer)

    def test_a_verb_off_the_list_or_a_project_of_another_kind_runs_nothing(self):
        cases = [("studio.episode", "art/gang/episodes/door", "rm"), ("studio.song", "art/songs/tune", "import"),
                 ("studio.episode", "art/shirts/cat", "check"), ("studio.song", "art/gang/episodes/door", "validate")]
        for action, project, verb in cases:
            with self.subTest(action=action, project=project, verb=verb), self.assertRaises(ValueError):
                self.run_action(action=action, project=project, verb=verb)

    def test_a_project_with_no_tool_above_it_runs_nothing(self):
        (self.art / "songs" / "tools" / "song_pipeline.py").unlink()
        with self.assertRaisesRegex(ValueError, "no songs/tools/song_pipeline.py|no tools/song_pipeline.py"):
            self.run_action(action="studio.song", project="art/songs/tune", verb="validate")

    def test_a_slow_action_answers_504_unknown(self):
        (self.art / "Makefile").write_text("check:\n\t@sleep 5\n", encoding="utf-8")
        with mock.patch.object(studio, "CHECK_SECONDS", 1):
            status, answer = self.run_action(action="studio.check", project="art/shirts/cat")
        self.assertEqual((status, answer["outcome"]), (504, "unknown"))

    def test_session_starts_claude_in_herdr_and_notes_the_item(self):
        from sd_dashboard import fix_session

        number = self.item("Cat shirt")
        name_item(self.root, number)
        launched = []
        with mock.patch.object(fix_session, "_launch", lambda d, label, text: launched.append((d, label, text)) or "pane-7"):
            status, answer = self.run_action(action="studio.session", project="art/shirts/cat")
        self.assertEqual((status, answer["exit"]), (200, 0), answer)
        directory, label, text = launched[0]
        self.assertEqual((directory, label), (self.art.resolve(), "studio-art-shirts-cat"))
        self.assertIn("shirts/cat/project.json", text)
        self.assertNotIn("A cat on a shirt", text, "the brief is read from the file, never typed from the page")
        notes = self.connection.execute("SELECT body FROM note WHERE item = ?", (number,)).fetchall()
        self.assertIn("pane pane-7", notes[-1]["body"])

    def test_session_with_herdr_down_or_a_note_that_fails_says_so(self):
        from sd_dashboard import fix_session

        with mock.patch.object(fix_session, "_launch", lambda *_: (503, {"error": "Fix failed: herdr is not running"})):
            status, answer = self.run_action(action="studio.session", project="art/shirts/cat")
        self.assertEqual((status, answer["exit"], answer["output"]), (200, 1, "herdr is not running"))
        name_item(self.root, 9999)
        with mock.patch.object(fix_session, "_launch", lambda *_: "pane-8"):
            status, answer = self.run_action(action="studio.session", project="art/shirts/cat")
        self.assertEqual(answer["exit"], 1)
        self.assertIn("claude started in herdr pane pane-8, but the note on sd:9999 was not recorded", answer["output"])


class TheRange(unittest.TestCase):
    def test_each_header_shape_answers_its_status_and_bytes(self):
        cases = {
            None: (200, 0, 1000), "": (200, 0, 1000),
            "bytes=0-99": (206, 0, 100), "bytes=900-": (206, 900, 100), "bytes=-10": (206, 990, 10),
            "bytes=990-5000": (206, 990, 10), "bytes=-5000": (206, 0, 1000),
            "bytes=1000-": (416, 0, 0), "bytes=5000-6000": (416, 0, 0), "bytes=-0": (416, 0, 0),
            "bytes=0-1,5-9": (200, 0, 1000), "bytes=9-1": (200, 0, 1000), "lines=0-9": (200, 0, 1000),
            "bytes=-": (200, 0, 1000), "bytes=a-b": (200, 0, 1000),
        }
        for header, expected in cases.items():
            with self.subTest(header=header):
                self.assertEqual(studio.byte_range(header, 1000), expected)

    def test_an_empty_file_answers_any_range_with_416(self):
        self.assertEqual(studio.byte_range("bytes=0-", 0), (416, 0, 0))
        self.assertEqual(studio.byte_range(None, 0), (200, 0, 0))

    def test_an_open_range_is_cut_at_one_chunk(self):
        size = studio.CHUNK * 3
        self.assertEqual(studio.byte_range("bytes=0-", size), (206, 0, studio.CHUNK))


class TheStudioRegistration(Registers, unittest.TestCase):
    page, section, route = "studio", "Studio", "/studio"
    api = ("/api/studio", "/api/studio/view")


class TheServer(BrowserSession):
    def setUp(self):
        super().setUp()
        self.root, self.outside = fixture(Path(self.tmp.name))
        register(self.connection, self.root / "example" / "art")
        environment = mock.patch.dict(os.environ, {"REPO_ROOT": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)

    def fetch(self, path, **headers):
        """(status, headers, bytes) for a GET with the session's cookie and `headers`."""
        request = urllib.request.Request(self.base + path, headers={"Cookie": self.cookie, **headers})
        try:
            answer = urllib.request.urlopen(request, timeout=patience(self.http_timeout))
        except urllib.error.HTTPError as error:
            answer = error
        with answer:
            return answer.status, answer.headers, answer.read()

    def test_the_page_serves_and_the_api_lists_the_projects(self):
        status, _, body = self.fetch("/studio")
        self.assertEqual(status, 200)
        self.assertIn(b'<script src="/ui/studio.js?v=', body)
        status, _, body = self.fetch("/api/studio")
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in json.loads(body)["projects"]], ["art/shirts/cat", "art/songs/broken"])

    def test_every_gallery_file_the_api_lists_answers_200_under_its_policy(self):
        doc = json.loads(self.fetch("/api/studio")[2])
        paths = [f["path"] for p in doc["projects"] for r in p["roots"] for f in r["files"]]
        self.assertEqual(len(paths), 3)
        for path in paths:
            with self.subTest(path=path):
                status, headers, _ = self.fetch(f"/studio/files/art/{path}")
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Security-Policy"], studio.policy(Path(path)))
        self.assertEqual(self.fetch("/studio/files/art/shirts/cat/candidates/one.png")[1]["Content-Type"], "image/png")

    def run_page(self, doc, body):
        """studio.js under JavaScriptCore against the stand-in shell, `/api/studio` answering `doc`; `R` as `body` left it."""
        script = (STAND_IN + "location.origin = 'http://dash.example.test';\n" + (STATIC / "markup.js").read_text(encoding="utf-8")
                  + "\nconst mk = window.markup.html;\n" + SHELL + READ_SHELL
                  + f"\nANSWER = p => p === '/api/studio' ? [200, {json.dumps(doc)}] : [404, {{}}];\n"
                  + (STATIC / "studio.js").read_text(encoding="utf-8")
                  + "\nvar R = {};\n(async () => { try {\n(DOC_LISTENERS.DOMContentLoaded || []).forEach(f => f());\nawait flush();\n"
                  + body + "\n} catch (e) { OUT.error = String(e) + ' ' + e.stack; } })();\n"
                  + "function run() { OUT.R = R; return JSON.stringify(OUT); }\n")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out

    def test_every_gallery_file_the_page_links_answers_200_and_a_bad_file_lists_with_its_error(self):
        """The design's criteria: the links are the ones studio.js draws in Details, not the API's paths."""
        doc = json.loads(self.fetch("/api/studio")[2])
        out = self.run_page(doc, "R.rows = ELS.rows.html; window.PAGE_LIST.select('art/shirts/cat'); R.details = ELS.details.html;")
        rows, details = out["R"]["rows"], out["R"]["details"]
        self.assertIn('title="project.json does not parse:', rows)
        self.assertIn("<button type=\"button\">broken</button>", rows)
        links = sorted({html.unescape(u) for u in re.findall(r'(?:src|href)="(/studio/files/[^"]*)"', details)})
        self.assertEqual(links, ["/studio/files/art/shirts/cat/candidates/one.png", "/studio/files/art/shirts/cat/media/clip.mp4",
                                 "/studio/files/art/shirts/cat/media/take.wav"])
        self.assertIn('<video controls preload="metadata" src="/studio/files/art/shirts/cat/media/clip.mp4">', details)
        self.assertIn('<audio controls preload="metadata" src="/studio/files/art/shirts/cat/media/take.wav">', details)
        for link in links:
            with self.subTest(link=link):
                self.assertEqual(self.fetch(link)[0], 200)

    def test_details_draw_the_strip_and_next_stage_posts_the_items_route_with_the_revision(self):
        number = self.item("Cat shirt")
        name_item(self.root, number)
        doc = json.loads(self.fetch("/api/studio")[2])
        cat = doc["projects"][0]
        self.post(f"/api/items/{number}/stage", {"revision": cat["revision"], "stage": "brief"})
        doc = json.loads(self.fetch("/api/studio")[2])
        cat = doc["projects"][0]
        out = self.run_page(doc, "window.PAGE_LIST.select('art/shirts/cat'); R.details = ELS.details.html;"
                                 "const c = REG.find(x => x.id === 'studio.stage'); R.does = c.does(OBJ.get('art/shirts/cat'));"
                                 "C.run(c, OBJ.get('art/shirts/cat')); await flush();")
        details = out["R"]["details"]
        self.assertIn('<li class="now" aria-current="step">brief</li><li class="" aria-current="false">candidates</li>', details)
        self.assertIn("print export", details)
        self.assertEqual(out["R"]["does"], f"Moves #{number} from brief to candidates, with a note.")
        self.assertIn([f"/api/items/{number}/stage", {"revision": cat["revision"], "stage": "candidates"}, 64], out["posts"])
        self.assertIn("studio.stage", out["confirms"])

    def test_the_project_commands_run_their_studio_action_and_a_tool_of_another_kind_is_off(self):
        doc = json.loads(self.fetch("/api/studio")[2])
        out = self.run_page(doc, "const ran = []; window.commands = { runAction: (o, a, ids) => { ran.push([a, ids]); return Promise.resolve('ok'); } };"
                                 "const o = OBJ.get('art/shirts/cat'), c = id => REG.find(x => x.id === id);"
                                 "R.off = ['studio.check', 'studio.song-validate', 'studio.episode-pack'].map(id => C.offWhy(c(id), o));"
                                 "C.run(c('studio.check'), o); await flush(); C.run(c('studio.session'), o); await flush(); R.ran = ran;")
        self.assertEqual(out["R"]["off"], ["", "it is a shirt, not a song", "it is a shirt, not an episode"])
        self.assertEqual(out["R"]["ran"], [["studio.check", {"project": "art/shirts/cat"}], ["studio.session", {"project": "art/shirts/cat"}]])
        self.assertIn("studio.session", out["confirms"])

    def test_a_pinned_file_leads_its_root_a_hidden_one_folds_and_pin_posts_the_view(self):
        self.post("/api/studio/view", {"file": "art/shirts/cat/media/take.wav", "pinned": True})
        self.post("/api/studio/view", {"file": "art/shirts/cat/candidates/one.png", "hidden": True})
        doc = json.loads(self.fetch("/api/studio")[2])
        out = self.run_page(doc, "window.PAGE_LIST.select('art/shirts/cat'); R.details = ELS.details.html;"
                                 "const o = OBJ.get('file:art/shirts/cat/media/clip.mp4');"
                                 "R.off = ['studio.pin', 'studio.unpin', 'studio.hide', 'studio.unhide'].map(id => C.offWhy(REG.find(x => x.id === id), o));"
                                 "C.run(REG.find(x => x.id === 'studio.pin'), o); await flush();")
        details = out["R"]["details"]
        media = details[details.index("<h3>media"):]
        self.assertLess(media.index("take.wav"), media.index("clip.mp4"))
        self.assertIn('<b class="pinmark">pinned · </b>take.wav', media)
        candidates = details[details.index("<h3>candidates"):details.index("<h3>media")]
        self.assertIn("Every file in this root is hidden.", candidates)
        self.assertIn('<summary>Hidden <span class="n">1</span></summary>', candidates)
        self.assertEqual(out["R"]["off"], ["", "not pinned", "", "not hidden"])
        self.assertIn(["/api/studio/view", {"file": "art/shirts/cat/media/clip.mp4", "pinned": True}, 64], out["posts"])

    def rendered(self, body):
        """studio.js on a shirt (no render verb) and a song (assemble), each with an input root and a result root."""
        def file(path, modified, hidden=False):
            return {"path": path, "name": path.rsplit("/", 1)[1], "bytes": 1, "type": "image", "ranged": False,
                    "modified": modified, "pinned": False, "hidden": hidden}

        def project(ident, kind, render, updated, roots):
            return {"id": f"art/{ident}", "repo": "art", "folder": ident, "kind": kind, "title": ident.rsplit("/", 1)[1],
                    "brief": "", "item": None, "problems": [], "error": "", "strip": list(studio.STAGES[kind]), "stage": "",
                    "next": "", "revision": "", "updated": updated, "render": render,
                    "roots": [{"role": role, "path": role, "result": role != "candidates", "cut": False, "files": files}
                              for role, files in roots]}

        doc = {"read": "2026-11-04T07:00:00Z", "root": "/repos", "problems": [], "repositories": 1,
               "store": {"available": True, "reason": ""}, "attention": {"state": "ok", "n": 0, "what": ""},
               "projects": [
                   project("shirts/cat", "shirt", "", "2026-11-02T09:00:00Z", [
                       ("candidates", [file("shirts/cat/candidates/one.png", "2026-11-02T09:00:00Z")]),
                       ("print", [file("shirts/cat/print/front.png", "2026-11-01T08:00:00Z")])]),
                   project("songs/tune", "song", "assemble", "2026-11-03T10:00:00Z", [
                       ("media", [file("songs/tune/media/old.mp4", "2026-11-01T10:00:00Z"),
                                  file("songs/tune/media/new.mp4", "2026-11-03T10:00:00Z"),
                                  file("songs/tune/media/gone.mp4", "2026-11-03T11:00:00Z", hidden=True)])])]}
        click = ("const expand = id => ELS.rows.listeners.click.forEach(f => f({ target: { closest: s => "
                 "s === '[data-expand]' ? { dataset: { expand: id } } : null } }));\n")
        return self.run_page(doc, click + body)["R"]

    def test_each_project_row_says_when_its_files_last_changed(self):
        # pack sd:7490: an Updated column, the project's newest mtime through the shell's time.rel renderer.
        out = self.rendered("R.rows = ELS.rows.html; R.head = ELS['rows-head'].html;")
        self.assertIn('<td class="when"><time class="rel" datetime="2026-11-02T09:00:00Z"></time></td>', out["rows"])
        self.assertIn('<td class="when"><time class="rel" datetime="2026-11-03T10:00:00Z"></time></td>', out["rows"])
        self.assertIn('data-sort="updated"', out["head"])
        self.assertIn(">Updated<", out["head"])

    def test_a_project_row_expands_and_only_one_is_expanded_at_a_time(self):
        # pack sd:7490: a disclosure button per row; opening one closes the other, a second press closes it.
        out = self.rendered("R.none = ELS.rows.html; expand('art/shirts/cat'); R.cat = ELS.rows.html;"
                            "expand('art/songs/tune'); R.tune = ELS.rows.html; expand('art/songs/tune'); R.shut = ELS.rows.html;")
        def toggle(ident, state):
            return f'data-expand="art/{ident}" aria-expanded="{state}"'

        self.assertIn(toggle("shirts/cat", "false"), out["none"])
        self.assertNotIn('<tr class="sub"', out["none"])
        self.assertIn(toggle("shirts/cat", "true"), out["cat"])
        self.assertIn("front.png", out["cat"])
        self.assertIn(toggle("shirts/cat", "false"), out["tune"])
        self.assertIn(toggle("songs/tune", "true"), out["tune"])
        self.assertNotIn("front.png", out["tune"])
        self.assertIn("new.mp4", out["tune"])
        self.assertNotIn('<tr class="sub"', out["shut"])
        self.assertNotIn('aria-expanded="true"', out["shut"])

    def test_a_sub_row_per_rendered_file_opens_it_and_re_renders_it_with_its_kinds_verb(self):
        # pack sd:7490: one sub-row per unhidden file of a result root, newest first, each with its time, Open and,
        # for a kind with a render verb, Re-render; a shirt has none, so its row shows no Re-render.
        out = self.rendered(
            "const ran = []; window.commands = { runAction: (o, a, ids) => { ran.push([o.id, a, ids]); return Promise.resolve('ok'); } };"
            "expand('art/shirts/cat'); R.cat = ELS.rows.html; expand('art/songs/tune'); R.tune = ELS.rows.html;"
            "const c = REG.find(x => x.id === 'studio.rerender');"
            "R.off = C.offWhy(c, OBJ.get('file:art/shirts/cat/print/front.png'));"
            "R.cli = c.cli(OBJ.get('file:art/songs/tune/media/new.mp4'));"
            "C.run(c, OBJ.get('file:art/songs/tune/media/new.mp4')); await flush(); R.ran = ran; R.confirms = OUT.confirms;")
        cat, tune = out["cat"], out["tune"]
        self.assertIn('<a class="btn quiet sm" href="/studio/files/art/shirts/cat/print/front.png" target="_blank" rel="noopener">Open</a>', cat)
        self.assertNotIn("one.png", cat, "a candidate is no rendered result")
        self.assertNotIn("Re-render", cat)
        self.assertNotIn("gone.mp4", tune, "a hidden file is no sub-row")
        self.assertLess(tune.index("new.mp4"), tune.index("old.mp4"))
        for name, when in (("new.mp4", "2026-11-03T10:00:00Z"), ("old.mp4", "2026-11-01T10:00:00Z")):
            with self.subTest(name=name):
                self.assertIn(f'href="/studio/files/art/songs/tune/media/{name}" target="_blank" rel="noopener">Open</a>', tune)
                self.assertIn(f'<button class="btn quiet sm" type="button" data-cmd="studio.rerender" data-obj="file:art/songs/tune/media/{name}">Re-render</button>', tune)
                self.assertIn(f'<td class="when"><time class="rel" datetime="{when}"></time></td>', tune)
        self.assertEqual(out["off"], "a shirt has no render verb")
        self.assertEqual(out["ran"], [["art/songs/tune", "studio.song", {"project": "art/songs/tune", "verb": "assemble"}]])
        self.assertIn("studio.rerender", out["confirms"])
        self.assertEqual(out["cli"], "tools/song_pipeline.py assemble --replace songs/tune")

    def test_scan_problems_show_before_the_page_says_no_project_json_exists(self):
        """sd:7151: a scan that could not read a folder found nothing it can vouch for, so the page names the problem."""
        doc = {"read": "2026-11-01T07:00:00Z", "root": "/repos", "projects": [], "attention": {"state": "caution", "n": 1, "what": "x"},
               "repositories": 0,
               "problems": ["art: songs could not be read: [Errno 13] Permission denied",
                            "Two registered repositories take the key twin (a/twin, b-twin): neither is served."]}
        out = self.run_page(doc, "R.details = ELS.details.html;")
        last = out["states"][-1]
        self.assertEqual(last["kind"], "partial", out["states"])
        self.assertEqual(last["text"], "art: songs could not be read: [Errno 13] Permission denied · Two registered repositories "
                                       "take the key twin (a/twin, b-twin): neither is served. No repository was read, so this is "
                                       "not a sign that no project exists.")
        self.assertIn("The scan named a problem, so nothing is selected.", out["R"]["details"])
        self.assertNotIn("No project.json is under the repositories", json.dumps(out["states"]) + out["R"]["details"])
        out = self.run_page({**doc, "problems": []}, "R.details = ELS.details.html;")
        self.assertEqual(out["states"][-1]["kind"], "empty")
        self.assertIn("No project.json is under the repositories yet.", out["R"]["details"])

    def test_a_scan_that_read_repositories_and_found_no_project_says_how_many_it_read(self):
        """sd:7392: a problem beside repositories that were read is not 'No project was read': the banner counts them."""
        doc = {"read": "2026-11-01T07:00:00Z", "root": "/repos", "projects": [], "attention": {"state": "ok", "n": 0, "what": "x"},
               "repositories": 3, "problems": ["Two registered repositories take the key twin (a/twin, b-twin): neither is served."]}
        out = self.run_page(doc, "R.details = ELS.details.html;")
        last = out["states"][-1]
        self.assertEqual(last["kind"], "partial", out["states"])
        self.assertEqual(last["text"], "Two registered repositories take the key twin (a/twin, b-twin): neither is served. "
                                       "The scan read 3 repositories and found no project in them.")
        self.assertNotIn("No project was read", last["text"])
        one = self.run_page({**doc, "repositories": 1}, "")["states"][-1]["text"]
        self.assertTrue(one.endswith("The scan read 1 repository and found no project in it."), one)

    def test_a_stage_move_posts_the_items_route_and_a_stale_or_skipped_one_writes_nothing(self):
        """The design's criterion: a stage move with a stale revision answers 409 and writes no note; a skip is a 400."""
        number = self.item("Cat shirt")
        name_item(self.root, number)
        cat = json.loads(self.fetch("/api/studio")[2])["projects"][0]
        status, _, out = self.post(f"/api/items/{number}/stage", {"revision": cat["revision"], "stage": cat["next"]})
        self.assertEqual((status, out["item"]["stage"]), (200, "brief"), out)
        before = self.unjournalled()
        status, _, out = self.post(f"/api/items/{number}/stage", {"revision": cat["revision"], "stage": "candidates"})
        self.assertEqual((status, out.get("reload")), (409, True), out)
        self.assertEqual(self.unjournalled(), before)
        fresh = json.loads(self.fetch("/api/studio")[2])["projects"][0]
        for payload in ({"stage": "selected"}, {"stage": "ordered"}, {"stage": "candidates", "reason": "a reason"}):
            with self.subTest(payload=payload):
                status, _, out = self.post(f"/api/items/{number}/stage", {"revision": fresh["revision"], **payload})
                self.assertEqual(status, 400, out)
                self.assertEqual(self.unjournalled(), before)
        status, _, out = self.post(f"/api/items/{number}/stage", {"revision": fresh["revision"], "stage": "candidates"})
        self.assertEqual((status, out["item"]["stage"]), (200, "candidates"), out)

    def test_an_item_no_project_names_still_moves_as_writing_moves_it(self):
        """Guards: the Studio branch takes only an item a project names; any other keeps writing's refusal."""
        from sd_db import workflow

        number = self.item("not a project")
        revision = workflow.item_state(self.connection, number)["revision"]
        status, _, out = self.post(f"/api/items/{number}/stage", {"revision": revision, "stage": "drafting"})
        self.assertEqual(status, 400, out)
        self.assertIn("is not a writing piece", out["error"])

    def test_pin_and_hide_write_the_files_view_and_a_file_not_served_writes_nothing(self):
        path = "art/shirts/cat/candidates/one.png"
        status, _, out = self.post("/api/studio/view", {"file": path, "hidden": True})
        self.assertEqual((status, out["file"], out["hidden"]), (200, path, True), out)
        status, _, out = self.post("/api/studio/view", {"file": path, "pinned": True})
        self.assertEqual((status, out["pinned"], out["hidden"]), (200, True, True), out)
        doc = json.loads(self.fetch("/api/studio")[2])
        one = doc["projects"][0]["roots"][0]["files"][0]
        self.assertEqual((one["name"], one["pinned"], one["hidden"], doc["store"]), ("one.png", True, True, {"available": True, "reason": ""}))
        before = self.unjournalled()
        for payload in ({"file": "art/shirts/cat/stray.png", "hidden": True}, {"file": "art/shirts/cat/candidates/out.png", "hidden": True},
                        {"file": path}, {"file": path, "hidden": "yes"}, {"file": path, "tags": ["x"]}, {"hidden": True}):
            with self.subTest(payload=payload):
                status, _, out = self.post("/api/studio/view", payload)
                self.assertEqual(status, 400, out)
                self.assertEqual(self.unjournalled(), before)

    def test_a_range_on_an_mp4_answers_206_with_its_bytes(self):
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/clip.mp4", Range="bytes=0-99")
        self.assertEqual((status, headers["Content-Range"], headers["Accept-Ranges"], body), (206, "bytes 0-99/1000", "bytes", MEDIA[:100]))
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/take.wav", Range="bytes=-10")
        self.assertEqual((status, headers["Content-Range"], body), (206, "bytes 990-999/1000", MEDIA[990:]))

    def test_a_media_name_with_spaces_and_punctuation_is_linked_encoded_and_served_with_a_range(self):
        """sd:7395: studio.js links 'Song Title!.mp4' encoded; the server decodes it and answers 200 and a 206 Range."""
        (self.root / "example" / "art" / "shirts" / "cat" / "media" / "Song Title!.mp4").write_bytes(MEDIA)
        doc = json.loads(self.fetch("/api/studio")[2])
        details = self.run_page(doc, "window.PAGE_LIST.select('art/shirts/cat'); R.details = ELS.details.html;")["R"]["details"]
        self.assertIn('src="/studio/files/art/shirts/cat/media/Song%20Title!.mp4"', details)
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/Song%20Title!.mp4")
        self.assertEqual((status, headers["Content-Type"], body), (200, "video/mp4", MEDIA))
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/Song%20Title%21.mp4", Range="bytes=10-19")
        self.assertEqual((status, headers["Content-Range"], body), (206, "bytes 10-19/1000", MEDIA[10:20]))
        self.post("/api/studio/view", {"file": "art/shirts/cat/media/Song Title!.mp4", "pinned": True})
        doc = json.loads(self.fetch("/api/studio")[2])
        media = {f["name"]: f for r in doc["projects"][0]["roots"] for f in r["files"]}
        self.assertTrue(media["Song Title!.mp4"]["pinned"])

    def test_a_range_past_the_end_is_416_and_one_that_does_not_parse_gets_the_whole_file(self):
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/clip.mp4", Range="bytes=1000-")
        self.assertEqual((status, headers["Content-Range"], body), (416, "bytes */1000", b""))
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/clip.mp4", Range="bytes=0-1,5-9")
        self.assertEqual((status, headers["Content-Length"], body), (200, "1000", MEDIA))

    def test_audio_and_video_answer_without_a_sandbox_and_an_image_keeps_it(self):
        """pack sd:7513: Open loads a file as a top-level document. Under `sandbox` a media document has origin null,
        and Chrome blocks its own load (CORS, ERR_FAILED), so nothing plays; an image, and above all an SVG, keeps it."""
        cat = self.root / "example" / "art" / "shirts" / "cat"
        (cat / "media" / "now.mp3").write_bytes(MEDIA)
        (cat / "candidates" / "mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        for tail, status, headers in (("media/now.mp3", 200, {}), ("media/clip.mp4", 200, {}),
                                      ("media/clip.mp4", 206, {"Range": "bytes=0-9"}),
                                      ("media/take.wav", 416, {"Range": "bytes=1000-"})):
            with self.subTest(tail=tail, **headers):
                got, answer, _ = self.fetch(f"/studio/files/art/shirts/cat/{tail}", **headers)
                policy = answer["Content-Security-Policy"]
                self.assertEqual(got, status)
                self.assertNotIn("sandbox", policy)
                self.assertIn("default-src 'none'", policy)
                self.assertIn("media-src 'self'", policy)
                self.assertEqual(answer["X-Content-Type-Options"], "nosniff")
        for tail in ("candidates/mark.svg", "candidates/one.png"):
            with self.subTest(tail=tail):
                got, answer, _ = self.fetch(f"/studio/files/art/shirts/cat/{tail}")
                self.assertEqual((got, answer["Content-Security-Policy"], answer["X-Content-Type-Options"]),
                                 (200, studio.POLICY, "nosniff"))
                self.assertTrue(studio.POLICY.startswith("sandbox;"))

    def test_an_image_ignores_a_range(self):
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/candidates/one.png", Range="bytes=0-1")
        self.assertEqual((status, body, headers.get("Accept-Ranges")), (200, b"\x89PNG one", None))

    def test_a_songs_final_video_is_served_and_another_file_of_its_folder_is_404(self):
        song = self.root / "example" / "art" / "songs" / "tune"
        song.mkdir(parents=True)
        (song / "project.json").write_text(json.dumps({"kind": "song", "title": "Tune"}), encoding="utf-8")
        (song / "final-video.mp4").write_bytes(MEDIA)
        (song / "other.mp4").write_bytes(MEDIA)
        status, headers, body = self.fetch("/studio/files/art/songs/tune/final-video.mp4", Range="bytes=0-9")
        self.assertEqual((status, body, headers["Content-Security-Policy"]), (206, MEDIA[:10], studio.MEDIA_POLICY))
        self.assertEqual(self.fetch("/studio/files/art/songs/tune/other.mp4")[0], 404)

    def test_a_path_outside_its_roots_answers_404(self):
        for tail in ("art/shirts/cat/stray.png", "art/shirts/cat/previews/secret.png", "art/shirts/cat/candidates/.hidden.png",
                     "art/shirts/cat/candidates/link.png", "art/shirts/cat/candidates/out.png",
                     "art/shirts/cat/candidates/notes.md", "art/shirts/cat/candidates/../stray.png",
                     "art/shirts/cat/candidates/%2e%2e/stray.png", "art/shirts/cat/project.json", "missing/a.png", "art"):
            with self.subTest(tail=tail):
                self.assertEqual(self.fetch(f"/studio/files/{tail}")[0], 404)

    def test_a_file_without_a_session_is_refused(self):
        request = urllib.request.Request(self.base + "/studio/files/art/shirts/cat/candidates/one.png")
        with self.assertRaises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=patience(self.http_timeout))
        refused.exception.close()
        self.assertEqual(refused.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
