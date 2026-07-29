# Implementation — regenerate the source-only fleet-refresh adapters

## Order

1. **Resolve the neutral-adapter asymmetry first.** Templates carry
   `.commands/sd-fleet-refresh.md`; the dev tree carries
   `.opencode/commands/sd-fleet-refresh.md`.

   ```bash
   diff templates/.commands/sd-fleet-refresh.md .opencode/commands/sd-fleet-refresh.md
   ```

   **Gate:** decide which path the generator owns before writing derivation code,
   or it emits a fifth file nobody wants.

2. **Add the shared path-derivation helper** — source-only command name plus
   target families to dev-tree adapter paths. One helper, imported by both the
   generator and the drift gate. Two independent lists is how this refroze.

3. **Extend `generate-command-surfaces.py`** so source-only commands emit to
   dev-tree paths as well as `templates/`. `bespoke_adapter_path:568` covers
   claude/gemini/github; the neutral form follows step 1.

4. **Regenerate and read the diff.** These files are frozen at 0.20.0, so this
   will be large.

   ```bash
   python3 .github/scripts/generate-command-surfaces.py && git diff --stat .claude .gemini .github/prompts .opencode
   ```

   **Gate:** read the full diff. Anything beyond the checkout-trust block and
   pipeline description is a behavioral change that needs justifying, not
   accepting. Record what changed.

5. **Prove the manifest did not move** — this is the R4 guarantee:

   ```bash
   git diff --exit-code manifest.json && echo "manifest unchanged"
   ```

   Non-empty output means `SOURCE_ONLY_COMMAND_NAMES` semantics shifted and
   fleet-refresh is about to ship to consumers. Stop and fix.

6. **Wire the four paths into the drift gate** using the step-2 helper. Do not
   route it through `load_manifest()` — `generate-command-surfaces.py:881`
   excludes source-only commands from the manifest by design, so that path is
   structurally empty.

7. **Verify the gate bites.** Hand-edit one adapter out of sync and confirm
   `make check` fails. A gate added without this check is not known to work.

## Validation

```bash
grep -c checkout-trust .claude/commands/sd/fleet-refresh.md templates/.claude/commands/sd/fleet-refresh.md
```

Both must report `1`. Before the change the dev copy reports `0` — that is the
decisive before/after line.

```bash
make check
```

## Review gates

- Before step 3: neutral-adapter path decided.
- Before step 6: `manifest.json` proven byte-unchanged.
- Before completion: the drift gate demonstrated failing on a hand-desynced
  adapter, and the step-4 diff reviewed rather than skimmed.

## Rollback

Plain revert; the adapters return to their frozen state and the gate disappears
with them. No consumer artifact is involved — `installer/removal.py:272` skips
source-only targets in source checkouts, so nothing was ever installed from here.
