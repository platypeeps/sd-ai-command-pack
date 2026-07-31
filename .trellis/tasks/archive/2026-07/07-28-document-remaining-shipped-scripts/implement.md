# Implementation — document the shipped script surface

## Order

1. **Classify all 26 targets** (PRD R1). Produce the list mechanically, then
   decide each:

   ```bash
   python3 -c "
   import json
   m=json.load(open('manifest.json'))
   t=sorted({e['source'] for e in m['files'] if e.get('kind')=='script'})
   print(len(t)); [print(' ',x) for x in t]"
   ```

   Record classification and rationale in `design.md`. Default
   `pr-eligibility.py` to public — it is referenced from a shipped skill.
   **Gate:** all 26 carry a classification before anything is written.

2. **Narrow `CONTRIBUTING.md:135`** if step 1 marked anything internal. Add the
   internal category explicitly; do not leave "shipped script paths and CLIs"
   unqualified while an undocumented internal target exists.

3. **Build the gate before writing the prose.** A test that enumerates manifest
   `scripts/` targets and asserts each is either named in
   `docs/SD_AI_COMMAND_PACK.md` or on the internal allowlist. Seed the allowlist
   from step 1.
   **Gate:** run it now — it must fail, naming exactly the targets step 1 called
   public and left undocumented. A gate that passes before the docs are written is
   not checking anything.

4. **Write the guide entries** for everything classified public, in the shape the
   existing 23 entries use — purpose, invocation, arguments, output, exit codes
   (PRD R3). No lighter format for the stragglers.

5. **Resolve the `review-local` collision** (PRD R4). In the existing `.sh`
   section, name `scripts/sd-ai-command-pack-review-local.py`, state that it is
   the stage `sd-review` actually invokes via `review.py:34`, and state that the
   two do not call each other. One paragraph; it is the only thing standing
   between a reader and a wrong conclusion.

6. **Mirror to `templates/docs/SD_AI_COMMAND_PACK.md`**, `make sync`.

7. **Re-run the gate** — must pass. Then verify the failure direction: add a fake
   `scripts/` target to a manifest copy and confirm the gate fails.

## Validation

```bash
python3 -m pytest tests/ -k "doc_coverage or shipped_script" -q
```

```bash
make sync && make check
```

Confirm the two doc copies agree:

```bash
diff docs/SD_AI_COMMAND_PACK.md templates/docs/SD_AI_COMMAND_PACK.md && echo identical
```

## Review gates

- Before step 2: classification complete for all 26, with rationale.
- Before step 4: the gate exists and **fails** for the expected reason.
- Before completion: both failure and success directions of the gate verified —
  PRD AC explicitly requires testing the failure mode, not just the passing one.

## Rollback

Docs plus one test. Plain revert. No runtime behavior, no manifest target moved,
no consumer-visible contract tightened — `CONTRIBUTING.md:135` is only relaxed.
