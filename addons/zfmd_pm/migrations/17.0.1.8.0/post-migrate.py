from odoo import SUPERUSER_ID, api


def _table_exists(cr, table_name):
    cr.execute("SELECT to_regclass(%s)", (table_name,))
    return bool(cr.fetchone()[0])


def _column_exists(cr, table_name, column_name):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if _table_exists(cr, "zfmd_site") and _column_exists(cr, "zfmd_site", "site_category"):
        cr.execute(
            """
            UPDATE zfmd_site
               SET site_category = CASE
                    WHEN site_category IN ('wind', 'solar') THEN site_category
                    WHEN site_category LIKE '%%风电%%' THEN 'wind'
                    WHEN site_category LIKE '%%光伏%%' THEN 'solar'
                    ELSE NULL
               END
             WHERE site_category IS NOT NULL
            """
        )

    if _table_exists(cr, "zfmd_contract") and _column_exists(cr, "zfmd_contract", "site_category"):
        cr.execute(
            """
            UPDATE zfmd_contract
               SET site_category = CASE
                    WHEN site_category IN ('wind', 'solar') THEN site_category
                    WHEN site_category LIKE '%%风电%%' THEN 'wind'
                    WHEN site_category LIKE '%%光伏%%' THEN 'solar'
                    ELSE NULL
               END
             WHERE site_category IS NOT NULL
            """
        )
        cr.execute(
            """
            UPDATE zfmd_contract c
               SET customer_code = p.customer_code,
                   customer_code_manual = FALSE
              FROM res_partner p
             WHERE c.partner_id = p.id
               AND COALESCE(c.customer_code, '') = ''
               AND COALESCE(p.customer_code, '') != ''
            """
        )

    if _table_exists(cr, "zfmd_invoice_record") and _column_exists(cr, "zfmd_invoice_record", "cancel_amount"):
        cr.execute(
            """
            UPDATE zfmd_invoice_record
               SET cancel_amount = COALESCE(NULLIF(cancel_amount, 0), invoice_amount, 0)
             WHERE state = 'cancel'
               AND COALESCE(cancel_amount, 0) = 0
            """
        )

    if _table_exists(cr, "zfmd_service_record") and _column_exists(cr, "zfmd_service_record", "service_end_date"):
        cr.execute(
            """
            UPDATE zfmd_service_record sr
               SET service_end_date = latest.service_end_date
              FROM (
                    SELECT s.name AS site_name, MAX(c.service_end_date) AS service_end_date
                      FROM zfmd_contract c
                      JOIN zfmd_site s ON s.id = c.site_id
                     WHERE c.service_end_date IS NOT NULL
                     GROUP BY s.name
                   ) latest
             WHERE sr.site_name = latest.site_name
            """
        )

    env = api.Environment(cr, SUPERUSER_ID, {})
    payment_type_model = env["zfmd.payment.type"]
    payment_types = {}
    for sequence, name in enumerate(("初装", "软件", "硬件", "服务", "其他"), start=1):
        payment_type = payment_type_model.search([("name", "=", name)], limit=1)
        if not payment_type:
            payment_type = payment_type_model.create({"name": name, "sequence": sequence})
        payment_types[name] = payment_type

    for payment in env["zfmd.payment.record"].search([("payment_type", "!=", False)]):
        names = [
            item.strip()
            for item in str(payment.payment_type or "").replace("，", ",").replace("、", ",").split(",")
            if item.strip()
        ]
        matched = payment_type_model.browse()
        for name in names:
            matched |= payment_types.get(name) or payment_type_model.browse()
        if matched:
            payment.payment_type_ids = [(6, 0, matched.ids)]

    env["zfmd.service.record"].search([])._compute_service_end_date_from_site()
    env["zfmd.project.management"].action_refresh_all_projects()
