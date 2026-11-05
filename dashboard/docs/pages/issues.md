# Issues

Issues is at `/issues` (pack sd:7682), in the rail's Work group after GitHub,
in two views: Your issues and Issue Intake. They were GitHub's Your issues
and Intake views until pack sd:7682; an old `/github#view=issues` or
`#view=intake` address, or Today's `#view=issues`, opens here with its query.
Both views keep Hide and Hidden, and Refresh from GitHub, as on GitHub.

Your issues (sd:4628) lists each repo's open Jira and GitHub issues assigned
to or filed by the operator, and their GitHub issues in other repos, which
Pull requests listed until sd:5899. Its State filter adds their GitHub
issues closed in the last 7 days; closed Jira issues are not read. Issue Intake (sd:4840) lists each `policy.issues` read or ask
repo's open third-party issues no item carries; File as item posts
`/api/items` with the issue's `github:<owner>/<repo>#N` ref. Both are one read,
`GET /api/github/issues` (`issues.document`, `issues.intake`), made when either
view first shows and on Read again. A failed read is a row naming it, never an
empty list. An issue row of either view opens its Details (sd:5877): key,
title, state, tracker, assignee, reporter, opened and updated, and the item
filed under its ref, from the `shadow` row `sd shadow sync` stored; no tracker
is called. The sync stores no labels, priority or description, and Details
say so. Its actions are Open in Jira or Open on GitHub, and Open item; an
Issue Intake row keeps File as item.
