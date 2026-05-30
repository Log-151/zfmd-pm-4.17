/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { NavBar } from "@web/webclient/navbar/navbar";

function menuContains(menu, menuId) {
    if (!menu || !menuId) {
        return false;
    }
    if (Number(menu.id) === menuId) {
        return true;
    }
    return (menu.childrenTree || []).some((child) => menuContains(child, menuId));
}

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.zfmdCurrentMenuId = Number(this.env.services.router.current.hash.menu_id || 0);
        useBus(this.env.bus, "ROUTE_CHANGE", () => {
            this.zfmdCurrentMenuId = Number(this.env.services.router.current.hash.menu_id || 0);
            this.render();
        });
    },

    onNavBarDropdownItemSelection(menu) {
        if (menu) {
            this.zfmdCurrentMenuId = Number(menu.id);
            this.render();
        }
        return super.onNavBarDropdownItemSelection(...arguments);
    },

    isZfmdCurrentMenu(menu) {
        const menuId =
            this.zfmdCurrentMenuId || Number(this.env.services.router.current.hash.menu_id || 0);
        return menuContains(menu, menuId);
    },
});
