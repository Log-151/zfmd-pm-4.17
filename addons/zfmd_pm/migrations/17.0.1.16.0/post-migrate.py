from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.cr.execute(
        """
        UPDATE zfmd_project_management
           SET bad_debt_manual = TRUE
         WHERE COALESCE(bad_debt_amount, 0) <> 0
        """
    )
    env.invalidate_all()
    env["zfmd.sync.engine"].rebuild_projects_from_ledgers()
