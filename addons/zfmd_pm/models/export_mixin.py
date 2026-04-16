from io import BytesIO

import xlsxwriter

from odoo import fields, models


class ZfmdExportMixin(models.AbstractModel):
    _name = "zfmd.export.mixin"
    _description = "ZFMD Export Mixin"

    def _action_export_excel_for(self, records):
        active_ids = self.env.context.get("active_ids") or []
        if active_ids:
            records = records.browse(active_ids).exists()
        if not records:
            records = records.search([])
        return {
            "type": "ir.actions.act_url",
            "url": "/zfmd_pm/export_xlsx?model=%s&ids=%s" % (records._name, ",".join(map(str, records.ids))),
            "target": "self",
        }

    def _format_export_value(self, record, field_name):
        field = record._fields[field_name]
        value = record[field_name]
        if field.type == "many2one":
            return value.display_name or ""
        if field.type in {"one2many", "many2many"}:
            return ", ".join(value.mapped("display_name"))
        if field.type == "selection":
            return dict(field.selection).get(value, "") if value else ""
        if field.type == "boolean":
            return "是" if value else "否"
        if field.type == "date":
            return fields.Date.to_string(value) if value else ""
        if field.type == "datetime":
            return fields.Datetime.to_string(value) if value else ""
        if field.type in {"float", "monetary"}:
            return value or 0.0
        if value is False or value is None:
            return ""
        return value

    def _build_export_xlsx_for(self, records, columns, file_label):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("台账")

        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        cell_format = workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"})
        date_format = workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd", "valign": "top"})

        for col_index, (field_name, label) in enumerate(columns):
            worksheet.write(0, col_index, label, header_format)
            worksheet.set_column(col_index, col_index, 18)

        for row_index, record in enumerate(records, start=1):
            for col_index, (field_name, _label) in enumerate(columns):
                value = self._format_export_value(record, field_name)
                field = record._fields[field_name]
                if field.type in {"date", "datetime"} and value:
                    worksheet.write(row_index, col_index, value, date_format)
                else:
                    worksheet.write(row_index, col_index, value, cell_format)

        workbook.close()
        output.seek(0)
        filename = "%s.xlsx" % file_label
        return output.read(), filename


