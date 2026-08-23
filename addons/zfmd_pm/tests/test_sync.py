from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from odoo import api, fields


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

    def test_dashboard_overview_blocks_are_computed_on_read(self):
        dashboard_model = self.env["zfmd.dashboard"]
        for field_name in (
            "overview_metrics_html",
            "overview_warning_html",
            "overview_shortcuts_html",
        ):
            field = dashboard_model._fields[field_name]
            self.assertEqual(field.compute, "_compute_overview_blocks")
            self.assertFalse(field.store)

        dashboard = self.env.ref("zfmd_pm.zfmd_dashboard_overview")
        self.assertIn("合同数量", str(dashboard.overview_metrics_html))

    def test_dashboard_partial_invoice_progress_uses_net_invoice_less_payment_and_bad_debt(self):
        dashboard_model = self.env["zfmd.dashboard"]
        before_amount = dict(dashboard_model._build_progress_receivable_stats())[
            "②有合同已开具部分发票的实际进度应收款"
        ]
        self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 600,
                "invoice_situation": "partial",
            }
        )
        self.env["zfmd.payment.record"].create(
            {
                "contract_id": self.contract.id,
                "payment_date": fields.Date.today(),
                "cash_amount": 200,
            }
        )
        self.env["zfmd.receivable.plan"].create(
            {
                "contract_id": self.contract.id,
                "receivable_item_name": "测试坏账",
                "receivable_amount": 50,
                "exception_type": "bad_debt",
            }
        )

        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.invoice_status, "部分未开")
        self.assertEqual(project.invoiced_receivable_amount, 400)
        self.assertEqual(project.bad_debt_amount, 50)
        progress_rows = dict(dashboard_model._build_progress_receivable_stats())
        self.assertEqual(progress_rows["②有合同已开具部分发票的实际进度应收款"] - before_amount, 350)

    def test_all_bulk_import_wizards_mark_formal_rows_confirmed(self):
        wizard_models = (
            "zfmd.contract.import.wizard",
            "zfmd.invoice.import.wizard",
            "zfmd.payment.import.wizard",
            "zfmd.project.start.import.wizard",
            "zfmd.receivable.import.wizard",
            "zfmd.service.record.import.wizard",
            "zfmd.project.management.import.wizard",
            "zfmd.after.sale.service.import.wizard",
        )
        for model_name in wizard_models:
            vals = self.env[model_name]._confirmed_import_vals({"entry_state": "draft"})
            self.assertEqual(vals["entry_state"], "confirmed", model_name)
            self.assertTrue(vals["confirmed_at"], model_name)
            self.assertEqual(vals["confirmed_by"], self.env.user.id, model_name)

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

    def test_multi_segment_contract_numbers_remain_distinct(self):
        contract_model = self.env["zfmd.contract"]
        wizard = self.env["zfmd.contract.import.wizard"].create({})
        cache = wizard._build_caches()
        names = [
            "ZFMD/SD-23121-21140-1-SH",
            "ZFMD/SD-23121-21140-2-SH",
            "ZFMD/SD-23121-21140-3-SH",
        ]
        for index, name in enumerate(names, start=1):
            contract_key = wizard._extract_contract_key(name)
            wizard._upsert_contract_cached(
                {
                    **self._contract_required_vals(),
                    "name": name,
                    "contract_key": contract_key,
                    "partner_id": self.partner.id,
                    "site_id": self.site.id,
                    "product_line": f"产品线{index}",
                },
                cache,
            )

        contracts = contract_model.search([("name", "in", names)], order="name")
        self.assertEqual(len(contracts), 3)
        self.assertEqual(
            contracts.mapped("contract_key"),
            ["23121-21140-1", "23121-21140-2", "23121-21140-3"],
        )

    def test_formal_contract_import_confirms_existing_draft(self):
        draft_contract = (
            self.env["zfmd.contract"]
            .with_context(default_entry_state="draft")
            .create(
                {
                    "name": "ZFMD/SD-26890-SH",
                    "contract_key": "26890",
                    "partner_id": self.partner.id,
                    "site_id": self.site.id,
                    **self._contract_required_vals(),
                }
            )
        )
        self.assertEqual(draft_contract.entry_state, "draft")

        wizard = self.env["zfmd.contract.import.wizard"].create({})
        wizard._upsert_contract_cached(
            {
                "name": draft_contract.name,
                "contract_key": draft_contract.contract_key,
                "contract_name": "正式导入后自动确认",
            },
            wizard._build_caches(),
        )

        self.assertEqual(draft_contract.entry_state, "confirmed")
        self.assertTrue(draft_contract.confirmed_at)
        self.assertEqual(draft_contract.confirmed_by, self.env.user)
        self.assertEqual(
            self.env["zfmd.project.management"].search_count([("contract_id", "=", draft_contract.id)]),
            1,
        )

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
                "payment_category": "未回款",
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
        self.assertEqual(project.actual_progress_receivable_amount, 500)
        payment.unlink()
        self.assertEqual(project.paid_amount, 0)

    def test_project_invoice_status_uses_aggregate_confirmed_amount(self):
        self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 400,
                "invoice_situation": "partial",
            }
        )
        self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 600,
                "invoice_situation": "partial",
            }
        )

        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.invoice_status, "已开")
        self.assertEqual(project.invoiced_receivable_amount, 1000)

    def test_negative_invoice_amount_is_not_truncated(self):
        self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": -100,
                "invoice_situation": "none",
            }
        )

        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.invoiced_receivable_amount, -100)

        self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 120,
                "invoice_situation": "partial",
            }
        )
        self.assertEqual(project.invoiced_receivable_amount, 20)

    def test_receivable_balances_can_be_negative_after_advance_payment(self):
        self.env["zfmd.payment.record"].create(
            {
                "contract_id": self.contract.id,
                "payment_date": fields.Date.today(),
                "payment_item_name": "预收款",
                "cash_amount": 1200,
            }
        )

        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.total_receivable_amount, -200)
        self.assertEqual(project.actual_total_receivable_amount, -200)
        self.assertEqual(project.invoiced_receivable_amount, -1200)

    def test_actual_progress_receivable_uses_due_unpaid_plans(self):
        today = fields.Date.today()
        receivables = self.env["zfmd.receivable.plan"].create(
            [
                {
                    "contract_id": self.contract.id,
                    "receivable_item_name": "首款",
                    "receivable_amount": 300,
                    "receivable_date": fields.Date.subtract(today, days=1),
                    "payment_category": "未回款",
                },
                {
                    "contract_id": self.contract.id,
                    "receivable_item_name": "尾款",
                    "receivable_amount": 200,
                    "receivable_date": today,
                    "payment_category": "未回款",
                },
                {
                    "contract_id": self.contract.id,
                    "receivable_item_name": "未来款",
                    "receivable_amount": 400,
                    "receivable_date": fields.Date.add(today, days=1),
                    "payment_category": "未回款",
                },
                {
                    "contract_id": self.contract.id,
                    "receivable_item_name": "已收款",
                    "receivable_amount": 100,
                    "receivable_date": today,
                    "payment_category": "已回款",
                },
            ]
        )
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(project.progress_receivable_item_name, "首款；尾款")
        self.assertEqual(project.actual_progress_receivable_amount, 500)

        receivables[0].with_context(skip_entry_confirmation_stage=True).write({"payment_category": "已回款"})
        self.assertEqual(project.progress_receivable_item_name, "尾款")
        self.assertEqual(project.actual_progress_receivable_amount, 200)

        receivables[1].with_context(skip_entry_confirmation_stage=True).write({"payment_category": "已回款"})
        self.assertFalse(project.progress_receivable_item_name)
        self.assertEqual(project.actual_progress_receivable_amount, 0)

    def test_actual_total_receivable_subtracts_payments_and_bad_debt(self):
        payment = self.env["zfmd.payment.record"].create(
            {
                "contract_id": self.contract.id,
                "payment_date": fields.Date.today(),
                "cash_amount": 200,
            }
        )
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        project.write({"bad_debt_amount": 150})
        self.assertTrue(project.bad_debt_manual)
        project.action_confirm_entry()
        self.assertEqual(project.paid_amount, 200)
        self.assertEqual(project.bad_debt_amount, 150)
        self.assertEqual(project.actual_total_receivable_amount, 650)

        self.env["zfmd.receivable.plan"].create(
            {
                "contract_id": self.contract.id,
                "receivable_item_name": "坏账款",
                "receivable_amount": 300,
                "receivable_date": fields.Date.today(),
                "exception_type": "bad_debt",
            }
        )
        self.env["zfmd.sync.engine"].rebuild_projects_from_ledgers()
        self.assertEqual(project.bad_debt_amount, 150)
        self.assertEqual(project.actual_total_receivable_amount, 650)

        project.write({"bad_debt_manual": False})
        project.action_confirm_entry()
        self.assertEqual(project.bad_debt_amount, 300)
        self.assertEqual(project.actual_total_receivable_amount, 500)

        payment.unlink()
        self.assertEqual(project.actual_total_receivable_amount, 700)

    def test_formal_invoice_import_is_confirmed(self):
        wizard = self.env["zfmd.invoice.import.wizard"].with_context(default_entry_state="draft").create({})
        invoice = wizard._create_invoice(
            {
                "contract_id": self.contract.id,
                "invoice_date": fields.Date.today(),
                "invoice_amount": 1000,
                "import_source_row": 3,
            }
        )
        self.assertEqual(invoice.entry_state, "confirmed")
        self.assertTrue(invoice.confirmed_at)

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

    def test_views_hide_invoiced_amount_and_project_start_orders_by_number(self):
        receivable_view = self.env.ref("zfmd_pm.view_zfmd_receivable_plan_tree").arch_db
        project_start_view = self.env.ref("zfmd_pm.view_zfmd_project_start_tree").arch_db

        self.assertNotIn('name="invoiced_amount"', receivable_view)
        self.assertIn('default_order="name desc, id desc"', project_start_view)
        self.assertEqual(self.env["zfmd.project.start"]._order, "name desc, id desc")

    def test_invoice_can_fully_invoice_multiple_receivable_plans(self):
        receivables = self.env["zfmd.receivable.plan"].create(
            [
                {
                    "contract_id": self.contract.id,
                    "receivable_item_name": "到货款",
                    "receivable_amount": 300,
                },
                {
                    "contract_id": self.contract.id,
                    "receivable_item_name": "验收款",
                    "receivable_amount": 700,
                },
            ]
        )
        invoice_date = fields.Date.from_string("2026-07-13")
        invoice = self.env["zfmd.invoice.record"].create(
            {
                "contract_id": self.contract.id,
                "invoice_date": invoice_date,
                "invoice_amount": 500,
                "receivable_plan_ids": [(6, 0, receivables.ids)],
            }
        )

        self.assertEqual(invoice.receivable_plan_ids, receivables)
        self.assertEqual(receivables.mapped("actual_invoice_date"), [invoice_date, invoice_date])
        self.assertEqual(receivables[0].invoiced_amount, 300)
        self.assertEqual(receivables[1].invoiced_amount, 700)

        invoice.with_context(skip_entry_confirmation_stage=True).write({"state": "cancel"})

        self.assertFalse(any(receivables.mapped("actual_invoice_date")))
        self.assertEqual(receivables.mapped("invoiced_amount"), [0.0, 0.0])

    def test_invoice_rejects_receivable_plan_from_another_contract(self):
        other_contract = self.env["zfmd.contract"].create(
            {
                "name": "ZFMD/SD-99995-SH",
                "partner_id": self.partner.id,
                "site_id": self.site.id,
                **self._contract_required_vals(),
            }
        )
        other_receivable = self.env["zfmd.receivable.plan"].create(
            {
                "contract_id": other_contract.id,
                "receivable_item_name": "其他合同应收",
                "receivable_amount": 100,
            }
        )

        with self.assertRaises(ValidationError):
            self.env["zfmd.invoice.record"].create(
                {
                    "contract_id": self.contract.id,
                    "invoice_date": fields.Date.today(),
                    "invoice_amount": 100,
                    "receivable_plan_ids": [(6, 0, other_receivable.ids)],
                }
            )

    def test_service_end_date_uses_site_and_province(self):
        early_contract = self.env["zfmd.contract"].create(
            {
                "name": "ZFMD/SD-99994-SH",
                "partner_id": self.partner.id,
                "site_id": self.site.id,
                "service_end_date": fields.Date.from_string("2026-06-30"),
                **self._contract_required_vals(),
            }
        )
        late_contract = self.env["zfmd.contract"].create(
            {
                "name": "ZFMD/SD-99993-SH",
                "partner_id": self.partner.id,
                "site_id": self.site.id,
                "service_end_date": fields.Date.from_string("2026-12-31"),
                **self._contract_required_vals(),
            }
        )
        other_partner = self.env["res.partner"].create({"name": "跨省同名场站客户"})
        other_site = self.env["zfmd.site"].create(
            {"name": self.site.name, "partner_id": other_partner.id, "province_name": "其他省区"}
        )
        self.env["zfmd.contract"].create(
            {
                "name": "ZFMD/SD-99992-SH",
                "partner_id": other_partner.id,
                "site_id": other_site.id,
                "service_end_date": fields.Date.from_string("2027-12-31"),
                **{**self._contract_required_vals(), "province_name": "其他省区"},
            }
        )

        service = self.env["zfmd.service.record"].create(
            {
                "site_name": self.site.name,
                "province_name": "测试省区",
            }
        )
        self.assertEqual(service.service_end_date, fields.Date.from_string("2026-12-31"))
        self.assertEqual(service.contract_id, late_contract)

        late_contract.write({"service_end_date": fields.Date.from_string("2027-03-31")})
        self.assertEqual(late_contract.entry_state, "draft")
        self.assertEqual(service.service_end_date, early_contract.service_end_date)

        late_contract.action_confirm_entry()
        self.assertEqual(service.service_end_date, fields.Date.from_string("2027-03-31"))
        self.assertEqual(service.contract_id, late_contract)

    def test_service_end_date_keeps_imported_value_without_matching_contract(self):
        imported_date = fields.Date.from_string("2028-05-31")
        service = self.env["zfmd.service.record"].create(
            {
                "site_name": "未匹配场站",
                "province_name": "未匹配省份",
                "service_end_date": imported_date,
            }
        )
        self.assertEqual(service.imported_service_end_date, imported_date)
        self.assertEqual(service.service_end_date, imported_date)
        self.assertFalse(service.contract_id)

    def test_rebuild_projects_recreates_soft_deleted_project(self):
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        project.unlink()
        self.assertFalse(self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)]))

        action = api.call_kw(
            self.env["zfmd.project.management"],
            "action_rebuild_projects_from_ledgers",
            [[]],
            {},
        )

        rebuilt = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        self.assertEqual(len(rebuilt), 1)
        self.assertNotEqual(rebuilt.id, project.id)
        self.assertEqual(action["params"]["title"], "项目管理已重新生成")

    def test_import_result_does_not_truncate_issue_lines(self):
        wizard = self.env["zfmd.service.record.import.wizard"].new({})
        issue_lines = [f"问题 {index}" for index in range(1, 76)]
        result_html = wizard._build_import_result_html(
            title="预览",
            total_count=75,
            issue_count=75,
            issue_lines=issue_lines,
            mode="preview",
        )
        self.assertIn("问题 75", result_html)
        self.assertNotIn("仅展示前 50 条", result_html)

    def test_export_action_uses_short_token_url(self):
        project = self.env["zfmd.project.management"].search([("contract_id", "=", self.contract.id)])
        action = project.action_export_excel()
        self.assertIn("/zfmd_pm/export_xlsx?token=", action["url"])
        self.assertNotIn("ids=", action["url"])
        self.assertLess(len(action["url"]), 160)

    def test_obsolete_progress_receivable_column_is_removed(self):
        project_model = self.env["zfmd.project.management"]
        self.assertNotIn("progress_receivable_amount", project_model._fields)
        export_fields = [field_name for field_name, _label, _width in project_model._export_columns()]
        self.assertNotIn("progress_receivable_amount", export_fields)

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
        self.assertEqual(project.invoice_status, "未开")
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
