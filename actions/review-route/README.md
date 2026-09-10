# Advisory review routing

`actions/review-route` reports the plan from `sd-review --scope pr --explain`.
It does not run checks or reviewers, post review results, or approve a pull request.
Check out the pull request with full Git history before calling this action.

Consumer commits, including Dependabot commits, do not need `Authored-with:` trailers for this advisory report.
Missing or invalid attribution appears as unknown authorship, with every reviewer marked ineligible.
The report selects no provider and still exits successfully.
Valid attribution retains the normal rule that an author vendor cannot review its own change.

An actual review still requires valid attribution for every commit in its reviewed range.
`--dry-run` retains that requirement because it plans concrete provider requests.
Other errors, including invalid routing policy or an unavailable comparison base, still fail the action.
This correction replaces the unconditional advisory refusal introduced by #750, as reported in [#799](https://github.com/platypeeps/sd-ai-command-pack/issues/799).
