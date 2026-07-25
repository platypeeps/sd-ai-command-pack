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

    def test_review_window_marks_unread_pages_as_truncated(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_thread_bounds",
        )
        payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": True},
                            "nodes": [
                                {
                                    "isResolved": True,
                                    "isOutdated": False,
                                    "path": "scripts/controller.py",
                                    "comments": {
                                        "pageInfo": {"hasNextPage": True},
                                        "nodes": [
                                            {
                                                "author": {"login": module.COPILOT_LOGIN},
                                                "body": "Validate the boundary.",
                                                "createdAt": "2026-07-24T00:00:00Z",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        }

        with mock.patch.object(module, "_run_gh_json", return_value=payload):
            window = module.fetch_copilot_review_for_prs(
                Path("."),
                pr_numbers=[7],
                github_repo="owner/name",
            )

        self.assertEqual(len(window.comments), 1)
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

    def test_cluster_signature_examples_use_safe_markdown_code_spans(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_signature_markdown",
        )
        cluster = learnings.HistoricalSignalCluster(
            category=learnings.SIGNAL_CONTRACT_DOCUMENTATION,
            count=3,
            signature_count=2,
            pr_numbers=(214,),
            path_families=("docs",),
            first_seen="2026-07-21",
            last_seen="2026-07-22",
            signature_examples=(("Use `docs/a.md` and **bold**.", 2), ("Plain.", 1)),
            examples=(),
        )

        rendered = "\n".join(cluster.markdown_items())

        self.assertIn(
            "Representative signatures: `` Use `docs/a.md` and **bold**. `` (x2); "
            "`Plain.` (x1)",
            rendered,
        )

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
            ".github/agents/trellis-check.agent.md",
            ".github/copilot/hooks/trellis-context.js",
            ".github/hooks/trellis.json",
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

    def test_signal_category_recognizes_singular_and_plural_test_directories(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_test_directories",
        )

        for index, directory in enumerate(("test", "tests"), start=1):
            path = f"{directory}/metadata.test.js"
            with self.subTest(path=path):
                comment = learnings.PullRequestComment(
                    pr_number=index,
                    pr_title="historical",
                    pr_url=f"https://github.com/owner/repo/pull/{index}",
                    path=path,
                    body="Clarify this edge case.",
                    is_resolved=True,
                    is_outdated=False,
                )
                self.assertEqual(learnings._path_family(path), "tests")
                self.assertEqual(
                    learnings._signal_category(comment),
                    learnings.SIGNAL_REVIEWER_TEST_HARNESS,
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
        actions = rendered.split("### Suggested Preventive Actions", 1)[1]
        self.assertNotIn("**Task metadata**", actions)

    def test_planning_signal_exposes_bounded_cluster_contract(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_planning_contract",
        )
        raw_body = "Validate the boundary and failure matrix. " + "private detail " * 30
        comments = [
            learnings.PullRequestComment(
                pr_number=200 + index,
                pr_title="historical",
                pr_url=f"https://github.com/owner/repo/pull/{200 + index}",
                path=f"scripts/state-controller-{index}.py",
                body=f"{raw_body}{index}",
                is_resolved=True,
                is_outdated=False,
                created_at=f"2026-07-{10 + index:02d}T00:00:00Z",
            )
            for index in range(6)
        ]
        window = learnings.CopilotReviewWindow(
            tuple(comments),
            6,
            "2026-07-01T00:00:00Z",
            False,
        )

        signal = learnings.build_review_learning_signal(
            comments,
            window,
            changed_paths=("scripts/review-state-controller.py",),
            requested=True,
        )

        self.assertEqual(signal["schemaVersion"], 1)
        self.assertEqual(signal["selection"]["familyIds"], ["boundary-validation"])
        self.assertEqual(len(signal["historicalClusters"]), 1)
        cluster = signal["applicableClusters"][0]
        self.assertEqual(cluster["familyId"], "boundary-validation")
        self.assertEqual(cluster["commentCount"], 6)
        self.assertTrue(cluster["truncation"]["occurred"])
        self.assertEqual(
            cluster["representativeSignatures"][0]["summary"],
            cluster["representativeSignatures"][0]["summary"].lower(),
        )
        self.assertFalse(signal["confidenceCredit"]["granted"])
        serialized = json.dumps(signal, sort_keys=True)
        self.assertNotIn(raw_body, serialized)
        self.assertNotIn("private detail " * 10, serialized)

    def test_planning_signal_selects_only_relevant_path_families(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_planning_selection",
        )
        comments = [
            learnings.PullRequestComment(
                pr_number=1,
                pr_title="historical",
                pr_url="https://github.com/owner/repo/pull/1",
                path="scripts/state-controller.py",
                body="Validate the state boundary.",
                is_resolved=True,
                is_outdated=False,
            ),
            learnings.PullRequestComment(
                pr_number=2,
                pr_title="historical",
                pr_url="https://github.com/owner/repo/pull/2",
                path="docs/contract.md",
                body="Align the documentation contract.",
                is_resolved=True,
                is_outdated=False,
            ),
        ]
        window = learnings.CopilotReviewWindow(tuple(comments), 2, None, False)

        controller = learnings.build_review_learning_signal(
            comments,
            window,
            changed_paths=("scripts/state-controller.py",),
            requested=True,
        )
        documentation = learnings.build_review_learning_signal(
            comments,
            window,
            changed_paths=("docs/operator-guide.md",),
            requested=True,
        )

        self.assertEqual(
            [item["familyId"] for item in controller["applicableClusters"]],
            ["boundary-validation"],
        )
        self.assertEqual(
            [item["familyId"] for item in documentation["applicableClusters"]],
            ["contract-documentation-drift"],
        )
        self.assertNotIn(
            "boundary-validation",
            documentation["selection"]["familyIds"],
        )

    def test_planning_signal_reports_tracked_snapshot_freshness(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_snapshot_status",
        )
        comment = module.PullRequestComment(
            pr_number=12,
            pr_title="historical",
            pr_url="https://github.com/owner/repo/pull/12",
            path="docs/contract.md",
            body="Align the documentation contract.",
            is_resolved=True,
            is_outdated=False,
            created_at="2026-07-24T12:00:00Z",
        )
        window = module.CopilotReviewWindow((comment,), 1, None, False)

        def signal(snapshot: str, *, exists: bool = True):
            return module.build_review_learning_signal(
                [comment],
                window,
                changed_paths=("docs/guide.md",),
                requested=True,
                snapshot_text=snapshot,
                snapshot_exists=exists,
            )["trackedSnapshot"]

        stale = signal(
            f"{module.MANAGED_START}\n_Last updated: 2026-07-21_\n{module.MANAGED_END}\n"
        )
        current = signal(
            f"{module.MANAGED_START}\n_Last updated: 2026-07-24_\n{module.MANAGED_END}\n"
        )
        invalid = signal(
            f"{module.MANAGED_START}\n_Last updated: 2026-99-99_\n{module.MANAGED_END}\n"
        )
        missing = signal("", exists=False)

        self.assertEqual(stale["status"], "stale")
        self.assertTrue(stale["updateRecommended"])
        self.assertEqual(current["status"], "current")
        self.assertFalse(current["updateRecommended"])
        self.assertEqual(invalid["status"], "unknown")
        self.assertEqual(missing["status"], "missing")
        self.assertTrue(missing["updateRecommended"])

    def test_review_attempt_cache_reuses_one_scan_with_private_receipt(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_attempt_cache",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-attempt-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        repo = base / "repo"
        repo.mkdir()
        artifact_root = base / "artifacts"
        calls = 0
        comment = learnings.PullRequestComment(
            pr_number=7,
            pr_title="historical",
            pr_url="https://github.com/owner/repo/pull/7",
            path="scripts/controller.py",
            body="Validate the boundary.",
            is_resolved=True,
            is_outdated=False,
            created_at="2026-07-24T00:00:00Z",
        )

        def fetch_window():
            nonlocal calls
            calls += 1
            return learnings.CopilotReviewWindow((comment,), 1, None, False)

        now = learnings.dt.datetime(2026, 7, 24, tzinfo=learnings.dt.timezone.utc)
        arguments = {
            "repo_root": repo,
            "repository_id": "owner/repo",
            "attempt_id": "attempt-1",
            "changed_paths": ("scripts/controller.py",),
            "request": {"githubDays": 30, "githubLimit": 50},
            "fetch_window": fetch_window,
            "artifact_root": artifact_root,
        }

        first = learnings.collect_review_learning_signal_once(**arguments, now=now)
        second = learnings.collect_review_learning_signal_once(
            **arguments,
            now=now + learnings.dt.timedelta(seconds=10),
        )

        self.assertEqual(calls, 1)
        self.assertEqual(first["cache"]["status"], "miss")
        self.assertEqual(second["cache"]["status"], "hit")
        self.assertEqual(second["signal"], first["signal"])
        self.assertEqual(first["githubWatermark"], second["githubWatermark"])
        receipt_path = Path(first["cache"]["path"])
        self.assertEqual(receipt_path.stat().st_mode & 0o077, 0)
        self.assertNotIn(str(repo), receipt_path.read_text(encoding="utf-8"))
        tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
        tampered["githubWatermark"] = {"digest": "sha256:tampered"}
        receipt_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
        third = learnings.collect_review_learning_signal_once(
            **arguments,
            now=now + learnings.dt.timedelta(seconds=20),
        )
        self.assertEqual(calls, 2)
        self.assertEqual(third["cache"]["status"], "miss")

    def test_review_attempt_cache_reports_stale_and_unavailable_evidence(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_attempt_stale",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-stale-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        repo = base / "repo"
        repo.mkdir()
        artifact_root = base / "artifacts"
        now = learnings.dt.datetime(2026, 7, 24, tzinfo=learnings.dt.timezone.utc)
        comment = learnings.PullRequestComment(
            pr_number=8,
            pr_title="historical",
            pr_url="https://github.com/owner/repo/pull/8",
            path="docs/contract.md",
            body="Align the contract wording.",
            is_resolved=True,
            is_outdated=False,
        )
        common = {
            "repo_root": repo,
            "repository_id": "owner/repo",
            "attempt_id": "attempt-2",
            "changed_paths": ("docs/guide.md",),
            "request": {"githubDays": 30, "githubLimit": 50},
            "artifact_root": artifact_root,
            "ttl_seconds": 60,
        }
        learnings.collect_review_learning_signal_once(
            **common,
            fetch_window=lambda: learnings.CopilotReviewWindow((comment,), 1, None, False),
            now=now,
        )

        stale = learnings.collect_review_learning_signal_once(
            **common,
            fetch_window=lambda: (_ for _ in ()).throw(RuntimeError("rate limited")),
            now=now + learnings.dt.timedelta(seconds=61),
        )
        unavailable_calls = 0

        def unavailable_fetch():
            nonlocal unavailable_calls
            unavailable_calls += 1
            raise RuntimeError("malformed payload")

        unavailable_arguments = {
            "repo_root": repo,
            "repository_id": "owner/repo",
            "attempt_id": "attempt-3",
            "changed_paths": ("docs/guide.md",),
            "request": {"githubDays": 30, "githubLimit": 50},
            "fetch_window": unavailable_fetch,
            "artifact_root": artifact_root,
        }
        unavailable = learnings.collect_review_learning_signal_once(
            **unavailable_arguments,
            now=now,
        )
        unavailable_hit = learnings.collect_review_learning_signal_once(
            **unavailable_arguments,
            now=now + learnings.dt.timedelta(seconds=10),
        )

        self.assertEqual(stale["cache"]["status"], "stale")
        self.assertEqual(stale["signal"]["status"], "stale")
        self.assertIn("rate limited", " ".join(stale["signal"]["limitations"]))
        self.assertFalse(stale["signal"]["confidenceCredit"]["granted"])
        self.assertEqual(unavailable["signal"]["status"], "unavailable")
        self.assertIn(
            "malformed payload",
            " ".join(unavailable["signal"]["limitations"]),
        )
        self.assertFalse(unavailable["signal"]["confidenceCredit"]["granted"])
        self.assertEqual(unavailable_calls, 1)
        self.assertEqual(unavailable_hit["cache"]["status"], "hit")
        self.assertEqual(unavailable_hit["signal"], unavailable["signal"])

    def test_planning_attempt_cli_reuses_receipt_without_markdown_writes(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_planning_cli",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-cli-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        repo = base / "repo"
        repo.mkdir()
        diff = repo / "review.diff"
        diff.write_text(
            "--- a/scripts/controller.py\n"
            "+++ b/scripts/controller.py\n"
            "@@ -0,0 +1 @@\n"
            "+state = {}\n",
            encoding="utf-8",
        )
        artifact_root = base / "artifacts"
        comment = module.PullRequestComment(
            pr_number=9,
            pr_title="historical",
            pr_url="https://github.com/owner/repo/pull/9",
            path="scripts/controller.py",
            body="Validate the boundary.",
            is_resolved=True,
            is_outdated=False,
        )
        window = module.CopilotReviewWindow((comment,), 1, None, False)
        command = [
            "--repo-root",
            str(repo),
            "--diff-from",
            str(diff),
            "--github-days",
            "30",
            "--github-repo",
            "owner/repo",
            "--planning-attempt",
            "attempt-cli",
            "--review-artifact-root",
            str(artifact_root),
            "--json",
        ]

        with mock.patch.object(
            module,
            "fetch_recent_copilot_review_window",
            return_value=window,
        ) as fetch:
            outputs = []
            for _ in range(2):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(module.main(command), 0)
                outputs.append(json.loads(stdout.getvalue()))

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(outputs[0]["cache"]["status"], "miss")
        self.assertEqual(outputs[1]["cache"]["status"], "hit")
        self.assertEqual(outputs[1]["signal"], outputs[0]["signal"])
        self.assertEqual(outputs[1]["signal"]["trackedSnapshot"]["status"], "missing")
        self.assertFalse((repo / "docs").exists())

    def test_review_attempt_cache_rejects_repository_storage(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_attempt_boundary",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-boundary-")
        self.addCleanup(tempdir.cleanup)
        repo = Path(tempdir.name) / "repo"
        repo.mkdir()

        with self.assertRaisesRegex(ValueError, "outside the repository"):
            module.collect_review_learning_signal_once(
                repo_root=repo,
                repository_id="owner/repo",
                attempt_id="attempt-boundary",
                changed_paths=("docs/guide.md",),
                request={"githubDays": 30, "githubLimit": 50},
                fetch_window=lambda: module.CopilotReviewWindow((), 0, None, False),
                artifact_root=repo / ".review-artifacts",
            )

    def test_planning_arguments_are_bounded_and_mutually_exclusive(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_planning_arguments",
        )
        parser = module._build_parser()
        cases = (
            (
                ["--review-artifact-root", "/tmp/review-artifacts"],
                "--review-artifact-root requires --planning-attempt",
            ),
            (
                ["--planning-cache-ttl", "30"],
                "--planning-cache-ttl requires --planning-attempt",
            ),
            (
                ["--planning-attempt", "attempt-1"],
                "--planning-attempt requires --json",
            ),
            (
                ["--planning-attempt", "attempt-1", "--json", "--update"],
                "cannot be combined",
            ),
            (
                ["--planning-attempt", "attempt-1", "--json"],
                "requires --github-repo",
            ),
            (
                [
                    "--planning-attempt",
                    "attempt-1",
                    "--json",
                    "--github-repo",
                    "owner/repo",
                ],
                "requires --github-days or --github-pr",
            ),
            (
                [
                    "--planning-attempt",
                    "attempt-1",
                    "--json",
                    "--github-repo",
                    "owner/repo",
                    "--github-days",
                    "91",
                ],
                "limits --github-days",
            ),
            (
                [
                    "--planning-attempt",
                    "attempt-1",
                    "--json",
                    "--github-repo",
                    "owner/repo",
                    "--github-days",
                    "30",
                    "--github-limit",
                    "101",
                ],
                "limits --github-limit",
            ),
        )

        self.assertIsNone(module._planning_argument_error(parser.parse_args([])))
        for argv, expected in cases:
            with self.subTest(argv=argv):
                self.assertIn(
                    expected,
                    module._planning_argument_error(parser.parse_args(argv)) or "",
                )

        too_many_prs = [
            "--planning-attempt",
            "attempt-1",
            "--json",
            "--github-repo",
            "owner/repo",
            *[
                value
                for number in range(1, module.MAX_PLANNING_GITHUB_PRS + 2)
                for value in ("--github-pr", str(number))
            ],
        ]
        self.assertIn(
            "limits --github-pr",
            module._planning_argument_error(parser.parse_args(too_many_prs)) or "",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(module.main(["--planning-attempt", "attempt-1", "--json"]), 2)
        self.assertIn("requires --github-repo", stdout.getvalue())

    def test_planning_path_and_signal_validation_is_explicit(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_planning_validation",
        )
        invalid_paths = (
            [1],
            ["../outside.py"],
            ["x" * 501],
            [f"docs/item-{number}.md" for number in range(module.MAX_PLANNING_CHANGED_PATHS + 1)],
        )
        for paths in invalid_paths:
            with self.subTest(paths_type=type(paths[0]).__name__, count=len(paths)):
                with self.assertRaises(ValueError):
                    module._normalize_planning_changed_paths(paths)

        selected = module.planning_signal_categories(
            (
                ".trellis/tasks/example/task.json",
                "templates/scripts/generated.py",
                "tests/test_generated.py",
                "docs/contract.md",
                "scripts/review-controller.py",
            )
        )
        self.assertEqual(selected, module.SIGNAL_CATEGORY_ORDER[:-1])
        self.assertEqual(
            module.planning_signal_categories(("assets/icon.svg",)),
            (module.SIGNAL_OTHER,),
        )

        truncated_window = module.CopilotReviewWindow((), 0, None, True)
        naive_now = module.dt.datetime(2026, 7, 24)
        truncated = module.build_review_learning_signal(
            [],
            truncated_window,
            changed_paths=(),
            requested=True,
            now=naive_now,
        )
        self.assertEqual(truncated["status"], "truncated")
        self.assertIn("github-window-truncated", truncated["limitations"])
        self.assertEqual(
            module.build_review_learning_signal(
                [],
                truncated_window,
                changed_paths=(),
                requested=False,
            )["status"],
            "not-requested",
        )
        self.assertEqual(
            module.build_review_learning_signal(
                [],
                module.CopilotReviewWindow((), 0, None, False),
                changed_paths=(),
                requested=True,
                source="cached",
            )["status"],
            "cached",
        )
        with self.assertRaisesRegex(ValueError, "source"):
            module.build_review_learning_signal(
                [],
                truncated_window,
                changed_paths=(),
                requested=True,
                source="invalid",
            )
        with self.assertRaisesRegex(ValueError, "status"):
            module.build_review_learning_signal(
                [],
                truncated_window,
                changed_paths=(),
                requested=True,
                status_override="invalid",
            )

    def test_planning_cache_rejects_unsafe_inputs_and_receipts(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_cache_validation",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-security-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        repo = base / "repo"
        repo.mkdir()

        def fetch():
            return module.CopilotReviewWindow((), 0, None, False)

        common = {
            "repo_root": repo,
            "repository_id": "owner/repo",
            "attempt_id": "attempt-1",
            "changed_paths": ("docs/guide.md",),
            "request": {"githubDays": 30},
            "fetch_window": fetch,
        }

        for override in (
            {"repository_id": ""},
            {"repository_id": "owner/repo\n"},
            {"repository_id": "x" * 201},
            {"attempt_id": "unsafe attempt"},
            {"ttl_seconds": True},
            {"ttl_seconds": 0},
            {"ttl_seconds": module.MAX_PLANNING_CACHE_TTL_SECONDS + 1},
        ):
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    module.collect_review_learning_signal_once(**{**common, **override})

        with self.assertRaisesRegex(ValueError, "bounded JSON"):
            module.collect_review_learning_signal_once(
                **{**common, "request": {"bad": {1, 2}}}
            )
        with self.assertRaisesRegex(ValueError, "exceeds"):
            module.collect_review_learning_signal_once(
                **{**common, "request": {"large": "x" * module.MAX_PLANNING_REQUEST_BYTES}}
            )
        with self.assertRaisesRegex(ValueError, "absolute"):
            module.collect_review_learning_signal_once(
                **{**common, "artifact_root": Path("relative-artifacts")}
            )

        non_directory = base / "not-a-directory"
        non_directory.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "real directory"):
            module.collect_review_learning_signal_once(
                **{**common, "artifact_root": non_directory}
            )
        public_directory = base / "public"
        public_directory.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, "private permissions"):
            module.collect_review_learning_signal_once(
                **{**common, "artifact_root": public_directory}
            )

        receipt = base / "receipt.json"
        self.assertIsNone(module._load_planning_receipt(receipt))
        receipt.mkdir()
        self.assertIsNone(module._load_planning_receipt(receipt))
        receipt.rmdir()
        receipt.write_text("not-json", encoding="utf-8")
        receipt.chmod(0o600)
        self.assertIsNone(module._load_planning_receipt(receipt))
        receipt.write_text("[]\n", encoding="utf-8")
        self.assertIsNone(module._load_planning_receipt(receipt))
        receipt.write_text('{"ok": true}\n', encoding="utf-8")
        self.assertEqual(module._load_planning_receipt(receipt), {"ok": True})
        receipt.chmod(0o644)
        self.assertIsNone(module._load_planning_receipt(receipt))

        valid_signal = module.unavailable_review_learning_signal(
            changed_paths=(),
            limitation="offline",
        )
        self.assertTrue(module._valid_cached_planning_signal(valid_signal))
        for invalid in (None, {}, {**valid_signal, "status": "invalid"}):
            with self.subTest(invalid=invalid):
                self.assertFalse(module._valid_cached_planning_signal(invalid))

    def test_planning_cache_refreshes_and_handles_invalid_collectors(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_cache_refresh",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-refresh-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        repo = base / "repo"
        repo.mkdir()
        artifact_root = base / "artifacts"
        now = module.dt.datetime(2026, 7, 24)
        calls = 0

        def fetch():
            nonlocal calls
            calls += 1
            return module.CopilotReviewWindow((), 0, None, False)

        common = {
            "repo_root": repo,
            "repository_id": "owner/repo",
            "attempt_id": "attempt-refresh",
            "changed_paths": ("docs/guide.md",),
            "request": {"githubDays": 30},
            "fetch_window": fetch,
            "artifact_root": artifact_root,
            "ttl_seconds": 1,
        }
        first = module.collect_review_learning_signal_once(**common, now=now)
        refreshed = module.collect_review_learning_signal_once(
            **common,
            now=now + module.dt.timedelta(seconds=2),
        )
        self.assertEqual(calls, 2)
        self.assertEqual(first["cache"]["status"], "miss")
        self.assertEqual(refreshed["cache"]["status"], "refreshed")

        invalid = module.collect_review_learning_signal_once(
            repo_root=repo,
            repository_id="owner/repo",
            attempt_id="attempt-invalid-window",
            changed_paths=(),
            request={"githubPrs": [1]},
            fetch_window=lambda: object(),
            now=now,
        )
        self.assertEqual(invalid["cache"]["status"], "unavailable")
        self.assertIn("invalid window", " ".join(invalid["signal"]["limitations"]))

        with mock.patch.object(module, "MAX_PLANNING_RECEIPT_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "receipt exceeds"):
                module.collect_review_learning_signal_once(
                    repo_root=repo,
                    repository_id="owner/repo",
                    attempt_id="attempt-oversize",
                    changed_paths=(),
                    request={},
                    fetch_window=fetch,
                    artifact_root=base / "oversize-artifacts",
                    now=now,
                )

    def test_planning_cli_supports_explicit_prs_and_reports_collection_errors(self) -> None:
        module = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_planning_pr_cli",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learning-pr-cli-")
        self.addCleanup(tempdir.cleanup)
        repo = Path(tempdir.name) / "repo"
        repo.mkdir()
        diff = repo / "review.diff"
        diff.write_text(
            "--- a/docs/guide.md\n+++ b/docs/guide.md\n@@ -0,0 +1 @@\n+guide\n",
            encoding="utf-8",
        )
        command = [
            "--repo-root",
            str(repo),
            "--diff-from",
            str(diff),
            "--github-pr",
            "7",
            "--github-repo",
            "owner/repo",
            "--planning-attempt",
            "attempt-pr",
            "--json",
        ]
        window = module.CopilotReviewWindow((), 1, None, False)
        with mock.patch.object(
            module,
            "fetch_copilot_review_for_prs",
            return_value=window,
        ) as fetch:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(module.main(command), 0)
            self.assertEqual(json.loads(stdout.getvalue())["cache"]["status"], "miss")
            fetch.assert_called_once()

        with mock.patch.object(
            module,
            "collect_review_learning_signal_once",
            side_effect=ValueError("unsafe planning request"),
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(module.main(command), 2)
            self.assertIn("unsafe planning request", stdout.getvalue())

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
        plan = module.resolve_target_plan(
            Path(tempdir.name),
            target,
            mode="update",
            confirmed_external_target=None,
        )
        updated = module.render_target_update(
            plan.existing_text,
            block,
            target=plan.resolved,
        )

        with mock.patch.object(module.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(OSError, "blocked"):
                module.apply_target_update(
                    plan,
                    updated,
                    mode="update",
                    confirmed_external_target=None,
                )

        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(list(target.parent.glob(".*.tmp")), [])

    def test_review_learnings_revalidates_before_creating_temporary_file(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_pre_temp_revalidation",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-pre-temp-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        events: list[str] = []
        original_named_temporary_file = module.tempfile.NamedTemporaryFile

        def revalidate() -> None:
            events.append("revalidate")

        def checked_named_temporary_file(*args: object, **kwargs: object) -> object:
            self.assertEqual(events, ["revalidate"])
            events.append("temporary")
            return original_named_temporary_file(*args, **kwargs)

        with mock.patch.object(
            module.tempfile,
            "NamedTemporaryFile",
            side_effect=checked_named_temporary_file,
        ):
            module.atomic_write_text(
                target,
                "candidate\n",
                revalidate=revalidate,
            )

        self.assertEqual(events[0:2], ["revalidate", "temporary"])
        self.assertEqual(target.read_text(encoding="utf-8"), "candidate\n")

    def test_review_learnings_default_scan_is_read_only_and_reports_target(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-scan-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        seed = root / "seed.txt"
        seed.write_text("seed\n", encoding="utf-8")
        for git_args in (
            ("init",),
            ("config", "user.email", "test@example.com"),
            ("config", "user.name", "Test User"),
            ("add", "seed.txt"),
            ("commit", "-m", "seed"),
        ):
            subprocess.run(
                ["git", *git_args],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        before = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }
        before_git = subprocess.run(
            ["git", "status", "--porcelain=v2", "--branch"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        before_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout

        result = subprocess.run(
            [
                sys.executable,
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"),
                "--repo-root",
                str(root),
                "--include-working-tree",
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["mode"], "scan")
        self.assertEqual(report["repositoryRoot"], str(root.resolve()))
        self.assertEqual(report["target"]["containment"], "repository-local")
        self.assertEqual(report["reviewLearning"]["status"], "not-requested")
        self.assertEqual(
            report["reviewLearning"]["evidence"]["source"],
            "not-requested",
        )
        self.assertFalse(report["reviewLearning"]["confidenceCredit"]["granted"])
        self.assertEqual(report["changes"], {"applied": 0, "proposed": 1})
        self.assertEqual(
            report["write"],
            {
                "occurred": False,
                "reason": "scan mode is read-only",
                "status": "skipped",
            },
        )
        after = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }
        self.assertEqual(after, before)
        self.assertEqual(
            subprocess.run(
                ["git", "status", "--porcelain=v2", "--branch"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout,
            before_git,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout,
            before_head,
        )
        self.assertFalse((root / "docs").exists())

    def test_review_learnings_external_update_requires_exact_confirmation(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-external-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        root = base / "repo"
        root.mkdir()
        diff = root / "empty.diff"
        diff.write_text("", encoding="utf-8")
        external = base / "outside" / "review-learnings.md"
        command = [
            sys.executable,
            str(install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"),
            "--repo-root",
            str(root),
            "--diff-from",
            str(diff),
            "--target",
            str(external),
            "--update-external",
        ]

        missing = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(missing.returncode, 2, missing.stdout)
        self.assertIn("--confirmed-external-target", missing.stdout)
        self.assertFalse(external.exists())

        mismatch = subprocess.run(
            [*command, "--confirmed-external-target", str(base / "wrong.md")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(mismatch.returncode, 2, mismatch.stdout)
        self.assertIn("must exactly match", mismatch.stdout)
        self.assertFalse(external.exists())

        confirmed = subprocess.run(
            [
                *command,
                "--confirmed-external-target",
                str(external.resolve()),
                "--json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        self.assertTrue(external.is_file())
        self.assertIn("<!-- sd-review-learnings:start -->", external.read_text())
        report = json.loads(confirmed.stdout)
        self.assertEqual(report["target"]["containment"], "external")
        self.assertEqual(
            report["externalAuthorization"],
            {
                "confirmed": True,
                "decision": "review-learnings.external-target",
                "resolvedTarget": str(external.resolve()),
            },
        )
        self.assertEqual(report["write"]["status"], "applied")

    def test_review_learnings_rejects_unsafe_local_targets(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_target_safety",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-targets-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        root = base / "repo"
        root.mkdir()
        outside = base / "outside"
        outside.mkdir()
        (root / "escape").symlink_to(outside, target_is_directory=True)
        (root / "final-link.md").symlink_to(root / "missing.md")
        (root / "existing.md").write_text("existing\n", encoding="utf-8")
        (root / "existing-link.md").symlink_to(root / "existing.md")
        (root / "directory-target").mkdir()
        invalid_utf8 = root / "invalid.md"
        invalid_utf8.write_bytes(b"\xff\xfe")

        cases = (
            (Path("../outside.md"), "outside the repository"),
            (outside / "absolute.md", "outside the repository"),
            (Path("escape/review.md"), "outside the repository"),
            (Path("final-link.md"), "broken symlink"),
            (Path("existing-link.md"), "not a symlink"),
            (Path("directory-target"), "regular file"),
            (Path("invalid.md"), "valid UTF-8"),
        )
        for target, message in cases:
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, message):
                module.resolve_target_plan(
                    root,
                    target,
                    mode="update",
                    confirmed_external_target=None,
                )

        with mock.patch.object(module.Path, "read_bytes", side_effect=PermissionError("blocked")):
            with self.assertRaisesRegex(PermissionError, "blocked"):
                module.resolve_target_plan(
                    root,
                    Path("existing.md"),
                    mode="update",
                    confirmed_external_target=None,
                )

        if hasattr(module.os, "geteuid"):
            owner = (root / "existing.md").stat().st_uid
            with mock.patch.object(module.os, "geteuid", return_value=owner + 1):
                with self.assertRaisesRegex(ValueError, "not owned"):
                    module.resolve_target_plan(
                        root,
                        Path("existing.md"),
                        mode="update",
                        confirmed_external_target=None,
                    )

    def test_review_learnings_revalidates_identity_before_replace(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_identity_recheck",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-race-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        target = root / "review-learnings.md"
        target.write_text("before\n", encoding="utf-8")
        plan = module.resolve_target_plan(
            root,
            target,
            mode="update",
            confirmed_external_target=None,
        )
        target.write_text("changed by another process\n", encoding="utf-8")

        with self.assertRaisesRegex(OSError, "content changed"):
            module.apply_target_update(
                plan,
                "candidate\n",
                mode="update",
                confirmed_external_target=None,
            )

        self.assertEqual(target.read_text(), "changed by another process\n")
        self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_review_learnings_rejects_parent_symlink_race_before_write(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_parent_race",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-parent-race-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        root = base / "repo"
        docs = root / "docs"
        docs.mkdir(parents=True)
        outside = base / "outside"
        outside.mkdir()
        target = docs / "review-learnings.md"
        plan = module.resolve_target_plan(
            root,
            target,
            mode="update",
            confirmed_external_target=None,
        )
        docs.rename(root / "docs-before-race")
        docs.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "outside the repository"):
            module.apply_target_update(
                plan,
                "candidate\n",
                mode="update",
                confirmed_external_target=None,
            )

        self.assertFalse((outside / "review-learnings.md").exists())
        self.assertEqual(list(outside.glob(".*.tmp")), [])

    def test_review_learnings_skill_declares_bounded_write_contract(self) -> None:
        skill = (
            install.ROOT / "templates/.agents/skills/sd-review-learnings/SKILL.md"
        ).read_text(encoding="utf-8")

        for heading in (
            "## Arguments",
            "## Structured decisions",
            "## Safety and mutation boundaries",
            "## Failure behavior",
            "## Final report",
        ):
            self.assertIn(heading, skill)
        self.assertIn("--update-external", skill)
        self.assertIn("--confirmed-external-target", skill)
        self.assertIn("for every external write", skill)
        self.assertIn("noninteractive execution stop without writing", skill)
        self.assertIn("Never stage, commit, push, publish", skill)

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

    def test_review_learnings_main_describes_truncation_without_assuming_limit(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_truncation_warning_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        truncated = module.CopilotReviewWindow((), 1, None, True)

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                with mock.patch.object(
                    module,
                    "fetch_copilot_review_for_prs",
                    return_value=truncated,
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        result = module.main(
                            [
                                "--repo-root",
                                tempdir.name,
                                "--github-pr",
                                "7",
                            ]
                        )

        self.assertEqual(result, 0)
        self.assertIn("truncated by configured safety bounds", stderr.getvalue())
        self.assertNotIn("--github-limit", stderr.getvalue())

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
            module.render_target_update(
                target.read_text(encoding="utf-8"),
                "<!-- sd-review-learnings:start -->\nnew\n<!-- sd-review-learnings:end -->\n",
                target=target,
            )

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

        plan = module.resolve_target_plan(
            Path(tempdir.name),
            target,
            mode="update",
            confirmed_external_target=None,
        )
        updated = module.render_target_update(
            plan.existing_text,
            "<!-- sd-review-learnings:start -->\n"
            "new\n"
            "<!-- sd-review-learnings:end -->\n",
            target=plan.resolved,
        )
        module.apply_target_update(
            plan,
            updated,
            mode="update",
            confirmed_external_target=None,
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
