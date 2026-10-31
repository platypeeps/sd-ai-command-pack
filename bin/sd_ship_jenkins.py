"""`sd-ship merge` waits on the Jenkins job a repository's policy names (sd:6880, repo-policy design § Failure table).

`policy.ci = {"provider": "jenkins", "url": ..., "job": "folder/job/PR-{pr}"}`. The job's recent builds are read
from Jenkins' JSON API; a build counts for the head only when the head's SHA appears in its actions (the git
plugin's `lastBuiltRevision`, or the branch source's PR revision), never by branch name. Jenkins unreachable, a
StrongDM sign-out included, holds as `ci_unreachable`: unknown is never green. sd-ship reads the job; it never
triggers or edits one.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from sd_ship_remote import Refusal

#: The builds read per poll, newest first, and the fields that tie one to a commit.
TREE = ("builds[number,result,building,url,"
        "actions[lastBuiltRevision[SHA1],revision[hash,pullHash]]]{0,20}")
POLL_SECONDS = 30
READ_SECONDS = 20


def job_url(ci: dict, number: int) -> str:
    """The job's API address: each `/`-separated name of `job` (with `{pr}` filled) under `/job/`."""
    names = [name for name in ci["job"].replace("{pr}", str(number)).split("/") if name]
    return ci["url"].rstrip("/") + "".join(f"/job/{urllib.parse.quote(name, safe='')}" for name in names)


def head_build(ci: dict, number: int, head: str, opener: Callable[..., Any] = urllib.request.urlopen) -> dict | None:
    """The newest build of the job that built `head`, or None; an unreachable Jenkins refuses `ci_unreachable`."""
    address = f"{job_url(ci, number)}/api/json?tree={urllib.parse.quote(TREE, safe='')}"
    try:
        with opener(address, timeout=READ_SECONDS) as response:
            builds = json.loads(response.read()).get("builds") or []
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None  # the job (a PR's branch job) has not been indexed yet
        raise jenkins_unreachable(ci, f"HTTP {error.code}") from None
    except (OSError, ValueError, AttributeError) as error:
        raise jenkins_unreachable(ci, str(error) or type(error).__name__) from None
    # ponytail: the SHA anywhere in the build's actions, not one plugin's field; narrow if a plugin echoes others
    return next((build for build in builds if isinstance(build, dict) and head in json.dumps(build.get("actions"))),
                None)


def jenkins_unreachable(ci: dict, why: str) -> Refusal:
    return Refusal(f"Jenkins at {ci['url']} did not answer for {ci['job']} ({why}); an unread job is not green",
                   code="ci_unreachable", boundary="ci", state="retryable_failure",
                   next_action="Run sdm-login (StrongDM), check the policy's ci url, then retry merge.")


def wait_green(ci: dict, number: int, head: str, *, wait_seconds: int, opener: Callable[..., Any] = urllib.request.urlopen,
               sleep: Callable[[float], None] = time.sleep) -> dict:
    """Return the green build of `head`, polling up to `wait_seconds`; a red, missing or running one refuses."""
    waited = 0
    while True:
        build = head_build(ci, number, head, opener)
        if build is not None and not build.get("building") and build.get("result") == "SUCCESS":
            return build
        if build is not None and not build.get("building") and build.get("result") is not None:
            raise Refusal(f"Jenkins build {build.get('url') or build.get('number')} of {head[:12]} is "
                          f"{build['result']}", code="ci_not_passing", boundary="ci", state="retryable_failure",
                          next_action="Fix the failing Jenkins build, push, then retry merge.")
        if waited >= wait_seconds:
            seen = "is still running" if build is not None else "has no build yet"
            raise Refusal(f"Jenkins job {ci['job']} {seen} for {head[:12]} after {waited}s", code="ci_pending",
                          boundary="ci", state="retryable_failure",
                          next_action="Wait for the Jenkins build of this head, then retry merge.")
        sleep(POLL_SECONDS)
        waited += POLL_SECONDS
