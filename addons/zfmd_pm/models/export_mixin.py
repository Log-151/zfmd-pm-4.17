from io import BytesIO

import xlsxwriter
from odoo.exceptions import UserError

from odoo import fields, models


class ZfmdExportMixin(models.AbstractModel):
    _name = "zfmd.export.mixin"
    _description = "ZFMD 导出混入"

    def _action_export_excel_for(self, records=None):
        if records is None:
            model_name = self.env.context.get("active_model") or self.env.context.get("model")
            if not model_name:
                raise UserError("无法确定要导出的数据模型，请从具体台账页面重新导出。")
            records = self.env[model_name]

        active_ids = self.env.context.get("active_ids") or []
        if active_ids:
            records = records.browse(active_ids).exists()
        if not records:
            order = getattr(records, "_order", "id asc")
            active_domain = self.env.context.get("active_domain") or self.env.context.get("domain") or []
            records = records.search(active_domain, order=order)
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
            return float(value or 0.0)
        if field.type == "integer":
            return int(value or 0)
        if value is False or value is None:
            return ""
        return value

    def _build_export_xlsx_for(self, records, columns, file_label):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet_name = (file_label or "台账数据")[:31]
        worksheet = workbook.add_worksheet(sheet_name)

        header_format = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#D9EAF7",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        )
        text_format = workbook.add_format({"border": 1, "valign": "top", "align": "left", "text_wrap": True})
        center_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "center", "text_wrap": True})
        number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0.00"})
        integer_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "center", "num_format": "0"})

        for col_index, (_field_name, label, width) in enumerate(columns):
            worksheet.write(0, col_index, label, header_format)
            worksheet.set_column(col_index, col_index, width)

        for row_index, record in enumerate(records, start=1):
            for col_index, (field_name, _label, _width) in enumerate(columns):
                field = record._fields[field_name]
                value = self._format_export_value(record, field_name)
                if field.type in {"float", "monetary"}:
                    worksheet.write_number(row_index, col_index, float(value or 0.0), number_format)
                elif field.type == "integer":
                    worksheet.write_number(row_index, col_index, int(value or 0), integer_format)
                elif field.type == "boolean":
                    worksheet.write(row_index, col_index, value, center_format)
                elif field.type in {"date", "datetime"}:
                    worksheet.write(row_index, col_index, value, center_format)
                else:
                    worksheet.write(row_index, col_index, value, text_format)

        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, max(len(records), 1), len(columns) - 1)
        workbook.close()
        output.seek(0)
        return output.read(), f"{file_label}.xlsx"


