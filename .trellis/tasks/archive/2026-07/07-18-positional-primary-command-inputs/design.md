# Positional Primary Inputs Design

## Overview

Apply a narrow ergonomics convention to five existing commands: bare text may
name the command's primary subject, while options continue to control behavior.
Keep parsing local to each canonical skill except for `sd-status`, whose Python
CLI parser must also accept a positional repository path.

## Proposal

### Parsing Policy

Each command follows this order:

1. Tokenize the invocation using the platform's existing argument handoff.
2. Recognize documented flags and key/value options.
3. Reject unknown option-shaped tokens.
4. Collect the remaining positional subject according to the command contract.
5. Reject positional/explicit duplication.
6. Normalize and validate the subject exactly as the explicit form does.
7. For mutating commands, report the normalized target and controls.
8. Begin the existing workflow without changing its lifecycle gates.

Do not add a generic shell parser or central runtime solely for instruction-led
skills. Record the convention in adapter guidance and assert each command's
contract in tests. Reuse the existing Python argument parser for `sd-status`.

### Command Mappings

| Command | Positional subject | Explicit equivalent | Explicit-only controls |
| --- | --- | --- | --- |
| `sd-retro` | Entire bare phrase | `topic=` | None currently |
| `sd-test-gaps` | One file path | `file=` | `max-gaps=` |
| `sd-fleet-refresh` | Consumer names | `consumer=` | `dry-run`, `no-merge` |
| `sd-audit-repo` | Exact charter names | `dimensions=` | `depth=`, `follow-up` mode |
| `sd-status` | One repo path; reserved `fleet` | `--repo` | `--fleet-manifest`, `--json`, `--no-network` |

For list-like subjects, whitespace and commas are delimiters, order is stable,
and exact duplicate values collapse to the first occurrence. For phrase/path
subjects, preserve the complete quoted or handed-off value.

### Failure Safety

Fleet consumers and audit dimensions have dangerous broad defaults when no
filter is present. A failed positional value therefore cannot degrade to the
no-filter path. Validation must produce an explicit error naming the rejected
value and accepted values before any install, reviewer dispatch, PR action, or
merge attempt.

Unknown option-shaped tokens also fail. This keeps a typo such as
`no-merg` from being interpreted as a consumer or topic. `sd-retro` may accept
ordinary prose freely, but a token that uses recognized option syntax with an
unknown key remains an error.

### Documentation And Adapters

Update the canonical template skills and synchronize root installed mirrors.
Platform wrappers should remain thin resolvers and pass invocation arguments
unchanged. Update wrappers only if a current adapter omits or rewrites free
text. Add examples to `sd-help` and the distributed command guide.

## Boundaries And Non-Goals

- Do not make `sd-ship` lifecycle stop points positional.
- Do not make housekeeping merge strategy, remote, or mutation flags
  positional.
- Do not add positional retry, timeout, depth, dry-run, merge, or output modes.
- Do not add fuzzy matching for consumers, charter names, or file paths.
- Do not redesign the five commands beyond their invocation parsing and
  documentation.

## Affected Files

- `templates/.agents/skills/sd-retro/SKILL.md`
- `templates/.agents/skills/sd-test-gaps/SKILL.md`
- `templates/.agents/skills/sd-fleet-refresh/SKILL.md`
- `templates/.agents/skills/sd-audit-repo/SKILL.md`
- `templates/.agents/skills/sd-status/SKILL.md`
- synchronized root mirrors under `.agents/skills/`
- `templates/scripts/sd-ai-command-pack-status.py` and its root mirror
- `templates/.agents/skills/sd-help/references/command-catalog.md`
- `templates/.agents/skills/sd-help/references/examples.md`
- `templates/docs/SD_AI_COMMAND_PACK.md`, `README.md`, and adapter guidance
- focused command-contract, status, help, installer, and parity tests
- `manifest.json` and `CHANGELOG.md` for the shipped behavior change

## Risks And Edge Cases

- Paths with spaces depend on adapters preserving the raw invocation. Test
  representative prompt/command wrappers rather than assuming shell parsing.
- A fleet consumer could theoretically share a name with a bare flag. Document
  flag precedence and retain `consumer=` as the escape hatch.
- `sd-audit-repo follow-up` is already a mode. Keep it reserved and reject
  incompatible dimension combinations.
- Different platforms may prefix slash/skill arguments differently. Tests
  should verify their wrappers pass free text to the canonical skill resolver.
- Positional convenience can hide typos if validation is permissive. Exact
  matching and fail-closed broad defaults are mandatory.

## Validation

Add table-driven contract tests for positional, explicit, mixed, duplicate,
unknown, quoted-path, flag-precedence, and no-argument cases. Extend status
parser tests with path/fleet conflicts and JSON/no-network combinations. Run
generated parity, installer, docs, release, and canonical checks.
