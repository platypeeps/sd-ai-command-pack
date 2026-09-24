# Operator defaults

These rules apply to Claude and Codex work in this pack and its companion repositories.
They record this maintainer's choices, not installation grants for another operator.
Explicit task instructions and stricter execution permissions take precedence.

## Reviewers

- Prefer Codex when no reviewed commit carries OpenAI authorship.
- Use Claude as backup, including for Codex-authored changes, when Anthropic did not author the reviewed change.
- Do not let a provider review its own vendor's work.
- Use MiniMax or Baseten only after an explicit user request naming that provider for the task.
- Do not select either provider automatically for fallback, retries, or an additional review slot.
- Availability, configured credentials, and standing transmission consent do not constitute that explicit request.
- If no permitted independent reviewer remains, report that condition once and stop the review.

Before expensive checks or external transmission, inspect `sd-review --explain --json` for the intended scope.
Check the complete fallback chain, required review count, authorship exclusions, and effective authorization.
Stop if the plan includes an unrequested explicit-only provider.
One completed independent local review satisfies each reviewing tier; risk classification does not add reviewers.
Complete local review and fix verification before requesting any Copilot review.
Copilot is an optional second review.
Repository policy may request it automatically for the configured `deep` tier.
Otherwise, request it only after explicit task direction.
Do not repeat an automatic request after a later push.
Honor repository restrictions on remote reviewer requests.
An unavailable local reviewer needs an operator decision, not an automatic remote escalation.

The pack's consent and the agent runtime's execution approval are separate boundaries.
Name the rejecting boundary and exact intended recipient when approval is missing.
Do not request blanket approval for unused fallbacks or weaken the runtime's protections.

## Writing and diagrams

Writing style and diagram tooling come from each agent's global instructions.
This file does not restate them.

## Reports

Treat skill report fields as a completeness check, not mandatory headings in every reply.
Include only applicable results, verification evidence, unresolved limits, and required decisions.
Link detailed evidence instead of repeating it in chat.
Do not omit failed checks or incomplete work to shorten a report.

## Enforcement boundary

These are agent instructions, not proof that generated prose or provider dispatch complies.
The executable review gate reads its registry, authorization, and tier policy.
Existing installations retain their configured reviewer order until explicitly migrated.
Report conflicts before execution; do not describe changed defaults as a completed machine migration.
