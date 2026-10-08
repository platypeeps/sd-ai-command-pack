# Provider registry detail

The detail behind the shipped registry entries in [WORKFLOW.md § Providers](../WORKFLOW.md#providers).
It describes the meter, token ceiling and reasoning controls each shipped entry uses.

Pins as of 2026-09-05, each read from the vendor's model list on that day:
`kimi-k3` is Moonshot's current flagship with a one-million-token window;
`MiniMax-M3` is MiniMax's newest, and it runs on the Token Plan the
operator has already paid, so the entry's price is zero and the bill
carries a meter instead: the plan grants use in a five-hour window and a
weekly window, and `GET /v1/token_plan/remains` on `www.minimax.io`, with
the same key, answers with `current_interval_remaining_percent` and
`current_weekly_remaining_percent` for `model_name: general`, probed
2026-09-05. The bill carries that meter as a URL and the variable holding
its key as `meter_env`. A review reads it only for an eligible selected or fallback provider: one `GET` to
that URL, and to no other -- the scheme, host, port and path are pinned in
`bin/sd_registry.py` and any other value is refused naming the value and
the four, with nothing sent -- then the two percents written as `meter`
rows for every enabled entry on the bill, then the newest row per window
read back. A window at zero, no row at all, or a newest row older than
five hours puts the bill beside the capped ones, so fallthrough passes it
over and `--provider` refuses it by name; a `GET` that fails writes nothing,
names itself in the result's `meter_faults`, and the rows already there
decide; `--explain` and `--dry-run` send nothing and read the rows alone. A
`meter:` without a `meter_env:` reads, and caps the bill at that step naming
the missing field, because a reinstall never rewrites this file in your
home. The Baseten registry entry pins `deepseek-ai/DeepSeek-V4-Pro-0813`.
`max_tokens` bounds generated reasoning and the final answer together;
exhausting it does not establish that the review subject was too large.
The shipped entries give each reviewer 65536, well under each model's
documented output ceiling. At 16384, `kimi-k3` spent the whole budget
reasoning on a 35k-token prompt and sent no answer (sd:1805); K3 always
thinks, and its effort can only drop to `low`. A stop at the ceiling reads
`<name> hit max_tokens (N) and it sent no answer`, with the completion
tokens and reasoning bytes, and `sd-ship` repeats that detail in its
refusal, one equal share of its bound per failed reviewer, each under its
name. A `length` stop below the ceiling says the context window may be
full and names shortening the review input first. An entry with no
`max_tokens` reads `stopped on length with no max_tokens set`, and names
setting one (sd:1819). The installer never rewrites the registry in your home, so a
home copy still at 16384 keeps the old ceiling until you edit it.
URL entries can declare one optional control: `thinking: disabled|adaptive`
or `reasoning_effort: none|low|high|max`. The client sends `thinking` as
`{"type": "disabled"}` or `{"type": "adaptive"}`, and effort as a top-level
string. Both registry readers validate and preserve these fields; omission
retains the endpoint default. These values require support from the selected
model: MiniMax-M3 supports disabled thinking, and Baseten's DeepSeek-V4-Pro-0813
supports effort `none`. Lower reasoning can change finding quality; full
subject coverage and the required reviewer count remain mandatory.
A URL entry can also declare `response_format: json_schema`. `sd-review`
then sends the findings schema as a strict `response_format`, in the copy
Moonshot's strict mode takes: every property typed, `line` as `anyOf`
integer or null, and no `minLength` or `maxItems`. The answer is still parsed
against the full schema. Only an entry that declares the field sends it; an
endpoint that accepts it may ignore it, as MiniMax-M3 does (sd:1827).
The shipped `kimi` entry declares it, and no other entry does. A home copy
seeded before that keeps its own entry; add the line there by hand.
Incomplete output still fails the review. A pin is changed by editing the
registry file, never by a page.
A `url` answer that fails the findings schema is retried once on the same
entry only when its `price` names both `in` and `out` as zero, so a retry
never doubles a bill; the failed attempt stays in the outcomes with any
blocker it recovered. A priced entry falls through to the next reviewer as
before. Temperature is not a registry field: `kimi-k3` refuses any value but
1, and MiniMax-M3 at 0.2 broke the schema as often as at its default (sd:1821).
