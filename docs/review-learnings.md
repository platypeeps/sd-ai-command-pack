# Review Learnings

Human-maintained notes live outside the managed block so `sd-review-learnings
--update` can refresh generated findings without replacing durable lessons.

## Durable Notes

- Installer remove-mode paths should preserve and continue on user-owned or
  drifted target state. When changing `install.py --remove` or adjacent
  uninstall helpers, wrap target path resolution, target reads, and managed
  marker parsing in preservation paths unless the operation is explicitly
  install/update-only or intentionally destructive. Add regressions for unsafe
  paths, unreadable files, malformed marker blocks, and receipt/provenance
  drift before requesting remote review.

## Preflight Candidates

- Consider a local review/preflight check that flags new remove-mode calls to
  path resolution, strict text reads, or marker parsing when they are not inside
  a preserve-and-continue branch.
