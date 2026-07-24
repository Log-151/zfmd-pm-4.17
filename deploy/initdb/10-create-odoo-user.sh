#!/bin/bash
set -euo pipefail

if [ -z "${ODOO_DB_USER:-}" ] || [ -z "${ODOO_DB_PASSWORD_FILE:-}" ]; then
    echo "ODOO_DB_USER and ODOO_DB_PASSWORD_FILE are required." >&2
    exit 1
fi
if [ ! -r "${ODOO_DB_PASSWORD_FILE}" ]; then
    echo "Odoo database password secret is not readable." >&2
    exit 1
fi

odoo_db_password="$(tr -d '\r\n' < "${ODOO_DB_PASSWORD_FILE}")"
if [ -z "${odoo_db_password}" ] || [ "${odoo_db_password}" = "odoo" ]; then
    echo "Refusing to initialize an empty or default Odoo database password." >&2
    exit 1
fi

psql \
    --username "${POSTGRES_USER}" \
    --dbname postgres \
    --set=odoo_user="${ODOO_DB_USER}" \
    --set=odoo_password="${odoo_db_password}" \
    --set=odoo_database="${POSTGRES_DB}" <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'odoo_user',
    :'odoo_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'odoo_user')
\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'odoo_database', :'odoo_user')
\gexec
SQL

unset odoo_db_password
