/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

const ZFMD_ENTRY_MODELS = new Set([
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

patch(ListController.prototype, {
    async createRecord(params = {}) {
        if (ZFMD_ENTRY_MODELS.has(this.props.resModel) && !params.group) {
            const current = this.env.services.router.current.hash;
            const hash = new URLSearchParams();
            for (const key of ["action", "menu_id", "cids"]) {
                if (current[key]) {
                    hash.set(key, current[key]);
                }
            }
            hash.set("model", this.props.resModel);
            hash.set("view_type", "form");
            browser.open(`/web#${hash.toString()}`, "_blank", "noopener");
            return;
        }
        return super.createRecord(...arguments);
    },
});
