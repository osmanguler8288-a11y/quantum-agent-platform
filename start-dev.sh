#!/usr/bin/env bash
#
# start-dev.sh — 一键启动完整本地开发环境（macOS）
#
# 同时启动三个服务：
#   Go 认证网关(:8080) + FastAPI 后端(:8001) + 前端 vite(:5173)
# 三者后台运行、日志写 backend/logs/，按 Ctrl+C 一键停掉。
#
# 链路：浏览器 → vite(5173) → 网关(8080) → FastAPI(8001)
#
# 依赖：python3 / go / node+npm / curl / nc（macOS 自带）
# 密钥与数据库连接信息统一由 backend/.env 提供。
#
# 可用环境变量覆盖（命令行前缀即可）：
#   BACKEND_PORT=8001  GATEWAY_PORT=8080  FRONTEND_PORT=5173
#   SKIP_AUTH=true  JWT_SECRET=...  BACKEND_URL=...

set -u

# ── 参数 ─────────────────────────────────────────────────
BACKEND_PORT="${BACKEND_PORT:-8001}"
GATEWAY_PORT="${GATEWAY_PORT:-8080}"   # 网关端口写死在 auth/main.go，此变量仅用于健康检查与提示
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
SKIP_AUTH="${SKIP_AUTH:-true}"
JWT_SECRET="${JWT_SECRET:-local-dev-secret}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

# ── 路径 ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # 仓库根目录
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
AUTH_DIR="$BACKEND_DIR/auth"
AUTH_BIN="$AUTH_DIR/auth"                                    # macOS 二进制（非 auth.exe）
LOG_DIR="$BACKEND_DIR/logs"
mkdir -p "$LOG_DIR"

# ── 颜色 ─────────────────────────────────────────────────
RESET='\033[0m'; CYAN='\033[36m'; GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; GRAY='\033[90m'
ok()   { printf "  ${GREEN}[OK]${RESET}   %s\n" "$*"; }
warn() { printf "  ${YELLOW}[WARN]${RESET} %s\n" "$*"; }
err()  { printf "  ${RED}[ERR]${RESET}  %s\n" "$*"; }

# ── Python 解释器选择 ───────────────────────────────────
# 项目用了 3.10+ 语法（PEP 604 的 `X | None`），Dockerfile 是 python:3.11。
# 不能直接 trust shell 的 `python3`：macOS 的 CommandLineTools python3 是 3.9，
# 会因 `dict | None` 崩在 import 阶段。优先用 conda 等 3.10+ 环境。
find_python() {
  # 1) 显式指定 PYTHON 环境变量优先
  if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then
    command -v "$PYTHON"; return 0
  fi
  # 2) 当前 python3 版本 >= 3.10 就用它
  if command -v python3 >/dev/null 2>&1 && \
     python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    command -v python3; return 0
  fi
  # 3) 显式版本号
  local v
  for v in 3.13 3.12 3.11 3.10; do
    if command -v "python$v" >/dev/null 2>&1; then
      command -v "python$v"; return 0
    fi
  done
  # 4) conda 常见安装路径（conda 可能不在 PATH 里）
  local c
  for c in /opt/anaconda3/bin/python /opt/miniconda3/bin/python \
           "$HOME/anaconda3/bin/python" "$HOME/miniconda3/bin/python" \
           /usr/local/anaconda3/bin/python /usr/local/miniconda3/bin/python; do
    if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      printf '%s' "$c"; return 0
    fi
  done
  return 1
}

# ── 工具 ─────────────────────────────────────────────────
# 用 nc 探测端口（lsof 对 _mysql 等其它用户进程可能探测不到，造成误报）
# 同时探 IPv4 / IPv6 回环：vite 默认绑 ::1，只探 127.0.0.1 会漏判
port_in_use() { nc -z -w1 127.0.0.1 "$1" >/dev/null 2>&1 || nc -z -w1 ::1 "$1" >/dev/null 2>&1; }

