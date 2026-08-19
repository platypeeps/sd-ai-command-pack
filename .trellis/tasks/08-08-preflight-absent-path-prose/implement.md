# Implementation plan

Order matters: the code change and the two content reverts land in one commit,
because either alone leaves `main` in a worse state than before (see
`design.md`, Rollback).

"Acceptance criterion N" below means the Nth bullet of the PRD's Acceptance
criteria list, counted in order: 1 preflight green, 2 marked-passes/unmarked-
fails, 3 no cross-file leak, 4 the two references fixed without touching
`optionalReferencePaths`, 5 marker visibility as a static syntax check,
6 `optionalReferencePaths` unchanged from both sources, 7 `make check`.

## 1. Marker recognition in the template script

- [ ] In `templates/scripts/sd-ai-command-pack-review-preflight.mjs`, add a
      module-level constant next to the other reference patterns:

      ```js
      const ABSENT_PATH_MARKER_PATTERN =
        /^[ \t]*\[absent:[^\]\r\n\u2028\u2029]*[^\]\s][^\]\r\n\u2028\u2029]*\]/;
      ```

- [ ] In `extractDocumentationPathReferences`, compute the end offset of each
      match and skip the reference when the text at that offset matches the
      pattern.
- [ ] Record each `markdown-link` match's `[start, end)` span **and its
      resolved target** in the first pass. In the `code-span` pass, a match
      wholly inside one of those spans accepts a marker at that link's end
      **only when the two targets are the same path**; otherwise only its own
      end counts. Without the span rule, the common `` [`docs/x.md`](docs/x.md) ``
      form yields two references and a marker after the link suppresses only
      one. Without the same-target condition,
      `` [`docs/display.md`](docs/target.md) `` lets one marker silence two
      different paths. See `design.md`, "The code-formatted link".
- [ ] Export a named predicate (`isAbsentPathMarked(text, endOffset)` or
      equivalent) so the node unit harness can assert the fail-closed cases
      directly rather than only through end-to-end output.
- [ ] Leave `shouldCheckDocumentationPathReference` untouched — it sees only a
      target string and must stay a pure function of the path.
- [ ] Update the `pass()` message in `checkDocumentationPathReferences` to name
      all three accepted outcomes: resolved, optional by configuration, or
      marked absent at the point of use.

Validation: `node --check` is not applicable to ESM specifics here, so use
`node -e "import('./templates/scripts/sd-ai-command-pack-review-preflight.mjs')"`
to confirm the module still parses and loads.

## 2. Mirror, generate, and treat this as a payload change

The template is a manifest payload row (`manifest.json:278`), so this is a
release-payload change with obligations beyond a file copy. See `design.md`,
Shipped-payload consequences.

- [ ] `make sync` — `install.py . --force` synchronizes
      `scripts/sd-ai-command-pack-review-preflight.mjs` from the template and
      refreshes the spec KB. Do not hand-copy the mirror.
- [ ] `diff templates/scripts/sd-ai-command-pack-review-preflight.mjs scripts/sd-ai-command-pack-review-preflight.mjs`
      must print nothing afterwards.
- [ ] `make generate` — refreshes the plugin `bin/` and `machine-payload/`
      copies. `tests/test_generate_plugin.py:827` fails on drift and names this
      command.
- [ ] Bump `manifest.json` and add the matching top `CHANGELOG.md` heading. CI
      runs a `Release payload gate` against the PR base and blocks a payload
      change without both (`CONTRIBUTING.md:146-152`).
- [ ] Do **not** run `make release-prep` here. It goes in step 8, after the
      last shipped-payload edit; `CONTRIBUTING.md:133-134` says to run it only
      once payload, version, changelog, and documentation edits are ready, and
      step 5 still edits `templates/docs/SD_AI_COMMAND_PACK.md`.
- [ ] Budget for the release tail. A one-function change to the preflight
      carries a bump, a changelog heading, generation, and fleet candidate
      validation, and that tail is most of the work. It is not optional and not
      deferrable to a follow-up: CI blocks the pull request without it.

## 3. Revert the two backtick-stripping workarounds

Both are the degradation this task exists to remove, and both must move to the
new marker rather than to `optionalReferencePaths`.

- [ ] `.trellis/tasks/08-07-distributed-gitignore-python-cache/prd.md`:
      restore the code span on the `check_review_readiness.sh` reference and on
      the `scripts/__pycache__/y.pyc` reference, and add a marker to each.
      Reword the surrounding sentence where needed so the reference sits
      immediately before its marker.
