from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Make every existing invoice effective and rebuild dependent figures."""
    cr.execute(
        """
        UPDATE zfmd_invoice_record
           SET entry_state = 'confirmed',
               confirmed_at = COALESCE(confirmed_at, write_date, create_date, NOW()),
               confirmed_by = COALESCE(confirmed_by, write_uid, create_uid, %s)
         WHERE entry_state IS DISTINCT FROM 'confirmed'
            OR confirmed_at IS NULL
            OR confirmed_by IS NULL
        """,
        [SUPERUSER_ID],
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.invalidate_all()
    env["zfmd.sync.engine"].rebuild_projects_from_ledgers()
    env.invalidate_all()