class ZfmdContractExport(models.Model):
    _inherit = "zfmd.contract"

    def _export_file_label(self):
        return "合同台账"

    def _export_columns(self):
        return [
            ("display_order_text", "序号", 8),
            ("name", "合同编号", 24),
            ("contract_name", "合同名称", 28),
            ("customer_level_1", "一级公司", 18),
            ("customer_level_2", "二级公司", 18),
            ("customer_level_3", "三级公司", 18),
            ("partner_id", "客户", 24),
            ("site_id", "场站", 20),
            ("site_other_name", "其他名称", 18),
            ("site_category", "场站类别", 14),
            ("capacity_text", "场站容量", 14),
            ("contract_project_no", "项目编号", 18),
            ("province_name", "省区", 12),
            ("group_name", "集团", 14),
            ("product_line", "产品线", 16),
            ("project_content", "合同项目内容", 32),
            ("sale_manager", "签订合同销售经理", 16),
            ("sale_contact", "销售联系人", 14),
            ("contract_sign_date", "合同签订日期", 14),
            ("contract_sign_date_text", "合同签订日期原文", 18),
            ("archive_date", "合同存档日期", 14),
            ("archive_date_text", "合同存档日期原文", 18),
            ("archive_document_type", "合同存档原件/复印件", 20),
            ("archive_copy_count", "合同存档份数", 12),
            ("service_start_date", "服务收费起始时间", 16),
            ("service_start_date_text", "服务开始说明", 20),
            ("service_end_date", "服务收费终止时间", 16),
            ("service_end_date_text", "服务收费终止时间原文", 20),
            ("initial_fee", "初装费（元）", 14),
            ("service_fee", "预测服务费（元）", 16),
            ("amount_total", "合同总额（元）", 16),
            ("amount_untaxed", "不含税合同金额（元）", 20),
            ("exclude_sales_revenue", "不算销售收入", 14),
            ("exclude_sales_performance", "不算销售业绩", 14),
            ("bond_status", "保函开具情况", 14),
            ("special_contract", "特殊合同", 12),
            ("delivery_department", "交付部门", 14),
            ("project_manager", "项目经理", 14),
            ("handover_meeting_date", "合同交底会时间", 14),
            ("handover_meeting_date_text", "合同交底会时间原文", 20),
            ("third_party_interface_fee", "第三方接口费（元）", 18),
            ("start_application_no", "开工申请编号", 16),
            ("after_sale_no", "售后服务编号", 16),
            ("change_no", "合同变更号", 16),
            ("state", "状态", 10),
            ("note", "备注", 28),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(
            records, self._export_columns(), self._export_file_label()
        )


class ZfmdProjectStartExport(models.Model):
    _inherit = "zfmd.project.start"

    def _export_file_label(self):
        return "开工申请台账"

    def _export_columns(self):
        return [
            ("name", "开工申请编号", 18),
            ("display_contract_no", "合同编号", 22),
            ("contract_match_state", "合同匹配状态", 14),
            ("change_request_no", "开工变更申请表编号", 20),
            ("cancel_date", "开工申请取消时间", 14),
            ("has_cost", "是否发生成本费用", 16),
            ("cost_handling", "成本费用处理", 20),
            ("transfer_date", "开工申请流转时间", 14),
            ("province_name", "省区", 12),
            ("group_name", "集团", 14),
            ("site_name", "场站名称", 20),
            ("site_category", "场站类型", 14),
            ("product_line", "产品线", 16),
            ("project_content", "开工项目内容", 30),
            ("sale_manager", "销售经理", 14),
            ("handover_meeting_date", "项目交底会时间", 14),
            ("estimated_contract_amount", "预计合同金额（元）", 18),
            ("estimated_cost_amount", "预计成本（元）", 16),
            ("actual_contract_amount", "实际合同金额（元）", 18),
            ("delivery_department", "交付部门", 14),
            ("project_manager", "项目经理", 14),
            ("arrival_date", "到货时间", 14),
            ("acceptance_date", "验收时间", 14),
            ("state", "状态", 10),
            ("note", "备注", 28),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(
            records, self._export_columns(), self._export_file_label()
        )


class ZfmdServiceRecordExport(models.Model):
    _inherit = "zfmd.service.record"

    def _export_file_label(self):
        return "服务记录台账"

    def _export_columns(self):
        return [
            ("name", "服务记录编号", 18),
            ("display_contract_no", "合同编号", 22),
            ("contract_match_state", "合同匹配状态", 14),
            ("record_date", "记录日期", 14),
            ("site_name", "场站名称", 20),
            ("site_category", "场站类别", 14),
            ("service_type", "服务类别", 24),
            ("signing_sale_manager", "签订合同销售经理", 18),
            ("sale_manager", "销售经理", 14),
            ("province_name", "省区", 12),
            ("group_name", "集团", 14),
            ("product_line", "产品线", 16),
            ("service_content", "服务项目内容", 30),
            ("chargeable", "是否收费", 12),
            ("start_forecast_date", "开始预报时间", 14),
            ("formal_forecast_date", "正式预报时间", 14),
            ("service_end_date", "服务合同到期时间", 18),
            ("service_end_date_text", "服务合同到期时间说明", 22),
            ("expired_months", "超期时间（天）", 12),
            ("is_overdue", "是否超期", 12),
            ("expected_contract_amount", "预计签订服务合同金额（元）", 22),
            ("expected_contract_sign_date", "预计签订服务合同时间", 18),
            ("stop_forecast_date", "停止预报时间", 14),
            ("break_months", "中断时间（月）", 12),
            ("renewal_before_end_date", "续签前服务到期时间", 18),
            ("renewal_after_start_date", "续签后服务开始时间", 18),
            ("break_fee_handling", "中断期间服务费如何处理", 24),
            ("renewal_note", "续签服务合同情况说明", 24),
            ("note", "备注", 24),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(
            records, self._export_columns(), self._export_file_label()
        )


class ZfmdInvoiceRecordExport(models.Model):
    _inherit = "zfmd.invoice.record"

    def _export_file_label(self):
        return "开票登记台账"

    def _export_columns(self):
        return [
            ("name", "开票记录编号", 18),
            ("display_contract_no", "合同编号", 22),
            ("contract_match_state", "合同匹配状态", 14),
            ("invoice_date", "开票日期", 14),
            ("invoice_request_date", "申请开票日期", 16),
            ("invoice_partner_name", "开票客户", 24),
            ("province_name", "省区", 12),
            ("group_name", "集团", 14),
            ("site_name", "场站", 20),
            ("product_line", "产品线", 16),
            ("project_content", "项目内容", 30),
            ("sale_manager", "销售经理", 14),
            ("sale_contact", "销售联系人", 14),
            ("contract_amount", "合同金额（元）", 18),
            ("invoice_amount", "开票金额（元）", 18),
            ("tax_rate", "税率", 10),
            ("amount_untaxed", "不含税金额（元）", 18),
            ("promised_payment_date", "承诺回款日期", 16),
            ("promised_payment_note", "承诺回款说明", 24),
            ("promised_payment_amount", "承诺回款金额（元）", 20),
            ("actual_payment_date", "实际回款日期", 16),
            ("actual_payment_date_note", "实际回款日期说明", 24),
            ("actual_payment_amount", "实际回款（元）", 18),
            ("actual_payment_amount_note", "实际回款金额说明", 24),
            ("express_no", "发票快递单号", 18),
            ("cancel_date", "作废时间", 14),
            ("cancel_reason", "作废原因", 20),
            ("state", "状态", 10),
            ("note", "备注", 28),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(
            records, self._export_columns(), self._export_file_label()
        )


class ZfmdPaymentRecordExport(models.Model):
    _inherit = "zfmd.payment.record"

    def _export_file_label(self):
        return "回款登记台账"

    def _export_columns(self):
        return [
            ("display_contract_no", "合同编号", 22),
            ("contract_match_state", "合同匹配状态", 14),
            ("payment_date", "回款日期", 14),
            ("payer_name", "付款单位", 24),
            ("province_name", "省区", 12),
            ("group_name", "集团", 14),
            ("site_name", "场站", 20),
            ("product_line", "产品线", 16),
            ("project_content", "项目内容", 30),
            ("contract_amount", "合同金额（元）", 18),
            ("payment_type", "类型", 12),
            ("bill_amount", "汇票回款（元）", 18),
            ("cash_amount", "现金回款（元）", 18),
            ("amount_total", "回款金额（元）", 18),
            ("promised_payment_date", "承诺回款日期", 16),
            ("payment_ratio_text", "回款比例", 12),
            ("payment_item_name", "回款项名称", 18),
            ("sale_manager", "销售经理", 14),
            ("sale_contact", "销售联系人", 14),
            ("note", "备注", 28),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(
            records, self._export_columns(), self._export_file_label()
        )


class ZfmdReceivablePlanExport(models.Model):
    _inherit = "zfmd.receivable.plan"

    def _export_file_label(self):
        return "应收计划台账"

    def _export_columns(self):
        return [
            ("display_contract_no", "合同编号", 22),
            ("contract_match_state", "合同匹配状态", 14),
            ("sale_manager", "销售经理", 14),
            ("sale_contact", "销售联系人", 14),
            ("province_name", "省区", 12),
            ("group_name", "集团", 14),
            ("site_name", "场站名称", 20),
            ("product_line", "产品线", 16),
            ("project_content", "合同项目内容", 30),
            ("contract_amount", "合同金额（元）", 18),
            ("receivable_item_name", "应收款项名称", 18),
            ("receivable_amount", "应收金额（元）", 18),
            ("receivable_date", "应收时间", 14),
            ("receivable_date_text", "应收时间说明", 18),
            ("pending_progress_date", "待工程实施进展确定回款时间", 22),
            ("promised_entry_date", "承诺进入回款期时间", 18),
            ("promised_payment_date", "承诺回款时间", 16),
            ("promised_payment_amount", "承诺回款金额（元）", 20),
            ("actual_payment_date", "实际回款时间", 16),
            ("actual_payment_amount", "实际回款（元）", 18),
            ("overdue_months", "超期时间（月）", 12),
            ("late_payment_months_display", "迟后回款的月数", 14),
            ("actual_invoice_date", "实际开票时间", 16),
            ("actual_arrival_date", "实际到货时间", 16),
            ("arrival_voucher", "到货单", 10),
            ("actual_acceptance_date", "实际验收时间", 16),
            ("acceptance_voucher", "验收单", 10),
            ("payment_term", "合同约定付款条件", 24),
            ("state", "状态", 10),
            ("payment_category", "回款类别", 14),
            ("note", "备注", 24),
        ]

    def action_export_excel(self):
        return self.env["zfmd.export.mixin"]._action_export_excel_for(self)

    def _build_export_xlsx(self, records):
        return self.env["zfmd.export.mixin"]._build_export_xlsx_for(
            records, self._export_columns(), self._export_file_label()
        )
