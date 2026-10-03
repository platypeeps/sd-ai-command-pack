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

- `plugin_local.js` -- an inert opencode 2.x server plugin (sd:2445). It
  registers and does nothing; a test drops it into a config dir's `plugins/`
  to see whether opencode loads it and whether the probe refuses it.

`tests/test_sd_review_opencode.py::TheEscapeIsClosedLive` builds a throwaway
checkout from these and launches opencode the way the reader does. The marker
that the checkout's config loaded is its MCP server starting: the mutator
writes `server-started` to `MUTATOR_EVIDENCE` during bootstrap. A control arm,
inside the checkout with project config on, shows the marker fires; the
reader's launch, from a neutral dir with an inherited `PWD` naming the
checkout, and from inside with project config off, never fires it. The class
runs only against opencode 2.x, the major the reader accepts, and self-skips
where the binary is absent or another major is installed.

`TheEscapeIsClosedLive::test_opencode_resolves_the_map_and_the_probe_refuses_a_widening`
runs the probe `sd_opencode.confinement_breach` runs before every review: a
private `opencode serve` asked for the resolved agent and its plugins. Under
the reader's environment the resolution is exactly the map, from the neutral
dir and from inside. With project config on, this config's `mutator_mutate`
allowance is contributed but lands before our `*: deny`, as 2.x merges the
inline config last. A rule after the deny is refused, and so is
`plugin_local.js` in the run's config dir; through `XDG_CONFIG_HOME` it no
longer reaches the run, because the reader names its own config dir.
