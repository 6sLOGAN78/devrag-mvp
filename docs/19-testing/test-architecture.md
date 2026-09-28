# Test Architecture & Go Test Tiers

## Level 1: Conceptual Explanation

The RAGFlow test architecture isolates software components according to dependency requirements and execution speeds. Fast unit tests run without external databases, while integration and CGO tests validate C++ bindings and live vector database engines.

---

## Level 2: Implementation Details

### Python Test Runner Breakdown (`run_tests.py`)

The Python test runner [`run_tests.py`](file:///home/logan78/Desktop/ragflow/run_tests.py#L111-L358) provides a unified CLI for test discovery, execution, parallelization, and HTML coverage generation:

#### CLI Options & Flags
- `-p, --parallel`: Uses `pytest-xdist` to spawn parallel worker processes across CPU cores ([`run_tests.py:L210-L220`](file:///home/logan78/Desktop/ragflow/run_tests.py#L210-L220)).
- `-t, --test <path>`: Specifies a target test file or directory ([`run_tests.py:L183-L188`](file:///home/logan78/Desktop/ragflow/run_tests.py#L183-L188)).
- `-m, --markers <expr>`: Filters tests by Pytest markers (e.g. `-m "unit"` or `-m "integration"`) ([`run_tests.py:L192-L194`](file:///home/logan78/Desktop/ragflow/run_tests.py#L192-L194)).
- `-i, --ignore`: Adds `-W ignore::SyntaxWarning` option to silence non-fatal Python deprecations ([`run_tests.py:L222-L224`](file:///home/logan78/Desktop/ragflow/run_tests.py#L222-L224)).

---

### Complete Go Test Tiers Breakdown

Go tests across the repository are divided into **5 formal tiers** controlled via Go build tags (`//go:build ...`) and file naming conventions:

| Test Tier | Purpose / Scope | Execution Command | Target Files / Build Tag | Mocking / Requirement |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Unit** | Pure in-memory unit logic (parsers, state machines, serializers) | `go test -v ./internal/...` | `*_test.go` (Default) | No external services required |
| **Tier 2: Integration** | Microservice inter-communication & storage drivers | `go test -v -tags=integration ./...` | `//go:build integration` or `*_integration_test.go` | Requires MySQL / Redis / NATS |
| **Tier 3: E2E** | Full end-to-end HTTP REST endpoint flow verification | `go test -v -tags=e2e ./...` | `//go:build e2e` | Requires running RAGFlow stack |
| **Tier 4: Manual** | Interactive debugging & manual verification scripts | `go test -v -tags=manual ./...` | `//go:build manual` | Executed on demand by developers |
| **Tier 5: CGO Native** | Verification of C/C++ native static bindings (PDFium, OfficeOxide) | `CGO_ENABLED=1 build.sh --test` | `//go:build cgo` | Requires native C++ `.a` static libs |

---

## References & Source Links

- [`run_tests.py:L111-L230`](file:///home/logan78/Desktop/ragflow/run_tests.py#L111-L230) - `TestRunner` class implementation.
- [`internal/cli/user_parser_test.go:L1-L80`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser_test.go#L1-L80) - Go Tier 1 unit test example.
- [`internal/deepdoc/parser/pdf/inference_client_integration_test.go:L1-L50`](file:///home/logan78/Desktop/ragflow/internal/deepdoc/parser/pdf/inference_client_integration_test.go#L1-L50) - Go Tier 2/5 CGO integration test.
