#!/usr/bin/env bash
# =============================================================================
# Quantum Agent Platform 部署脚本（前后端分离，本地执行、SSH 推送）
# =============================================================================
# 拓扑（前后端分离）：
#   前端 frontend/dist → python3 http.server SPA，端口 8000（systemd qap-frontend）
#   后端 backend/      → uvicorn app.main:app，端口 8001（systemd qap-backend）
#
# 用法（⚠️ 必须在项目根目录运行）：
#   cd <项目根目录>
#   DEPLOY_PASSWORD='<服务器密码>' ./deploy.sh          # 密码经环境变量临时注入
#   # 或自备 askpass：
#   SSH_ASKPASS=/tmp/askpass.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0 ./deploy.sh
#
# 目标机/端口可用环境变量覆盖：
#   DEPLOY_HOST=1.2.3.4 FRONTEND_PORT=8000 BACKEND_PORT=8001 ./deploy.sh
#   只部署前端（后端依赖未就绪时）： SKIP_BACKEND=1 ./deploy.sh
#   前端切真实后端（联调）：         VITE_USE_MOCK=false ./deploy.sh
#
# 纪律（见 deploy skill）：
#   - 密码不硬编码进脚本；用 SSH_ASKPASS / DEPLOY_PASSWORD 临时注入，用完删
#   - 脚本用 pwd 定位项目根，运行时 cwd 必须是项目根（脚本可放任意位置）
#   - 部署前确认 backend/.env 是目标状态（LLM key / 模型 / 端口等以本地 .env 为准）
# =============================================================================
set -euo pipefail

ROOT="$(pwd)"

# ── 项目根校验 ──
if [ ! -d "$ROOT/frontend" ] || [ ! -d "$ROOT/backend" ]; then
  echo "[ERR] 当前目录不是项目根（缺少 frontend/ 或 backend/）" >&2
  echo "     请先 cd 到项目根再运行：cd <项目根> && ./deploy.sh" >&2
  exit 8
fi

# ── 目标机 / 端口 / 远端路径 ──
HOST="${DEPLOY_HOST:-120.55.84.80}"
SSH_USER="${DEPLOY_USER:-root}"
SSH="$SSH_USER@$HOST"
FRONTEND_PORT="${FRONTEND_PORT:-8000}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/quantum-agent-platform}"
REMOTE_BACKEND="$REMOTE_ROOT/backend"
REMOTE_FRONTEND="$REMOTE_ROOT/frontend"
REMOTE_ENV_FILE="$REMOTE_ROOT/.env"
SKIP_BACKEND="${SKIP_BACKEND:-0}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }

# ── 安全护栏：远端路径必须指向本项目，防止误覆盖其它项目 ──
case "$REMOTE_ROOT" in
  *quantum*|*qap*) ;;
  *) err "REMOTE_ROOT 异常: $REMOTE_ROOT（应包含 quantum/qap，防止误覆盖其它项目）"; exit 9 ;;
esac

# ── SSH 密码处理（askpass，不硬编码；用完清理）──
CLEANUP_ASKPASS=0
if [ -z "${SSH_ASKPASS:-}" ] && [ -n "${DEPLOY_PASSWORD:-}" ]; then
  ASKPASS_FILE="$(mktemp /tmp/qap_askpass.XXXXXX)"
  cat > "$ASKPASS_FILE" <<'EOF'
#!/usr/bin/env bash
echo "$QAP_DEPLOY_PASSWORD"
EOF
  chmod 700 "$ASKPASS_FILE"
  export SSH_ASKPASS="$ASKPASS_FILE"
  export SSH_ASKPASS_REQUIRE=force
  export DISPLAY=:0
  export QAP_DEPLOY_PASSWORD="$DEPLOY_PASSWORD"
  CLEANUP_ASKPASS=1
