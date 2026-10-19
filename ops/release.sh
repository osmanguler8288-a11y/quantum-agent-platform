#!/usr/bin/env bash
# Called by deploy.py. Immutable code/images, persistent data, automatic code rollback.
set -Eeuo pipefail
ROOT=/opt/quantum-agent-platform
RELEASE=${1:?release ID required}
[[ "$RELEASE" =~ ^[0-9]{8}-[0-9]{6}-[a-f0-9]{7,12}$ ]] || exit 2
TARGET="$ROOT/releases/$RELEASE"
exec 9>"$ROOT/deploy.lock"
flock -n 9 || { echo 'Another deployment is running'; exit 3; }
test -f "$TARGET/ops/compose.yml"
PREVIOUS=''
if [[ -L "$ROOT/current" ]]; then
    candidate=$(readlink -f "$ROOT/current" || true)
    if [[ "$candidate" == "$ROOT/releases/"* && -f "$candidate/ops/compose.yml" ]]; then
        PREVIOUS="$candidate"
    fi
fi
compose() {
    docker compose --env-file "$ROOT/shared/compose.env" --env-file "$1/release.env" -f "$1/ops/compose.yml" "${@:2}"
}
compose "$TARGET" config --quiet
nginx -t
echo '[deploy] Building versioned images; live services continue running'
compose "$TARGET" build
echo '[deploy] Verifying vector and memory storage with temporary data'
timeout 180 docker run --rm --name "qap-storage-check-$RELEASE" --memory 768m -e PYTHONPATH=/app \
    -v "$TARGET/ops/check_storage.py:/tmp/check_storage.py:ro" \
    "qap-backend:$RELEASE" python /tmp/check_storage.py

if [[ -n "$PREVIOUS" && -f "$PREVIOUS/ops/compose.yml" ]]; then
    echo '[deploy] Backing up persistent databases before switching'
    BACKUP="$ROOT/shared/backups/$(date +%Y%m%d-%H%M%S)-$RELEASE"
    mkdir -p "$BACKUP"
    compose "$PREVIOUS" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction quantum_auth' > "$BACKUP/auth.sql"
    compose "$PREVIOUS" exec -T app python -c 'import sqlite3; s=sqlite3.connect("/app/data/qap.db"); d=sqlite3.connect("/app/data/pre-update.sqlite3"); s.backup(d); d.close(); s.close()'
    cp "$ROOT/shared/data/pre-update.sqlite3" "$BACKUP/qap.sqlite3"
    # Keep hashed chunks needed by browser tabs opened before this update.
    if [[ "$PREVIOUS" != "$TARGET" && -d "$PREVIOUS/frontend/dist/assets" ]]; then
        cp -an "$PREVIOUS/frontend/dist/assets/." "$TARGET/frontend/dist/assets/"
    fi
fi

rollback_on_error() {
    local code=$?
    trap - ERR
    echo '[deploy] Activation failed; restoring previous code when available'
    if [[ -n "$PREVIOUS" && -f "$PREVIOUS/ops/compose.yml" ]]; then
        compose "$PREVIOUS" up -d --wait --wait-timeout 240 || true
        ln -sfn "$PREVIOUS" "$ROOT/current"
        echo '[deploy] Previous release restored; persistent data was kept'
    fi
    exit "$code"
}
trap rollback_on_error ERR
echo '[deploy] Starting containers and waiting for health checks'
compose "$TARGET" up -d --wait --wait-timeout 240
for attempt in $(seq 1 20); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:19000/api/health/server || true)
    [[ "$code" == 401 ]] && break
    sleep 2
done
[[ "$code" == 401 ]]
echo '[deploy] Gateway authentication verified'

if [[ -f /etc/nginx/conf.d/qap-platform.conf ]]; then
    cp /etc/nginx/conf.d/qap-platform.conf "$ROOT/shared/nginx.previous.conf"
fi
cp "$TARGET/ops/nginx.conf" /etc/nginx/conf.d/qap-platform.conf
if ! nginx -t; then
    if [[ -f "$ROOT/shared/nginx.previous.conf" ]]; then
        cp "$ROOT/shared/nginx.previous.conf" /etc/nginx/conf.d/qap-platform.conf
    else
        rm -f /etc/nginx/conf.d/qap-platform.conf
    fi
    false
fi
ln -sfn "$TARGET" "$ROOT/current"
systemctl reload-or-restart nginx
curl -fsS --max-time 10 http://127.0.0.1:8889/ -o /dev/null
if [[ -n "$PREVIOUS" && "$PREVIOUS" != "$TARGET" ]]; then
    ln -sfn "$PREVIOUS" "$ROOT/previous"
fi
trap - ERR
echo "[deploy] SUCCESS $RELEASE http://139.196.11.38:8889"
compose "$TARGET" ps
