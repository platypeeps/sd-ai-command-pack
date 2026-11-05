"""Issues (pack sd:7682, GitHub's Your issues and Intake views until then): Your issues (sd:4628) and Issue Intake
(sd:4840). Both read `/api/github/issues` and Hide writes `/api/github/issues/view`: the GitHub page module keeps those
routes, since its Refresh from GitHub reads the sync job from the same read, so this page registers none."""

from __future__ import annotations

from . import Page

PAGE = Page(section="Issues", routes=("/issues",), html="issues.html", item="sd:7682")