class ZfmdContractExport(models.Model):
    _inherit = "zfmd.contract"

    def _export_file_label(self):
        return "合同台账"

    def _export_columns(self):
        return [
            ("name", "合同编号"),
            ("contract_name", "合同名称"),
            ("partner_id", "客户"),
            ("site_id", "场站"),
            ("province_name", "省区"),
            ("group_name", "集团"),
            ("product_line", "产品线"),
            ("sale_manager", "销售经理"),
            ("sale_contact", "销售联系人"),
            ("contract_sign_date", "合同签订日期"),
            ("archive_date", "合同存档日期"),
            ("service_start_date", "服务开始日期"),
            ("service_end_date", "服务结束日期"),
            ("initial_fee", "初装费"),
            ("service_fee", "服务费"),
            ("amount_total", "合同总额"),
            ("amount_untaxed", "不含税金额"),
            ("delivery_department", "交付部门"),
            ("project_manager", "项目经理"),
            ("state", "状态"),
            ("project_content", "项目内容"),
            ("note", "备注"),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(records, self._export_columns(), self._export_file_label())


class ZfmdProjectStartExport(models.Model):
    _inherit = "zfmd.project.start"

    def _export_file_label(self):
        return "开工申请台账"

    def _export_columns(self):
        return [
            ("name", "开工申请编号"),
            ("contract_id", "对应合同"),
            ("transfer_date", "流转时间"),
            ("province_name", "省区"),
            ("group_name", "集团"),
            ("site_name", "场站名称"),
            ("product_line", "产品线"),
            ("sale_manager", "销售经理"),
            ("estimated_contract_amount", "预计合同金额"),
            ("actual_contract_amount", "实际合同金额"),
            ("delivery_department", "交付部门"),
            ("project_manager", "项目经理"),
            ("arrival_date", "到货时间"),
            ("acceptance_date", "验收时间"),
            ("state", "状态"),
            ("project_content", "项目内容"),
            ("note", "备注"),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(records, self._export_columns(), self._export_file_label())


class ZfmdServiceRecordExport(models.Model):
    _inherit = "zfmd.service.record"

    def _export_file_label(self):
        return "服务记录台账"

    def _export_columns(self):
        return [
            ("name", "服务记录编号"),
            ("contract_id", "对应合同"),
            ("site_id", "场站"),
            ("sale_manager", "销售经理"),
            ("province_name", "省区"),
            ("group_name", "集团"),
            ("product_line", "产品线"),
            ("service_content", "服务内容"),
            ("start_forecast_date", "开始预报时间"),
            ("formal_forecast_date", "正式预报时间"),
            ("service_end_date", "服务到期时间"),
            ("expected_contract_amount", "预计合同金额"),
            ("expected_contract_sign_date", "预计签约时间"),
            ("break_months", "断档月份"),
            ("is_overdue", "是否超期"),
            ("expired_months", "超期月数"),
            ("renewal_note", "续签情况"),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(records, self._export_columns(), self._export_file_label())


class ZfmdInvoiceRecordExport(models.Model):
    _inherit = "zfmd.invoice.record"

    def _export_file_label(self):
        return "开票登记台账"

    def _export_columns(self):
        return [
            ("name", "开票记录编号"),
            ("contract_id", "合同"),
            ("invoice_date", "开票日期"),
            ("invoice_partner_name", "开票单位"),
            ("province_name", "省区"),
            ("group_name", "集团"),
            ("site_name", "场站名称"),
            ("product_line", "产品线"),
            ("sale_manager", "销售经理"),
            ("sale_contact", "销售联系人"),
            ("contract_amount", "合同金额"),
            ("invoice_amount", "开票金额"),
            ("amount_untaxed", "不含税金额"),
            ("promised_payment_date", "承诺回款日期"),
            ("promised_payment_amount", "承诺回款金额"),
            ("actual_payment_date", "实际回款日期"),
            ("actual_payment_amount", "实际回款金额"),
            ("state", "状态"),
            ("project_content", "项目内容"),
            ("note", "备注"),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(records, self._export_columns(), self._export_file_label())


class ZfmdPaymentRecordExport(models.Model):
    _inherit = "zfmd.payment.record"

    def _export_file_label(self):
        return "回款登记台账"

    def _export_columns(self):
        return [
            ("name", "回款记录编号"),
            ("contract_id", "合同"),
            ("payment_date", "回款日期"),
            ("payer_name", "付款单位"),
            ("province_name", "省区"),
            ("group_name", "集团"),
            ("site_name", "场站名称"),
            ("product_line", "产品线"),
            ("payment_item_name", "款项名称"),
            ("bill_amount", "汇票回款"),
            ("cash_amount", "现金回款"),
            ("amount_total", "回款总额"),
            ("payment_ratio_text", "回款比例"),
            ("sale_manager", "销售经理"),
            ("sale_contact", "销售联系人"),
            ("project_content", "项目内容"),
            ("note", "备注"),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(records, self._export_columns(), self._export_file_label())


class ZfmdReceivablePlanExport(models.Model):
    _inherit = "zfmd.receivable.plan"

    def _export_file_label(self):
        return "应收计划台账"

    def _export_columns(self):
        return [
            ("name", "应收计划编号"),
            ("contract_id", "合同"),
            ("sale_manager", "销售经理"),
            ("sale_contact", "销售联系人"),
            ("province_name", "省区"),
            ("group_name", "集团"),
            ("site_name", "场站名称"),
            ("product_line", "产品线"),
            ("receivable_item_name", "应收款项"),
            ("contract_amount", "合同金额"),
            ("receivable_amount", "应收金额"),
            ("receivable_date", "应收时间"),
            ("promised_payment_date", "承诺回款时间"),
            ("promised_payment_amount", "承诺回款金额"),
            ("actual_invoice_date", "实际开票时间"),
            ("actual_arrival_date", "实际到货时间"),
            ("actual_acceptance_date", "实际验收时间"),
            ("actual_payment_date", "实际回款时间"),
            ("actual_payment_amount", "实际回款金额"),
            ("overdue_months", "逾期月数"),
            ("state", "状态"),
            ("project_content", "项目内容"),
            ("payment_term", "付款条件"),
            ("note", "备注"),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(records, self._export_columns(), self._export_file_label())
