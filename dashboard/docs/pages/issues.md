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

Your issues groups its Jira rows by local category (pack sd:7708), one
group open at a time, as GitHub's Pull requests group by repo; Uncategorized
is the last group, and GitHub rows stay ungrouped above the groups. New
category, in the view's head, adds a name; a group's Rename and Remove change
it, and Remove leaves its issues uncategorized, with Undo. Set category, on a
Jira row's ⋯ menu, and the Category field in its Details put an issue in a
category or clear it, with Undo. The names are the tags of one view row,
`issue:categories`, and a row's category is a tag on its own view row, the
store Hide writes; `POST /api/github/issues/categories` saves the list and
`POST /api/github/issues/view` with `category` sets a row's. Nothing is
written to Jira. A view store that does not read groups nothing and says why.
The table keeps no column sort or filter, since a sort would split the groups.
