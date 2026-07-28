# Current CI and finish-work lifecycle evidence

## Workflow behavior

- `.github/workflows/tests.yml:3-10` triggers on every pull-request update. Only
  main pushes have a path ignore, and it covers `.trellis/workspace/**` rather
  than task archives.
- `.github/workflows/tests.yml:16-169` defines the three-entry test matrix,
  lint, security, and PR release-payload work that is repeated for a
  bookkeeping head.
- `.github/workflows/tests.yml:215-245` keeps `CI Result` as the single required
  aggregate context.
- `templates/.agents/skills/sd-review-pr/SKILL.md:681-721` runs finish-work and
  then performs one push for archive/journal commits.
- `templates/.agents/skills/sd-ship/SKILL.md:116-130` delegates the merge tail
  to housekeeping, which pushes finish-work changes and waits for checks on
  the new exact head.

## Observed PR #243 sequence

- Full PR run on code head `997886694d63b0e11cd06f6f3e017704eb1ddc5f`:
  <https://github.com/platypeeps/sd-ai-command-pack/actions/runs/30090352024>
- Full PR run on successor `c0525b31242c4aea7341f27471405440cf520e8c`:
  <https://github.com/platypeeps/sd-ai-command-pack/actions/runs/30090744209>
- `c0525b3` is `chore: record journal` and changes only
  `.trellis/workspace/sdelmas/index.md` and
  `.trellis/workspace/sdelmas/journal-5.md`.
- The PR merge then produced the normal main-push run:
  <https://github.com/platypeeps/sd-ai-command-pack/actions/runs/30091020982>

The second PR run is the avoidable cost addressed here. The main merge run is
not bookkeeping-only and remains full because it owns post-merge/release
validation.

## Related but non-duplicated work

`07-22-integrate-routed-review-backends` R27 defines an exact-head review
decision for a verified bookkeeping successor. It deliberately leaves
deterministic CI re-entry in place. This task optimizes that CI re-entry and
does not create a command-pack-local review exemption.
