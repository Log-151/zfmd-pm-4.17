/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

function isZfmdMenu(menu, currentApp) {
    const xmlid = menu?.xmlID || menu?.xmlid || "";
    const appXmlid = currentApp?.xmlID || currentApp?.xmlid || "";
    return (
        xmlid.startsWith("zfmd_pm.") ||
        appXmlid === "zfmd_pm.menu_zfmd_root" ||
        (menu?.appID === currentApp?.id && currentApp?.name === "兆方美迪项目管理")
    );
}

patch(NavBar.prototype, {
    onNavBarDropdownItemSelection(menu) {
        if (menu?.actionID && isZfmdMenu(menu, this.currentApp)) {
            const current = this.env.services.router.current.hash;
            const hash = new URLSearchParams({
                menu_id: String(menu.id),
                action: String(menu.actionID),
            });
            if (current.cids) {
                hash.set("cids", current.cids);
            }
            browser.open(`/web#${hash.toString()}`, "_blank", "noopener");
            return;
        }
        return super.onNavBarDropdownItemSelection(...arguments);
    },
});
