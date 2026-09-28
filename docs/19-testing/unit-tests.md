# Unit Tests

## Level 1: Conceptual Explanation

Unit tests validate individual functions, parsers, cryptographic routines, data serialization modules, and canvas state machines in complete isolation without calling external network APIs or databases.

---

## Level 2: Implementation Details

### Unit Test Suites & Modules

#### 1. Go Parser & CLI Unit Tests
Located in [`internal/cli/user_parser_test.go`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser_test.go#L1-L100) and [`internal/cli/cli_test.go`](file:///home/logan78/Desktop/ragflow/internal/cli/cli_test.go#L1-L60):
- Verifies SQL-like command lexing and tokenization (`LOGIN`, `CREATE DATASET`, `SEARCH`).
- Validates parameter extraction and error handling for malformed input strings.

#### 2. Agent Canvas & State Machine Unit Tests
Located under `internal/agent/canvas/`:
- [`canvas_test.go`](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/canvas_test.go): Verifies graph node execution sequence.
- [`checkpoint_store_test.go`](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/checkpoint_store_test.go): Validates workflow state persistence.
- [`loop_semantics_test.go`](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/loop_semantics_test.go): Tests loop iteration and break criteria.
- [`state_bench_test.go`](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/state_bench_test.go): Measures state serialization throughput.

#### 3. Python Service & RAG Unit Tests
Located under `test/unit_test/`:

#### 4. Sandbox Security Unit Tests
Located in [`agent/sandbox/tests/test_security.py`](file:///home/logan78/Desktop/ragflow/agent/sandbox/tests/test_security.py#L1-L80):
- Tests Seccomp system call filtering, memory restriction validation, and illegal module blocking.

---

## References & Source Links

- [`internal/cli/user_parser_test.go:L1-L100`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser_test.go#L1-L100) - CLI unit test file.
- [`internal/agent/canvas/state_test.go:L1-L80`](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/state_test.go#L1-L80) - Agent state unit tests.
- [`agent/sandbox/tests/test_security.py:L1-L80`](file:///home/logan78/Desktop/ragflow/agent/sandbox/tests/test_security.py#L1-L80) - Sandbox security unit tests.
