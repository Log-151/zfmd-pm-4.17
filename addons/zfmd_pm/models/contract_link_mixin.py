from odoo import api, fields, models


class ZfmdContractLinkMixin(models.AbstractModel):
    _name = "zfmd.contract.link.mixin"
    _description = "ZFMD 合同关联接口"

    contract_id = fields.Many2one("zfmd.contract", string="关联合同", tracking=True)
    source_contract_no = fields.Char(string="来源合同号", tracking=True)
    display_contract_no = fields.Char(string="合同编号", compute="_compute_display_contract_no", store=True)
    contract_match_state = fields.Selection(
        [
            ("matched", "已匹配合同"),
            ("unmatched", "未匹配合同"),
            ("empty", "无合同号"),
        ],
        string="合同匹配状态",
        compute="_compute_contract_match_state",
        store=True,
        index=True,
    )

    @api.depends("contract_id", "source_contract_no")
    def _compute_display_contract_no(self):
        for record in self:
            record.display_contract_no = record.contract_id.name or record.source_contract_no or False

    @api.depends("contract_id", "source_contract_no")
    def _compute_contract_match_state(self):
        for record in self:
            if record.contract_id:
                record.contract_match_state = "matched"
            elif record.source_contract_no:
                record.contract_match_state = "unmatched"
            else:
                record.contract_match_state = "empty"

    def _prepare_contract_link_vals(self, contract):
        if not contract:
            return {}
        return {
            "contract_id": contract.id,
            "source_contract_no": contract.name or False,
        }

    def _prepare_contract_snapshot_vals(self, contract):
        vals = self._prepare_contract_link_vals(contract)
        if hasattr(self, "_prepare_business_vals_from_contract"):
            vals.update(self._prepare_business_vals_from_contract(contract))
        return vals
