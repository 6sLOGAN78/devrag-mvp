
## From plan 02-13

- `test/unit_test/test_auth_gate.py::test_bad_token_classes_are_401_without_a_database_lookup[tampered_signature]` is intermittent
  (failed once in four unit runs, passes on rerun). The case flips the last base64url character of the signature to `A` or `B`;
  when only the unused trailing bits of that character differ, the decoded signature bytes are identical and the token is still
  valid. Fix belongs to the auth gate test owner: alter a character in the middle of the signature instead of the last one.
  Not touched here because it is outside this plan's files.
