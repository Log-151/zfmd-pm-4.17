from odoo import api, models


class ZfmdUiCleanup(models.AbstractModel):
    _name = "zfmd.ui.cleanup"
    _description = "ZFMD UI Cleanup"

    @api.model
    def apply(self):
        system_group = self.env.ref("base.group_system")
        for xmlid in ("mail.menu_root_discuss", "base.menu_management"):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.write({"groups_id": [(6, 0, [system_group.id])]})
        return True
