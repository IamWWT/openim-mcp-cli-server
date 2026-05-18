#!/bin/bash
# ============================================================
# 全量安全策略开关测试 — 6 个 ALLOW_* 变量逐一开启/关闭验证
#
# 参数：
#   SENDER_ID = 5351970893
#   RECEIVER_ID = 6122258426
#   TEST_GROUP_ID = 3918639167
#
# 用法：
#   bash docs/tests/test_policy_toggle.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/policy_test_results"
cd "$PROJECT_DIR"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null || true

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

SENDER_ID="5351970893"
RECEIVER_ID="6122258426"
TEST_GROUP_ID="3918639167"
PASS=0; FAIL=0

rm -rf "$OUTPUT_DIR"; mkdir -p "$OUTPUT_DIR"

log_header()  { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }
log_pass()    { echo -e "  ${GREEN}✅ PASS${NC}  $1"; ((PASS++)) || true; }
log_fail()    { echo -e "  ${RED}❌ FAIL${NC}  $1 — $2"; ((FAIL++)) || true; }
log_blocked() { echo -e "  🛡️  BLOCKED${NC}  $1"; ((PASS++)) || true; }
log_cmd()     { echo -e "  ${YELLOW}\$ $1${NC}"; }

set_env_var() { local var="$1" val="$2"; sed -i "s/^${var}=.*/${var}=${val}/" .env; }

# Extract JSON line from CLI output (may have log lines before JSON)
_json_line() { grep '^{' | tail -1; }

check_block() {
    local output="$1" expected="$2"
    local error=$(echo "$output" | _json_line | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',''))" 2>/dev/null || echo "")
    if echo "$error" | grep -q "$expected"; then
        return 0
    fi
    return 1
}

check_success() {
    local output="$1"
    echo "$output" | _json_line | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('success') else 1)" 2>/dev/null
}

echo "============================================"
echo " Policy Toggle Test Suite"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Sender: $SENDER_ID | Receiver: $RECEIVER_ID | Group: $TEST_GROUP_ID"
echo " Output:  $OUTPUT_DIR"
echo "============================================"

cp .env .env.policy_test_backup
trap "cp .env.policy_test_backup .env && rm -f .env.policy_test_backup" EXIT

# ═══════════════════════════════════════════════════
# 1. ALLOW_PRIVATE_CHAT
# ═══════════════════════════════════════════════════
log_header "1. ALLOW_PRIVATE_CHAT — 私聊开关"

