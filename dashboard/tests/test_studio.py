"""Studio, slice 2 (sd:6920): the projects it lists, the files it serves, and the ranges it answers.

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

    def test_a_repo_root_that_does_not_resolve_is_a_problem_not_an_empty_list(self):
        missing = Path(self.tmp.name) / "no-such-root"
        doc = studio.document(self.connection, now="2026-11-01T07:00:00Z", repo_root=missing)
        self.assertEqual(doc["projects"], [])
        self.assertEqual(len(doc["problems"]), 1, doc["problems"])
        self.assertTrue(doc["problems"][0].startswith(f"REPO_ROOT {missing} does not resolve: "), doc["problems"])

    def test_two_registered_repositories_with_one_name_are_neither_served(self):
        twin = self.root / "other" / "art"
        (twin / "p").mkdir(parents=True)
        (twin / "p" / "project.json").write_text('{"kind": "song"}', encoding="utf-8")
        register(self.connection, twin)
        doc = self.read()
        self.assertEqual(doc["projects"], [])
        self.assertEqual(doc["problems"], ["Two registered repositories are named art: neither is served."])
        self.assertIsNone(studio.located(self.connection, "art/shirts/cat/candidates/one.png", self.root))


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
    api = ("/api/studio",)


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

    def test_every_gallery_file_the_api_lists_answers_200_under_a_sandbox(self):
        doc = json.loads(self.fetch("/api/studio")[2])
        paths = [f["path"] for p in doc["projects"] for r in p["roots"] for f in r["files"]]
        self.assertEqual(len(paths), 3)
        for path in paths:
            with self.subTest(path=path):
                status, headers, _ = self.fetch(f"/studio/files/art/{path}")
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Security-Policy"], studio.POLICY)
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

    def test_scan_problems_show_before_the_page_says_no_project_json_exists(self):
        """sd:7151: a scan that could not read a folder found nothing it can vouch for, so the page names the problem."""
        doc = {"read": "2026-11-01T07:00:00Z", "root": "/repos", "projects": [], "attention": {"state": "caution", "n": 1, "what": "x"},
               "problems": ["art: songs could not be read: [Errno 13] Permission denied",
                            "Two registered repositories are named twin: neither is served."]}
        out = self.run_page(doc, "R.details = ELS.details.html;")
        last = out["states"][-1]
        self.assertEqual(last["kind"], "partial", out["states"])
        self.assertTrue(last["text"].startswith("art: songs could not be read: [Errno 13] Permission denied · Two registered "
                                                "repositories are named twin: neither is served. No project was read"), last["text"])
        self.assertIn("The scan named a problem, so nothing is selected.", out["R"]["details"])
        self.assertNotIn("No project.json is under the repositories", json.dumps(out["states"]) + out["R"]["details"])
        out = self.run_page({**doc, "problems": []}, "R.details = ELS.details.html;")
        self.assertEqual(out["states"][-1]["kind"], "empty")
        self.assertIn("No project.json is under the repositories yet.", out["R"]["details"])

    def test_a_range_on_an_mp4_answers_206_with_its_bytes(self):
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/clip.mp4", Range="bytes=0-99")
        self.assertEqual((status, headers["Content-Range"], headers["Accept-Ranges"], body), (206, "bytes 0-99/1000", "bytes", MEDIA[:100]))
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/take.wav", Range="bytes=-10")
        self.assertEqual((status, headers["Content-Range"], body), (206, "bytes 990-999/1000", MEDIA[990:]))

    def test_a_range_past_the_end_is_416_and_one_that_does_not_parse_gets_the_whole_file(self):
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/clip.mp4", Range="bytes=1000-")
        self.assertEqual((status, headers["Content-Range"], body), (416, "bytes */1000", b""))
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/media/clip.mp4", Range="bytes=0-1,5-9")
        self.assertEqual((status, headers["Content-Length"], body), (200, "1000", MEDIA))

    def test_an_image_ignores_a_range(self):
        status, headers, body = self.fetch("/studio/files/art/shirts/cat/candidates/one.png", Range="bytes=0-1")
        self.assertEqual((status, body, headers.get("Accept-Ranges")), (200, b"\x89PNG one", None))

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
