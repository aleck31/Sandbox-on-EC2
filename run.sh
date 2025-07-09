#!/bin/bash

# EC2 Sandbox Agent - WebUI启动管理脚本

APP_FILE="demo_webui.py"
PID_FILE=".pid"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/webui.log"
AWS_PROFILE=""
HOST="0.0.0.0"
PORT="8086"

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 解析参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --profile)
                AWS_PROFILE="$2"
                shift 2
                ;;
            *)
                ACTION="$1"
                shift
                ;;
        esac
    done
}

# 检查是否运行
is_running() {
    [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1
}

# 启动
start() {
    if is_running; then
        echo "⚠️  应用已运行 (PID: $(cat "$PID_FILE"))"
        return 1
    fi
    
    echo "🚀 启动应用..."
    [ -n "$AWS_PROFILE" ] && echo "🔧 AWS Profile: $AWS_PROFILE"
    echo "🌐 服务地址: http://$HOST:$PORT"
    
    # 设置环境变量
    local env_vars=""
    if [ -n "$AWS_PROFILE" ]; then
        env_vars="AWS_PROFILE=$AWS_PROFILE"
    fi
    
    # 启动应用
    if [ -n "$env_vars" ]; then
        nohup env $env_vars uv run "$APP_FILE" > "$LOG_FILE" 2>&1 &
    else
        nohup uv run "$APP_FILE" > "$LOG_FILE" 2>&1 &
    fi
    
    echo $! > "$PID_FILE"
    
    sleep 3
    if is_running; then
        echo "✅ 启动成功 (PID: $(cat "$PID_FILE"))"
        echo "📍 访问: http://$HOST:$PORT"
        echo "📋 日志: tail -f $LOG_FILE"
    else
        echo "❌ 启动失败，检查日志: $LOG_FILE"
    fi
}

# 停止
stop() {
    if ! is_running; then
        echo "⚠️  应用未运行"
        return 1
    fi
    
    echo "🛑 停止应用..."
    local pid=$(cat "$PID_FILE")
    kill "$pid" 2>/dev/null
    
    # 等待停止
    for i in {1..10}; do
        if ! ps -p "$pid" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # 强制停止
    if ps -p "$pid" > /dev/null 2>&1; then
        kill -9 "$pid" 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    echo "✅ 应用已停止"
}

# 重启
restart() {
    echo "🔄 重启应用..."
    stop
    sleep 1
    start
}

# 状态
status() {
    echo "📊 应用状态:"
    if is_running; then
        local pid=$(cat "$PID_FILE")
        echo "✅ 运行中 (PID: $pid)"
        echo "📍 访问: http://$HOST:$PORT"
        [ -f "$LOG_FILE" ] && echo "📋 日志: tail -f $LOG_FILE"
    else
        echo "❌ 未运行"
    fi
}

# 主函数
parse_args "$@"

case "$ACTION" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    *)
        echo "用法: $0 {start|stop|restart|status} [--profile PROFILE_NAME]"
        echo "  start   - 启动应用"
        echo "  stop    - 停止应用"
        echo "  restart - 重启应用"
        echo "  status  - 显示状态"
        echo ""
        echo "选项:"
        echo "  --profile PROFILE_NAME  - 设置 AWS Profile"
        echo ""
        echo "示例:"
        echo "  $0 start --profile production"
        echo "  $0 restart --profile dev"
        exit 1
        ;;
esac
