# Design

Keep the runtime scanner tables static and add a manifest-derived regression
test rather than deriving the tables dynamically.

Static tables preserve the current standalone behavior of consumer-shipped
scripts: `sd-ai-command-pack-pr-body-scope.py` and
`sd-ai-command-pack-install-audit.py` can run in a target repo without reading
the source checkout manifest. The new test loads `manifest.json` in this source
repo and asserts every shipped file target is covered by both scanner surfaces
at subpath granularity, excluding managed block targets where file-shape
matching is not the contract.

This gives the manifest a durable reconciliation role without changing
consumer behavior.
