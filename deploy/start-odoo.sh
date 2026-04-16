#!/bin/bash
set -euo pipefail

DB_HOST_VALUE="${DB_HOST:-${PGHOST:-db}}"
DB_PORT_VALUE="${DB_PORT:-${PGPORT:-5432}}"
DB_USER_VALUE="${DB_USER:-${PGUSER:-odoo}}"
DB_PASSWORD_VALUE="${DB_PASSWORD:-${PGPASSWORD:-odoo}}"
DB_NAME_VALUE="${DB_NAME:-${PGDATABASE:-}}"
HTTP_PORT_VALUE="${PORT:-8069}"
ADMIN_PASSWORD_VALUE="${ADMIN_PASSWORD:-${MASTER_PASSWORD:-admin}}"
LIST_DB_VALUE="${LIST_DB:-False}"
PROXY_MODE_VALUE="${PROXY_MODE:-True}"

TEMP_CONF="/tmp/odoo-runtime.conf"
cp /etc/odoo/odoo.railway.conf "$TEMP_CONF"

{
    echo "db_host = ${DB_HOST_VALUE}"
    echo "db_port = ${DB_PORT_VALUE}"
    echo "db_user = ${DB_USER_VALUE}"
    echo "db_password = ${DB_PASSWORD_VALUE}"
    echo "admin_passwd = ${ADMIN_PASSWORD_VALUE}"
    echo "list_db = ${LIST_DB_VALUE}"
    echo "proxy_mode = ${PROXY_MODE_VALUE}"
    if [ -n "${DB_NAME_VALUE}" ]; then
        echo "db_name = ${DB_NAME_VALUE}"
    fi
} >> "$TEMP_CONF"

exec odoo -c "$TEMP_CONF" --http-port "${HTTP_PORT_VALUE}"

