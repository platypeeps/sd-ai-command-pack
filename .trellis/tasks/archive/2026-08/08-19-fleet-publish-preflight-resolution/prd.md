# Resolve fleet-publish pack helpers from the source checkout

## Problem

`scripts/sd-ai-command-pack-fleet-publish.py` is a source-only tool: it is
listed in `SOURCE_ONLY_ALLOWED_PACK_FILES`
(`scripts/sd-ai-command-pack-install-audit.py:88`, whose row for this file is
at `:120`) and is never installed into a consumer. It runs from the pack checkout with `--repo <consumer>`.

Its fourth step, `completion_receipt()`, invokes the review preflight with a
bare consumer-relative path and the consumer as the working directory:

```python
result = run(
    [
        "node",
        "scripts/sd-ai-command-pack-review-preflight.mjs",
        "final-bundle",
        ...
    ],
    cwd=repo,
    check=False,
)
```

No thin consumer vendors `scripts/sd-ai-command-pack-*`. Node therefore exits
without writing stdout, and the helper fails parsing an empty string:

```
fleet-publish: completion receipt was not valid JSON: Expecting value: line 1 column 1 (char 0)
```

Every consumer in `docs/fleet/consumers.json` is `mode: thin` and none vendors
that file, so the defect blocks the `pr-publication` stage for the whole fleet,
not one lane.

The same function already has the correct pattern immediately beside it:
`publish()` resolves the record-session wrapper as
`Path(__file__).resolve().parent / "sd-ai-command-pack-record-session.py"` with
a `--record-session` override. Both helpers are siblings in the pack's
`scripts/` directory. Only the preflight was left consumer-relative.

Because the tool is source-only, no corrective pack release is required: the
fix takes effect for an in-flight campaign as soon as it lands in the source
checkout.

## Two defects, not one

Resolving the path is necessary but not sufficient.

`review-preflight.mjs` does not take its repository from the working directory
directly. `defaultRootDir()` (`scripts/sd-ai-command-pack-review-preflight.mjs`)
consults, in order: the `SD_AI_COMMAND_PACK_REPO_ROOT` environment override,
then `git rev-parse --show-toplevel` from the inherited cwd, then
`resolve(scriptDir, '..')`. Only the second of those is the consumer.

`plugins/sd/bin/sd-ai-command-pack-full-check.sh:34` exports
`SD_AI_COMMAND_PACK_REPO_ROOT`, and the fleet pipeline runs a consumer full
check at the `local-checks` stage, immediately before `pr-publication`. So an
absolute-path fix alone converts a loud crash into a silent wrong answer: the
helper would emit a well-formed completion receipt describing the **pack**
checkout while claiming to describe the consumer.

The explicit `--repo` argument outranks both the environment override and the
cwd fallback (`options.rootDir ? resolve(options.rootDir) : defaultRootDir()`),
so passing it is what actually makes the receipt deterministic.

## Non-goals

- Making `fleet-publish.py` resumable after a partial run. The helper's
  all-or-nothing shape and its `resolve_task_dir` precondition are unchanged
  here; recovering a lane that already folded its commits is a separate
  concern.
- Changing which receipt the publish step produces, its mode, or its scope.

## Requirements

1. `completion_receipt()` resolves `sd-ai-command-pack-review-preflight.mjs`
   from the pack checkout that owns the running script, not from the consumer
   working directory.
2. That invocation passes `--repo <consumer>` explicitly, so the inspected
   repository cannot be decided by an ambient `SD_AI_COMMAND_PACK_REPO_ROOT` or
   by cwd-fallback ordering. `cwd=repo` is retained as well.
3. An explicit override exists, matching the `--record-session` precedent in
   shape and help text, so an operator can point at a different preflight.
4. The preflight's existence is verified in `check_preconditions()`, before the
   work commit, the archive move, and the journal — not at step 4. A missing
   preflight must stop the run while it is still a no-op, with a
   precondition-shaped diagnostic (code 3) naming the resolved absolute path.
   This is the defect that turned a wrong path into a stranded consumer: the
   helper folded three commits and archived the task, then failed on a
   dependency it could have checked before touching anything.

## Acceptance criteria

- [x] `completion_receipt()` invokes an absolute preflight path resolved from
      `Path(__file__)`, passes `--repo <consumer>`, and retains `cwd=repo`.
- [x] A `--review-preflight` argument overrides that default and is documented
      in `--help` consistently with `--record-session`.
- [x] `check_preconditions()` fails with code 3 naming the resolved absolute
      path when the preflight is absent, proven by a test in
      `tests/test_fleet_publish.py` that asserts no commit, archive move, or
      journal was produced.
- [x] A test in `tests/test_fleet_publish.py` asserts the invoked argv carries
      an absolute preflight path and `--repo <consumer>`, so a regression to a
      cwd-relative or ambient-root invocation fails the suite.
- [x] Running the resolved `final-bundle --mode completion` command against the
      `rwbp-coordinator` checkout returns valid JSON carrying a `status` field.
- [x] `docs/FLEET_ROLLOUT.md` states that the publish helper resolves its pack
      helpers from the source checkout, so a thin consumer needs no vendored
      `scripts/`.
