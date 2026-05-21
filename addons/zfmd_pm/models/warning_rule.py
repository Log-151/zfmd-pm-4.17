from odoo import fields, models


class ZfmdWarningRule(models.Model):
    _name = "zfmd.warning.rule"
    _description = "预警规则"
    _inherit = ["zfmd.soft.delete.mixin"]
    _order = "rule_type, warning_level, id"

    name = fields.Char(string="规则名称", required=True)
    active = fields.Boolean(string="是否启用", default=True)
    rule_type = fields.Selection(
        [
            ("invoice_payment_due", "预计回款逾期"),
            ("invoice_receivable_balance", "开票应收余额"),
            ("invoice_aging", "账龄超期"),
        ],
        string="规则类型",
        required=True,
    )
    threshold_days = fields.Integer(string="天数阈值", default=0)
    threshold_amount = fields.Float(string="金额阈值（元）", default=0.0)
    warning_level = fields.Selection(
        [
            ("info", "提示"),
            ("warning", "一般"),
            ("danger", "严重"),
        ],
        string="预警等级",
        required=True,
        default="warning",
    )
    show_on_dashboard = fields.Boolean(string="显示在全局概览", default=True)
    note = fields.Text(string="说明")
