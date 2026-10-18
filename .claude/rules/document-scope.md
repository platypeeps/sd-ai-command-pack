---
paths:
  - "**/*.md"
  - "tests/test_doc_citations.py"
---

# What a document owns

- A document owns the scope it describes, never the argv that reached it: a page about this pack's rules describes them whichever command opened it.
- Leave a path written for the reader's own checkout unqualified.
- These rules bind live text only: never rewrite a preserved review or an archived work item to match current behavior.
- An archive move may add lifecycle metadata, never change the recorded discussion.
- A provenance citation needs no qualifying: naming where a fact came from is not an instruction to open it.
- Qualify a path only when it points into `.claude/rules/`: the pack authors that surface and cannot install it in the reader's checkout.
- Leave the per-repository configuration `bin/sd_setup_github.py` writes under `.github/` unqualified: the reader's checkout carries it.
- `tests/test_doc_citations.py` enforces both scopes and enumerates them from the filesystem.
