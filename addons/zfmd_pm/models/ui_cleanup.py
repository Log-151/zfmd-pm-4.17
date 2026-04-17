from odoo import api, models


class ZfmdUiCleanup(models.AbstractModel):
    _name = "zfmd.ui.cleanup"
    _description = "ZFMD UI Cleanup"

    @api.model
    def apply(self):
        system_group = self.env.ref("base.group_system")
        internal_group = self.env.ref("base.group_user")
        zfmd_group = self.env.ref("zfmd_pm.group_zfmd_manager")

        for xmlid in ("mail.menu_root_discuss", "base.menu_management"):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.write({"groups_id": [(6, 0, [system_group.id])]})

        zfmd_user = self.env["res.users"].sudo().search([("login", "=", "zfmd")], limit=1)
        zfmd_vals = {
            "name": "兆方美迪业务账号",
            "login": "zfmd",
            "password": "zfmd123456",
            "groups_id": [(6, 0, [internal_group.id, zfmd_group.id])],
        }
        if zfmd_user:
            zfmd_user.write(zfmd_vals)
        else:
            self.env["res.users"].sudo().create(zfmd_vals)
        return True
