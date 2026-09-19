# Provider recovery

Read this only for an explicitly authorized URL-provider diagnostic or recovery task.
Do not start the cancelled `sd:777` experiment.
Do not treat recovery instructions as permission to select an explicit-only provider.

## Synthetic preflight

Inspect `sd-review --preflight --provider NAME --explain --json` first.
This resolves one URL provider without calling it.
It checks consent, enabled state, credentials, transport, and committed-branch authorship.

Without `--explain`, the command sends one fixed synthetic schema probe.
It sends no repository source or local conventions.
It spends one provider call within the authorized allowance.
It does not retry, select fallback, run repository checks, or establish code-review coverage.
CLI providers, review modifiers, and `--dry-run` are invalid here.
Use `--explain` for zero calls.

The receipt names `operation: provider_preflight` and `scope: provider_preflight`.
Requested and completed reviews remain zero.
`preflight_passed` requires the requested empty findings response.
It proves neither source coverage nor the serving model's identity.
`preflight_failed` exits 5.
`preflight_planned` makes no recovery claim.

## Diagnostics and evidence

Diagnostics retain configured provider, vendor, model, host, options, prompt digest, and observed HTTP status.
Failure stages distinguish transport, HTTP, API, envelope, completion, and schema errors.
Sanitized responses preserve fixed-key structure, types, byte counts, digests, and bounded numeric usage.
They omit arbitrary response content, reasoning, model identifiers, error messages, headers, and credentials.
Returned-model absence or mismatch remains explicit.
Hashes cannot recover discarded raw responses.

Local fixtures are not live provider acceptance.
An authorized exact-head `--scope branch --provider <name>` review can provide evidence for that selected registry entry.
It does not waive required review depth, author exclusions, spending limits, or shipping gates.
An exhausted allowance stops further calls.
