from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["zfmd.sync.engine"].rebuild_projects_from_ledgers()
