# Planning adversarial review ledger

Scope under review (FINAL, owner option 3): **parity only** — add `"claude"` to
`SKILL_FANOUT_PLATFORMS`, ship sd skills to `.claude/skills/` like the 10 other
fanout platforms. **Guard-embed evaluated across rounds 1-2 and DROPPED** (C-8:
an in-skill guard can't stop a checkout that modified the skill body). Auto-invoke
exposure accepted as parity with the 10 existing platforms.

Applicable concerns for the final parity-only scope: C-1..C-5 (round 1), plus
C-10 (AC2 must not execute sd-ship), C-12 (no exact-byte parity test → rely on
diff -q), C-14 (audit phantom path ADDED not excluded), C-16 (resolver timing
after sync). **Moot (guard-specific, dropped):** C-8, C-9, C-11, C-13, C-15.

## Round 1 (host + Codex, both ran; Codex exit 0, 174k tokens)

| ID | Source | Concern | Severity / blocks | Evidence | Disposition |
|----|--------|---------|-------------------|----------|-------------|
| C-1 | Codex | `make generate` runs surface-check inline (`Makefile:17`); it writes manifest/templates, NOT root `.claude/skills/*` mirrors — those land via `make sync` (`Makefile:29`). So generate's own surface-check + missing-mirror gate (`test_pack_drift.py:151`, `surface-check.py:518`) fail before the planned sync. | HIGH — plan's step order cannot go green | Makefile:17,29; surface-check:518; test_pack_drift:151 | **addressed** — implement.md re-ordered: run generator, then `make sync`, THEN surface-check/drift; treat a green result only after sync. |
| C-2 | Codex | `command_installed_targets` iterates `SKILL_FANOUT_PLATFORMS` (`registry.py:1211`); every footprint (incl. retired + source-only fleet-refresh at `registry.py:1289`) gains one `.claude/skills/<n>/SKILL.md`. Pinned counts break: `test_retired_targets.py:78-82` (each 25→26, `RETIRED_TARGETS` 100→104); `SOURCE_ONLY_COMMAND_TARGETS` 25→26; `SOURCE_ONLY_ALLOWED_PACK_FILES` equality pin `test_install_audit.py:95`. Note: fleet-refresh footprint is already fully phantom today (source-only ships none), so claude just extends existing phantom pattern +1. | HIGH — tests break | registry.py:1211,1289; test_retired_targets:78; test_install_audit:95 | **addressed** — implement.md enumerates each pin to update (26/104) and the audit-allow reconciliation; no logic change, footprint growth is consistent with existing per-platform phantom behavior. |
| C-3 | Codex | install-audit `PACK_FILE_PATTERNS` omits `.claude/skills/sd-*/*` in BOTH root (`scripts/sd-ai-command-pack-install-audit.py:38`) and template twin (`templates/scripts/sd-ai-command-pack-install-audit.py:38`). Generic coverage test (`test_install_core.py:2113`) passes on any `.claude/` pattern; rogue-skill regression covers only Qoder (`test_install_audit.py:35`). An unrecorded auto-invocable `.claude/skills/sd-*` would escape audit. | HIGH — parity + audit-coverage gap; MANDATORY not conditional | both audit twins:38; test_install_audit:35 | **addressed** — implement.md: add pattern to BOTH twins + add a Claude rogue-skill regression test mirroring the Qoder one. |
| C-4 | Codex + host | Planned manual drift-check edit is spurious: `SKILL_PUBLIC_ROOTS` derives from `SKILL_FANOUT_PLATFORMS` (`check-command-surface-drift.py:58`), `PUBLIC_PATH_PATTERNS` target `(sd-[a-z0-9-]+)` (`:98`) so `.claude` auto-joins and trellis-* is not falsely flagged. | LOW — plan inaccuracy | drift-check:58,98 | **addressed** — implement.md already changed to verify-only (no edit). |
| C-5 | Codex | AC2 promises read-only `/sd:*` proceed past resolution AND side-effecting skills resolve (`prd.md:79`); implement only checks frontmatter + `Skill("sd-help")` (`implement.md:64`). | MEDIUM — AC not closed by validation | prd.md AC2; implement.md V5 | **addressed** — implement.md V5 expanded: `Skill()` resolves a read-only AND a side-effecting sd skill same-session, and a `/sd:*` command run proceeds past step 1. |

Host lane also independently confirmed: `test_help_command.py:139` hardcoded `25`→`26`; self-deriving gates (`test_surface_generation.py:595`, `test_help_command.py:700`) auto-adjust; C-4.

No unresolved blockers. No lane conflict. All concerns `addressed` in artifacts.

## Round 2 (host + Codex, both ran; Codex exit 0, 181k tokens)

| ID | Sev / blocks | Concern | Evidence | Disposition |
|----|--------------|---------|----------|-------------|
| C-8 | **HIGH — blocks** | Body guard cannot satisfy its own "stop BEFORE loading checkout content" boundary. Auto-invoke loads the SKILL.md into context *before* the guard line runs; a fork checkout that MODIFIED the skill body would just delete the guard. W1 mitigates only the "canonical skill on untrusted DATA checkout" case (Threat B), NOT "attacker-modified skill file" (Threat A). "Closes the gap" is too strong. | design.md:103; sd-fleet-refresh.md:27; Claude project skills load from checkout | **STOP-AND-ASK** — affects whether guard-embed meets the goal. Surfaced to owner. |
| C-9 | HIGH | Guarding `sd-fleet-refresh` skill source leaves its `.agents/skills/sd-fleet-refresh/SKILL.md` root twin STALE — source-only skills aren't manifest-driven and the source-only dev generator emits command adapters only; drift test won't catch it. | generate-command-surfaces.py:883; registry.py:1245; test_pack_drift.py:168 | **addressed** — exclude `sd-fleet-refresh` from W1 (source-only; its skill is never auto-invocable; command already guards). |
| C-10 | HIGH | AC2 probe `Skill("sd-ship")` would EXECUTE the ship workflow (commit/push/PR/merge) — a verification step with side effects. | implement.md:148; sd-ship/SKILL.md:19,75 | **addressed** — verify side-effecting skills by resolution/inspection only, never execution. |
| C-11 | HIGH | W1b "treat sd-start per research doc" could exempt `sd-start`, which loads checkout skill instructions + runs `get_context.py`. | implement.md:43; classification:74; sd-start/SKILL.md:11 | **addressed** — allow-list is now `{sd-help}` ONLY; sd-start explicitly guarded. |
| C-12 | MEDIUM | `test_generated_parity.py` gives NO exact skill-body byte coverage (frontmatter/substring only). "Auto-covered twin parity" claim overstated. | test_generated_parity.py:1453,1879 | **addressed** — rely on explicit `diff -q` (V1); soften claim; optionally add exact-byte twin test. |
| C-13 | MEDIUM | "verbatim" (AC6) vs "adapt self-references" (W1a) contradiction; W1e says "four reason codes" but block has 7 states (3 trusted/untrusted + 4 indeterminate). | implement.md:36,60; sd-fleet-refresh.md:16 | **addressed** — pick "canonical, only self-reference noun adapted"; W1e asserts all 7 reason codes. |
| C-14 | MEDIUM | C-2 audit reconciliation backwards: the 10 phantom skill paths ARE in `SOURCE_ONLY_ALLOWED_PACK_FILES` (not excluded); equality pinned. Claude fleet-refresh phantom path must be ADDED, not excluded. | install-audit.py:85; test_install_audit.py:95 | **addressed** — add `.claude/skills/sd-fleet-refresh/SKILL.md` to `SOURCE_ONLY_ALLOWED_PACK_FILES` mirroring the 10. |
| C-15 | LOW | "passes silently" wrong — block mandates a final `checkout-trust:` report line; and not all 22 commands use the exact gate (`sd-help` uses trusted-static exemption). | sd-fleet-refresh.md:31; sd-help.md:12; design.md:80 | **addressed** — reword "without halting" not "silent"; correct the all-22 claim. |
| C-16 | LOW | design.md R1 resolver-timing says "after make generate"; correct is "after make sync". | design.md:191 vs 62 | **addressed** — fix R1 wording. |

C-9..C-16 are mechanical/wording fixes (apply once direction on C-8 is set).
**C-8 is a blocking substantive concern → stop before `task.py start`, ask owner
(contract §4).**
