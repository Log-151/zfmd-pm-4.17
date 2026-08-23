from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Activate legacy formal invoices, then recompute all project balances."""
    cr.execute(
        """
        UPDATE zfmd_invoice_record
           SET entry_state = 'confirmed',
               confirmed_at = COALESCE(write_date, create_date, NOW()),
               confirmed_by = COALESCE(write_uid, create_uid, %s)
         WHERE entry_state = 'draft'
           AND state IN ('open', 'paid')
        """,
        [SUPERUSER_ID],
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.invalidate_all()
    env["zfmd.sync.engine"].rebuild_projects_from_ledgers()
    env.invalidate_all()
