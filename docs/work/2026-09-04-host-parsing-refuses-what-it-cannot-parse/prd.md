---
title: the Host guard repairs what it should refuse, and the fix opens with a cap re-derivation
status: done
created: 2026-09-04
---

# PRD — a boundary that repairs its input is not a boundary

## Problem

`host_ok` (`dashboard/server.py`) is the DNS-rebinding guard. Its own docstring says
so: *"a name resolving to 127.0.0.1 makes a page on the open internet same-origin
with this port, and the binding cannot tell it from the operator's own. The `Host`
is what differs, so it is what is checked."* It delegates parsing to `host_name`,
and `host_name` repairs malformed input instead of rejecting it.

```python
if name.startswith("["):
    return name.partition("]")[0] + "]"
```

`str.partition` returns the whole string as its first element when the separator is
absent, so the `+ "]"` appends a bracket that the header never had. Verified by
running it against the merged tree:

| `Host` header | `host_name()` | `host_ok()` |
|---|---|---|
| `[::1]:8767` | `[::1]` | `True` — correct, this is why the branch exists |
| `[::1` | `[::1]` | **`True`** — the closing bracket was invented |
| `[::1]evil.com` | `[::1]` | **`True`** — everything after `]` was discarded |
| `[evil.com` | `[evil.com]` | `False` — refused, but by accident |

Two headers that are not the IPv6 loopback are accepted as the IPv6 loopback.

**Corrected during design, left standing here.** The sentence above is wrong and
is kept because `design.md` quotes it. Running `host_name` over a corpus rather
than reading it shows the admitted set is not two headers and is not a number at
all: `partition("]")` discards everything after the first `]`, so every header
of the form `[::1]<anything>` is admitted as the IPv6 loopback. 2000 of 2000
randomly generated tails were accepted. The table above lists the two the review
happened to name, which is how a fix written against the examples in a report
comes to be narrower than the defect -- and `design.md` records that its own
first draft made the same mistake one size up, by counting the rows of a corpus
and calling that the answer.

**What this is not.** It is not a DNS-rebinding bypass. A page on the open internet
cannot set a `Host` header; the browser sets it from the URL authority, and
`[::1]evil.com` is not a URL authority a browser will produce. Reaching this needs
a client that sets the header directly — `curl`, a proxy, a misconfigured
reverse-proxy in front of the dashboard — which is a real adversary but a much
smaller one than the guard was built against. The severity is "a security boundary
does not do what it says", not "the boundary is bypassed today".

**What this is not, second.** It is not a regression from
`2026-09-02-dashboard-ack-and-mutation-count` (#733). That item lifted the
expression out of `host_ok` into a shared `host_name` so that the guard and the new
mutation classifier would stop disagreeing about what `[::1]:8767` means — a fix in
its own right, and a strict improvement. The parsing it moved is byte-for-byte what
`origin/main` carried before it:

```
$ git show d46aee30:dashboard/server.py | grep -A1 'startswith..\['
    if name.startswith("["):
        name = name.partition("]")[0] + "]"
```

The defect predates the helper. Splitting it out is what made it visible to a
reviewer, which is the argument for splitting it out.

## Why this needs its own item

`dashboard/` stands at **4,348 against a 4,350 cap**. The fix is one line of code:

```python
return address + bracket if bracket and port[:1] in ("", ":") else name
```

Returning the *unrepaired* header, so `host_ok` refuses it — which is what the
review that found this recommended. But a boundary that now deliberately refuses
input it used to repair needs the sentence saying why, and the sentence does not
fit in two lines.

Paying for it by deleting rationale elsewhere in `dashboard/` is precisely the
failure R11-D24 split the cap in two to prevent: *"a single total let a docstring
and a branch compete for the same line, and 6b-7 was spent deleting rationale to
fit a write path."* So this item opens by re-deriving `DASHBOARD_CAP`, in its own
change, under the ceiling it replaces — which is also what the R11-D29 record says
the next change under `dashboard/` must do.

R11-D29 predicted this item without knowing what it would be: *"Two unclaimed lines
is what remains, and the next change under `dashboard/` writes its own record
rather than spending them."*

## Acceptance criteria

1. `host_ok('[::1')` is `False`, `host_ok('[::1]evil.com')` is `False`, and
   `host_ok('[::1]:8767')` is still `True`.
2. The refusal is asserted by a test that fails against the current
   implementation — mutation-tested, not merely covered, per the standing bar.
3. `host_name` returns the header unmodified when it cannot parse it, rather than
   returning `""`. `""` is in `LOOPBACK_NAMES`, so an empty return would classify a
   malformed header as loopback in the mutation record's `tailnet_host` field.
   (`""` is *not* in `allowed_hosts()`, which uses `LOOPBACK`, so `host_ok` would
   still refuse — but the two callers must not disagree, which is the whole reason
   `host_name` exists.)
4. The unbracketed path is examined and its behaviour stated either way. A
   malformed port there (`localhost:evil`) yields `localhost`, which is the correct
   host, so it widens nothing — but that should be a recorded finding, not an
   assumption.
5. `DASHBOARD_CAP` is re-derived in its own change with an itemisation, ahead of
   the fix, per `test_loc_caps.py`'s docstring.

## Open questions

1. Should the port be validated as digits, or only as "starts with a colon"? Digits
   is stricter and refuses `[::1]:8767:9`; a colon check is one token shorter and
   the port plays no part in the origin comparison.
2. Does anything else in the repo parse a `Host`, or is `host_name` the only one?
   The blast-radius rule says enumerate before fixing.
3. Is the citation-gate gap (the sibling item opened alongside this one) worth
   folding in here, or does it stay separate? They share nothing but a discovery
   date, and the sibling turned out to be the larger of the two once its premise
   was measured rather than assumed.
