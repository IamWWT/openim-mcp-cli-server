#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 清除系统代理变量（避免干扰 httpx 请求）
clear_proxy() {
    unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null || true
}

# 加载 .env 文件
load_env() {
    if [ -f ".env" ]; then
        set -a
        source .env
        set +a
        print_info "已加载 .env 配置文件"
    else
        print_warn ".env 文件不存在，使用默认配置"
    fi
}

# 获取配置（优先环境变量，否则使用 .env 中的值，最后使用默认值）
get_config() {
    # MCP 传输配置
    MCP_TRANSPORT="${MCP_TRANSPORT:-http}"
    MCP_HOST="${MCP_HOST:-0.0.0.0}"
    MCP_PORT="${MCP_PORT:-8084}"
    
    # OpenIM 配置
    OPENIM_API_ADDRESS="${OPENIM_API_ADDRESS:-http://localhost:10002}"
    OPENIM_ADMIN_SECRET="${OPENIM_ADMIN_SECRET:-OpenIM123}"
    OPENIM_SENDER_ID="${OPENIM_SENDER_ID:-openIMAdmin}"
    OPENIM_PLATFORM_ID="${OPENIM_PLATFORM_ID:-5}"
    
    # 服务配置
    LOG_DIR="${LOG_DIR:-./logs}"
    LOG_FILE="${LOG_FILE:-$LOG_DIR/openim-mcp.log}"
    PID_FILE="${PID_FILE:-./openim-mcp.pid}"
}

# 显示当前配置
show_config() {
    echo ""
    print_info "当前配置:"
    echo "  ┌─────────────────────────────────────────────────"
    echo "  │ MCP Transport:      $MCP_TRANSPORT"
    echo "  │ MCP Listen:         $MCP_HOST:$MCP_PORT"
    echo "  ├─────────────────────────────────────────────────"
    echo "  │ OpenIM API:         $OPENIM_API_ADDRESS"
    echo "  │ OpenIM Sender ID:   $OPENIM_SENDER_ID"
    echo "  │ OpenIM Platform ID: $OPENIM_PLATFORM_ID"
    echo "  ├─────────────────────────────────────────────────"
    echo "  │ Log File:           $LOG_FILE"
    echo "  │ PID File:           $PID_FILE"
    echo "  └─────────────────────────────────────────────────"
    echo ""
}

# 激活虚拟环境
activate_venv() {
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        print_info "已激活虚拟环境 (.venv)"
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        print_info "已激活虚拟环境 (venv)"
    else
        print_warn "未找到虚拟环境，使用系统 Python"
    fi
}

# 获取可执行命令
get_command() {
    # 优先使用 console script（如果已安装）
    if command -v openim-mcp &> /dev/null; then
        echo "openim-mcp"
        return
    fi
    
    # 使用模块方式运行
    echo "python -m openim_mcp"
}

# 检查依赖（简单检查关键模块）
check_dependencies() {
    local missing=()
    
    if ! command -v python &> /dev/null; then
        missing+=("python")
    fi
    
    if [ ${#missing[@]} -gt 0 ]; then
        print_error "缺少依赖: ${missing[*]}"
        exit 1
    fi
}

# 确保项目已安装（可选）
ensure_dependencies() {
    # 检查 fastmcp 是否可用
    if ! python -c "import fastmcp" 2>/dev/null; then
        print_warn "依赖未完整安装，运行 uv sync 安装..."
        if command -v uv &> /dev/null; then
            uv sync
        else
            print_error "未找到 uv 命令，请先安装依赖: uv sync"
            exit 1
        fi
    fi
    
    # 检查项目模块是否可导入
    if ! python -c "import openim_mcp" 2>/dev/null; then
        print_warn "项目未安装，运行 pip install -e . 安装..."
        pip install -e . -q
    fi
}

# 启动服务
start_service() {
    # 检查是否已运行
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        print_error "服务已在运行 (PID: $(cat "$PID_FILE"))"
        exit 1
    fi
    rm -f "$PID_FILE"
    
    # 创建日志目录
    mkdir -p "$LOG_DIR"
    
    # 清除代理
    clear_proxy

    # 加载配置
    load_env
    get_config
    
    # 显示配置
    show_config
    
    # 检查依赖
    check_dependencies
    
    # 激活环境
    activate_venv
    
    # 确保依赖已安装
    ensure_dependencies
    
    # 获取启动命令
    CMD=$(get_command)
    print_info "启动命令: $CMD"
    
    # 设置环境变量（供服务使用）
    export MCP_TRANSPORT
    export MCP_HOST
    export MCP_PORT
    export OPENIM_API_ADDRESS
    export OPENIM_ADMIN_SECRET
    export OPENIM_SENDER_ID
    export OPENIM_PLATFORM_ID
    
    # 启动服务
    print_info "正在启动 OpenIM MCP Server..."
    
    # 根据传输模式显示额外信息
    case "$MCP_TRANSPORT" in
        http|sse)
            print_info "HTTP 服务将监听: http://$MCP_HOST:$MCP_PORT"
            ;;
        stdio)
            print_info "stdio 模式，等待父进程通信"
            ;;
    esac
    
    # 后台启动
    nohup $CMD >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"
    
    # 等待服务启动
    sleep 2
    
    # 检查启动状态
    if kill -0 "$pid" 2>/dev/null; then
        print_info "✓ 服务启动成功 (PID: $pid)"
        
        # HTTP/SSE 模式下进行健康检查（可选）
        if [[ "$MCP_TRANSPORT" =~ ^(http|sse)$ ]] && command -v curl &> /dev/null; then
            sleep 1
            # 尝试发送初始化请求
            if curl -s -X POST "http://$MCP_HOST:$MCP_PORT/mcp" \
                -H "Content-Type: application/json" \
                -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"0.1.0","capabilities":{}},"id":1}' \
                > /dev/null 2>&1; then
                print_info "✓ HTTP 服务响应正常"
            else
                print_warn "HTTP 服务可能未完全就绪，请检查日志"
            fi
        fi
        
        echo ""
        print_info "查看日志: tail -f $LOG_FILE"
        print_info "停止服务: $0 stop"
        print_info "查看状态: $0 status"
    else
        print_error "✗ 服务启动失败"
        print_error "最后 30 行日志:"
        tail -30 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# 停止服务
