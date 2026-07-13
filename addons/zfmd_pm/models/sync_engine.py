from odoo import fields, models


class ZfmdSyncEngine(models.AbstractModel):
    _name = "zfmd.sync.engine"
    _description = "ZFMD 跨模块联动引擎"

    def _contract_numbers(self, records):
        return {
            value.strip() for value in records.mapped("display_contract_no") if isinstance(value, str) and value.strip()
        }

    def _records_by_contract_numbers(self, model_name, contract_numbers):
        contract_numbers = {value for value in contract_numbers if value}
        if not contract_numbers:
            return self.env[model_name].browse()
        return self.env[model_name].search(
            [
                ("entry_state", "=", "confirmed"),
                "|",
                ("contract_id.name", "in", list(contract_numbers)),
                ("source_contract_no", "in", list(contract_numbers)),
            ]
        )

    def _projects_by_contract_numbers(self, contract_numbers):
        contract_numbers = {value for value in contract_numbers if value}
        if not contract_numbers:
            return self.env["zfmd.project.management"].browse()
        return self.env["zfmd.project.management"].search(
            [
                ("entry_state", "=", "confirmed"),
                "|",
                ("contract_id.name", "in", list(contract_numbers)),
                ("name", "in", list(contract_numbers)),
            ]
        )

    def _contract_to_project_vals(self, contract):
        return {
            "name": contract.name or False,
            "contract_id": contract.id,
            "contract_key": contract.contract_key or False,
            "contract_match_state": "matched",
            "contract_project_no": contract.contract_project_no or False,
            "contract_sign_date": contract.contract_sign_date or False,
            "customer_level_1": contract.customer_level_1 or False,
            "customer_level_2": contract.customer_level_2 or False,
            "customer_level_3": contract.customer_level_3 or False,
            "customer_name": contract.partner_id.name or False,
            "customer_code": contract.customer_code or contract.partner_id.customer_code or False,
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "site_name": contract.site_id.name or False,
            "product_line": contract.product_line or False,
            "project_content": contract.project_content or False,
            "contract_sale_manager": contract.sale_manager or False,
            "sale_contact": contract.sale_contact or False,
            "service_start_date": contract.service_start_date or False,
            "service_end_date": contract.service_end_date or False,
            "delivery_department": contract.delivery_department or False,
            "project_manager": contract.project_manager or False,
            "initial_fee": contract.initial_fee or 0.0,
            "forecast_service_fee": contract.service_fee or 0.0,
            "contract_amount": contract.amount_total or 0.0,
        }

    def refresh_service_records_by_keys(self, service_keys):
        service_model = self.env["zfmd.service.record"].sudo()
        normalized_keys = {
            ((site_name or "").strip(), (province_name or "").strip())
            for site_name, province_name in service_keys
            if (site_name or "").strip() and (province_name or "").strip()
        }
        for site_name, province_name in normalized_keys:
            services = service_model.search(
                [
                    ("site_name", "=", site_name),
                    ("province_name", "=", province_name),
                ]
            )
            services._refresh_service_end_date_from_contracts()
        return True

    def sync_contracts(self, contracts, previous_service_keys=None):
        service_keys = set(previous_service_keys or [])
        service_keys.update(
            (contract.site_id.name, contract.province_name)
            for contract in contracts
            if contract.site_id.name and contract.province_name
        )
        confirmed_contracts = contracts.filtered(lambda record: record.entry_state == "confirmed")
        project_model = self.env["zfmd.project.management"].sudo().with_context(skip_zfmd_sync=True)
        for contract in confirmed_contracts:
            vals = self._contract_to_project_vals(contract)
            projects = project_model.search(
                [
                    "|",
                    ("contract_id", "=", contract.id),
                    "&",
                    ("name", "=", contract.name),
                    ("site_name", "=", contract.site_id.name or False),
                ]
            )
            if projects:
                projects.write(vals)
            elif not contract.is_deleted:
                project_model.create(vals)
        self.refresh_service_records_by_keys(service_keys)
        self.refresh_projects({contract.name for contract in confirmed_contracts})

    def sync_projects_to_contracts(self, projects, changed_fields):
        projects = projects.filtered(lambda record: record.entry_state == "confirmed")
        if not projects:
            return
        field_map = {
            "name": "name",
            "contract_project_no": "contract_project_no",
            "contract_sign_date": "contract_sign_date",
            "province_name": "province_name",
            "group_name": "group_name",
            "product_line": "product_line",
            "project_content": "project_content",
            "contract_sale_manager": "sale_manager",
            "sale_contact": "sale_contact",
            "service_start_date": "service_start_date",
            "service_end_date": "service_end_date",
            "delivery_department": "delivery_department",
            "project_manager": "project_manager",
            "initial_fee": "initial_fee",
            "forecast_service_fee": "service_fee",
            "contract_amount": "amount_total",
        }
        sync_fields = set(changed_fields) & set(field_map)
        if not sync_fields and not {"customer_name", "site_name"} & set(changed_fields):
            return
        for project in projects.filtered(
            lambda record: record.contract_id and record.contract_id.entry_state == "confirmed"
        ):
            vals = {field_map[name]: project[name] for name in sync_fields}
            if "customer_name" in changed_fields and project.customer_name:
                partner = self.env["res.partner"].search([("name", "=", project.customer_name)], limit=1)
                if partner:
                    vals["partner_id"] = partner.id
            if "site_name" in changed_fields and project.site_name:
                site_domain = [("name", "=", project.site_name)]
                if vals.get("partner_id") or project.contract_id.partner_id:
                    site_domain.append(
                        (
                            "partner_id",
                            "=",
                            vals.get("partner_id") or project.contract_id.partner_id.id,
                        )
                    )
                site = self.env["zfmd.site"].search(site_domain, limit=1)
                if site:
                    vals["site_id"] = site.id
            project.contract_id.sudo().with_context(skip_zfmd_sync=True).write(vals)

    def refresh_from_payments(self, contract_numbers):
        self._refresh_invoice_payments(contract_numbers)
        self._refresh_receivable_payments(contract_numbers)
        self.refresh_projects(contract_numbers)

    def refresh_from_invoices(self, contract_numbers):
        invoices = self._records_by_contract_numbers("zfmd.invoice.record", contract_numbers).filtered(
            lambda record: record.state != "cancel"
        )
        receivables = self._records_by_contract_numbers("zfmd.receivable.plan", contract_numbers)
        for receivable in receivables:
            matches = invoices.filtered(
                lambda invoice: receivable in invoice.receivable_plan_ids and invoice.invoice_date
            ).sorted(key=lambda invoice: (invoice.invoice_date, invoice.id), reverse=True)
            if not matches and receivable.actual_invoice_manual:
                continue
            receivable.with_context(skip_zfmd_sync=True, auto_link_sync=True).write(
                {"actual_invoice_date": matches[:1].invoice_date if matches else False}
            )
        self.refresh_projects(contract_numbers)

    def refresh_from_receivables(self, contract_numbers):
        self.refresh_projects(contract_numbers)

    def _refresh_invoice_payments(self, contract_numbers):
        invoices = self._records_by_contract_numbers("zfmd.invoice.record", contract_numbers).filtered(
            lambda record: record.state != "cancel"
        )
        payments = self._records_by_contract_numbers("zfmd.payment.record", contract_numbers).filtered("active")
        for invoice in invoices:
            if invoice.actual_payment_manual:
                continue
            matches = payments.filtered(
                lambda payment: payment.display_contract_no == invoice.display_contract_no
                and payment.payer_name
                and payment.payer_name == invoice.invoice_partner_name
            ).sorted(
                key=lambda payment: (
                    payment.payment_date or fields.Date.from_string("1900-01-01"),
                    payment.id,
                ),
                reverse=True,
            )
            if not matches:
                continue
            dates = [fields.Date.to_string(payment.payment_date) for payment in matches if payment.payment_date]
            amounts = [f"{payment.amount_total:.2f}" for payment in matches]
            invoice.with_context(skip_zfmd_sync=True, auto_link_sync=True).write(
                {
                    "actual_payment_date": matches[0].payment_date,
                    "actual_payment_amount": sum(matches.mapped("amount_total")),
                    "actual_payment_date_note": ("; ".join(dates) if len(matches) > 1 else False),
                    "actual_payment_amount_note": ("; ".join(amounts) if len(matches) > 1 else False),
                }
            )

    def _refresh_receivable_payments(self, contract_numbers):
        receivables = self._records_by_contract_numbers("zfmd.receivable.plan", contract_numbers)
        payments = self._records_by_contract_numbers("zfmd.payment.record", contract_numbers).filtered("active")
        for receivable in receivables:
            if receivable.actual_payment_manual:
                continue
            matches = payments.filtered(
                lambda payment: payment.display_contract_no == receivable.display_contract_no
                and payment.site_name
                and payment.site_name == receivable.site_name
                and payment.payment_item_name
                and payment.payment_item_name == receivable.receivable_item_name
            ).sorted(
                key=lambda payment: (
                    payment.payment_date or fields.Date.from_string("1900-01-01"),
                    payment.id,
                ),
                reverse=True,
            )
            if not matches:
                continue
            receivable.with_context(skip_zfmd_sync=True, auto_link_sync=True).write(
                {
                    "actual_payment_date": matches[0].payment_date,
                    "actual_payment_amount": matches[0].amount_total,
                }
            )

    def refresh_projects(self, contract_numbers):
        for project in self._projects_by_contract_numbers(contract_numbers):
            self._refresh_project(project)

    def _refresh_project(self, project):
        contract_no = project.contract_id.name or project.name
        invoices = self._records_by_contract_numbers("zfmd.invoice.record", {contract_no}).filtered(
            lambda record: record.state != "cancel"
        )
        payments = self._records_by_contract_numbers("zfmd.payment.record", {contract_no}).filtered("active")
        receivables = self._records_by_contract_numbers("zfmd.receivable.plan", {contract_no}).filtered(
            lambda record: not record.is_summary_line
        )
        site_receivables = receivables.filtered(
            lambda record: project.site_name and record.site_name == project.site_name
        )
        customer_invoices = invoices.filtered(
            lambda record: project.customer_name and record.invoice_partner_name == project.customer_name
        )
        dated_invoices = customer_invoices.filtered("invoice_date").sorted(
            key=lambda record: (record.invoice_date, record.id), reverse=True
        )
        latest_invoice = invoices.sorted(
            key=lambda record: (
                record.invoice_date or fields.Date.from_string("1900-01-01"),
                record.id,
            ),
            reverse=True,
        )[:1]
        paid_amount = sum(payments.mapped("amount_total"))
        invoice_amount = sum(invoices.mapped("invoice_amount"))
        cancel_amount = sum(invoices.mapped("cancel_amount"))
        today = fields.Date.context_today(project)
        due_receivables = receivables.filtered(
            lambda record: record.receivable_date and record.receivable_date <= today
        ).sorted(key=lambda record: (record.receivable_date, record.id))
        progress_amount = sum(due_receivables.mapped("receivable_amount"))
        progress_receivable_amount = max(progress_amount - paid_amount, 0.0)
        bad_debt_receivables = receivables.filtered(lambda record: record.exception_type == "bad_debt")
        bad_debt = sum(
            (record.bad_debt_amount if record.bad_debt_amount else record.receivable_amount or 0.0)
            for record in bad_debt_receivables
        )
        progress_item_names = []
        unpaid_receivables = due_receivables.filtered(
            lambda record: not record.actual_payment_amount
            or record.actual_payment_amount < (record.receivable_amount or 0.0)
        )
        for item_name in unpaid_receivables.mapped("receivable_item_name"):
            item_name = (item_name or "").strip()
            if item_name and item_name not in progress_item_names:
                progress_item_names.append(item_name)
        arrival_voucher = "有" if any(site_receivables.mapped("actual_arrival_date")) else "无"
        acceptance_voucher = "有" if any(site_receivables.mapped("actual_acceptance_date")) else "无"
        if project.service_end_date:
            execution_status = "服务中" if project.service_end_date >= today else "服务结束"
        elif acceptance_voucher == "有":
            execution_status = "已完工"
        elif arrival_voucher == "有":
            execution_status = "施工中"
        else:
            execution_status = "未开工"
        invoice_status = project.invoice_status
        if latest_invoice and latest_invoice.invoice_situation:
            invoice_status = dict(latest_invoice._fields["invoice_situation"].selection).get(
                latest_invoice.invoice_situation
            )
        elif invoices:
            invoice_status = (
                "已开" if project.contract_amount and invoice_amount >= project.contract_amount else "部分未开"
            )
        invoice_dates = [fields.Date.to_string(record.invoice_date) for record in dated_invoices]
        customer_code = project.customer_code
        if project.contract_id:
            customer_code = project.contract_id.customer_code or project.contract_id.partner_id.customer_code or False
        vals = {
            "invoice_date": (dated_invoices[:1].invoice_date if dated_invoices else project.invoice_date),
            "invoice_date_note": (
                "; ".join(invoice_dates)
                if len(invoice_dates) > 1
                else project.invoice_date_note if not dated_invoices else False
            ),
            "customer_code": customer_code,
            "paid_amount": paid_amount,
            "total_receivable_amount": max((project.contract_amount or 0.0) - paid_amount, 0.0),
            "actual_total_receivable_amount": max((project.contract_amount or 0.0) - paid_amount - bad_debt, 0.0),
            "invoiced_receivable_amount": max(invoice_amount - paid_amount - cancel_amount, 0.0),
            "progress_receivable_amount": progress_receivable_amount,
            "progress_receivable_item_name": "；".join(progress_item_names) or False,
            "actual_progress_receivable_amount": max(progress_receivable_amount - bad_debt, 0.0),
            "has_bad_debt": "是" if bad_debt else "否",
            "bad_debt_amount": bad_debt,
        }
        if not project.arrival_voucher_manual:
            vals["arrival_voucher"] = arrival_voucher
        if not project.acceptance_voucher_manual:
            vals["acceptance_voucher"] = acceptance_voucher
        if not project.execution_status_manual:
            vals["contract_execution_status"] = execution_status
        if not project.invoice_status_manual:
            vals["invoice_status"] = invoice_status
        project.sudo().with_context(skip_zfmd_sync=True, skip_manual_override=True).write(vals)
