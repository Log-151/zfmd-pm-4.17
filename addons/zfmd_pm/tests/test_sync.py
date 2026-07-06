from odoo.tests.common import TransactionCase

from odoo import fields


class TestZfmdSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "联动测试客户", "customer_code": "C-001"})
        cls.site = cls.env["zfmd.site"].create(
            {"name": "联动测试场站", "partner_id": cls.partner.id, "site_category": "wind"}
        )
        cls.contract = cls.env["zfmd.contract"].create(
            {
                "name": "ZFMD/SD-99999-SH",
                "partner_id": cls.partner.id,
                "site_id": cls.site.id,
                "amount_total": 1000,
                **cls._contract_required_vals(),
            }
        )
        cls.manager_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "联动测试业务用户",
                    "login": "zfmd-sync-test-manager",
                    "groups_id": [(6, 0, [cls.env.ref("zfmd_pm.group_zfmd_manager").id])],
                    "company_id": cls.env.company.id,
                    "company_ids": [(6, 0, [cls.env.company.id])],
                }
            )
        )

    @classmethod
    def _contract_required_vals(cls):
        return {
            "contract_name": "联动测试合同",
            "province_name": "测试省区",
            "group_name": "测试集团",
            "product_line": "测试产品线",
            "project_content": "测试项目内容",
            "sale_manager": "测试销售经理",
            "sale_contact": "测试销售联系人",
            "amount_total": 1000,
            "amount_untaxed": 900,
            "archive_date": fields.Date.today(),
            "initial_fee": 0,
            "service_fee": 0,
            "delivery_department": "测试交付部门",
        }

    def test_contract_creates_project_and_syncs_customer_code(self):
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(len(project), 1)
        self.assertEqual(project.customer_code, "C-001")
        self.assertEqual(self.contract.project_management_count, 1)
        self.assertEqual(
            self.contract.action_open_project_management()["domain"],
            [("contract_id", "=", self.contract.id)],
        )
        self.contract.write({"contract_project_no": "P-001"})
        self.assertEqual(self.contract.entry_state, "draft")
        self.assertFalse(project.contract_project_no)
        self.contract.action_confirm_entry()
        self.assertEqual(project.contract_project_no, "P-001")

    def test_contract_core_number_builds_full_contract_number(self):
        contract = self.env["zfmd.contract"].create(
            {
                "contract_key": "26888-1",
                "partner_id": self.partner.id,
                "site_id": self.site.id,
                **self._contract_required_vals(),
            }
        )
        self.assertEqual(contract.name, "ZFMD/SD-26888-1-SH")
        contract.write({"contract_key": "26889"})
        self.assertEqual(contract.name, "ZFMD/SD-26889-SH")
        self.assertEqual(contract.contract_key, "26889")

    def test_payment_invoice_receivable_and_project_sync(self):
        invoice = self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 500,
                "invoice_situation": "partial",
            }
        )
        receivable = self.env["zfmd.receivable.plan"].create(
            {
                "contract_id": self.contract.id,
                "receivable_item_name": "验收款",
                "receivable_amount": 500,
                "receivable_date": fields.Date.today(),
                "actual_arrival_date": fields.Date.today(),
            }
        )
        payment = self.env["zfmd.payment.record"].create(
            {
                "contract_id": self.contract.id,
                "payment_date": fields.Date.today(),
                "payment_item_name": "验收款",
                "cash_amount": 200,
            }
        )
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(payment.payment_ratio_text, "20.00%")
        self.assertEqual(receivable.actual_payment_amount, 200)
        self.assertEqual(invoice.actual_payment_amount, 200)
        self.assertEqual(project.paid_amount, 200)
        self.assertEqual(project.invoice_status, "部分未开")
        self.assertEqual(project.arrival_voucher, "有")
        self.assertEqual(project.progress_receivable_item_name, "验收款")
        self.assertEqual(project.progress_receivable_amount, 300)
        payment.unlink()
        self.assertEqual(project.paid_amount, 0)

    def test_invoice_tax_calculation(self):
        invoice = self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_amount": 113,
                "tax_rate": "13%",
            }
        )
        self.assertAlmostEqual(invoice.amount_untaxed, 100, places=2)
        self.assertAlmostEqual(invoice.tax_amount, 13, places=2)
        self.assertFalse(invoice.tax_amount_warning)

    def test_manual_customer_code_is_preserved(self):
        self.contract.write({"customer_code": "MANUAL"})
        self.partner.write({"customer_code": "C-002"})
        self.assertEqual(self.contract.customer_code, "MANUAL")

    def test_project_updates_contract_scalar_fields(self):
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        project.write({"contract_sale_manager": "测试经理"})
        self.assertEqual(project.entry_state, "draft")
        self.assertNotEqual(self.contract.sale_manager, "测试经理")
        project.action_confirm_entry()
        self.assertEqual(self.contract.sale_manager, "测试经理")

    def test_manual_edit_requires_confirmation_before_sync(self):
        self.assertEqual(self.contract.entry_state, "confirmed")
        self.contract.write({"sale_manager": "待确认经理"})
        self.assertEqual(self.contract.entry_state, "draft")
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertNotEqual(project.contract_sale_manager, "待确认经理")

        self.contract.action_confirm_entry()

        self.assertEqual(self.contract.entry_state, "confirmed")
        self.assertEqual(project.contract_sale_manager, "待确认经理")

    def test_acceptance_without_service_dates_is_done(self):
        self.env["zfmd.receivable.plan"].create(
            {
                "contract_id": self.contract.id,
                "receivable_item_name": "验收款",
                "actual_acceptance_date": fields.Date.today(),
            }
        )
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.contract_execution_status, "已完工")

    def test_invoice_status_falls_back_to_invoice_total(self):
        self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 1000,
            }
        )
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.invoice_status, "已开")

    def test_manager_can_use_business_helper_fields(self):
        contract_model = self.env["zfmd.contract"].with_user(self.manager_user)
        _partner_id, partner_name = self.env["res.partner"].with_user(self.manager_user).name_create("业务用户新建客户")
        self.assertEqual(partner_name, "业务用户新建客户")

        draft_contract = contract_model.new(
            {
                "name": "ZFMD/SD-99998-SH",
                "partner_id": self.partner.id,
            }
        )
        draft_contract._onchange_partner_id()
        self.assertEqual(draft_contract.customer_code, "C-001")

        contract = contract_model.create(
            {
                "name": "ZFMD/SD-99998-SH",
                "partner_id": self.partner.id,
                "site_id": self.site.id,
                **self._contract_required_vals(),
                "contract_sign_date_text": "待确认",
            }
        )
        self.assertFalse(contract.customer_code_manual)
        export_content, _filename = contract._build_export_xlsx(contract)
        self.assertTrue(export_content)

        invoice_model = self.env["zfmd.invoice.record"].with_user(self.manager_user)
        draft_invoice = invoice_model.new({"invoice_amount": 113, "tax_rate": "13%"})
        draft_invoice._onchange_invoice_tax()
        self.assertAlmostEqual(draft_invoice.amount_untaxed, 100, places=2)
        invoice = invoice_model.create(
            {
                "contract_id": contract.id,
                "invoice_amount": 113,
                "tax_rate": "13%",
                "import_source_file": "test.xlsx",
            }
        )
        self.assertFalse(invoice.amount_untaxed_manual)

        receivable = (
            self.env["zfmd.receivable.plan"]
            .with_user(self.manager_user)
            .create(
                {
                    "contract_id": contract.id,
                    "receivable_item_name": "测试应收",
                    "actual_invoice_date": fields.Date.today(),
                }
            )
        )
        self.assertTrue(receivable.actual_invoice_manual)

        self.env["zfmd.project.start"].with_user(self.manager_user).create(
            {
                "name": "START-PERMISSION-CHECK",
                "contract_id": contract.id,
                "raw_import_data": "{}",
            }
        )
        service = (
            self.env["zfmd.service.record"]
            .with_user(self.manager_user)
            .create(
                {
                    "name": "SERVICE-PERMISSION-CHECK",
                    "contract_id": contract.id,
                    "raw_import_data": "{}",
                }
            )
        )
        self.assertEqual(service.contract_match_state, "matched")

    def test_draft_entry_only_syncs_after_confirmation(self):
        draft_contract = self.env["zfmd.contract"].create(
            {
                "name": "ZFMD/SD-99997-SH",
                "partner_id": self.partner.id,
                "site_id": self.site.id,
                "entry_state": "draft",
                **self._contract_required_vals(),
                "amount_total": 2000,
            }
        )
        project_model = self.env["zfmd.project.management"]
        self.assertFalse(project_model.search([("contract_id", "=", draft_contract.id)]))

        draft_contract.action_confirm_entry()
        project = project_model.search([("contract_id", "=", draft_contract.id)])
        self.assertEqual(draft_contract.entry_state, "confirmed")
        self.assertEqual(project.entry_state, "confirmed")

        draft_invoice = self.env["zfmd.invoice.record"].create(
            {
                "contract_id": draft_contract.id,
                "invoice_amount": 2000,
                "entry_state": "draft",
            }
        )
        self.assertFalse(project.invoice_status)
        self.assertEqual(draft_contract.invoice_record_count, 0)
        draft_invoice.action_confirm_entry()
        self.assertEqual(project.invoice_status, "已开")
        self.assertEqual(draft_contract.invoice_record_count, 1)

    def test_manager_can_soft_delete_contract_and_linked_project(self):
        contract = (
            self.env["zfmd.contract"]
            .with_user(self.manager_user)
            .create(
                {
                    "name": "ZFMD/SD-99996-SH",
                    "partner_id": self.partner.id,
                    "site_id": self.site.id,
                    **self._contract_required_vals(),
                }
            )
        )
        project = self.env["zfmd.project.management"].search([("contract_id", "=", contract.id)])
        self.assertTrue(project)

        contract.unlink()

        deleted_contract = self.env["zfmd.contract"].with_context(include_deleted=True).browse(contract.id)
        deleted_project = self.env["zfmd.project.management"].with_context(include_deleted=True).browse(project.id)
        self.assertTrue(deleted_contract.is_deleted)
        self.assertEqual(deleted_contract.deleted_by, self.manager_user)
        self.assertTrue(deleted_project.is_deleted)
