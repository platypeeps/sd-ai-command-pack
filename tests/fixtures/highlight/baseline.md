**Review copy — The Memory Experiment, Twice: a Team Retro and a Personal-Framework Field Report**

Repo: content/2026/memory-experiment-retro/index.md · status: drafting · 1755 words · pushed 2026-11-02 12:04

Comment, suggest, or edit — the author pulls all three back into the repo. Suggestion mode is clearest; direct edits are recovered as a diff against this pushed copy.

---

"Just vibe code it" has become a normal thing to hear in engineering. Over about six weeks this fall, a small group of us at Mezmo built an agent memory service mostly with coding agents, took it from nothing to a working service in our dev environment, and got a successful demo out of it. This piece is what that taught me about speed, review and breakage. I don't have the final answer. I want to start a conversation with the engineers who will have to live with whatever we settle on, and the sceptics most of all.

## Where the pressure comes from

The push comes from the whole industry, and *mostly* from the top. Shopify's CEO told staff that [reflexive AI usage is a baseline expectation](https://betakit.com/shopify-ceo-tobi-lutke-tells-employees-to-prove-ai-cant-do-the-job-before-asking-for-resources/). Coinbase's CEO [fired engineers who didn't onboard to AI tools](https://techcrunch.com/2025/08/22/coinbase-ceo-explains-why-he-fired-engineers-who-didnt-try-ai-immediately) within a week, and [set a goal of more than half its code being AI-written](https://decrypt.co/338072/brian-armstrong-wants-half-of-coinbase-code-to-be-ai-written-by-october).

So both camps have a point, because output and mess go up together.

## Where I stand

The shift I expect is from "prevent every break" to **break fast, detect fast, fix fast**. DORA's own guidance says ["speed and stability are not tradeoffs"](https://dora.dev/guides/dora-metrics/). The incident record backs the mechanics. Google Cloud's [June 2025 outage report](https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW) traced the failure to a code path that "did not have appropriate error handling nor was it feature flag protected." CrowdStrike's [root cause analysis](https://www.crowdstrike.com/wp-content/uploads/2024/08/Channel-File-291-Incident-Root-Cause-Analysis-08.06.2024.pdf) landed on staged rollout with rollback.

## Risks and open questions

- [ ] The tiers only work if "experiment" really means throwaway. An experiment that touches production credentials or shared data is high blast radius, whatever we call it.
- [ ] Detection costs something. Flags and canaries carry their own debt, and I haven't found a good public number for what they cost a small team.
