from psycopg2 import sql

from odoo import SUPERUSER_ID, api

_CONTRACT_LINK_TABLES = (
    "zfmd_project_start",
    "zfmd_service_record",
    "zfmd_invoice_record",
    "zfmd_payment_record",
    "zfmd_receivable_plan",
    "zfmd_project_management",
)


def _ensure_contract_links_set_null(cr):
    for table_name in _CONTRACT_LINK_TABLES:
        cr.execute(
            """
            SELECT con.conname, con.confdeltype
              FROM pg_constraint con
              JOIN pg_attribute att
                ON att.attrelid = con.conrelid
               AND att.attnum = ANY(con.conkey)
             WHERE con.contype = 'f'
               AND con.conrelid = %s::regclass
               AND con.confrelid = 'zfmd_contract'::regclass
               AND att.attname = 'contract_id'
            """,
            [table_name],
        )
        for constraint_name, delete_type in cr.fetchall():
            if delete_type == "n":
                continue
            cr.execute(
                sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.Identifier(table_name), sql.Identifier(constraint_name)
                )
            )
            cr.execute(
                sql.SQL(
                    "ALTER TABLE {} ADD CONSTRAINT {} "
                    "FOREIGN KEY (contract_id) REFERENCES zfmd_contract(id) ON DELETE SET NULL"
                ).format(sql.Identifier(table_name), sql.Identifier(constraint_name))
            )


def _repair_service_contract_links(env):
    services = (
        env["zfmd.service.record"]
        .sudo()
        .with_context(include_deleted=True)
        .search([("source_contract_no", "!=", False)])
    )
    contract_model = env["zfmd.contract"].sudo()
    for service in services:
        contract = contract_model.find_by_contract_no(service.source_contract_no)
        if contract and service.contract_id != contract:
            service.with_context(
                skip_service_end_date_recompute=True,
                skip_entry_confirmation_stage=True,
                skip_zfmd_sync=True,
            ).write(
                {
                    "contract_id": contract.id,
                    "source_contract_no": contract.name,
                    "contract_link_manual": True,
                }
            )


def migrate(cr, version):
    allowed_departments = (
        "产品部",
        "工程项目部",
        "软件部",
        "运算服务中心",
        "综合管理部",
        "其他",
    )
    for table_name in ("zfmd_contract", "zfmd_project_start", "zfmd_project_management"):
        cr.execute(
            sql.SQL(
                "UPDATE {} SET delivery_department = '其他' "
                "WHERE delivery_department IS NOT NULL "
                "AND BTRIM(delivery_department) <> '' "
                "AND delivery_department NOT IN %s"
            ).format(sql.Identifier(table_name)),
            [allowed_departments],
        )

    _ensure_contract_links_set_null(cr)
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.invalidate_all()
    _repair_service_contract_links(env)
    env.invalidate_all()
