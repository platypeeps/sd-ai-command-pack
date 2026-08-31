"""The pack's own dashboard: a read-only view over the checkout fleet.

Deliberately small. The system dashboard it will eventually replace is 1,728
lines and collects from a dozen sources; this one starts with the facts the
backbone itself owns and grows a tab at a time under the 3c-to-6b parity
checklist. What it must never grow is a write path: the server answers GET and
nothing else, so no amount of drift can turn the view into an actor.
"""
