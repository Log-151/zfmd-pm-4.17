from odoo import api, fields, models


class ZfmdPaymentRecord(models.Model):
    _name = "zfmd.payment.record"
    _description = "回款登记"
    _inherit = [
        "mail.thread",
        "zfmd.soft.delete.mixin",
        "zfmd.entry.confirmation.mixin",
    ]
    _order = "payment_date desc, id desc"

    active = fields.Boolean(string="有效", default=True, index=True)
    name = fields.Char(string="回款记录编号", required=True, copy=False, default="New")
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

    payment_date = fields.Date(string="回款日期", tracking=True)
    payer_name = fields.Char(string="付款单位")
    province_name = fields.Char(string="省区")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="项目内容")
    contract_amount = fields.Float(string="合同金额（元）")
    payment_type = fields.Char(string="类型")
    bill_amount = fields.Float(string="汇票回款（元）")
    cash_amount = fields.Float(string="现金回款（元）")
    amount_total = fields.Float(string="回款金额（元）", compute="_compute_amount_total", store=True)
    promised_payment_date = fields.Date(string="承诺回款日期")
    promised_payment_note = fields.Char(string="承诺回款说明")
    payment_ratio_text = fields.Char(string="回款比例", compute="_compute_payment_ratio_text", store=True)
    payment_item_name = fields.Char(string="回款项名称")
    sale_manager = fields.Char(string="销售经理")
    sale_contact = fields.Char(string="销售联系人")
    note = fields.Text(string="备注")
    message_has_sms_error = fields.Boolean(groups="base.group_no_one")

    payment_year = fields.Char(string="回款年度", compute="_compute_period_labels", store=True, index=True)
    payment_quarter = fields.Char(string="回款季度", compute="_compute_period_labels", store=True, index=True)
    payment_month = fields.Char(string="回款月份", compute="_compute_period_labels", store=True, index=True)

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

    @api.depends("payment_date")
    def _compute_period_labels(self):
        for record in self:
            if not record.payment_date:
                record.payment_year = False
                record.payment_quarter = False
                record.payment_month = False
                continue
            year = record.payment_date.year
            month = record.payment_date.month
            quarter = ((month - 1) // 3) + 1
            record.payment_year = str(year)
            record.payment_quarter = f"{year}年Q{quarter}"
            record.payment_month = f"{year}-{month:02d}"

    def _prepare_contract_sync_vals(self, contract):
        return {
            "source_contract_no": contract.name or False,
            "payer_name": contract.partner_id.name or False,
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "site_name": contract.site_id.name or False,
            "product_line": contract.product_line or False,
            "project_content": contract.project_content or False,
            "sale_manager": contract.sale_manager or False,
            "sale_contact": contract.sale_contact or False,
            "contract_amount": contract.amount_total or 0.0,
        }

    @api.onchange("contract_id")
    def _onchange_contract_id(self):
        for record in self:
            if record.contract_id:
                for key, value in record._prepare_contract_sync_vals(record.contract_id).items():
                    setattr(record, key, value)

    @api.onchange("site_name")
    def _onchange_site_name(self):
        for record in self:
            site_name = (record.site_name or "").strip()
            if not site_name:
                continue
            site = self.env["zfmd.site"].search(
                ["|", ("name", "=", site_name), ("other_name", "=", site_name)],
                limit=2,
            )
            if len(site) != 1:
                continue
            site = site[:1]
            record.province_name = site.province_name or record.province_name
            record.group_name = site.group_name or record.group_name
            if site.partner_id:
                record.payer_name = site.partner_id.name or record.payer_name
            reference = self.env["zfmd.contract"].search(
                [("site_id", "=", site.id)],
                order="archive_date desc, id desc",
                limit=1,
            )
            if reference:
                record.product_line = reference.product_line or record.product_line
                record.project_content = reference.project_content or record.project_content
                record.sale_manager = reference.sale_manager or record.sale_manager
                record.sale_contact = reference.sale_contact or record.sale_contact
                record.contract_amount = reference.amount_total or record.contract_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.payment.record") or "New"
            if vals.get("contract_id"):
                contract = self.env["zfmd.contract"].browse(vals["contract_id"])
                for key, value in self._prepare_contract_sync_vals(contract).items():
                    if not vals.get(key):
                        vals[key] = value
        records = super().create(vals_list)
        if not self.env.context.get("skip_zfmd_sync"):
            self.env["zfmd.sync.engine"].refresh_from_payments(self.env["zfmd.sync.engine"]._contract_numbers(records))
        return records

    def write(self, vals):
        old_contract_numbers = self.env["zfmd.sync.engine"]._contract_numbers(self)
        if vals.get("contract_id"):
            vals = dict(vals)
            contract = self.env["zfmd.contract"].browse(vals["contract_id"])
            for key, value in self._prepare_contract_sync_vals(contract).items():
                if not vals.get(key):
                    vals[key] = value
        result = super().write(vals)
        if not self.env.context.get("skip_zfmd_sync"):
            contract_numbers = old_contract_numbers | self.env["zfmd.sync.engine"]._contract_numbers(self)
            self.env["zfmd.sync.engine"].refresh_from_payments(contract_numbers)
        return result

    @api.depends("bill_amount", "cash_amount")
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = (record.bill_amount or 0.0) + (record.cash_amount or 0.0)

    @api.depends("amount_total", "contract_amount")
    def _compute_payment_ratio_text(self):
        for record in self:
            record.payment_ratio_text = (
                f"{record.amount_total / record.contract_amount * 100:.2f}%" if record.contract_amount else False
            )