stop_service() {
    if [ ! -f "$PID_FILE" ]; then
        print_warn "PID 文件不存在"
        # 尝试通过进程名查找
        local pids=$(pgrep -f "openim-mcp\|openim_mcp" 2>/dev/null)
        if [ -n "$pids" ]; then
            print_info "找到相关进程: $pids"
            echo "$pids" | xargs kill -15 2>/dev/null
            sleep 2
            echo "$pids" | xargs kill -9 2>/dev/null
            print_info "已停止相关进程"
        else
            print_warn "未找到运行中的服务"
        fi
        exit 0
    fi
    
    local pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        print_info "停止服务 (PID: $pid)..."
        kill -15 "$pid"
        sleep 3
        if kill -0 "$pid" 2>/dev/null; then
            print_warn "进程未响应 SIGTERM，强制终止..."
            kill -9 "$pid"
        fi
        print_info "服务已停止"
    else
        print_warn "进程不存在 (PID: $pid)"
    fi
    rm -f "$PID_FILE"
}

# 查看状态
status_service() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_info "服务运行中 (PID: $pid)"
            echo ""
            echo "最近日志:"
            tail -10 "$LOG_FILE" 2>/dev/null | sed 's/^/  /'
            
            # 如果 HTTP/SSE 模式，测试端点
            if [[ "$MCP_TRANSPORT" =~ ^(http|sse)$ ]] && command -v curl &> /dev/null; then
                echo ""
                if curl -s -X POST "http://$MCP_HOST:$MCP_PORT/mcp" \
                    -H "Content-Type: application/json" \
                    -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}' \
                    > /dev/null 2>&1; then
                    print_info "✓ HTTP 端点可访问"
                else
                    print_warn "HTTP 端点不可访问"
                fi
            fi
        else
            print_warn "PID 文件存在但进程已停止"
        fi
    else
        print_warn "服务未运行"
    fi
}

# 查看日志
logs_service() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        print_error "日志文件不存在: $LOG_FILE"
    fi
}

# 重启服务
restart_service() {
    print_info "重启服务..."
    stop_service
    sleep 2
    start_service
}

# 显示帮助
show_help() {
    cat << 'HELP'
Usage: $0 {start|stop|restart|status|logs} [options]

Commands:
    start              启动服务（读取 .env 配置）
    stop               停止服务
    restart            重启服务
    status             查看服务状态
    logs               查看实时日志

Environment (.env file):
    MCP_TRANSPORT               传输模式: stdio, http, sse (默认: http)
    MCP_HOST                    HTTP 绑定地址 (默认: 0.0.0.0)
    MCP_PORT                    HTTP 绑定端口 (默认: 8084)
    OPENIM_API_ADDRESS          OpenIM API 地址 (默认: http://localhost:10002)
    OPENIM_ADMIN_SECRET         管理员密钥 (默认: OpenIM123)
    OPENIM_SENDER_ID            发送者 ID (默认: openIMAdmin)
    OPENIM_PLATFORM_ID          平台 ID (默认: 5)

Examples:
    # 启动服务
    ./start.sh start

    # 查看状态
    ./start.sh status

    # 查看日志
    ./start.sh logs

    # 停止服务
    ./start.sh stop

    # 重启服务
    ./start.sh restart
HELP
}

# 主入口
case "${1:-}" in
    start)
        shift
        start_service "$@"
        ;;
    stop)
        shift
        stop_service "$@"
        ;;
    restart)
        shift
        restart_service "$@"
        ;;
    status)
        shift
        status_service "$@"
        ;;
    logs)
        shift
        logs_service "$@"
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        if [ -n "${1:-}" ]; then
            print_error "未知命令: $1"
            echo ""
        fi
        show_help
        exit 1
        ;;
esac