fi
if [ -z "${SSH_ASKPASS:-}" ]; then
  err "未提供 SSH 密码。请二选一："
  err "  1) DEPLOY_PASSWORD='<密码>' ./deploy.sh"
  err "  2) 自建 askpass 后 SSH_ASKPASS=/tmp/askpass.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0 ./deploy.sh"
  exit 2
fi
cleanup() { [ "$CLEANUP_ASKPASS" = "1" ] && rm -f "${ASKPASS_FILE:-}"; }
trap cleanup EXIT

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)

# ── 前置检查 ──
for cmd in node npm ssh scp curl; do
  command -v "$cmd" >/dev/null 2>&1 || { err "缺少命令: $cmd"; exit 3; }
done

# ── 1) 构建前端 ──
log "1) 构建前端 (npm install && npm run build) ..."
( cd "$ROOT/frontend" && npm install && npm run build ) || { err "前端构建失败"; exit 1; }

# ── 2) 推送代码（失败仅告警）──
BRANCH="$(git -C "$ROOT" branch --show-current 2>/dev/null || echo master)"
log "2) 推送代码到 origin/$BRANCH ..."
git -C "$ROOT" push origin "$BRANCH" 2>/dev/null || warn "git push 失败（使用本地工作树部署）"

# ── 3) 同步后端代码（排除 venv/.env/logs 等）──
if [ "$SKIP_BACKEND" = "1" ]; then
  warn "SKIP_BACKEND=1，跳过后端同步/装配"
else
  log "3) 同步后端代码到 $REMOTE_BACKEND ..."
  ssh "${SSH_OPTS[@]}" "$SSH" "mkdir -p $REMOTE_BACKEND $REMOTE_FRONTEND"
  tar czf - --exclude='.venv' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='.env' --exclude='logs' --exclude='*.db' --exclude='.pytest_cache' \
    -C "$ROOT/backend" . | ssh "${SSH_OPTS[@]}" "$SSH" "tar xzf - -C $REMOTE_BACKEND"
fi

# ── 4) 同步前端 dist（带备份）+ serve.py ──
log "4) 同步前端 dist 到 $REMOTE_FRONTEND/dist（备份旧版）..."
ssh "${SSH_OPTS[@]}" "$SSH" "mkdir -p $REMOTE_FRONTEND; rm -rf $REMOTE_FRONTEND/dist.bak; [ -d $REMOTE_FRONTEND/dist ] && cp -r $REMOTE_FRONTEND/dist $REMOTE_FRONTEND/dist.bak; mkdir -p $REMOTE_FRONTEND/dist"
tar czf - -C "$ROOT/frontend/dist" . | ssh "${SSH_OPTS[@]}" "$SSH" "tar xzf - -C $REMOTE_FRONTEND/dist"

log "4b) 上传前端 serve.py ..."
scp "${SSH_OPTS[@]}" "$ROOT/frontend/serve.py" "$SSH:$REMOTE_FRONTEND/serve.py"

# ── 5) 上传本地 .env（后端用）──
if [ "$SKIP_BACKEND" = "1" ]; then
  :
else
  log "5) 上传本地 backend/.env 作为远端基础 ..."
  scp "${SSH_OPTS[@]}" "$ROOT/backend/.env" "$SSH:/tmp/qap_local.env"
fi

# ── 6) 远端装配后端（venv + 依赖 + .env + systemd）──
if [ "$SKIP_BACKEND" = "1" ]; then
  :
else
  log "6) 远端装配后端（venv / 依赖 / .env / systemd qap-backend）..."
  ssh "${SSH_OPTS[@]}" "$SSH" \
    BACKEND_PORT="$BACKEND_PORT" \
    REMOTE_BACKEND="$REMOTE_BACKEND" REMOTE_ENV_FILE="$REMOTE_ENV_FILE" \
    bash -s <<'RCMD'
set -e
echo "[remote] 1) 建 venv (python3)"
if [ ! -x "$REMOTE_BACKEND/.venv/bin/python" ]; then
  python3 -m venv "$REMOTE_BACKEND/.venv"
