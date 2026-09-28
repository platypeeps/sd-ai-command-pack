---
title: sd skill schedule writes a cron job file for a skill
created: 2026-09-28
---
# PRD — sd skill schedule

## Problem

The v2 Skills mockup offers Schedule on a skill, written as "no sd verb: a job
is a launchd agent; the proposal opens a pull request" (ui-design, verb check of
2026-09-28). The form parses "weekdays at 07:30" into a `StartCalendarInterval`.

The build cannot do what the mockup says. Scheduled jobs are `.job` files under
`<config>/cron-jobs/jobs/`, shell variables such as `JOB_SCHEDULE` in cron form
and `JOB_PROMPT` or `JOB_COMMAND`, installed into launchd by `cron-jobs.sh
install <job>` (system repository, `local-cron-jobs/README.md`). The config
directory, `~/.config/system`, is not a git repository (checked 2026-09-28), so
no pull request can carry the proposal. A skill on a schedule is a job file
that nothing writes.

## Requirements

1. `sd skill schedule <skill> --at "<cron expression>" [--prompt "<text>"]
   [--dry-run] [--json]` writes `<config>/cron-jobs/jobs/<skill>.job` and
   prints the path and the install command. `--dry-run` prints the file and
   writes nothing.
2. The file is a `JOB_PROMPT` job that invokes the skill with the prompt, in the
   pack's interpreter, and carries the same header comment shape as the jobs
   already there.
3. The verb refuses to overwrite an existing job file, and refuses a skill
   `sd skill list` does not name.
4. The verb does not install. Installing is `cron-jobs.sh install`, which stays
   the one place launchd is touched.
5. The mockup's proposal text changes to "writes the job file; install is a
   separate step", the "opens a pull request" claim goes, and
   `designs/tools/collect-counts.mjs` regenerates `data/commands.js` (ui-design,
   `skills.html`).

## Acceptance criteria

- [ ] `sd skill schedule --help` lists `--at`, `--prompt` and `--dry-run`.
- [ ] After `sd skill schedule <skill> --at "30 7 * * 1-5"`, `cron-jobs.sh list`
      names the job and reports it not installed.
- [ ] A second run against the same skill exits non-zero and leaves the file.
- [ ] `sd skill schedule nosuch --at "0 8 * * *"` exits non-zero.
- [ ] `designs/v2/commands.html` shows the schedule declaration with the new
      text and no pull-request claim.

## References

- ui-design `products/system/designs/v2/skills.html` (`skill.schedule`,
  `parseSchedule`).
- system `local-cron-jobs/README.md`, "Usage".
- `bin/sd_skill.py`, the group the verb joins.

## Log

- 2026-09-28 created
