# sd-review Configuration Operations Design

## Flow

```text
sd-review config <operation>
  -> discover compatible router capability
  -> validate local arguments and write intent
  -> invoke versioned router operation
  -> validate bounded response
  -> render stable human output and optional structured result
```

The controller treats router output as authoritative. It may format fields but
does not recalculate eligibility, normalize source independently, or produce a
competing digest.

## Operation Matrix

| Operation | Input | Result | Mutation |
| --- | --- | --- | --- |
| `init` | preset/version, destination | full explicit source and provenance | Explicit repository write |
| `validate` | source/catalog identities | diagnostics with locations | None |
| `render` | source/catalog identities | canonical manifest, explicit merge policy, and digests | None |
| `explain` | compiled identity and safe context | no-dispatch selection and assurance/gate readiness explanation | None |
| `diff` | current and proposed identities | semantic policy and Check-readiness change report | None |
| `migrate` | v1 source and target v2 version | preview plus transactional v2 write | Explicit repository write |

## Write Safety

`init` and `migrate` preview their result, verify the destination remains at
the observed identity, use atomic repository writes, and stop on conflicting
content. Migration retains a recoverable original until the v2 source validates
successfully. Noninteractive adapters require an explicit mutation flag or
equivalent unambiguous user instruction.

## Output Safety

Human and structured output allow only contract-declared safe aliases,
versions, diagnostic codes, locations, and digests. Credential values, private
catalog attributes, raw control-plane payloads, and inferred defaults are
rejected or redacted.

The pack does not choose or default merge behavior. It displays the router's
explicit `budgetExhaustion.<lane>.merge` value and stable assurance/gate Check
readiness. Branch-protection changes are guidance only unless a separately
authorized repository operation is introduced.
