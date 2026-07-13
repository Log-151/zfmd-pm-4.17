from odoo import SUPERUSER_ID, api


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
    if _column_exists(cr, "zfmd_invoice_record", "receivable_plan_id"):
        cr.execute(
            """
            INSERT INTO zfmd_invoice_receivable_plan_rel (invoice_record_id, receivable_plan_id)
            SELECT invoice.id, invoice.receivable_plan_id
              FROM zfmd_invoice_record invoice
             WHERE invoice.receivable_plan_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                      FROM zfmd_invoice_receivable_plan_rel relation
                     WHERE relation.invoice_record_id = invoice.id
                       AND relation.receivable_plan_id = invoice.receivable_plan_id
               )
            """
        )

    env = api.Environment(cr, SUPERUSER_ID, {})
    env.invalidate_all()

    env["zfmd.service.record"].search([])._refresh_service_end_date_from_contracts()

    invoices = env["zfmd.invoice.record"].search([])
    engine = env["zfmd.sync.engine"]
    engine.refresh_from_invoices(engine._contract_numbers(invoices))
