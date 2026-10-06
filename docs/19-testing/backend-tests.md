# Backend Tests

## Level 1: Conceptual Explanation

Backend testing covers both Go server packages (`/cmd`, `/internal`) and Python web services (`/api`, `/rag`, `/deepdoc`). It ensures API contract compliance, data model integrity, database transaction correctness, and vector search accuracy.

---

## Level 2: Implementation Details

### Go Backend Test Suite
Executed via standard Go toolchain:
```bash
# Run all Go unit tests
go test -v ./internal/...

# Run with race detector
go test -v -race ./internal/...

# Run specific package tests
go test -v ./internal/cli/...
```

### Python Backend Test Suite
Executed via [`run_tests.py`](file:///home/logan78/Desktop/ragflow/run_tests.py#L111-L358):
```bash
# Run all Python backend tests
python3 run_tests.py

# Run backend tests with coverage report
python3 run_tests.py --coverage

# Run tests matching specific module
python3 run_tests.py --test test/unit_test/services/test_dialog_service.py
```

---

## References & Source Links

- [`run_tests.py:L1-L358`](file:///home/logan78/Desktop/ragflow/run_tests.py#L1-L358) - Python test script.
- [`internal/cli/cli_test.go:L1-L50`](file:///home/logan78/Desktop/ragflow/internal/cli/cli_test.go#L1-L50) - Go backend unit test.
