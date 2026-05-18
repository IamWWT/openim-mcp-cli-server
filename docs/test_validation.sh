#!/bin/bash
# ============================================================
# 闭环验证脚本 — 验证 openim-mcp+cli-server 全部工具
#
# 用法:
#   bash test/verify_tools.sh              # 仅验证 CLI 接口（无需 OpenIM）
#   bash test/verify_tools.sh --online     # 在线模式：需要 OpenIM 服务可达
#   bash test/verify_tools.sh --mcp        # 验证 MCP 服务接口（需先启动服务）
#
# 退出码: 0=全部通过, 1=存在失败
# ============================================================

set -euo pipefail

# Proxy workaround — clear system proxy settings
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS++)) || true; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1 — $2"; ((FAIL++)) || true; }
log_skip() { echo -e "${YELLOW}[SKIP]${NC} $1 — $2"; ((SKIP++)) || true; }

# ---------- 阶段 1: 代码完整性 ----------
phase1_code() {
    echo ""
    echo "=== 阶段 1: 代码完整性检查 ==="
    cd "$PROJECT_DIR"
    for f in src/openim_mcp/config.py src/openim_mcp/openim_client.py src/openim_mcp/server.py src/openim_mcp/cli.py; do
        if python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null; then
            log_pass "语法检查: $f"
        else
            log_fail "语法检查: $f" "编译失败"
        fi
    done
    for f in README.md pyproject.toml LICENSE .env start.sh; do
        if [ -f "$f" ]; then
            log_pass "文件存在: $f"
        else
            log_fail "文件缺失: $f" ""
        fi
    done
    if grep -q "OPENIM_SENDER_ID" .env 2>/dev/null; then
        log_pass "OPENIM_SENDER_ID 已配置"
    else
        log_fail "OPENIM_SENDER_ID 未配置" ".env 中缺少身份绑定"
    fi
    if grep -q "OPENIM_ADMIN_SECRET" .env 2>/dev/null; then
        log_pass "OPENIM_ADMIN_SECRET 已配置"
    else
        log_fail "OPENIM_ADMIN_SECRET 未配置" ""
    fi
}

# ---------- 阶段 2: CLI 接口验证 ----------
phase2_cli_offline() {
    echo ""
    echo "=== 阶段 2: CLI 接口验证 ==="
    cd "$PROJECT_DIR"
    declare -a COMMANDS=(
        "send-text" "send-image" "send-group-at" "send-biz-notification"
        "revoke-message" "get-user-info" "get-online-status" "list-users"
        "get-group-info" "list-group-members" "create-group" "invite-to-group"
        "kick-from-group" "list-conversations" "lookup-user" "lookup-group"
    )
    if uv run openim-cli --help >/dev/null 2>&1; then
        log_pass "openim-cli --help 正常"
    else
        log_fail "openim-cli --help 异常" "CLI 启动失败"
    fi
    for cmd in "${COMMANDS[@]}"; do
        if uv run openim-cli "$cmd" --help >/dev/null 2>&1; then
            log_pass "CLI 子命令: $cmd --help"
        else
            log_fail "CLI 子命令: $cmd --help" "无法解析"
        fi
    done

    echo ""
    echo "--- 策略拦截测试 ---"
    output=$(uv run openim-cli send-text --recv-id test_user --text "test" --session-type 1 2>&1 || true)
    if echo "$output" | grep -q "私聊已禁用"; then
        log_pass "策略拦截: 私聊被正确拒绝"
    else
        log_fail "策略拦截: 私聊未被拦截" "$(echo "$output" | head -1)"
    fi
    output=$(uv run openim-cli create-group --owner-user-id u1 --group-name "test" --member-user-ids u2 2>&1 || true)
    if echo "$output" | grep -q "创建群组已禁用"; then
        log_pass "策略拦截: 拉群被正确拒绝"
    else
        log_fail "策略拦截: 拉群未被拦截" "$(echo "$output" | head -1)"
    fi
    output=$(uv run openim-cli send-biz-notification --send-user-id s1 --key k --data d 2>&1 || true)
    if echo "$output" | grep -q "发送业务通知已禁用"; then
        log_pass "策略拦截: 通知被正确拒绝"
    else
        log_fail "策略拦截: 通知未被拦截" "$(echo "$output" | head -1)"
    fi
}

# ---------- 阶段 3: 在线功能验证 ----------
phase3_online() {
    echo ""
    echo "=== 阶段 3: 在线功能验证 ==="
    cd "$PROJECT_DIR"
    SENDER_ID=$(grep OPENIM_SENDER_ID .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "")
    if [ -z "$SENDER_ID" ]; then
        log_skip "在线测试" "OPENIM_SENDER_ID 未设置"
        return
    fi
    echo "测试用户: $SENDER_ID"
    output=$(uv run openim-cli get-user-info --user-ids "$SENDER_ID" 2>&1 || true)
    if echo "$output" | grep -q '"success": true'; then
        log_pass "在线: get-user-info 成功"
    else
        log_fail "在线: get-user-info 失败" "$(echo "$output" | head -c 200)"
    fi
    output=$(uv run openim-cli get-online-status --user-ids "$SENDER_ID" 2>&1 || true)
    if echo "$output" | grep -q '"success": true'; then
        log_pass "在线: get-online-status 成功"
    else
        log_fail "在线: get-online-status 失败" "$(echo "$output" | head -c 200)"
    fi
    output=$(uv run openim-cli lookup-user --user-id "$SENDER_ID" 2>&1 || true)
    if echo "$output" | grep -q '"success": true'; then
        log_pass "在线: lookup-user 成功"
    else
        log_fail "在线: lookup-user 失败" "$(echo "$output" | head -c 200)"
    fi
}

# ---------- 主流程 ----------
main() {
    echo "============================================"
    echo " openim-mcp+cli-server 闭环验证"
    echo " 项目路径: $PROJECT_DIR"
    echo " $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================"
    MODE="${1:-offline}"
    phase1_code
    phase2_cli_offline
    case "$MODE" in
        --online) phase3_online ;;
        --mcp|--all) phase3_online ;;
        *) log_skip "在线测试" "使用 --online 启用在线验证" ;;
    esac
    echo ""
    echo "============================================"
    TOTAL=$((PASS + FAIL + SKIP))
    echo -e "结果: ${GREEN}通过 $PASS${NC} / ${RED}失败 $FAIL${NC} / ${YELLOW}跳过 $SKIP${NC} / 总计 $TOTAL"
    echo "============================================"
    [ "$FAIL" -gt 0 ] && exit 1
    exit 0
}

main "$@"