- [ ] `.trellis/tasks/08-08-preflight-absent-path-prose/prd.md`: this document
      applies the same degradation to itself in its blockquote and in the
      sentence explaining the allow-list. Restore both code spans, add markers,
      and delete the parenthetical that explains why the quotation deliberately
      drops the backticks — it is no longer true.

## 4. Tests

Node unit harness, inside the `-e` module script in
`tests/test_review_preflight.py`:

- [ ] A marked reference is not collected by
      `extractDocumentationPathReferences`, and an unmarked reference to the
      **same path in the same text** still is. This is acceptance criterion 2
      and requirement 5; assert both in one fixture so the pair cannot drift
      apart.
- [ ] Each fail-closed case from `design.md` leaves the reference collected:
      empty reason, missing colon, marker on the following line, marker before
      the reference, unclosed marker, non-whitespace between reference and
      marker, and `[absent:]]` — the case a `\S` reason class would wrongly
      accept with an empty reason.
- [ ] A marker after a `markdown-link` reference exempts it on the same terms
      as a `code-span` reference.
- [ ] `` [`docs/missing.md`](docs/missing.md) [absent: reason] `` yields no
      reference at all. Verified 2026-08-19 that the unfixed extractor returns
      two references for that form, so this test fails before the link-span
      anchor exists and passes after.
- [ ] `` [`docs/display.md`](docs/target.md) [absent: reason] `` still yields
      the `docs/display.md` code-span reference and drops only the link. This
      is the same-target condition; without it one marker silences two paths.
- [ ] A reason containing `\r`, U+2028, or U+2029 does not suppress. These are
      JavaScript line terminators that `[^\]\n]` would have admitted.

Python integration tests, alongside
`test_review_preflight_accepts_line_suffixed_doc_references`:

- [ ] A temp repo with a marked missing path in `docs/a.md` and the same
      missing path unmarked in `docs/b.md` fails on `docs/b.md` only. This is
      the "does not leak across files" criterion; the marker's per-match scope
      makes it true, and the test states it.
- [ ] `optionalReferencePaths` extension through
      `.sd-ai-command-pack/review-preflight.json` still skips a path. The
      existing assertions cover only the built-in defaults, so this is the half
      of requirement 3 that is currently unproven.
- [ ] The existing `optionalReferencePaths` assertions pass **unmodified** —
      the block of `shouldCheckDocumentationPathReference(...)` equality
      assertions over the built-in default paths. Identify them by content, not
      by line number; adding tests above them shifts every line.

Marker-visibility criterion (acceptance criterion 5), a static syntax check:

- [ ] A test enumerates every `[absent:` occurrence in the repository's
      documentation files and asserts that (a) it is not followed by `(` or
      `[`, which is what would turn it from literal text into a link and change
      how it renders, and (b) no `[absent: ...]:` link reference definition
      exists in the file, which would turn the marker into a shortcut reference
      link.
- [ ] Do **not** additionally require every occurrence to follow a path
      reference. `.trellis/tasks` is a documentation root, and this task's own
      `design.md` and `implement.md` discuss the marker in prose and in a
      regex; such a rule fails on the documents that define it. A suppressed
      reference is a code span or a Markdown link by construction — extraction
      finds nothing else — so the formatting half needs no separate assertion.
- [ ] State the limit in the test's own comment: this proves the marker is
      literal text rather than link syntax; it does not execute a Markdown
      renderer. The repository has no Markdown dependency (`package.json`
      carries `c8` alone) and the preflight is deliberately dependency-free.
      Acceptance criterion 5 was amended on 2026-08-19 to ask for exactly this
      static check, so the plan closes it as written rather than substituting a
      proxy for something the PRD still demands.

## 5. Documentation

- [ ] `templates/docs/SD_AI_COMMAND_PACK.md`, in the review-preflight section
      that lists what the check accepts (near the `optionalReferencePaths`
      sentence): document the marker, its required reason, and that it is
      scoped to the one reference it follows.
- [ ] The illustrative path in that sentence must be **ineligible** for the
      check — matching no `referencePrefixes` prefix and no
      `topLevelReferenceFiles` entry — or the example fails the installed
      preflight in every consumer still on an older pack. Fencing does not
      help; see `design.md`, Compatibility. `example/absent-file.md` is
      ineligible today (verified 2026-08-19:
      `shouldCheckDocumentationPathReference('example/absent-file.md')` returns
      `false`, while `docs/absent-file.md` returns `true`). Re-verify whatever
      path is chosen rather than trusting this note.
- [ ] Mirror to `docs/SD_AI_COMMAND_PACK.md`.

