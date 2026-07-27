# PARKED: Harden Trellis subagent-context read fallbacks

## Goal

Park the upstream-owned directory and JSONL read-fallback findings for the Trellis subagent-context hook until explicit upstream work is approved.

## Requirements

- Preserve the hook's non-blocking behavior: directory enumeration failures
  return files collected so far, and JSONL open/read failures return the safe
  existing fallback.
- Replace silent broad directory and JSONL read failures with stable, bounded,
  actionable diagnostics or equally explicit upstream code contracts.
- Do not expose absolute host paths, secrets, or raw unbounded exception text.
- Cover directory enumeration failures plus missing, malformed, and unreadable
  JSONL inputs with focused upstream tests.
- Treat `.claude/hooks/inject-subagent-context.py` and its sibling generated
  copies as Trellis-owned runtime. Do not patch them in this pack.
- Do not open an upstream Trellis pull request without the user's explicit
  approval for that specific PR. Until then, keep this task parked and preserve
  a paste-ready upstream handoff.

## Acceptance Criteria

- [ ] The user explicitly approves upstream Trellis work, or a released
      upstream change makes this task a verification/cleanup exercise.
- [ ] Current upstream behavior is re-verified before implementation.
- [ ] Directory-read and JSONL-read failures have bounded diagnostics while
      retaining their safe non-blocking fallbacks.
- [ ] Focused upstream tests cover the two failure families.
- [ ] No Trellis-owned runtime is patched in `sd-ai-command-pack` and no
      upstream PR is opened without separate approval.

## Notes

- Consolidates the stashed `document-trellis-directory-read-fallback` and
  `improve-trellis-jsonl-read-diagnostics` drafts.
- The installed Trellis 0.6.7 hook still contains silent broad exception
  fallbacks for both paths, so the findings remain valid but upstream-owned.
