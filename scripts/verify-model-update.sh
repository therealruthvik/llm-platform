#!/usr/bin/env bash
# verify-model-update.sh
# ─────────────────────────────────────────────────────────────────────────────
# Run this AFTER updating the model to confirm the new version is live.
# Usage:
#   ./scripts/verify-model-update.sh <expected_version> <expected_model>
# Example:
#   ./scripts/verify-model-update.sh v2 myuser/dialogpt-v2
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

EXPECTED_VERSION="${1:-}"
EXPECTED_MODEL="${2:-}"

if [ -z "$EXPECTED_VERSION" ] || [ -z "$EXPECTED_MODEL" ]; then
  echo "Usage: $0 <expected_version> <expected_model>"
  echo "  e.g. $0 v2 myuser/dialogpt-v2"
  exit 1
fi

NS="llm-platform"
PORT=18080   # local port for port-forward

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  LLM Platform – Model Update Verification"
echo "══════════════════════════════════════════════════════════"
echo "  Expected version : $EXPECTED_VERSION"
echo "  Expected model   : $EXPECTED_MODEL"
echo ""

# ── Check 1: Deployment rollout status ───────────────────────────────────────
echo "[ CHECK 1 ] Deployment rollout status …"
kubectl rollout status deployment/llm-backend -n $NS --timeout=300s
echo "  ✓ Rollout complete"

# ── Check 2: All pods Running ─────────────────────────────────────────────────
echo ""
echo "[ CHECK 2 ] Pod status …"
kubectl get pods -n $NS -l app=llm-backend
NOT_RUNNING=$(kubectl get pods -n $NS -l app=llm-backend \
  --field-selector=status.phase!=Running \
  --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$NOT_RUNNING" -gt 0 ]; then
  echo "  ✗ $NOT_RUNNING pod(s) not Running"
  exit 1
fi
echo "  ✓ All pods Running"

# ── Check 3: /health endpoint ─────────────────────────────────────────────────
echo ""
echo "[ CHECK 3 ] /health endpoint …"
kubectl port-forward svc/llm-backend $PORT:80 -n $NS >/dev/null 2>&1 &
PF_PID=$!
sleep 4

HEALTH=$(curl -sf http://localhost:$PORT/health || echo '{"status":"unreachable"}')
echo "  Response: $HEALTH"
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "parse_error")
if [ "$STATUS" != "ok" ]; then
  echo "  ✗ Health check failed (status=$STATUS)"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi
echo "  ✓ Health OK"

# ── Check 4: /version returns expected model ──────────────────────────────────
echo ""
echo "[ CHECK 4 ] /version endpoint …"
VERSION_RESP=$(curl -sf http://localhost:$PORT/version || echo '{}')
echo "  Response: $VERSION_RESP"

ACTUAL_VERSION=$(echo "$VERSION_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_version',''))")
ACTUAL_MODEL=$(echo "$VERSION_RESP"   | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_name',''))")

if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "  ✗ Version mismatch: expected=$EXPECTED_VERSION  actual=$ACTUAL_VERSION"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi
if [ "$ACTUAL_MODEL" != "$EXPECTED_MODEL" ]; then
  echo "  ✗ Model mismatch: expected=$EXPECTED_MODEL  actual=$ACTUAL_MODEL"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi
echo "  ✓ Version matches: $ACTUAL_VERSION"
echo "  ✓ Model matches  : $ACTUAL_MODEL"

# ── Check 5: Prometheus metric llm_model_version ─────────────────────────────
echo ""
echo "[ CHECK 5 ] Prometheus metric llm_model_version …"
METRICS=$(curl -sf http://localhost:$PORT/metrics | grep "^llm_model_version " || echo "")
echo "  $METRICS"
if [ -z "$METRICS" ]; then
  echo "  ✗ llm_model_version metric not found"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi
echo "  ✓ Metric present"

# ── Check 6: Smoke-test inference ────────────────────────────────────────────
echo ""
echo "[ CHECK 6 ] Smoke-test inference (/chat) …"
CHAT_RESP=$(curl -sf -X POST http://localhost:$PORT/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "history": []}' || echo '{}')
REPLY=$(echo "$CHAT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reply',''))" 2>/dev/null || echo "")
if [ -z "$REPLY" ]; then
  echo "  ✗ Inference returned empty reply"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi
echo "  ✓ Inference OK – reply: $REPLY"

kill $PF_PID 2>/dev/null || true

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  ALL CHECKS PASSED"
echo "  Model $EXPECTED_MODEL ($EXPECTED_VERSION) is live in cluster."
echo "══════════════════════════════════════════════════════════"
