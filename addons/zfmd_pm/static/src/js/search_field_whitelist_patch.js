/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DomainSelector } from "@web/core/domain_selector/domain_selector";
import { SearchBarMenu } from "@web/search/search_bar_menu/search_bar_menu";

const FIELD_WHITELISTS = {
    "zfmd.site": [
        "group_name", "name", "partner_id", "province_name", "site_category",
    ],
    "zfmd.contract": [
        "after_sale_no", "amount_total", "amount_untaxed", "archive_copy_count",
        "archive_date", "archive_date_text", "archive_document_type", "bond_status",
        "capacity_text", "change_no", "contract_name", "contract_project_no",
        "contract_sign_date", "contract_sign_date_text", "customer_code",
        "customer_level_1", "customer_level_2", "customer_level_3",
        "delivery_department", "exclude_sales_performance", "exclude_sales_revenue",
        "group_name", "handover_meeting_date", "handover_meeting_date_text",
        "initial_fee", "name", "note", "partner_id", "product_line",
        "project_content", "project_manager", "province_name", "sale_contact",
        "sale_manager", "service_end_date", "service_end_date_text", "service_fee",
        "service_start_date", "service_start_date_text", "site_category", "site_id",
        "site_other_name", "start_application_no", "state", "third_party_interface_fee",
    ],
    "zfmd.project.start": [
        "acceptance_date", "actual_contract_amount", "actual_contract_amount_band",
        "arrival_date", "change_request_no", "contract_match_state",
        "delivery_department", "display_contract_no", "estimated_contract_amount",
        "estimated_contract_amount_band", "estimated_cost_amount",
        "estimated_cost_amount_band", "group_name", "handover_meeting_date", "name",
        "note", "product_line", "project_manager", "province_name", "sale_manager",
        "site_category", "site_name", "state", "transfer_date",
    ],
    "zfmd.service.record": [
        "break_fee_handling", "break_months", "contract_match_state",
        "display_contract_no", "expected_contract_amount",
        "expected_contract_sign_date", "expired_days", "expiry_warning",
        "formal_forecast_date", "group_name", "is_overdue", "note", "product_line",
        "province_name", "record_date", "renewal_after_start_date",
        "renewal_before_end_date", "renewal_note", "sale_manager",
        "service_end_date", "service_end_date_text", "service_type",
        "signing_sale_manager", "site_category", "site_name", "source_contract_no",
        "start_forecast_date", "stop_forecast_date",
    ],
    "zfmd.invoice.record": [
        "actual_payment_amount", "actual_payment_amount_note", "actual_payment_date",
        "actual_payment_date_note", "amount_untaxed", "cancel_date", "cancel_reason",
        "contract_amount", "contract_match_state", "display_contract_no", "express_no",
        "group_name", "invoice_amount", "invoice_date", "invoice_month",
        "invoice_partner_name", "invoice_quarter", "invoice_request_date",
        "invoice_situation", "invoice_year", "is_payment_overdue", "note",
        "product_line", "project_content", "promised_payment_amount",
        "promised_payment_date", "promised_payment_note", "province_name",
        "receivable_balance", "sale_contact", "sale_manager", "site_name",
        "source_contract_no", "state", "state_manual_override", "tax_amount",
        "tax_rate", "warning_info",
    ],
    "zfmd.payment.record": [
        "amount_total", "bill_amount", "cash_amount", "contract_amount",
        "contract_match_state", "display_contract_no", "group_name", "note",
        "payer_name", "payment_date", "payment_item_name", "payment_ratio_text",
        "payment_type", "product_line", "project_content", "promised_payment_date",
        "province_name", "sale_contact", "sale_manager", "site_name",
        "source_contract_no",
    ],
    "zfmd.receivable.plan": [
        "acceptance_voucher", "actual_acceptance_date", "actual_arrival_date",
        "actual_invoice_date", "actual_payment_amount", "actual_payment_date",
        "arrival_voucher", "contract_amount", "contract_match_state", "customer_name",
        "display_contract_no", "exception_reason", "exception_type", "group_name",
        "late_payment_months_display", "note", "overdue_months", "payment_category",
        "payment_term", "pending_progress_date", "product_line", "project_content",
        "promised_entry_date", "promised_payment_amount", "promised_payment_date",
        "province_name", "receivable_amount", "receivable_date",
        "receivable_date_text", "receivable_item_name", "sale_contact",
        "sale_manager", "site_name", "state",
    ],
    "zfmd.project.management": [
        "acceptance_voucher", "actual_progress_receivable_amount",
        "actual_total_receivable_amount", "arrival_voucher", "bad_debt_amount",
        "contract_amount", "contract_execution_status", "contract_match_state",
        "contract_sale_manager", "contract_sign_date", "customer_code",
        "customer_level_1", "customer_level_2", "customer_level_3", "customer_name",
        "delivery_department", "forecast_service_fee", "group_name", "has_bad_debt",
        "initial_fee", "invoice_date", "invoice_date_note", "invoice_status",
        "invoiced_bad_debt_amount", "invoiced_receivable_amount", "name", "note",
        "paid_amount", "product_line", "progress_receivable_item_name",
        "project_content", "project_manager",
        "province_name", "sale_contact", "service_end_date", "service_end_date_note",
        "service_start_date", "service_start_date_note", "site_name",
        "total_receivable_amount",
    ],
    "zfmd.after.sale.service": [
        "chargeable", "contract_no", "expected_contract_amount", "group_name",
        "hardware_cost_budget", "met_tower_cost_budget", "name", "note",
        "payable_amount", "product_line", "province_name", "receivable_amount",
        "sale_manager", "service_content", "site_name",
        "technical_service_fee_budget",
    ],
};

for (const [model, fields] of Object.entries(FIELD_WHITELISTS)) {
    FIELD_WHITELISTS[model] = new Set(fields);
}

function isAllowedField(model, field) {
    const whitelist = FIELD_WHITELISTS[model];
    return !whitelist || whitelist.has(field.name);
}

patch(SearchBarMenu.prototype, {
    validateField(fieldName, field) {
        return isAllowedField(this.env.searchModel.resModel, { ...field, name: fieldName })
            && super.validateField(...arguments);
    },
});

patch(DomainSelector.prototype, {
    getPathEditorInfo() {
        const info = super.getPathEditorInfo(...arguments);
        const whitelist = FIELD_WHITELISTS[this.props.resModel];
        if (!whitelist) {
            return info;
        }
        const originalExtractProps = info.extractProps;
        info.extractProps = (params) => ({
            ...originalExtractProps(params),
            followRelations: false,
            filter: (field) => whitelist.has(field.name),
        });
        return info;
    },
});
