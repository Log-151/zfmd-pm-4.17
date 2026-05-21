from odoo.osv import expression

from odoo import api, fields, models


class ZfmdSoftDeleteMixin(models.AbstractModel):
    _name = "zfmd.soft.delete.mixin"
    _description = "ZFMD soft delete support"

    is_deleted = fields.Boolean(string="已删除", default=False, index=True, copy=False)
    deleted_at = fields.Datetime(string="删除时间", copy=False, readonly=True)
    deleted_by = fields.Many2one("res.users", string="删除人", copy=False, readonly=True)

    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        domain = list(domain or [])
        if not self.env.context.get("include_deleted") and not self._domain_mentions_deleted(domain):
            domain = expression.AND([domain, [("is_deleted", "=", False)]])
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            access_rights_uid=access_rights_uid,
        )

    @api.model
    def _domain_mentions_deleted(self, domain):
        for item in domain:
            if isinstance(item, (list, tuple)) and item and item[0] == "is_deleted":
                return True
        return False

    def unlink(self):
        if self.env.context.get("force_unlink"):
            return super().unlink()
        now = fields.Datetime.now()
        for record in self:
            vals = {
                "is_deleted": True,
                "deleted_at": now,
                "deleted_by": self.env.user.id,
            }
            if "active" in record._fields:
                vals["active"] = False
            record.write(vals)
        return True

    def action_restore(self):
        vals = {
            "is_deleted": False,
            "deleted_at": False,
            "deleted_by": False,
        }
        if "active" in self._fields:
            vals["active"] = True
        self.write(vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "已恢复",
                "message": f"已恢复 {len(self)} 条记录。",
                "type": "success",
                "sticky": False,
            },
        }
