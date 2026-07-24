#!/bin/bash
set -euo pipefail

read_secret() {
    local variable_name="$1"
    local file_variable_name="${variable_name}_FILE"
    local direct_value="${!variable_name:-}"
    local file_path="${!file_variable_name:-}"
    if [ -n "${direct_value}" ] && [ -n "${file_path}" ]; then
        echo "Set only ${variable_name} or ${file_variable_name}, not both." >&2
        exit 1
    fi
    if [ -n "${file_path}" ]; then
        if [ ! -r "${file_path}" ]; then
            echo "Secret file is not readable: ${file_path}" >&2
            exit 1
        fi
        tr -d '\r\n' < "${file_path}"
    else
        printf '%s' "${direct_value}"
    fi
}

DB_HOST_VALUE="${ODOO_DB_HOST:-${DB_HOST:-${PGHOST:-db}}}"
DB_PORT_VALUE="${ODOO_DB_PORT:-${DB_PORT:-${PGPORT:-5432}}}"
DB_USER_VALUE="${ODOO_DB_USER:-${DB_USER:-${PGUSER:-odoo}}}"
DB_PASSWORD_VALUE="$(read_secret ODOO_DB_PASSWORD)"
if [ -z "${DB_PASSWORD_VALUE}" ]; then
    DB_PASSWORD_VALUE="$(read_secret DB_PASSWORD)"
fi
DB_NAME_VALUE="${ODOO_DB_NAME:-${DB_NAME:-}}"
HTTP_PORT_VALUE="${PORT:-8069}"
ADMIN_PASSWORD_VALUE="$(read_secret ADMIN_PASSWORD)"
if [ -z "${ADMIN_PASSWORD_VALUE}" ]; then
    ADMIN_PASSWORD_VALUE="$(read_secret MASTER_PASSWORD)"
fi
LIST_DB_VALUE="${LIST_DB:-False}"
PROXY_MODE_VALUE="${PROXY_MODE:-True}"
PRODUCTION_MODE_VALUE="${PRODUCTION_MODE:-False}"
DB_FILTER_VALUE="${DB_FILTER:-}"
DB_CONNECT_TIMEOUT="${DB_CONNECT_TIMEOUT:-90}"
ODOO_BASE_CONF_VALUE="${ODOO_BASE_CONF:-/etc/odoo/odoo.conf}"

if [ "${PRODUCTION_MODE_VALUE}" = "True" ]; then
    if [ -z "${DB_PASSWORD_VALUE}" ] || [ "${DB_PASSWORD_VALUE}" = "odoo" ]; then
        echo "Production startup refused: configure a non-default database password." >&2
        exit 1
    fi
    if [ -z "${ADMIN_PASSWORD_VALUE}" ] || [ "${ADMIN_PASSWORD_VALUE}" = "admin" ]; then
        echo "Production startup refused: configure a non-default Odoo master password." >&2
        exit 1
    fi
    if [ -z "${DB_NAME_VALUE}" ]; then
        echo "Production startup refused: ODOO_DB_NAME is required." >&2
        exit 1
    fi
    if [ "${LIST_DB_VALUE}" != "False" ]; then
        echo "Production startup refused: LIST_DB must be False." >&2
        exit 1
    fi
fi

wait_for_db() {
    echo "Waiting for PostgreSQL at ${DB_HOST_VALUE}:${DB_PORT_VALUE}..."
    local start_time
    start_time="$(date +%s)"

    while true; do
        if command -v pg_isready >/dev/null 2>&1; then
            if PGPASSWORD="${DB_PASSWORD_VALUE}" pg_isready \
                -h "${DB_HOST_VALUE}" \
                -p "${DB_PORT_VALUE}" \
                -U "${DB_USER_VALUE}" >/dev/null 2>&1; then
                break
            fi
        else
            if python3 - "${DB_HOST_VALUE}" "${DB_PORT_VALUE}" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=2):
    pass
PY
            then
                break
            fi
        fi

        local now
        now="$(date +%s)"
        if [ $((now - start_time)) -ge "${DB_CONNECT_TIMEOUT}" ]; then
            echo "PostgreSQL is not ready after ${DB_CONNECT_TIMEOUT}s." >&2
            exit 1
        fi
        sleep 2
    done

    echo "PostgreSQL is ready."
}

TEMP_CONF="/tmp/odoo-runtime.conf"
if [ ! -f "${ODOO_BASE_CONF_VALUE}" ] && [ -f /etc/odoo/odoo.conf ]; then
    ODOO_BASE_CONF_VALUE="/etc/odoo/odoo.conf"
fi
if [ ! -f "${ODOO_BASE_CONF_VALUE}" ]; then
    echo "Odoo base config not found: ${ODOO_BASE_CONF_VALUE}" >&2
    exit 1
fi
cp "${ODOO_BASE_CONF_VALUE}" "$TEMP_CONF"
chmod 600 "$TEMP_CONF"

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
    if [ -n "${DB_FILTER_VALUE}" ]; then
        echo "dbfilter = ${DB_FILTER_VALUE}"
    elif [ -n "${DB_NAME_VALUE}" ]; then
        escaped_db_name="$(printf '%s' "${DB_NAME_VALUE}" | sed 's/[][(){}.^$*+?|\\]/\\&/g')"
        echo "dbfilter = ^${escaped_db_name}$"
    fi
} >> "$TEMP_CONF"

wait_for_db

if [ "$#" -gt 0 ]; then
    if [ "$1" = "odoo" ]; then
        shift
    fi
    exec odoo -c "$TEMP_CONF" "$@"
fi

exec odoo -c "$TEMP_CONF" --http-port "${HTTP_PORT_VALUE}"
