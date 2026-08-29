# Implementation plan: portable structured questions

## 1. Inventory Decisions And Host Capabilities

- Enumerate all current user-question points and classify whether repository
  evidence, invocation authority, a safe default, or user judgment owns them.
- Verify supported structured tools and limits for each generated platform.

## 2. Define The Interaction Contract

- Add validated decision descriptors or shared canonical guidance.
- Add capability metadata and conservative absent/unknown behavior.
- Encode common shape and question-economy validation.

## 3. Generate Host-Specific Guidance

- Add `AskUserQuestion` instructions to capable Claude adapters.
- Generate equivalent supported guidance for other hosts and plain/stop
  fallbacks where needed.
- Prohibit unsupported host names in neutral/cross-platform output.

## 4. Apply To Owning Skills

- Update the initial matrix consumers in their source templates.
- Remove redundant questions for already-authorized behavior.
- Preserve noninteractive fail-closed behavior for material decisions.

## 5. Validate

- Run descriptor/schema, capability matrix, generated snapshot, fallback,
  noninteractive, and no-redundant-prompt tests.
- Run `make sync`, `make check`, install audit, and representative adapters for
  Claude plus at least one structured-unsupported platform.

## Stop Points

- Stop if a host's tool contract has not been verified; use the portable plain
  fallback rather than inventing a tool name or schema.
- Stop if a proposed question would broaden standing authority or bypass a
  deterministic safety gate.
