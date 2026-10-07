
## From plan 02-13

- RESOLVED after plan 02-13: the intermittent `tampered_signature` case in `test/unit_test/test_auth_gate.py` now alters the first
  signature character (the last one carries unused trailing bits, so the old swap could leave the token valid).
