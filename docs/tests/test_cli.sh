#!/bin/bash
# ============================================================
# CLI 闭环验证 — 使用实际 OpenIM 参数
#
# 参数：
#   SENDER_ID = 5351970893
#   RECEIVER_ID = 6122258426
#   TEST_GROUP_ID = 3198639167
#
# 用法：
#   bash docs/tests/test_cli.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0; FAIL=0; SKIP=0

log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS++)) || true; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1 — $2"; ((FAIL++)) || true; }
log_skip() { echo -e "${YELLOW}[SKIP]${NC} $1 — $2"; ((SKIP++)) || true; }
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }

SENDER_ID="5351970893"
RECEIVER_ID="6122258426"
TEST_GROUP_ID="3918639167"

# Proxy workaround — clear system proxy settings
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null || true

# ---------- 1. Help & Syntax ----------
echo ""
echo "============================================"
echo " CLI Test Suite"
echo " Sender: $SENDER_ID | Receiver: $RECEIVER_ID | Group: $TEST_GROUP_ID"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

echo ""
echo "--- 1. CLI Help & Syntax ---"
if uv run openim-cli --help >/dev/null 2>&1; then
    log_pass "openim-cli --help"
else
    log_fail "openim-cli --help" "CLI 无法启动"
fi

# ---------- 2. Get User Info ----------
echo ""
echo "--- 2. User Info ---"
OUTPUT=$(uv run openim-cli get-user-info --user-ids "$RECEIVER_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "get-user-info ($RECEIVER_ID)"
    echo "$OUTPUT" | python3 -m json.tool 2>/dev/null | head -20
else
    log_fail "get-user-info" "$(echo "$OUTPUT" | head -c 200)"
fi

OUTPUT=$(uv run openim-cli get-user-info --user-ids "$SENDER_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "get-user-info ($SENDER_ID)"
else
    log_fail "get-user-info sender" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 3. Online Status ----------
echo ""
echo "--- 3. Online Status ---"
OUTPUT=$(uv run openim-cli get-online-status --user-ids "$RECEIVER_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "get-online-status ($RECEIVER_ID)"
else
    log_fail "get-online-status" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 4. Lookup User ----------
echo ""
echo "--- 4. Lookup User ---"
OUTPUT=$(uv run openim-cli lookup-user --user-id "$RECEIVER_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "lookup-user by ID ($RECEIVER_ID)"
else
    log_fail "lookup-user by ID" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 5. List Users ----------
echo ""
echo "--- 5. List Users ---"
OUTPUT=$(uv run openim-cli list-users --page-number 1 --show-number 10 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "list-users (page 1, size 10)"
else
    log_fail "list-users" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 6. Group Info ----------
echo ""
echo "--- 6. Group Info ---"
OUTPUT=$(uv run openim-cli get-group-info --group-ids "$TEST_GROUP_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "get-group-info ($TEST_GROUP_ID)"
    echo "$OUTPUT" | python3 -m json.tool 2>/dev/null | head -20
else
    log_fail "get-group-info" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 7. Group Member List ----------
echo ""
echo "--- 7. Group Member List ---"
OUTPUT=$(uv run openim-cli list-group-members --group-id "$TEST_GROUP_ID" --page-number 1 --show-number 10 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "list-group-members ($TEST_GROUP_ID)"
else
    log_fail "list-group-members" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 8. Lookup Group ----------
echo ""
echo "--- 8. Lookup Group ---"
OUTPUT=$(uv run openim-cli lookup-group --group-id "$TEST_GROUP_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "lookup-group ($TEST_GROUP_ID)"
else
    log_fail "lookup-group" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 9. Send Text (Group) ----------
echo ""
echo "--- 9. Send Group Text ---"
OUTPUT=$(uv run openim-cli send-text --recv-id "$TEST_GROUP_ID" --text "CLI integration test - $(date '+%H:%M:%S')" --session-type 3 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    MSG_ID=$(echo "$OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_msg_id'])" 2>/dev/null || echo "")
    log_pass "send-text to group ($TEST_GROUP_ID) msg_id=$MSG_ID"
else
    log_fail "send-text to group" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 10. Send Group AT ----------
echo ""
echo "--- 10. Send Group AT ---"
OUTPUT=$(uv run openim-cli send-group-at --group-id "$TEST_GROUP_ID" --text "AT integration test - $(date '+%H:%M:%S')" --at-user-ids "$RECEIVER_ID" 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    MSG_ID=$(echo "$OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_msg_id'])" 2>/dev/null || echo "")
    log_pass "send-group-at ($TEST_GROUP_ID, @$RECEIVER_ID) msg_id=$MSG_ID"
else
    log_fail "send-group-at" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 11. Send Text (Private - should be blocked) ----------
echo ""
echo "--- 11. Private Chat Policy ---"
OUTPUT=$(uv run openim-cli send-text --recv-id "$RECEIVER_ID" --text "Should be blocked" --session-type 1 2>&1 || true)
if echo "$OUTPUT" | grep -q "私聊已禁用"; then
    log_pass "policy: private chat correctly blocked"
else
    log_fail "policy: private chat" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- 12. Conversation List ----------
echo ""
echo "--- 12. Conversation List ---"
OUTPUT=$(uv run openim-cli list-conversations --user-id "$SENDER_ID" --page-number 1 --show-number 5 2>&1 || true)
if echo "$OUTPUT" | grep -q '"success": true'; then
    log_pass "list-conversations ($SENDER_ID)"
else
    log_fail "list-conversations" "$(echo "$OUTPUT" | head -c 200)"
fi

# ---------- Summary ----------
echo ""
echo "============================================"
TOTAL=$((PASS + FAIL + SKIP))
echo -e "Results: ${GREEN}Pass $PASS${NC} / ${RED}Fail $FAIL${NC} / ${YELLOW}Skip $SKIP${NC} / Total $TOTAL"
echo "============================================"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
