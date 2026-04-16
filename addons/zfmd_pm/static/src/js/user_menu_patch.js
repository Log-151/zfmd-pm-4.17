/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

patch(UserMenu.prototype, {
    getElements() {
        return super.getElements().filter((element) => element.id === "logout");
    },
});
