# Verification protocol

How claims earn their way into an evidence-backed report or claim audit. Source
quality and independence are defined in `source-standards.md`; this file defines
the process that applies them.

## Claim ladder

1. Classify every extracted claim:
   - **load-bearing** — the report's conclusion changes if this claim is
     wrong;
   - **contextual** — background and color.
2. Choose the verification path for each load-bearing claim:
   - One authoritative primary record may support a load-bearing claim only
     when the record is dispositive for the narrowly stated claim and its
     identity and applicability are verified. Bound the claim to the record's
     date, jurisdiction, version, environment, or period.
   - Otherwise require two independent sources, at least one Tier 1–2.
     Empirical, interpretive, disputed, surprising, or interested-party claims
     always require independent corroboration through this path or remain
     visibly low-confidence or unverified. A vendor assertion is not
     dispositive merely because it is first-party.
3. Contextual claims require one source, a date, and visible applicability.

A record is dispositive only when the issuing authority's role establishes the
exact fact being claimed, such as the text and effective date of its own rule,
filing, signed agreement, or versioned specification. Authority over a record
does not make its forecasts, performance claims, interpretations, or
self-interested comparisons dispositive.

## Verification passes

1. **Corroborate.** For each non-dispositive load-bearing claim, find the second
   independent source. Prefer a primary document over a second retelling. For a
   dispositive-record claim, verify the record's identity, authority, scope,
   date, and current applicability instead of manufacturing a redundant echo.
2. **Trace to origin.** Unwind statistics and quotes to their first
   publication; cite the origin. If the chain dead-ends in an unsourced
   assertion, downgrade the claim.
3. **Disconfirm.** For the top conclusions, actively search for contrary
   evidence, supersession, or an applicability limit: opposing analysts,
   criticism-oriented queries, later authoritative records, failure reports,
   and the strongest counter-argument you can find. Record what you searched
   for even when nothing surfaced — an empty disconfirmation pass is evidence
   only if it was a real search. The authoritative-record exception never
   waives this disconfirmation pass.

## Failure handling

- Every evaluated claim stays visible in the claim ledger or evidence-gap
  record. A claim that cannot be verified is labeled **unverified** with
  confidence **low**. If it is load-bearing, it is excluded from conclusions
  and recommendations rather than deleted from the verification record.
- Conflicting sources are presented side by side with dates, plus one
  sentence on which you weight and why.
- Paywalled or inaccessible sources are marked inaccessible; never guess
  their contents from the headline or snippet.
