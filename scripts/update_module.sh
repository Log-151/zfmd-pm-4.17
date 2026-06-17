#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${ODOO_DB_NAME:-zfmd-PM}"
MODULE_NAME="${ODOO_MODULE:-zfmd_pm}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Upgrading ${MODULE_NAME} on database ${DB_NAME}..."
docker compose exec -T "$ODOO_SERVICE" \
    odoo -d "$DB_NAME" -u "$MODULE_NAME" --stop-after-init --no-http

echo "Restarting ${ODOO_SERVICE}..."
docker compose restart "$ODOO_SERVICE"

echo "Done. Open http://127.0.0.1:8069"
