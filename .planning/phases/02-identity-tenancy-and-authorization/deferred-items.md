# Deferred items (phase 02)

- 02-10: `test/integration/test_migration_runner.py::test_init_db_entry_point_exit_codes` fails with `MissingVariable: SECRET_KEY` because `_conf_env(scratch)` does not provide SECRET_KEY, required by the renderer since plan 02-04. Pre-existing and unrelated to the auth gate. Fix: add a fake 32+ character SECRET_KEY to `_conf_env`.
