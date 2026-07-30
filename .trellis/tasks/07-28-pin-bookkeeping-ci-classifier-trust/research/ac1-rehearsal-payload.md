# AC1 rehearsal payload

Bookkeeping-eligible payload for the A-038 AC1 rehearsal. Its only job is to make
the second push of the rehearsal PR a `synchronize` event whose changed-path
increment falls entirely inside `ALLOWED_PATH_PREFIXES`
(`.github/scripts/bookkeeping_ci_scope.py:30`), so the fast lane would engage if
the identity guard did not fire first.

`$BEFORE_SHA` for this push is the classifier-tamper commit. Expected classify
result: `mode=full`, `reason=prior_classifier_not_base_identical`.

This file lives on `rehearsal/a038-identity-guard` and is deleted with it.
