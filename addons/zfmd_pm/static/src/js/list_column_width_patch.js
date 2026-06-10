/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { onMounted } from "@odoo/owl";

const ZFMD_LIST_MODELS = new Set([
    "zfmd.site",
    "zfmd.contract",
    "zfmd.project.start",
    "zfmd.service.record",
    "zfmd.invoice.record",
    "zfmd.payment.record",
    "zfmd.receivable.plan",
    "zfmd.project.management",
    "zfmd.after.sale.service",
]);

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => this.restoreZfmdColumnWidths());
    },

    getZfmdColumnWidthStorageKey() {
        return `zfmd_pm.list_widths.${this.props.list.resModel}`;
    },

    restoreZfmdColumnWidths() {
        if (!ZFMD_LIST_MODELS.has(this.props.list.resModel) || !this.tableRef.el) {
            return;
        }
        let widths;
        try {
            widths = JSON.parse(
                browser.localStorage.getItem(this.getZfmdColumnWidthStorageKey()) || "{}"
            );
        } catch {
            widths = {};
        }
        const headers = [...this.tableRef.el.querySelectorAll("thead th[data-name]")];
        for (const th of headers) {
            const width = widths[th.dataset.name];
            if (width) {
                th.style.width = `${width}px`;
                th.style.maxWidth = `${width}px`;
            }
        }
        if (headers.some((th) => widths[th.dataset.name])) {
            this.columnWidths = [
                ...this.tableRef.el.querySelectorAll("thead th:not(.o_list_actions_header)"),
            ].map((th) => th.getBoundingClientRect().width);
            this.keepColumnWidths = true;
        }
    },

    saveZfmdColumnWidths() {
        if (!ZFMD_LIST_MODELS.has(this.props.list.resModel) || !this.tableRef.el) {
            return;
        }
        const widths = {};
        for (const th of this.tableRef.el.querySelectorAll("thead th[data-name]")) {
            widths[th.dataset.name] = Math.round(th.getBoundingClientRect().width);
        }
        browser.localStorage.setItem(this.getZfmdColumnWidthStorageKey(), JSON.stringify(widths));
    },

    onStartResize() {
        super.onStartResize(...arguments);
        window.addEventListener(
            "pointerup",
            () => browser.setTimeout(() => this.saveZfmdColumnWidths(), 0),
            { once: true }
        );
    },
});
