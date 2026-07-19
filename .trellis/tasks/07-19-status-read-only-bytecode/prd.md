# Keep sd-status imports read-only

## Goal

Prevent direct `sd-status` execution from creating Python bytecode caches in a
consumer repository while preserving local and fleet status behavior.

## Background

During the 0.21.3 fleet rollout, Copilot review of
`platypeeps/se-ai-command-pack#9` found that `collect_work_loop()` dynamically
loads the work-loop helper. A direct Python invocation creates
`scripts/__pycache__/sd-ai-command-pack-work-loop*.pyc`, making a read-only
status command dirty its repository. The fleet helper import has the same
potential side effect.

The implementation belongs in the canonical sd-ai-command-pack templates and
must reach consumers only through a released installer refresh.

## Requirements

- Suppress Python bytecode writes around status-owned helper imports.
- Restore the caller's prior `sys.dont_write_bytecode` value on success and
  failure.
- Cover local work-loop and fleet helper loading.
- Keep template and installed script twins synchronized.
- Release the correction and resume the paused fleet rollout.

## Acceptance Criteria

- [x] Direct installed `sd-status fleet` execution with bytecode otherwise
  enabled creates no repository-local `__pycache__` directory.
- [x] Loader failures restore the prior bytecode setting.
- [x] Focused status tests, parity, candidate fleet validation, and canonical
  pack checks pass.
- [ ] The corrected release reaches the paused SE consumer PR through
  `install.py`.
