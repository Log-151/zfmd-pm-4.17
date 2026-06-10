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
            domain = expression.AND(
                [
                    domain,
                    [
                        "|",
                        ("is_deleted", "=", False),
                        ("is_deleted", "=", None),
                    ],
                ]
            )
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
        self.check_access_rights("unlink")
        self.check_access_rule("unlink")
        contract_numbers = set()
        if "display_contract_no" in self._fields:
            contract_numbers = {
                value.strip()
                for value in self.mapped("display_contract_no")
                if isinstance(value, str) and value.strip()
            }
        elif self._name == "zfmd.project.management":
            contract_numbers = {record.contract_id.name or record.name for record in self}
        vals = {
            "is_deleted": True,
            "deleted_at": fields.Datetime.now(),
            "deleted_by": self.env.user.id,
        }
        if "active" in self._fields:
            vals["active"] = False
        self.sudo().with_context(
            include_deleted=True,
            skip_zfmd_sync=True,
            tracking_disable=True,
        ).write(vals)
        self._refresh_after_soft_delete(contract_numbers)
        return True

    def _refresh_after_soft_delete(self, contract_numbers):
        if not contract_numbers:
            return
        engine = self.env["zfmd.sync.engine"]
        if self._name == "zfmd.invoice.record":
            engine.refresh_from_invoices(contract_numbers)
        elif self._name == "zfmd.payment.record":
            engine.refresh_from_payments(contract_numbers)
        elif self._name == "zfmd.receivable.plan":
            engine.refresh_from_receivables(contract_numbers)
        elif self._name == "zfmd.project.management":
            engine.refresh_projects(contract_numbers)

    def action_restore(self):
        self.check_access_rights("write")
        self.check_access_rule("write")
        vals = {
            "is_deleted": False,
            "deleted_at": False,
            "deleted_by": False,
        }
        if "active" in self._fields:
            vals["active"] = True
        self.sudo().with_context(
            include_deleted=True,
            skip_zfmd_sync=True,
            tracking_disable=True,
        ).write(vals)
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
