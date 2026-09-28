#!/bin/bash
set -e

echo "======================================"
echo "    DEV RAG: FULL STACK TEST SUITE    "
echo "======================================"

echo -e "\n1. Checking Docker Containers..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep ragflow-

echo -e "\n2. Generating Configuration..."
./generate_conf.sh

echo -e "\n3. Testing Python Backend (Quart)..."
source venv/bin/activate
PYTHONPATH=. python3 api/ragflow_server.py > python_test.log 2>&1 &
PY_PID=$!
sleep 3
if curl -s http://localhost:9380/api/health | grep -q '"status":"ok"'; then
    echo "✅ Python Backend Healthcheck Passed!"
    echo "Python Logs:"
    cat python_test.log
else
    echo "❌ Python Backend Healthcheck Failed!"
    cat python_test.log
    kill $PY_PID
    exit 1
fi
kill $PY_PID

echo -e "\n4. Testing Go Backend (Gin)..."
go run cmd/ragflow_server.go > go_test.log 2>&1 &
GO_PID=$!
sleep 5
if curl -s http://localhost:9381/api/health | grep -q '"status":"ok"'; then
    echo "✅ Go Backend Healthcheck Passed!"
    echo "Go Logs:"
    head -n 5 go_test.log
else
    echo "❌ Go Backend Healthcheck Failed!"
    cat go_test.log
    kill $GO_PID
    exit 1
fi
kill $GO_PID

echo -e "\n======================================"
echo " ✅ ALL STACK INTEGRATION TESTS PASSED "
echo "======================================"
