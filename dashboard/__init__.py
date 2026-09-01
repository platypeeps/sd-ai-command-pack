"""The pack's own dashboard: a view over the checkout fleet, and one way to act.

Deliberately small. The system dashboard it will eventually replace is 1,728
lines and collects from a dozen sources; this one starts with the facts the
backbone itself owns and grows a tab at a time under the 3c-to-6b parity
checklist. It was read-only until 6b-7, and the rule that replaced that one is
narrower and load-bearing: **no GET has a side effect**, writing is a
token-gated POST, and every mutation resolves to an id in `actions.py`'s
`RUN_ALLOWLIST`. Drift cannot turn a view into an actor without going through
that map.
"""
