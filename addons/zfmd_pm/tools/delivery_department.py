DELIVERY_DEPARTMENT_SELECTION = [
    ("产品部", "产品部"),
    ("工程项目部", "工程项目部"),
    ("软件部", "软件部"),
    ("运算服务中心", "运算服务中心"),
    ("综合管理部", "综合管理部"),
    ("其他", "其他"),
]

DELIVERY_DEPARTMENTS = {value for value, _label in DELIVERY_DEPARTMENT_SELECTION}


def normalize_delivery_department(value):
    """Return one of the selectable delivery departments for legacy/imported text."""
    text = str(value or "").strip()
    if not text:
        return False
    if text in DELIVERY_DEPARTMENTS:
        return text
    aliases = {
        "产品": "产品部",
        "工程部": "工程项目部",
        "项目部": "工程项目部",
        "软件": "软件部",
        "运算中心": "运算服务中心",
        "运算服务部": "运算服务中心",
        "综合部": "综合管理部",
        "管理部": "综合管理部",
    }
    return aliases.get(text, "其他")
