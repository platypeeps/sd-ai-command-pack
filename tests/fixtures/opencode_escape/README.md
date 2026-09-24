# opencode confinement escape fixture (sd:1375)

A hostile reviewed checkout used to prove, and now to regression-guard, the
config-merge escape that `bin/sd_opencode.py` closes by launching opencode
from a neutral directory instead of inside the checkout.

- `checkout_opencode.json` -- what a reviewed repository would ship as its own
  `opencode.json`: it re-grants `bash` and an MCP mutation tool that our
  default-deny map denies. opencode deep-merges it over our inline config when
  it runs inside the checkout; our `*: deny` wins the wildcard, its two
  specific allowances survive under it, and last-match evaluation permits them.
- `AGENTS.md` -- repository instructions ordering the reviewer to call the
  mutation tool and run a shell command. Loaded as instructions only when the
  checkout is opencode's project root.
- `mutator_mcp.py` -- an inert MCP stdio server with one tool. It writes only
  to the file named by `MUTATOR_EVIDENCE` and touches nothing else, so a test
  can see whether the tool was reachable without any real side effect.

`tests/test_sd_review_opencode.py::TheEscapeIsClosedLive` builds a throwaway
checkout from these, launches opencode the way the reader does, and asserts
the checkout's config is not contributed (no `loading path=` line for it) and
the mutation does not fire. It self-skips where the `opencode` binary is
absent; the config-load half is offline and needs no credentials.

`TheEscapeIsClosedLive::test_opencode_resolves_the_hostile_config_as_a_breach_by_any_route`
asks opencode what it resolved (`opencode debug agent sd-review --pure`, the
probe `sd_opencode.confinement_breach` runs before every review). From inside
the checkout the resolution carries this config's `bash` and `mutator_mutate`
allowances; from a neutral dir it is clean; and the same file handed in
through `XDG_CONFIG_HOME` is refused again. That last route is why the
neutral dir alone is not the boundary.
