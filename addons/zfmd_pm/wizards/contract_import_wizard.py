import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from .import_utils import ZfmdImportUtilityMixin, zfmd_extract_records


H_CONTRACT_NO = "合同编号"
H_CONTRACT_NAME = "合同名称"
H_CUSTOMER_NAME = "客户名称"
H_COMPANY_L1 = "一级公司"
H_COMPANY_L2 = "二级公司"
H_COMPANY_L3 = "三级公司"
H_SITE_NAME = "场站名称"
H_OTHER_NAME = "其他名称"
H_SITE_CATEGORY = "场站类别"
H_CAPACITY = "场站容量"
H_PROJECT_NO = "项目编号"
H_PROVINCE = "省（区）"
H_GROUP = "集团"
H_PRODUCT_LINE = "产品线"
H_PROJECT_CONTENT = "合同项目内容"
H_SALE_MANAGER = "签订合同销售经理"
H_SALE_CONTACT = "销售联系人"
H_SIGN_DATE = "合同签订日期"
H_ARCHIVE_DATE = "合同存档日期"
H_ARCHIVE_TYPE = "合同存档原件/复印件"
H_ARCHIVE_COUNT = "合同存档份数"
H_SERVICE_START = "服务收费起始时间"
H_SERVICE_END = "服务收费终止时间"
H_INITIAL_FEE = "初装费"
H_SERVICE_FEE = "预测服务费"
H_AMOUNT_TOTAL = "合同总额"
H_AMOUNT_UNTAXED = "不含税合同金额"
H_EXCLUDE_REVENUE = "不算销售收入"
H_EXCLUDE_PERFORMANCE = "不算销售业绩"
H_BOND_STATUS = "保函开具情况"
H_DELIVERY_DEPT = "交付部门"
H_PROJECT_MANAGER = "项目经理"
H_HANDOVER_DATE = "合同交底会时间"
H_INTERFACE_FEE = "第三方接口费"
H_START_NO = "开工申请编号"
H_AFTER_SALE_NO = "售后服务编号"
H_CHANGE_NO = "合同变更号"
H_NOTE = "备注"
SUMMARY_KEYWORDS = {"", "合计", "总计", "汇总", "小计"}


class ZfmdContractImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.contract.import.wizard"
    _description = "合同导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    unmatched_count = fields.Integer(string="未匹配合同数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    state = fields.Selection(
        [("draft", "待处理"), ("previewed", "已预览"), ("done", "已导入")],
        default="draft",
        string="状态",
        readonly=True,
    )

    def _ensure_partner(self, name, province=False, group_name=False):
        partner_name = self._clean_value(name)
        if not partner_name:
            return False
        partner_model = self.env["res.partner"].sudo()
        partner = partner_model.search([("name", "=", partner_name)], limit=1)
        vals = {
            "name": partner_name,
            "is_zfmd_customer": True,
            "province_name": self._clean_value(province) or False,
            "group_name": self._clean_value(group_name) or False,
            "company_type": "company",
        }
        if partner:
            partner.write(vals)
            return partner.id
        return partner_model.create(vals).id

    def _ensure_site(
        self,
        name,
        partner_id=False,
        province=False,
        group_name=False,
        site_category=False,
        other_name=False,
    ):
        site_name = self._clean_value(name)
        if not site_name:
            return False
        site_model = self.env["zfmd.site"].sudo()
        domain = [("name", "=", site_name)]
        if partner_id:
            domain.append(("partner_id", "=", partner_id))
        site = site_model.search(domain, limit=1)
        vals = {
            "name": site_name,
            "partner_id": partner_id or False,
            "province_name": self._clean_value(province) or False,
            "group_name": self._clean_value(group_name) or False,
            "site_category": self._clean_value(site_category) or False,
            "other_name": self._clean_value(other_name) or False,
        }
        if site:
            site.write(vals)
            return site.id
        return site_model.create(vals).id

    def _upsert_contract(self, vals):
        contract_model = self.env["zfmd.contract"].sudo()
        existing = False
        if vals.get("contract_key"):
            existing = contract_model.search([("contract_key", "=", vals["contract_key"])], limit=1)
        if not existing and vals.get("name"):
            existing = contract_model.search([("name", "=", vals["name"])], limit=1)
        if existing:
            existing.write(vals)
            return existing
        return contract_model.create(vals)

    def _is_summary_or_blank_row(self, row):
        contract_no = self._clean_value(row.get(H_CONTRACT_NO))
        customer_name = self._clean_value(row.get(H_CUSTOMER_NAME))
        contract_name = self._clean_value(row.get(H_CONTRACT_NAME))
        if self._norm_text(contract_no) in SUMMARY_KEYWORDS and self._norm_text(customer_name) in SUMMARY_KEYWORDS:
            return True
        return not any([contract_no, customer_name, contract_name])

    def _prepare_contract_vals(self, row):
        contract_no = self._clean_value(row.get(H_CONTRACT_NO))
        if not contract_no:
            return False
        partner_id = self._ensure_partner(row.get(H_CUSTOMER_NAME), row.get(H_PROVINCE), row.get(H_GROUP))
        site_id = self._ensure_site(
            row.get(H_SITE_NAME),
            partner_id,
            row.get(H_PROVINCE),
            row.get(H_GROUP),
            row.get(H_SITE_CATEGORY),
            row.get(H_OTHER_NAME),
        )
        return {
            "name": contract_no,
            "contract_key": self._extract_contract_key(contract_no),
            "contract_name": self._clean_value(row.get(H_CONTRACT_NAME)) or False,
            "customer_level_1": self._clean_value(row.get(H_COMPANY_L1)) or False,
            "customer_level_2": self._clean_value(row.get(H_COMPANY_L2)) or False,
            "customer_level_3": self._clean_value(row.get(H_COMPANY_L3)) or False,
            "partner_id": partner_id or False,
            "site_id": site_id or False,
            "site_other_name": self._clean_value(row.get(H_OTHER_NAME)) or False,
            "site_category": self._clean_value(row.get(H_SITE_CATEGORY)) or False,
            "capacity_text": self._clean_value(row.get(H_CAPACITY)) or False,
            "contract_project_no": self._clean_value(row.get(H_PROJECT_NO)) or False,
            "province_name": self._clean_value(row.get(H_PROVINCE)) or False,
            "group_name": self._clean_value(row.get(H_GROUP)) or False,
            "product_line": self._clean_value(row.get(H_PRODUCT_LINE)) or False,
            "project_content": self._clean_value(row.get(H_PROJECT_CONTENT)) or False,
            "sale_manager": self._clean_value(row.get(H_SALE_MANAGER)) or False,
            "sale_contact": self._clean_value(row.get(H_SALE_CONTACT)) or False,
            "contract_sign_date": self._parse_date(row.get(H_SIGN_DATE)),
            "archive_date": self._parse_date(row.get(H_ARCHIVE_DATE)),
            "archive_document_type": self._clean_value(row.get(H_ARCHIVE_TYPE)) or False,
            "archive_copy_count": int(self._parse_float(row.get(H_ARCHIVE_COUNT)) or 0),
            "service_start_date": self._parse_date(row.get(H_SERVICE_START)),
            "service_end_date": self._parse_date(row.get(H_SERVICE_END)),
            "initial_fee": self._parse_float(row.get(H_INITIAL_FEE)),
            "service_fee": self._parse_float(row.get(H_SERVICE_FEE)),
            "amount_total": self._parse_float(row.get(H_AMOUNT_TOTAL)),
            "amount_untaxed": self._parse_float(row.get(H_AMOUNT_UNTAXED)),
            "exclude_sales_revenue": self._clean_value(row.get(H_EXCLUDE_REVENUE)) or False,
            "exclude_sales_performance": self._clean_value(row.get(H_EXCLUDE_PERFORMANCE)) or False,
            "bond_status": self._clean_value(row.get(H_BOND_STATUS)) or False,
            "delivery_department": self._clean_value(row.get(H_DELIVERY_DEPT)) or False,
            "project_manager": self._clean_value(row.get(H_PROJECT_MANAGER)) or False,
            "handover_meeting_date": self._parse_date(row.get(H_HANDOVER_DATE)),
            "third_party_interface_fee": self._parse_float(row.get(H_INTERFACE_FEE)),
            "start_application_no": self._clean_value(row.get(H_START_NO)) or False,
            "after_sale_no": self._clean_value(row.get(H_AFTER_SALE_NO)) or False,
            "change_no": self._clean_value(row.get(H_CHANGE_NO)) or False,
            "note": self._clean_value(row.get(H_NOTE)) or False,
            "state": "running",
        }

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(_("请先上传 06 销售合同登记台账 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        raw_rows = zfmd_extract_records(file_bytes, [H_CONTRACT_NO, H_CUSTOMER_NAME])
        if not raw_rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 06 销售合同登记台账。"))
        rows = [row for row in raw_rows if not self._is_summary_or_blank_row(row)]
        if not rows:
            raise UserError(_("识别到的内容均为空白行或汇总行，没有可导入的合同记录。"))
        return rows

    def action_preview(self):
        self.ensure_one()
        rows = self._read_rows()

        issue_lines = []
        for index, row in enumerate(rows, start=1):
            if not self._clean_value(row.get(H_CONTRACT_NO)):
                issue_lines.append(f"第 {index} 行：缺少合同编号")
            elif not self._clean_value(row.get(H_CUSTOMER_NAME)):
                issue_lines.append(f"第 {index} 行：缺少客户名称")

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": 0,
                "unmatched_count": 0,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=0,
                    unmatched_count=0,
                    skipped_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "state": "previewed",
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "预览完成",
                "message": f"已识别 {len(rows)} 条合同记录。",
                "type": "success",
                "sticky": False,
            },
        }

    def action_import(self):
        self.ensure_one()
        rows = self._read_rows()

        imported_count = 0
        issue_lines = []
        for index, row in enumerate(rows, start=1):
            vals = self._prepare_contract_vals(row)
            if not vals:
                issue_lines.append(f"第 {index} 行：缺少合同编号，已跳过。")
                continue
            if not vals.get("partner_id"):
                issue_lines.append(f"第 {index} 行：缺少客户名称，已跳过。")
                continue
            vals["display_order"] = index
            self._upsert_contract(vals)
            imported_count += 1

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": imported_count,
                "unmatched_count": 0,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=imported_count,
                    unmatched_count=0,
                    skipped_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "state": "done",
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "导入完成",
                "message": f"成功导入 {imported_count} 条合同记录。",
                "type": "success" if not issue_lines else "warning",
                "sticky": bool(issue_lines),
            },
        }
