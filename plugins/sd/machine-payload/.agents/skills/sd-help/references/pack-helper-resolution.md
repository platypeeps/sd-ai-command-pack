# How a skill reaches a pack helper

> The single resolution rule for shipped Software Delivery skills. A skill
> reaches a pack helper **only** through the toolchain, and locates the
> toolchain with the bootstrap below. This file states both once; skills cite
> it rather than restating them, because two copies of a resolution order is
> one copy going stale.

## The bootstrap

Put this at the top of every fenced shell block that invokes a pack helper.
Each block runs in its own shell, so a block cannot rely on a variable set by
an earlier one.

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }
```

Then invoke helpers through it, never directly:

<!-- pack-helper-resolution: exempt - usage examples for the rule this file
     defines; the bootstrap above them is the block being illustrated -->

```bash
bash "$SD_PACK_TOOLCHAIN" run-python -- sd-ai-command-pack-status.py --json
bash "$SD_PACK_TOOLCHAIN" run -- sd-ai-command-pack-review-preflight.mjs --json
bash "$SD_PACK_TOOLCHAIN" run -- gh pr view --json number
```

## Why the order is what it is

1. **`SD_AI_COMMAND_PACK_TOOLCHAIN`** — an explicit override. It exists so a
   deliberately constructed version split can be tested without editing `PATH`,
   and so a developer can point a consumer checkout at a work-in-progress pack
   checkout.
2. **the checkout's own `scripts/` copy** — when that file exists, the working
   directory *is* a pack source checkout, and someone editing helpers there
   must run the edited ones. A consumer never has this directory, so preferring
   it costs consumers nothing.
3. **`$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh`** — the machine
   install. This is not a new convention: `docs/fleet/consumers.json` already
   invokes helpers from that root.

`[ -f "" ]` is false, so an unset override falls through without a separate
emptiness test.

### `PATH` is deliberately absent

`PATH` is where the version split comes from. A host that prepends a cached
plugin root leaves the oldest surviving entry answering first, and the answer
has nothing to do with which pack the running skill text came from. Resolving
the bootstrap through `PATH` would reintroduce exactly that split.

`$HOME/.agents/bin` is not necessarily on `PATH`, which is the point: when the
two disagree, the disagreement is visible in `sd-status` rather than silently
deciding which helper runs.

`CLAUDE_PLUGIN_ROOT` is rejected for a different reason — the pack ships to
`claude`, `gemini`, `github`, and `opencode`, so a Claude-only variable cannot
be the one rule.

## Why everything goes through the toolchain

`resolve_pack_script_operand` in the toolchain resolves a helper operand next
to the toolchain script itself, never against the working directory. Its own
comment states the guarantee: own location wins outright, so a repository
cannot shadow a pack helper with a same-named file of its own. Every helper
reached through the toolchain therefore comes from the same install as the
toolchain — a run cannot mix two installs.

Invoking a helper directly — `node` or `bash` against a working-directory
relative path under `scripts/` — bypasses that resolver entirely and breaks on
any consumer that has no `scripts/` directory, which is every thin consumer.

## The `run --` first-operand trap

`run` resolves only its **first** operand. Never name the interpreter:

Wrong — resolves `node`, leaves the `.mjs` unresolved, then fails:

```text
bash "$SD_PACK_TOOLCHAIN" run -- node sd-ai-command-pack-review-preflight.mjs
```

Right — the helper's shebang supplies the interpreter:

<!-- pack-helper-resolution: exempt - contrast example for the first-operand
     trap; not a runnable procedure -->

```bash
bash "$SD_PACK_TOOLCHAIN" run -- sd-ai-command-pack-review-preflight.mjs
```

Shipped helpers carry `#!/usr/bin/env node` or `#!/usr/bin/env bash` shebangs
and are installed executable, which is what makes the interpreter unnecessary.
A helper that is not executable in the machine install is a packaging defect:
report it rather than working around it by naming the interpreter.

## No `scripts/` prefix on operands

Write `run-python -- sd-ai-command-pack-status.py`, not
`run-python -- ~/.agents/bin/sd-ai-command-pack-status.py`. The resolver strips the
prefix, so both work — but the rule is "no `scripts/` in an executable block",
with no exception. A reader should not have to decide which `scripts/` token is
a harmless operand prefix and which is the working-directory-relative bootstrap
that this whole rule exists to remove.

## When the bootstrap fails

The failure branch is the diagnosis: it names all three candidates it checked.
Do not add a separate `command -v` guard beside an invocation — a guard that
accepts a different set of locations than the invocation uses can pass while
the invocation throws, which is precisely the defect this file replaces.
