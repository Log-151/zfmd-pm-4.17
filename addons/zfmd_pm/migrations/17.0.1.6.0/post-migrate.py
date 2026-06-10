from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        UPDATE zfmd_invoice_record
           SET amount_untaxed_manual = (COALESCE(amount_untaxed, 0) != 0),
               actual_payment_manual = (
                   actual_payment_date IS NOT NULL
                   OR COALESCE(actual_payment_amount, 0) != 0
               )
        """
    )
    cr.execute(
        """
        UPDATE zfmd_receivable_plan
           SET actual_payment_manual = (
                   actual_payment_date IS NOT NULL
                   OR COALESCE(actual_payment_amount, 0) != 0
               ),
               actual_invoice_manual = (actual_invoice_date IS NOT NULL)
        """
    )
    cr.execute(
        """
        UPDATE zfmd_contract c
           SET customer_code = p.customer_code
          FROM res_partner p
         WHERE c.partner_id = p.id
           AND COALESCE(c.customer_code, '') = ''
        """
    )
    contracts = env["zfmd.contract"].search([])
    env["zfmd.sync.engine"].sync_contracts(contracts)
    env["zfmd.project.management"].action_refresh_all_projects()
