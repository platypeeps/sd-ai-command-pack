---
name: sd-draft-review
description: Use when the user wants a draft from a writing content repository pushed to a private Google Doc for human review, or wants the reviewers' comments and edits pulled back as a working list.
disable-model-invocation: true
---

# sd-draft-review

Two modes on one private review copy per piece:

- `push` writes the draft and its research to Google Docs in the private drafts folder.
- `pull` reads comments and edits back. It writes nothing anywhere.

Run from the root of the writing content repository (it holds `scripts/pack.py`). `pack` below means `python3 scripts/pack.py`.
The piece comes from the arguments; with none, ask which piece, or offer the ones at `review` (push) or with a recorded review URL (pull).
Always pull before a push that replaces a document: a replace overwrites reviewer edits in the body, and no tool here recovers them.

It has no `bin/` command: the steps below are the procedure, and `scripts/pack.py` and the `workspace-mcp` tools do the work.

## Settings

```bash
sd config get sdw.google_account
sd config get sdw.drive_writing_folder
```

An unset value exits 1 and prints the `config set` command that fixes it. Stop and show the user that line. Never guess an address or a folder.
This skill writes only the drafts folder. It never writes the publishing folder: a draft there is published unreviewed. `sd-publish-drive` owns that folder.

## push

1. `pack pieces get --piece <year>/<slug> --json`; use `item.path` and `writing.stage`.
   - `review` is the intended stage. `drafting` and `ready` are allowed; name the stage in the report.
   - `idea` and `researching` refuse (suggest `sd-draft`); `published` refuses.
   - An empty or placeholder `## Draft` stops the push.
2. Read `writing.metadata.review_urls.gdocs`. A recorded URL means **replace in place**: one review doc per piece, one URL that never changes. Never create a second copy.
   If the piece has no `review_urls` block, run `pack pieces backfill-urls --piece <year>/<slug>`.
3. Confirm the push with the user every time. It writes to their Drive.
4. Build both documents with `pack review build-html --piece <year>/<slug> --out <scratch dir>`. It writes `draft.html` (the `## Draft` prose only, never `Notes / angle` or `Outline`) and `research.html` (all of `research.md`, marked internal), with images inlined. Do not hand-roll a converter.
   Check the printed `images=` count against the piece's `images/` folder. A `WARNING: missing image(s)` line is a stop.
5. Confirm the folder: `get_drive_shareable_link` on `drive_writing_folder` must return the drafts folder's name, not the publishing folder's. If it returns the publishing folder, the two keys are swapped: stop and tell the user.
6. Copy both files into the `workspace-mcp` attachments folder (`~/.workspace-mcp/attachments` by default; the server's refusal names it). Always pass `file_path`, never `content`.
7. Each piece gets `<drafts>/<year>/<slug>/`. Search for the year and slug folders before creating them.
   - First push: `import_to_google_doc` per document with `user_google_email`, `folder_id`, `file_name` (the title, or `Research — <title>`), `file_path`, and `source_format: "html"`.
   - Re-push: `update_drive_file` with the recorded `file_id`, the new `file_path`, and `source_format: "html"`. Say in the report that comment anchors detach, and that revision history keeps the old body.
   - A result that is not `application/vnd.google-apps.document` is a failure to report.
8. Read the doc back with `get_doc_as_markdown` (`comment_mode: "none"`). Check the header word count and push date, that images came back as `googleusercontent` URLs, and that headings arrived as `##`.
9. `pack pieces set-review-url --piece <year>/<slug> --target gdocs --url <draft URL>`. It also stamps `review_urls.gdocs_digest`. It changes no stage.
10. If the piece has `obsidian_source`, merge the links into its idea note's `Drive docs` section:
    `sd store get sdw.blog-idea "<idea title>" --section 'Drive docs'`, merge, then `sd store set sdw.blog-idea "<idea title>" --section-file 'Drive docs=<file>'`.
    The section is replaced whole, so carry the old lines over. One `- <label>: <url>` line per document: `Draft review copy`, `Research notes`, `Published copy`. Without `obsidian_source`, say so.

Push report: the URL, word count, stage, and how comments come back (`/sd-draft-review pull`; nothing watches for them). A failed push leaves `review_urls.gdocs` unchanged.

## pull

1. `pack pieces get --piece <year>/<slug> --json`; take `writing.metadata.review_urls.gdocs`. A null, empty or missing value means never pushed: say so and suggest `push`. Take the document ID from that URL only; never search Drive for a likely title.
2. `pack review status --piece <year>/<slug>`. A `review=stale` or `unstamped` copy may quote sentences that no longer exist: say so at the top of the report.
3. Comments: `list_document_comments` with `user_google_email` and `document_id`. "No comments" and "could not read" are different results; on an error, report it and stop. `get_doc_as_markdown` shows comments against their anchors when an anchor is thin.
4. Suggestion-mode edits: `get_doc_as_markdown` with `suggestions_view_mode=SUGGESTIONS_INLINE`.
5. Direct edits: rebuild with `pack review build-html`, confirm its digest matches `review_urls.gdocs_digest` (if not, report that instead of a mixed diff), then diff the `## Draft` markdown against the doc's markdown, whitespace-insensitive. Drop what the transport adds:
   - the header block;
   - image lines: compare image count and order only, not URLs or alt text;
   - an italic line under an image that matches that image's alt text. An italic line that differs is a reviewer's caption edit: report it.

Pull report, grouped by what the user must do:

- Open comments: quoted anchor, author, comment verbatim, replies in order.
- Resolved comments, briefly.
- Edits, both kinds. An edit is an opinion; it reaches the repository through an `sd-draft` pass the user approves.
- Factual challenges, called out on their own as work for the fact-check gate in `sd-draft`. Do not run that gate from here.

Then say what did not happen: nothing was applied, comments are still open, and no reviewer got a reply.

## Safety rules

- `pull` makes no writes: no reply, resolution or edit in the doc; no change to prose, stage, `review_urls` or `updated`.
- `push` writes only the drafts folder tree and only after the user confirms.
- Never reconstruct a document ID or a folder ID.
- Never edit the draft from a review comment; offer `sd-draft` instead.
