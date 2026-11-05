# GitHub

GitHub is at `/github` (sd:5781), in the rail's Work group, in three views.
They were Today's GitHub and Issues views until sd:5781; an old
`/today#view=github` address opens here with its query. Its views are Pull
requests, Dependabot and Tracked.

Pull requests (sd:5608) lists the operator's open pull requests, and those
merged or closed in the last 7 days, from `GET /api/today/github`
(`today_github.document`), which reads only what `sd shadow sync` and the
Contributions collector stored. It is one table, 25 rows a page (sd:5899),
grouped by repo with one group open at a time, as Today's Queue is
(sd:7664): the first group, or the selected row's, opens on load.
Show mine, the default, keeps rows assigned to the operator or opened by
them; Show all adds the rest. State open, the default, hides merged and
closed rows; with closed shows them. A pull request row opens its Details:
Open on GitHub, Open item, Adversarial review, Copilot review, Merge
(sd:5668) and Close original (sd:5669), each through the routes the README
names.

Your issues and Intake moved to the Issues page (`/issues`, pack sd:7682);
an old `/github#view=issues` or `#view=intake` address opens there with its
query. See `issues.md`.
