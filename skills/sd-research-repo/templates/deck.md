# deck.json example

Copy the block below to `30-brief/deck.json`. It is the example and the schema in use; `tests/test_sd_research_deck.py` builds it.

```json
{
  "name": "Example Revamp",
  "tagline": "Iteration 2: execution.",
  "date": "2026-10-20",
  "theme": {
    "cta": {"text": "Learn more", "url": "https://example.test/"}
  },
  "slides": [
    {
      "eyebrow": "Example Revamp  ·  Iteration 2: hypothesis and plan",
      "title": "A targeted revamp,",
      "accent": "not a rebuild.",
      "cards": [
        {"head": "1. Discover", "text": "Map the capabilities, probe production, rank the gaps", "pill": "Iteration 1 · done", "tone": "done"},
        {"head": "2. Fix in small PRs", "text": "Close each gap in a small, tested pull request", "pill": "Iteration 2 · now", "tone": "now"},
        {"head": "3. Ship and measure", "text": "Release, add one usage metric, decide the policies", "pill": "Iteration 2 · next", "tone": "planned"}
      ],
      "foot": "Pass when both client generations work and one usage metric has an owner."
    },
    {
      "eyebrow": "Example Revamp  ·  Iteration 2: execution",
      "title": "The service works.",
      "accent": "Now it needs reviewers.",
      "track": [
        {"label": "Discovery", "note": "iteration 1 · done", "state": "done"},
        {"label": "Review", "note": "iteration 2 · we are here", "state": "now"},
        {"label": "Merge", "state": "next"},
        {"label": "Production", "state": "next"}
      ],
      "cards": [
        {"big": "47", "text": "tools. Discovery and listing pass on production."},
        {"big": "11", "text": "pull requests open and passing CI. None has a reviewer yet."},
        {"big": "9", "text": "tickets for the next round."}
      ],
      "foot_label": "Asks:",
      "foot": "review the open pull requests, smallest first.",
      "link": {"text": "START HERE, Example Revamp: Status", "url": "https://example.test/status"}
    }
  ]
}
```
