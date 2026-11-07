"""GitHub (sd:5781, Today's GitHub and Issues views until then): Pull requests (sd:5608) are the operator's pull requests
and issues: `/api/today/github` (`today_github`); a pull request's Copilot review (sd:5633) writes through
`/api/today/github/copilot-review`, and its Merge (sd:5668) previews with a GET and copies into the lane with a POST
(`pr_merge`); Close original (sd:5669) previews its comment with a GET and closes with a POST (`pr_close`). Your issues
(sd:4628) and Intake (sd:4840) are `/api/github/issues` (`issues`); File as item posts `/api/items` with the ref.
Their rows' Hide (sd:6175) is the view state that read carries; Refresh from GitHub, on every view,
posts `/api/jobs/shadow-sync-nightly/retry` (pack sd:6702). Pack sd:7682 moved those two views to the Issues page
(`issues.py`); their routes stay here, since this page's Refresh from GitHub reads the sync job from the same read.
Your issues holds the operator's GitHub issues `today_github` reads too (sd:5899), so the Pull requests view lists none.
Dependabot (pack sd:7515) is `/api/github/dependabot` (`health_screen.dependabot_document`): the alerts `sd shadow sync`
stored in `repo_protection`, grouped by repository; a group's Fix is Health's (`/api/items` with its `dependabot:` ref).
Tracked (pack sd:7525, Operations > Trackers until then) is `/api/github/tracked` (`trackers_screen.document`): every
open pull request and issue `sd shadow sync` keeps, of every tracker, watched and Jira rows too."""

from __future__ import annotations

from . import Api, Page


def _github(read):
    from ... import today_github

    return today_github.document(read.connection, now=read.now)


def _issues(read):
    from sd_db import operations

    from ... import issues, today_github

    github = today_github.document(read.connection, now=read.now)
    found = issues.with_github(issues.document(read.connection), github)
    # sd:6175: each row's Hide state, and Refresh from GitHub's job, as HOA's Refresh now reads its own; `synced` is
    # when GitHub was last read, shown beside it (pack sd:6702).
    # pack sd:7841: each row names the pull requests that close it, from the same GitHub read.
    listed = issues.with_pulls({**found, **issues.intake(read.connection)}, github)
    return {**issues.with_views(listed, read.connection),
            "sync": issues.sync_job(read.connection, read.jobs or operations.LaunchdBackend()),
            "synced": github["collector"]}


def _dependabot(read):
    from sd_db import protection

    from ... import health_screen

    return health_screen.dependabot_document(protection.rows(read.connection))


def _tracked(read):
    from ... import trackers_screen

    return trackers_screen.document(read.connection, now=read.now)


def _view(payload, principal):
    from ... import issues

    return issues.view(payload)


def _categories(payload, principal):
    from ... import issues

    return issues.categories(payload)


def _copilot(payload, principal):
    from ... import today_github

    return today_github.copilot_request(payload)


def _merge_preview(read):
    from ... import pr_merge

    return pr_merge.preview(read.connection, read.parameters)


def _merge(payload, principal):
    from ... import pr_merge

    return pr_merge.request(payload, principal)


def _close_preview(read):
    from ... import pr_close

    return pr_close.preview(read.connection, read.parameters)


def _close(payload, principal):
    from ... import pr_close

    return pr_close.request(payload, principal)


PAGE = Page(
    section="GitHub",
    routes=("/github",),
    html="github.html",
    item="sd:5781",
    api=(Api("/api/today/github", _github), Api("/api/github/issues", _issues),
         Api("/api/github/dependabot", _dependabot), Api("/api/github/tracked", _tracked),
         # Hide (sd:6175): the per-page view route Designs, Documents and Contributions have, on the same view store.
         Api("/api/github/issues/view", write=_view),
         # Local Jira categories (pack sd:7708): the category names, in the same view store; a row's category goes to /view.
         Api("/api/github/issues/categories", write=_categories),
         Api("/api/today/github/copilot-review", write=_copilot),
         # Merge (sd:5668): the GET previews, the POST copies; `pr_merge` checks the preview's revision before anything moves.
         Api("/api/today/github/merge/preview", read=_merge_preview, query=True),
         Api("/api/today/github/merge", write=_merge),
         # Close original (sd:5669): the GET shows the comment, the POST posts it once and closes the pull request.
         Api("/api/today/github/close/preview", read=_close_preview, query=True),
         Api("/api/today/github/close", write=_close)),
)