## 6. Record phase 2 as a successor, do not build it

The PRD absorbs `08-06-preflight-bare-filename-references` as R1-R4 and
sequences it strictly after this escape hatch. It is not in this change.

- [ ] Create a successor Trellis task carrying R1-R4 verbatim, referencing this
      task as its predecessor. Do it when this task's work is complete, not
      before — a successor created early competes for selection with the task
      it depends on.
- [ ] Amend the PRD's absorbed section to say where phase 2 went, so the
      requirement is traceable rather than silently dropped.

## 7. Trim the sibling task

- [ ] `.trellis/tasks/08-18-preflight-path-refs-ignore-aware/prd.md`: record
      what this task delivers — the inline marker and the corrected `pass()`
      message, which answers its requirement 6 — and reduce its remaining scope
      to what a tracked declaration would still buy over a marker. Do not
      archive or delete it here.
- [ ] This makes the change span more than one Trellis task directory, which
      the preflight warns about. Disposition that warning explicitly in the PR
      body: the two content reverts are required by requirement 4 and the
      sibling trim prevents a merged change from leaving a task claiming
      unbuilt behavior.

## 8. Release preparation, last

- [ ] `make release-prep`. This is not conditional: the only bumpable field in
      `manifest.json` is `version` (currently `0.71.33`), so every payload
      change is a version bump, and a version bump requires the all-pass
      `docs/fleet/candidate-validation.json` that `release-prep` produces or
      reuses, matching the exact payload and fleet manifest
      (`CONTRIBUTING.md:150-152`).
- [ ] Nothing under `templates/**`, `docs/SD_AI_COMMAND_PACK.md`, or
      `manifest.json` may change after this step. Any later edit invalidates
      the exact-payload fleet evidence and the step must be repeated.

## Validation

This is the loop to run **while iterating on steps 1 through 7**, not a second
pass after step 8. `make release-prep` already runs generation, sync, and
`make check` itself, so once step 8 has produced the fleet evidence, re-running
`make sync` or `make generate` is only safe if it changes nothing — and if it
does change something, step 8 has to be repeated rather than the change kept.

Run in order; each must pass before the next is meaningful.

```bash
node -e "import('./templates/scripts/sd-ai-command-pack-review-preflight.mjs')"
make sync
make generate
diff templates/scripts/sd-ai-command-pack-review-preflight.mjs \
     scripts/sd-ai-command-pack-review-preflight.mjs
python3 -m pytest tests/test_review_preflight.py tests/test_generate_plugin.py -q
node scripts/sd-ai-command-pack-review-preflight.mjs
make check
```

Acceptance-criterion 4 evidence — the config array is untouched:

Compare the array's bytes directly. A diff grep is not sufficient: a change to
an entry in the middle of the array produces a hunk that never contains the
declaration line, so the grep comes back empty while the bytes differ.

```bash
extract() {
  sed -n '/optionalReferencePaths: \[/,/^    \],$/p'
}
git show origin/main:templates/scripts/sd-ai-command-pack-review-preflight.mjs \
  | extract | shasum
extract < templates/scripts/sd-ai-command-pack-review-preflight.mjs | shasum
```

The two digests must be equal. That is the byte-identity evidence acceptance
criterion 4 asks for; the existing per-path assertions in
`tests/test_review_preflight.py` cover the behavioral half. A difference means
the fix took the shortcut requirement 4 forbids.

## Review gates

- Planning convergence: the adversarial planning review contract in
  `.claude/rules/sd-planning-adversarial-review.md` runs before `task.py start`.
- `node scripts/sd-ai-command-pack-review-preflight.mjs` reporting zero
  failures is acceptance criterion 1. It passes on `main` today and proves
  nothing until step 3 restores the two stripped code spans; run it after that
  revert, not before, or it certifies the workaround rather than the fix.
- Remote review on the pull request, per the normal loop.

## Rollback points

- After step 1, before step 2: revert the template script. Nothing else has
  moved.
- After step 2 there is no two-file rollback. Step 2 also rewrites the root
  mirror, the plugin `bin/` and `machine-payload/` copies, `manifest.json`, and
  `CHANGELOG.md`. Reverting only the two scripts leaves generated copies and
  release metadata describing a change that is no longer there, which
  `tests/test_generate_plugin.py:827` and the `Release payload gate` both
  catch. Roll back by reverting the whole commit, then re-running `make sync`
  and `make generate` to prove the tree is clean again.
- After step 3: the code and the content are one unit. Revert both together —
  reverting only the script re-fails the same two references.
