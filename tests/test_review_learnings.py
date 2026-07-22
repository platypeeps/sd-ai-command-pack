from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
hashlib = _support.hashlib
importlib = _support.importlib
io = _support.io
json = _support.json
os = _support.os
re = _support.re
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
yaml = _support.yaml
install = _support.install
PACK_ROOT = _support.PACK_ROOT
INSTALLER = _support.INSTALLER
SECRET_MARKER_PATTERNS = _support.SECRET_MARKER_PATTERNS
InstallTestCase = _support.InstallTestCase


class ReviewLearningsTests(InstallTestCase):
    """Tests for review-learning detection and managed-block updates."""

    def test_learnings_survive_non_object_graphql_payload(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_payloads",
        )
        with mock.patch.object(learnings, "_run_gh_json", return_value=None):
            comments = learnings.fetch_recent_copilot_comments(
                Path("."), days=7, limit=5, github_repo="owner/name"
            )
        self.assertEqual(comments, [])

    def test_review_window_pages_to_exact_cutoff_and_reports_inventory(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_pagination",
        )
        calls: list[list[str]] = []

        def fake_run_gh_json(args: list[str], repo_root: Path):
            calls.append(args)
            query = next(value for value in args if value.startswith("query="))
            if "pullRequests(first:100" in query:
                if any(value == "endCursor=page-2" for value in args):
                    return {
                        "data": {
                            "repository": {
                                "pullRequests": {
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    "nodes": [
                                        {
                                            "number": 1,
                                            "title": "old",
                                            "url": "https://example.test/1",
                                            "updatedAt": "2000-01-01T00:00:00Z",
                                        }
                                    ],
                                }
                            }
                        }
                    }
                return {
                    "data": {
                        "repository": {
                            "pullRequests": {
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "page-2",
                                },
                                "nodes": [
                                    {
                                        "number": 7,
                                        "title": "current",
                                        "url": "https://example.test/7",
                                        "updatedAt": "2999-01-01T00:00:00Z",
                                    }
                                ],
                            }
                        }
                    }
                }
            return {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    {
                                        "isResolved": True,
                                        "isOutdated": False,
                                        "path": "src/current.py",
                                        "comments": {
                                            "nodes": [
                                                {
                                                    "author": {
                                                        "login": module.COPILOT_LOGIN
                                                    },
                                                    "body": "Add a boundary fixture.",
                                                }
                                            ]
                                        },
                                    }
                                ]
                            }
                        }
                    }
                }
            }

        with mock.patch.object(module, "_run_gh_json", fake_run_gh_json):
            window = module.fetch_recent_copilot_review_window(
                Path("."),
                days=2,
                github_repo="owner/name",
            )

        self.assertEqual(window.prs_inspected, 1)
        self.assertFalse(window.truncated)
        self.assertEqual(len(window.comments), 1)
        inventory_query = next(
            value
            for call in calls
            for value in call
            if value.startswith("query=") and "pullRequests(first:100" in value
        )
        self.assertIn("states:[OPEN,MERGED,CLOSED]", inventory_query)
        self.assertTrue(
            any("endCursor=page-2" in call for call in calls),
            calls,
        )

    def test_review_window_limit_is_explicitly_truncated(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_limit",
        )
        payload = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "number": number,
                                "title": f"PR {number}",
                                "url": f"https://example.test/{number}",
                                "updatedAt": "2999-01-01T00:00:00Z",
                            }
                            for number in (1, 2)
                        ],
                    }
                }
            }
        }

        with mock.patch.object(module, "_run_gh_json", return_value=payload):
            window = module.fetch_recent_copilot_review_window(
                Path("."),
                days=2,
                limit=1,
                github_repo="owner/name",
            )

        self.assertEqual(window.prs_inspected, 1)
        self.assertTrue(window.truncated)

    def test_explicit_pr_review_window_is_bounded_to_requested_pr(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_explicit_pr",
        )
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "path": "src/example.py",
                                    "comments": {
                                        "nodes": [
                                            {
                                                "author": {
                                                    "login": module.COPILOT_LOGIN
                                                },
                                                "body": "Cover the failure path.",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        with mock.patch.object(module, "_run_gh_json", return_value=payload):
            window = module.fetch_copilot_review_for_prs(
                Path("."),
                pr_numbers=[42, 42],
                github_repo="owner/name",
            )

        self.assertEqual(window.prs_inspected, 1)
        self.assertEqual(window.cutoff, None)
        self.assertFalse(window.truncated)
        self.assertEqual(window.comments[0].pr_number, 42)
        self.assertEqual(
            window.comments[0].pr_url,
            "https://github.com/owner/name/pull/42",
        )

    def test_learnings_neutralize_embedded_managed_markers(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_markers",
        )
        comment = learnings.PullRequestComment(
            pr_number=1,
            pr_title="t",
            pr_url=f"https://example.invalid/{learnings.MANAGED_START}/1",
            path=f"docs/{learnings.MANAGED_END}.md",
            body=f"evil {learnings.MANAGED_END} splice",
            is_resolved=False,
            is_outdated=False,
        )
        rendered = comment.markdown_item()
        self.assertNotIn(learnings.MANAGED_END, rendered)
        self.assertNotIn(learnings.MANAGED_START, rendered)
        self.assertIn("[managed-end marker removed]", rendered)
        self.assertIn("[managed-start marker removed]", rendered)

        finding = learnings.Finding(
            category="env",
            path=f"docs/{learnings.MANAGED_END}.md",
            lineno=3,
            detail=f"uses {learnings.MANAGED_START} somewhere",
            recommendation=f"drop {learnings.MANAGED_END} now",
        )
        rendered = finding.markdown_item()
        self.assertNotIn(learnings.MANAGED_END, rendered)
        self.assertNotIn(learnings.MANAGED_START, rendered)

    def test_learnings_render_historical_markdown_sensitive_remote_paths(
        self,
    ) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_remote_paths",
        )
        comment = learnings.PullRequestComment(
            pr_number=17,
            pr_title="historical",
            pr_url="https://github.com/owner/repo/pull/17",
            path="archive/odd`path[1].md\ncontinued",
            body="Mentions `docs/remote-missing.md` from the old head.",
            is_resolved=True,
            is_outdated=False,
        )

        rendered = comment.markdown_item()

        self.assertIn("**historical** PR #17", rendered)
        self.assertIn("`` archive/odd`path[1].md continued ``", rendered)
        self.assertIn("`docs/remote-missing.md`", rendered)
        self.assertNotIn("\n", rendered)

    def test_historical_signals_cluster_while_current_comments_stay_individual(
        self,
    ) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_clusters",
        )
        current = learnings.PullRequestComment(
            pr_number=212,
            pr_title="current",
            pr_url="https://github.com/owner/repo/pull/212",
            path="scripts/current.py",
            body="Validate the current boundary before publishing.",
            is_resolved=False,
            is_outdated=False,
            created_at="2026-07-21T12:00:00Z",
        )
        historical = [
            learnings.PullRequestComment(
                pr_number=206,
                pr_title="historical",
                pr_url="https://github.com/owner/repo/pull/206",
                path=f"docs/surface-{index}.md",
                body=(
                    "Use tracked-diff terminology in the documentation."
                    if index < 3
                    else "Align the tracked diff wording with the documented contract."
                ),
                is_resolved=True,
                is_outdated=False,
                created_at=f"2026-07-{10 + index:02d}T12:00:00Z",
            )
            for index in range(5)
        ]

        rendered = learnings.render_managed_block([], historical + [current])

        self.assertLess(
            rendered.index("#### Current Actionable Comments"),
            rendered.index("#### Historical Signal Clusters"),
        )
        self.assertEqual(rendered.count("**current** PR #212"), 1)
        self.assertEqual(rendered.count("**Contract/documentation drift**"), 2)
        self.assertIn("5 historical comment(s) across 2 normalized signature(s)", rendered)
        self.assertIn("observed 2026-07-10 to 2026-07-14", rendered)
        self.assertIn("examples 2/5", rendered)
        self.assertNotIn("**historical** PR #206", rendered)

    def test_cluster_rendering_is_deterministic_for_shuffled_input(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_cluster_order",
        )
        comments = [
            learnings.PullRequestComment(
                pr_number=number,
                pr_title="historical",
                pr_url=f"https://github.com/owner/repo/pull/{number}",
                path=path,
                body=body,
                is_resolved=True,
                is_outdated=False,
                created_at=created_at,
            )
            for number, path, body, created_at in (
                (3, "tests/a.py", "Add a failure fixture.", "2026-07-03T00:00:00Z"),
                (1, "docs/a.md", "Align the contract wording.", "2026-07-01T00:00:00Z"),
                (2, "docs/b.md", "Align the contract wording.", "2026-07-02T00:00:00Z"),
            )
        ]

        forward = learnings.render_managed_block([], comments)
        reversed_render = learnings.render_managed_block([], list(reversed(comments)))

        self.assertEqual(forward, reversed_render)
        self.assertLess(
            forward.index("**Contract/documentation drift**"),
            forward.index("**Reviewer/test harness quality**"),
        )

    def test_signal_category_recognizes_installed_generated_surfaces(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_generated_surfaces",
        )
        paths = (
            ".claude/commands/sd/review-learnings.md",
            ".github/prompts/sd-review-learnings.prompt.md",
            ".opencode/commands/sd-review-learnings.md",
            ".gemini/commands/sd/review-learnings.toml",
            ".agent/workflows/sd-review-learnings.md",
            ".sd-ai-command-pack/manifest.json",
            ".prism/rules.json",
            "scripts/sd-ai-command-pack-review-learnings.py",
            "scripts/sd_ai_command_pack_lib.py",
            "docs/SD_AI_COMMAND_PACK.md",
        )

        for index, path in enumerate(paths, start=1):
            with self.subTest(path=path):
                comment = learnings.PullRequestComment(
                    pr_number=index,
                    pr_title="historical",
                    pr_url=f"https://github.com/owner/repo/pull/{index}",
                    path=path,
                    body="Keep this installed surface aligned.",
                    is_resolved=True,
                    is_outdated=False,
                )
                self.assertEqual(
                    learnings._signal_category(comment),
                    learnings.SIGNAL_GENERATED_SURFACES,
                )

    def test_cluster_output_reports_all_evidence_bounds(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_cluster_bounds",
        )
        category_samples = (
            (".trellis/tasks/x/task.json", "The task metadata has the wrong base branch."),
            ("src/input.py", "Validate the untrusted boundary."),
            ("docs/contract.md", "Align the documentation contract wording."),
            ("templates/tool.py", "Keep the generated copy in sync."),
            ("tests/test_tool.py", "Add a direct failure fixture."),
            ("misc/note.txt", "Clarify this unusual edge case."),
        )
        comments = []
        for category_index, (path, body) in enumerate(category_samples):
            for observation in range(9):
                comments.append(
                    learnings.PullRequestComment(
                        pr_number=100 + category_index * 10 + observation,
                        pr_title="historical",
                        pr_url=(
                            "https://github.com/owner/repo/pull/"
                            f"{100 + category_index * 10 + observation}"
                        ),
                        path=(
                            path
                            if observation == 0
                            else f"{path.rsplit('/', 1)[0]}/surface-{observation}.md"
                        ),
                        body=f"{body} Observation {observation}.",
                        is_resolved=True,
                        is_outdated=False,
                        created_at=f"2026-06-{observation + 1:02d}T00:00:00Z",
                    )
                )

        rendered = learnings.render_managed_block([], comments)

        self.assertIn("Historical clusters truncated: showing 5 of 6 categories", rendered)
        self.assertIn("signatures 4/9", rendered)
        self.assertIn("PRs 8/9", rendered)
        self.assertIn("examples 3/9", rendered)

    def test_preventive_actions_require_a_detected_recurring_category(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_preventive_actions",
        )
        comments = [
            learnings.PullRequestComment(
                pr_number=number,
                pr_title="historical",
                pr_url=f"https://github.com/owner/repo/pull/{number}",
                path=path,
                body=body,
                is_resolved=True,
                is_outdated=False,
                created_at="2026-07-20T00:00:00Z",
            )
            for number, path, body in (
                (1, "docs/a.md", "Align the contract wording."),
                (2, "docs/b.md", "Align the contract wording."),
                (3, ".trellis/tasks/x/task.json", "Fix the task metadata."),
            )
        ]

        rendered = learnings.render_managed_block([], comments)
        actions = rendered.split("### Suggested Preventive Actions", 1)[1]

        self.assertIn("**Contract/documentation drift** (2 historical comments)", actions)
        self.assertNotIn("**Task metadata**", actions)
        self.assertNotIn("Move repeated mechanical findings", actions)

    def test_learnings_truncate_summaries_at_word_boundaries(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_truncation",
        )

        self.assertEqual(
            learnings._one_line("alpha beta gamma delta", limit=15),
            "alpha beta...",
        )
        self.assertEqual(
            learnings._one_line("supercalifragilistic", limit=10),
            "superca...",
        )
        self.assertEqual(learnings._one_line("alpha beta", limit=3), "...")

    def test_learnings_report_when_no_base_ref_resolves(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="sd-learnings-no-remote-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.run_git(root, "init", "--quiet")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("# base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "seed")

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no base ref could be resolved", result.stderr)
        self.assertIn("no local review-cycle findings detected", result.stdout)

    def test_review_learnings_script_detects_local_patterns(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nscratch=\"$(mktemp)\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+scratch=\"$(mktemp)\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[sd-review-learnings:portability]", result.stdout)
        self.assertIn("mktemp", result.stdout)

    def test_review_learnings_script_detects_positional_negative_offset(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nlast=\"${@: -1}\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+last=\"${@: -1}\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[sd-review-learnings:portability]", result.stdout)
        self.assertIn("negative array offsets", result.stdout)

    def test_review_learnings_script_allows_shell_default_expansions(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nmode=\"${TOOL_MODE:-0}\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+mode=\"${TOOL_MODE:-0}\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no local review-cycle findings detected", result.stdout)

    def test_review_learnings_script_negative_offset_regex_is_specific(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_regex_test",
        )

        self.assertIsNotNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${@: -1}"))
        self.assertIsNotNone(
            module._NEGATIVE_ARRAY_OFFSET_RE.search("${items[@]: -1}")
        )
        self.assertIsNotNone(
            module._NEGATIVE_ARRAY_OFFSET_RE.search("${items[-1]}")
        )
        self.assertIsNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${VALUE:-1}"))
        self.assertIsNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${value: -1}"))

    def test_review_learnings_script_extracts_explicit_env_refs_only(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_env_regex_test",
        )

        self.assertEqual(
            module._extract_env_refs(
                'echo "$SD_FOO" "${GH_BAR}" "${SD_DEFAULT:-0}" SD_BARE',
                ("SD", "GH"),
            ),
            {"SD_FOO", "GH_BAR", "SD_DEFAULT"},
        )

    def test_review_learnings_script_updates_managed_block(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        target = root / "docs/review-learnings.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Review Learnings\n\nHuman notes stay.\n", encoding="utf-8")
        diff = root / "diff.patch"
        diff.write_text("", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
                "--update",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        content = target.read_text(encoding="utf-8")
        self.assertIn("Human notes stay.", content)
        self.assertIn("<!-- sd-review-learnings:start -->", content)
        self.assertIn("No local review-cycle findings detected", content)

    def test_review_learnings_update_uses_atomic_write(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_atomic_write",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-atomic-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "docs/review-learnings.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        original = "# Review Learnings\n\nHuman notes stay.\n"
        target.write_text(original, encoding="utf-8")
        block = module.render_managed_block([], [])

        with mock.patch.object(module.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(OSError, "blocked"):
                module.update_target(target, block, dry_run=False)

        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(list(target.parent.glob(".*.tmp")), [])

    def test_review_learnings_script_rejects_malformed_payload_helpers(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_test",
        )

        with self.assertRaisesRegex(TypeError, "expected object"):
            module._as_dict(None)
        with self.assertRaisesRegex(TypeError, "expected list"):
            module._as_list({})

    def test_review_learnings_main_reports_malformed_payload_without_traceback(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_main_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                with mock.patch.object(
                    module,
                    "fetch_recent_copilot_review_window",
                    side_effect=TypeError("expected list in review learnings payload"),
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        result = module.main(
                            [
                                "--repo-root",
                                tempdir.name,
                                "--github-days",
                                "1",
                            ]
                        )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())
        self.assertIn("expected list in review learnings payload", stderr.getvalue())

    def test_review_learnings_main_reports_git_command_error_without_traceback(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_git_command_error_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)

        with mock.patch.object(
            module,
            "run_git_command",
            side_effect=module.CommandError("git timed out after 60s"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = module.main(["--repo-root", tempdir.name])

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:findings]", stderr.getvalue())
        self.assertIn("git timed out after 60s", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_review_learnings_main_reports_gh_command_error_without_traceback(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_gh_command_error_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        diff_file = Path(tempdir.name) / "empty.diff"
        diff_file.write_text("", encoding="utf-8")

        with mock.patch.object(
            module,
            "run_gh_command",
            side_effect=module.CommandError("gh timed out after 120s"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = module.main(
                    [
                        "--repo-root",
                        tempdir.name,
                        "--diff-from",
                        str(diff_file),
                        "--github-days",
                        "1",
                        "--github-repo",
                        "owner/repo",
                    ]
                )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())
        self.assertIn("gh timed out after 120s", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_review_learnings_script_rejects_invalid_managed_marker_order(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_marker_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:end -->\n"
            "old\n"
            "<!-- sd-review-learnings:start -->\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "invalid order"):
            module.update_target(target, "<!-- sd-review-learnings:start -->\nnew\n<!-- sd-review-learnings:end -->\n", dry_run=False)

    def test_review_learnings_main_reports_invalid_managed_marker_order(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_marker_main_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        target = root / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:end -->\n"
            "old\n"
            "<!-- sd-review-learnings:start -->\n",
            encoding="utf-8",
        )

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = module.main(
                        [
                            "--repo-root",
                            str(root),
                            "--target",
                            str(target),
                            "--update",
                        ]
                    )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:update]", stderr.getvalue())
        self.assertIn("invalid order", stderr.getvalue())

    def test_review_learnings_script_preserves_text_after_managed_block(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_layout_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:start -->\n"
            "old\n"
            "<!-- sd-review-learnings:end -->\n"
            "Human notes stay.\n",
            encoding="utf-8",
        )

        module.update_target(
            target,
            "<!-- sd-review-learnings:start -->\n"
            "new\n"
            "<!-- sd-review-learnings:end -->\n",
            dry_run=False,
        )

        content = target.read_text(encoding="utf-8")
        self.assertIn("<!-- sd-review-learnings:end -->\nHuman notes stay.", content)

    def test_review_learnings_script_skips_incomplete_github_payloads(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_github_payload_test",
        )

        def fake_run_gh_json(args: list[str], repo_root: Path):
            if args[:2] == ["pr", "list"]:
                return [{"number": 1, "title": "PR", "url": "https://example.test/pr/1"}]
            return {"errors": [{"message": "rate limited"}]}

        with mock.patch.object(module, "github_repo_slug", return_value=("owner", "repo")):
            with mock.patch.object(module, "_run_gh_json", fake_run_gh_json):
                comments = module.fetch_recent_copilot_comments(
                    Path("."),
                    days=1,
                    limit=1,
                )

        self.assertEqual(comments, [])

    def test_review_learnings_script_resolves_github_repo_generically(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        ).read_text(encoding="utf-8")

        self.assertIn("gh", script)
        self.assertIn("repo", script)
        self.assertIn("nameWithOwner", script)
        self.assertNotIn("answerbook", script)
        self.assertNotIn("mezmo_benchmark", script)

    def test_review_learnings_reports_subprocess_timeout_as_setup_failure(
        self,
    ) -> None:
        # Regression: a hung git/gh call must surface the [sd-review-learnings:*]
        # exit-2 contract, not a raw subprocess.TimeoutExpired traceback.
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_timeout_regression",
        )
        root = self.make_repo()

        with mock.patch.object(
            module,
            "build_local_diff",
            side_effect=RuntimeError("git timed out after 120s"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = module.main(["--repo-root", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("[sd-review-learnings:findings]", stderr.getvalue())

        diff_file = root / "empty.diff"
        diff_file.write_text("", encoding="utf-8")
        with mock.patch.object(
            module,
            "fetch_recent_copilot_review_window",
            side_effect=RuntimeError("gh timed out after 60s"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = module.main(
                    [
                        "--repo-root",
                        str(root),
                        "--diff-from",
                        str(diff_file),
                        "--github-days",
                        "7",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())

    def test_review_learnings_untracked_listing_failure_raises_runtime_error(
        self,
    ) -> None:
        # A nonzero `git ls-files` exit must surface as RuntimeError carrying
        # git's stderr, with a stable fallback message when stderr is blank.
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_untracked_failure",
        )
        failed_result = subprocess.CompletedProcess(
            args=["git"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository\n",
        )

        with mock.patch.object(module, "run_git_command", return_value=failed_result):
            with self.assertRaisesRegex(RuntimeError, "not a git repository"):
                module._git_untracked_paths(Path("."))

        blank_result = subprocess.CompletedProcess(
            args=["git"],
            returncode=1,
            stdout="",
            stderr="  \n",
        )

        with mock.patch.object(module, "run_git_command", return_value=blank_result):
            with self.assertRaisesRegex(RuntimeError, "git ls-files failed"):
                module._git_untracked_paths(Path("."))

    def test_review_learnings_working_tree_diff_includes_untracked_files(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_untracked_diff",
        )
        root = Path(tempfile.mkdtemp(prefix="sd-learnings-untracked-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.run_git(root, "init", "--quiet")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("# base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "--quiet", "-m", "seed")

        (root / "README.md").write_text(
            "# base\ntracked-change-line\n", encoding="utf-8"
        )
        untracked = root / "notes" / "untracked.md"
        untracked.parent.mkdir()
        untracked.write_text("untracked-learning-line\n", encoding="utf-8")
        # Untracked-but-not-a-regular-file entries must be skipped, not diffed.
        (root / "dangling-link").symlink_to("missing-target")

        diff_text = module.build_local_diff(root, base=None, include_working_tree=True)

        self.assertIn("+tracked-change-line", diff_text)
        self.assertIn("notes/untracked.md", diff_text)
        self.assertIn("+untracked-learning-line", diff_text)
        self.assertNotIn("dangling-link", diff_text)


if __name__ == "__main__":
    unittest.main()