fi
PIP="$REMOTE_BACKEND/.venv/bin/pip"

echo "[remote] 2) 安装依赖（requirements.txt，清华源）"
"$PIP" install -q -r "$REMOTE_BACKEND/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>&1 | tail -8

echo "[remote] 3) 装配 .env"
[ -f /tmp/qap_local.env ] && cp /tmp/qap_local.env "$REMOTE_ENV_FILE" && rm -f /tmp/qap_local.env

echo "[remote] 4) 注册 systemd qap-backend :$BACKEND_PORT"
cat > /etc/systemd/system/qap-backend.service <<EOF
[Unit]
Description=Quantum Agent Platform Backend (uvicorn)
After=network.target

[Service]
Type=simple
WorkingDirectory=$REMOTE_BACKEND
EnvironmentFile=$REMOTE_ENV_FILE
ExecStart=$REMOTE_BACKEND/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable qap-backend
systemctl restart qap-backend
RCMD
fi

# ── 7) 远端装配前端（systemd qap-frontend）──
log "7) 远端装配前端（systemd qap-frontend :$FRONTEND_PORT）..."
ssh "${SSH_OPTS[@]}" "$SSH" \
  FRONTEND_PORT="$FRONTEND_PORT" REMOTE_FRONTEND="$REMOTE_FRONTEND" \
  bash -s <<'RCMD'
set -e
cat > /etc/systemd/system/qap-frontend.service <<EOF
[Unit]
Description=Quantum Agent Platform Frontend (static SPA)
After=network.target

[Service]
Type=simple
WorkingDirectory=$REMOTE_FRONTEND
Environment=PORT=$FRONTEND_PORT
ExecStart=/usr/bin/python3 $REMOTE_FRONTEND/serve.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable qap-frontend
systemctl restart qap-frontend
RCMD

# ── 8) 健康检查 ──
log "8) 健康检查前端 http://$HOST:$FRONTEND_PORT/ ..."
OK=0
for i in $(seq 1 30); do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://$HOST:$FRONTEND_PORT/" 2>/dev/null || true)
  if [ "$CODE" = "200" ]; then OK=1; log "前端 UP after ${i}s (HTTP $CODE)"; break; fi
  sleep 1
done
[ "$OK" = "1" ] || { err "前端健康检查未通过（排查: ssh $SSH 'journalctl -u qap-frontend -n 50'）"; exit 6; }

if [ "$SKIP_BACKEND" = "1" ]; then
  warn "已跳过后端（SKIP_BACKEND=1），未做后端健康检查"
else
  log "8b) 健康检查后端 http://$HOST:$BACKEND_PORT/api/health/server ..."
  OK=0
  for i in $(seq 1 15); do
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://$HOST:$BACKEND_PORT/api/health/server" 2>/dev/null || true)
    if [ "$CODE" = "200" ]; then OK=1; log "后端 UP after ${i}s (HTTP $CODE)"; break; fi
    sleep 1
  done
  [ "$OK" = "1" ] || warn "后端健康检查未通过（HTTP ${CODE:-无响应}）——若 MySQL/Redis/Milvus 依赖未部署属预期；排查: ssh $SSH 'journalctl -u qap-backend -n 50'"
fi

# ── 完成摘要 ──
echo ""
log "============================================================"
log "  ✅ Quantum Agent Platform 部署完成（前后端分离）"
log "  前端:     http://$HOST:$FRONTEND_PORT  (http.server SPA)"
log "  后端:     http://$HOST:$BACKEND_PORT  (uvicorn, systemd qap-backend)"
log "  前端日志: ssh $SSH 'journalctl -u qap-frontend -f'"
log "  后端日志: ssh $SSH 'journalctl -u qap-backend -f'"
log "  回滚前端: ssh $SSH 'cp -r $REMOTE_FRONTEND/dist.bak/* $REMOTE_FRONTEND/dist/ && systemctl restart qap-frontend'"
log "============================================================"