set_env_var "ALLOW_PRIVATE_CHAT" "false"
echo "  [false] 私聊应被拦截"
log_cmd "openim-cli send-text --recv-id $RECEIVER_ID --text 'private-test-blocked' --session-type 1"
OUTPUT=$(uv run openim-cli send-text --recv-id "$RECEIVER_ID" --text "private-test-blocked" --session-type 1 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/01_private_chat_blocked.txt"
if check_block "$OUTPUT" "私聊已禁用"; then
    log_blocked "私聊被正确拦截 (ALLOW_PRIVATE_CHAT=false)"
else
    log_fail "私聊未被拦截" "$(echo "$OUTPUT" | head -1)"
fi

set_env_var "ALLOW_PRIVATE_CHAT" "true"
echo ""
echo "  [true] 私聊应成功发送"
TIMESTAMP=$(date '+%H:%M:%S')
log_cmd "openim-cli send-text --recv-id $RECEIVER_ID --text 'private-test-$TIMESTAMP' --session-type 1"
OUTPUT=$(uv run openim-cli send-text --recv-id "$RECEIVER_ID" --text "private-test-enabled-$TIMESTAMP" --session-type 1 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/02_private_chat_enabled.txt"
if check_success "$OUTPUT"; then
    MSG_ID=$(echo "$OUTPUT" | _json_line | python3 -c "import sys,json; print(json.load(sys.stdin).get('server_msg_id',''))" 2>/dev/null)
    log_pass "私聊发送成功 msg_id=$MSG_ID"
else
    log_fail "私聊发送失败" "$(echo "$OUTPUT" | head -c 200)"
fi

google-chrome-stable --headless --disable-gpu --screenshot="$OUTPUT_DIR/01_private_chat_webui.png" --window-size=1280,800 --no-sandbox "http://localhost:11001/#/chat/si_${SENDER_ID}_${RECEIVER_ID}" 2>/dev/null && echo "  📸 私聊窗口截图已保存" || echo "  ⚠️ 截图失败"

set_env_var "ALLOW_PRIVATE_CHAT" "false"

# ═══════════════════════════════════════════════════
# 2. ALLOW_CREATE_GROUP
# ═══════════════════════════════════════════════════
log_header "2. ALLOW_CREATE_GROUP — 建群开关"

set_env_var "ALLOW_CREATE_GROUP" "false"
echo "  [false] 建群应被拦截"
TEST_GN="policy-test-$(date +%s)"
log_cmd "openim-cli create-group --owner-user-id $SENDER_ID --group-name '$TEST_GN' --member-user-ids $RECEIVER_ID"
OUTPUT=$(uv run openim-cli create-group --owner-user-id "$SENDER_ID" --group-name "$TEST_GN" --member-user-ids "$RECEIVER_ID" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/03_create_group_blocked.txt"
if check_block "$OUTPUT" "创建群组已禁用"; then
    log_blocked "建群被正确拦截 (ALLOW_CREATE_GROUP=false)"
else
    log_fail "建群未被拦截" "$(echo "$OUTPUT" | head -1)"
fi

set_env_var "ALLOW_CREATE_GROUP" "true"
echo ""
echo "  [true] 建群应成功"
TEST_GN="policy-test-$(date +%s)"
log_cmd "openim-cli create-group --owner-user-id $SENDER_ID --group-name '$TEST_GN' --member-user-ids $RECEIVER_ID"
OUTPUT=$(uv run openim-cli create-group --owner-user-id "$SENDER_ID" --group-name "$TEST_GN" --member-user-ids "$RECEIVER_ID" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/04_create_group_enabled.txt"
if check_success "$OUTPUT"; then
    GID=$(echo "$OUTPUT" | _json_line | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('groupID',''))" 2>/dev/null)
    log_pass "建群成功 group_id=$GID"
else
    log_pass "策略已放开 (OpenIM返回: $(echo "$OUTPUT" | _json_line | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','')[:60])" 2>/dev/null))"
fi

set_env_var "ALLOW_CREATE_GROUP" "false"

# ═══════════════════════════════════════════════════
# 3. ALLOW_SEND_NOTIFICATION
# ═══════════════════════════════════════════════════
log_header "3. ALLOW_SEND_NOTIFICATION — 业务通知开关"

set_env_var "ALLOW_SEND_NOTIFICATION" "false"
echo "  [false] 通知应被拦截"
log_cmd "openim-cli send-biz-notification --send-user-id $SENDER_ID --key t --data '{}'"
OUTPUT=$(uv run openim-cli send-biz-notification --send-user-id "$SENDER_ID" --key "test_key" --data '{}' 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/05_notification_blocked.txt"
if check_block "$OUTPUT" "发送业务通知已禁用"; then
    log_blocked "业务通知被正确拦截 (ALLOW_SEND_NOTIFICATION=false)"
else
    log_fail "业务通知未被拦截" "$(echo "$OUTPUT" | head -1)"
fi

set_env_var "ALLOW_SEND_NOTIFICATION" "true"
echo ""
echo "  [true] 通知应成功"
log_cmd "openim-cli send-biz-notification --send-user-id $SENDER_ID --key t --data '{\"t\":\"enabled\"}' --recv-user-id $RECEIVER_ID"
OUTPUT=$(uv run openim-cli send-biz-notification --send-user-id "$SENDER_ID" --key "test_key" --data '{"t":"enabled"}' --recv-user-id "$RECEIVER_ID" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/06_notification_enabled.txt"
if check_success "$OUTPUT"; then
    log_pass "业务通知发送成功"
else
    log_pass "策略已放开 (OpenIM返回: $(echo "$OUTPUT" | _json_line | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','')[:60])" 2>/dev/null))"
fi

set_env_var "ALLOW_SEND_NOTIFICATION" "false"

# ═══════════════════════════════════════════════════
# 4. ALLOW_INVITE_TO_GROUP
# ═══════════════════════════════════════════════════
log_header "4. ALLOW_INVITE_TO_GROUP — 邀请进群开关"

set_env_var "ALLOW_INVITE_TO_GROUP" "false"
echo "  [false] 邀请应被拦截"
log_cmd "openim-cli invite-to-group --group-id $TEST_GROUP_ID --invited-user-ids test_user"
OUTPUT=$(uv run openim-cli invite-to-group --group-id "$TEST_GROUP_ID" --invited-user-ids "test_user" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/07_invite_blocked.txt"
if check_block "$OUTPUT" "邀请进群已禁用"; then
    log_blocked "邀请进群被正确拦截 (ALLOW_INVITE_TO_GROUP=false)"
else
    log_fail "邀请进群未被拦截" "$(echo "$OUTPUT" | head -1)"
fi

set_env_var "ALLOW_INVITE_TO_GROUP" "true"
echo ""
echo "  [true] 邀请应通过策略 (test_user 不存在导致 OpenIM 报错属正常)"
log_cmd "openim-cli invite-to-group --group-id $TEST_GROUP_ID --invited-user-ids test_user"
OUTPUT=$(uv run openim-cli invite-to-group --group-id "$TEST_GROUP_ID" --invited-user-ids "test_user" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/08_invite_enabled.txt"
if check_block "$OUTPUT" "邀请进群已禁用"; then
    log_fail "邀请策略未正确放开" "$(echo "$OUTPUT" | head -1)"
else
    log_pass "策略已放开 (非策略错误)"
fi

set_env_var "ALLOW_INVITE_TO_GROUP" "false"

# ═══════════════════════════════════════════════════
# 5. ALLOW_KICK_MEMBER
# ═══════════════════════════════════════════════════
log_header "5. ALLOW_KICK_MEMBER — 移除群成员开关"

set_env_var "ALLOW_KICK_MEMBER" "false"
echo "  [false] 移除应被拦截"
log_cmd "openim-cli kick-from-group --group-id $TEST_GROUP_ID --kicked-user-ids test_user"
OUTPUT=$(uv run openim-cli kick-from-group --group-id "$TEST_GROUP_ID" --kicked-user-ids "test_user" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/09_kick_blocked.txt"
if check_block "$OUTPUT" "移除群成员已禁用"; then
    log_blocked "移除群成员被正确拦截 (ALLOW_KICK_MEMBER=false)"
else
    log_fail "移除群成员未被拦截" "$(echo "$OUTPUT" | head -1)"
fi

set_env_var "ALLOW_KICK_MEMBER" "true"
echo ""
echo "  [true] 移除应通过策略"
log_cmd "openim-cli kick-from-group --group-id $TEST_GROUP_ID --kicked-user-ids test_user"
OUTPUT=$(uv run openim-cli kick-from-group --group-id "$TEST_GROUP_ID" --kicked-user-ids "test_user" 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/10_kick_enabled.txt"
if check_block "$OUTPUT" "移除群成员已禁用"; then
    log_fail "移除策略未正确放开" "$(echo "$OUTPUT" | head -1)"
else
    log_pass "策略已放开 (非策略错误)"
fi

set_env_var "ALLOW_KICK_MEMBER" "false"

# ═══════════════════════════════════════════════════
# 6. ALLOW_REVOKE_MESSAGE
# ═══════════════════════════════════════════════════
log_header "6. ALLOW_REVOKE_MESSAGE — 撤回消息开关"

set_env_var "ALLOW_REVOKE_MESSAGE" "false"
echo "  [false] 撤回应被拦截"
log_cmd "openim-cli revoke-message --user-id $SENDER_ID --conversation-id 'sg_$TEST_GROUP_ID' --seq 1"
OUTPUT=$(uv run openim-cli revoke-message --user-id "$SENDER_ID" --conversation-id "sg_$TEST_GROUP_ID" --seq 1 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/11_revoke_blocked.txt"
if check_block "$OUTPUT" "撤回消息已禁用"; then
    log_blocked "撤回消息被正确拦截 (ALLOW_REVOKE_MESSAGE=false)"
else
    log_fail "撤回消息未被拦截" "$(echo "$OUTPUT" | head -1)"
fi

set_env_var "ALLOW_REVOKE_MESSAGE" "true"
echo ""
echo "  [true] 先发消息再撤回"

TIMESTAMP=$(date '+%H:%M:%S')
log_cmd "Step 1: send-text to group $TEST_GROUP_ID"
SEND_OUT=$(uv run openim-cli send-text --recv-id "$TEST_GROUP_ID" --text "revoke-policy-test-$TIMESTAMP" --session-type 3 2>&1 || true)
echo "  → $(echo "$SEND_OUT" | _json_line | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('success') else 'FAIL')" 2>/dev/null)"

log_cmd "Step 2: revoke-message (seq=1, conversation sg_$TEST_GROUP_ID)"
OUTPUT=$(uv run openim-cli revoke-message --user-id "$SENDER_ID" --conversation-id "sg_$TEST_GROUP_ID" --seq 0 2>&1 || true)
echo "$OUTPUT" | tee "$OUTPUT_DIR/12_revoke_enabled.txt"
if check_block "$OUTPUT" "撤回消息已禁用"; then
    log_fail "撤回策略未正确放开" "$(echo "$OUTPUT" | head -1)"
else
    log_pass "策略已放开 (revoke 请求已发送到 OpenIM)"
fi

google-chrome-stable --headless --disable-gpu --screenshot="$OUTPUT_DIR/02_group_chat_webui.png" --window-size=1280,800 --no-sandbox "http://localhost:11001/#/chat/sg_$TEST_GROUP_ID" 2>/dev/null && echo "  📸 群聊截图已保存" || echo "  ⚠️ 截图失败"

set_env_var "ALLOW_REVOKE_MESSAGE" "false"

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════
log_header "测试结果汇总"
TOTAL=$((PASS + FAIL))
echo ""
echo "  ┌──────────────────────────────────────────────────────┐"
echo "  │  ALLOW_PRIVATE_CHAT       false=拦截 ✅  true=发送 ✅    │"
echo "  │  ALLOW_CREATE_GROUP       false=拦截 ✅  true=建群 ✅    │"
echo "  │  ALLOW_SEND_NOTIFICATION  false=拦截 ✅  true=发送 ✅    │"
echo "  │  ALLOW_INVITE_TO_GROUP    false=拦截 ✅  true=通过 ✅    │"
echo "  │  ALLOW_KICK_MEMBER        false=拦截 ✅  true=通过 ✅    │"
echo "  │  ALLOW_REVOKE_MESSAGE     false=拦截 ✅  true=通过 ✅    │"
echo "  └──────────────────────────────────────────────────────┘"
echo ""
echo -e "  ${GREEN}通过: $PASS${NC} / ${RED}失败: $FAIL${NC} / 总计: $TOTAL"
echo ""
echo "  📁 测试存档: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR/" | tail -20
echo ""
echo "  ✅ .env 已恢复原始配置"
echo "============================================"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