wait_port() {   # wait_port <port> <timeout_sec>
  local port=$1 timeout=${2:-40}
  local deadline=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    port_in_use "$port" && return 0
    sleep 0.5
  done
  return 1
}

wait_http() {   # wait_http <url> <timeout_sec>
  local url=$1 timeout=${2:-60}
  local deadline=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    curl -sf "$url" >/dev/null 2>&1 && return 0
    sleep 0.8
  done
  return 1
}

# ── 进程清理（递归杀子进程，覆盖 uvicorn --reload 与 vite 的 worker）──
PIDS=()
kill_tree() {
  local pid=$1 child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}
cleanup() {
  printf "\n${CYAN}停止服务…${RESET}\n"
  for pid in "${PIDS[@]:-}"; do
    kill_tree "$pid"
  done
  # 兜底：按命令精确匹配，清理 --reload / vite 可能遗留的 worker
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "$AUTH_BIN" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

printf "\n${CYAN}Quantum Agent Platform — 本地开发环境（macOS）${RESET}\n"
printf "${GRAY}──────────────────────────────────────────────${RESET}\n"

# ① 前置检查
printf "\n${CYAN}[1/4] 前置检查${RESET}\n"

PYTHON_BIN="$(find_python)" || {
  err "未找到 Python 3.10+（项目需要 3.10+，Dockerfile 为 python:3.11）"
  err "当前 python3 是 $(python3 --version 2>&1 || echo '缺失')，请用 conda 或安装 python3.11+"
  exit 1
}
ok "Python 解释器: ${PYTHON_BIN}（$(${PYTHON_BIN} --version 2>&1)）"
if [ ! -f "$BACKEND_DIR/app/main.py" ]; then
  err "找不到 $BACKEND_DIR/app/main.py，后端目录不完整"
  exit 1
fi
ok "FastAPI 项目目录: $BACKEND_DIR"

if [ ! -x "$AUTH_BIN" ]; then
  warn "网关二进制不存在，开始编译 Go 网关…"
  if ! command -v go >/dev/null 2>&1; then
    err "未安装 Go，无法编译网关。请先安装 Go，或手动提供 $AUTH_BIN"
    exit 1
  fi
  if ! ( cd "$AUTH_DIR" && go build -o auth . ); then
    err "网关编译失败"
    exit 1
  fi
  ok "Go 网关编译完成"
else
  ok "Go 网关已编译: $AUTH_BIN"
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  err "未找到 node/npm，请先安装 Node.js"
  exit 1
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  warn "前端依赖未安装，执行 npm install…"
  ( cd "$FRONTEND_DIR" && npm install ) || { err "前端依赖安装失败"; exit 1; }
fi
ok "前端目录: $FRONTEND_DIR"

# MySQL 只被网关使用；连不上网关会 fatal 退出，必须提醒
if port_in_use 3306; then
  ok "MySQL(3306) 可连接"
else
  warn "MySQL(3306) 连不上 —— 网关会启动失败。请先启动 MySQL，或确认 backend/.env 的 MYSQL_DSN 正确"
fi

# Redis / Milvus 供 FastAPI 使用（缺失时后端会降级，仅提醒）
port_in_use 6379  && ok "Redis(6379) 可连接"   || warn "Redis(6379) 连不上 —— 会话历史/记忆功能会不可用"
port_in_use 19530 && ok "Milvus(19530) 可连接" || warn "Milvus(19530) 连不上 —— RAG 检索/向量记忆会不可用"

# ② 端口检查
printf "\n${CYAN}[2/4] 端口检查${RESET}\n"
start_api=false; start_gw=false; start_fe=false
if port_in_use "$BACKEND_PORT"; then
  warn "FastAPI 端口 $BACKEND_PORT 已被占用 —— 认为它已在运行，跳过启动"
else
  ok "FastAPI 端口 $BACKEND_PORT 空闲，将启动"; start_api=true
fi
if port_in_use "$GATEWAY_PORT"; then
  warn "网关端口 $GATEWAY_PORT 已被占用 —— 认为它已在运行，跳过启动"
else
  ok "网关端口 $GATEWAY_PORT 空闲，将启动"; start_gw=true
fi
if port_in_use "$FRONTEND_PORT"; then
  warn "前端端口 $FRONTEND_PORT 已被占用 —— 认为它已在运行，跳过启动"
else
  ok "前端端口 $FRONTEND_PORT 空闲，将启动"; start_fe=true
fi

# ③ 启动
printf "\n${CYAN}[3/4] 启动服务${RESET}\n"
if $start_api; then
  ( cd "$BACKEND_DIR" && "$PYTHON_BIN" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" ) \
    >> "$LOG_DIR/fastapi.log" 2>&1 &
  PIDS+=("$!")
  ok "FastAPI 已启动（日志: logs/fastapi.log）"
fi
if $start_gw; then
  ( cd "$AUTH_DIR" && \
      BACKEND_URL="$BACKEND_URL" SKIP_AUTH="$SKIP_AUTH" JWT_SECRET="$JWT_SECRET" \
      "$AUTH_BIN" ) >> "$LOG_DIR/gateway.log" 2>&1 &
  PIDS+=("$!")
  ok "Go 网关已启动（日志: logs/gateway.log）"
fi
if $start_fe; then
  ( cd "$FRONTEND_DIR" && npm run dev ) >> "$LOG_DIR/frontend.log" 2>&1 &
  PIDS+=("$!")
  ok "前端已启动（日志: logs/frontend.log）"
fi
if ! $start_api && ! $start_gw && ! $start_fe; then
  ok "所有服务都已在运行，无需启动"
fi

# ④ 健康检查（无论是否本脚本启动，都探测一次）
printf "\n${CYAN}[4/4] 等待就绪…${RESET}\n"
api_ok=false; gw_ok=false; fe_ok=false
if wait_http "http://127.0.0.1:$BACKEND_PORT/api/health/server" 60; then
  ok "FastAPI :$BACKEND_PORT 就绪"; api_ok=true
else
  err "FastAPI :$BACKEND_PORT 未就绪（看 logs/fastapi.log）"
fi
if wait_port "$GATEWAY_PORT" 20; then
  ok "Go 网关 :$GATEWAY_PORT 就绪"; gw_ok=true
else
  err "Go 网关 :$GATEWAY_PORT 未就绪（看 logs/gateway.log）"
fi
if wait_http "http://localhost:$FRONTEND_PORT" 40; then
  ok "前端 :$FRONTEND_PORT 就绪"; fe_ok=true
else
  err "前端 :$FRONTEND_PORT 未就绪（看 logs/frontend.log）"
fi

# ── 汇总 ─────────────────────────────────────────────────
printf "\n${GRAY}──────────────────────────────────────────────${RESET}\n"
if $api_ok && $gw_ok && $fe_ok; then
  printf "${GREEN}  本地开发环境已就绪${RESET}\n"
else
  printf "${YELLOW}  部分服务未就绪，请查看对应日志${RESET}\n"
fi
printf "\n"
printf "   前端         http://localhost:%s\n" "$FRONTEND_PORT"
printf "   Go 网关      http://127.0.0.1:%s\n" "$GATEWAY_PORT"
printf "   FastAPI      http://127.0.0.1:%s\n" "$BACKEND_PORT"
printf "     API 文档   http://127.0.0.1:%s/docs\n" "$BACKEND_PORT"
if [ "$SKIP_AUTH" = "true" ]; then
  printf "   认证模式     SKIP_AUTH=true（固定用户 local_dev，不用登录）\n"
else
  printf "   认证模式     真实 JWT（需登录）\n"
fi
printf "\n"
printf "   实时日志     tail -f %s/fastapi.log %s/gateway.log %s/frontend.log\n" "$LOG_DIR" "$LOG_DIR" "$LOG_DIR"
printf "   停止服务     按 Ctrl+C\n"
printf "\n"

# 前台等待；Ctrl+C 触发 cleanup 停掉所有服务，任一服务退出也会连带停掉其余
wait
