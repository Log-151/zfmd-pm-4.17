import io
import re
import zipfile
import xml.etree.ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _normalize_text(value):
    text = "" if value is None else str(value)
    return (
        text.replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
        .replace("\u3000", "")
        .strip()
    )


class ZfmdImportUtilityMixin:
    def _norm_text(self, value):
        return _normalize_text(value)

    def _clean_value(self, value):
        if value is None:
            return False
        if isinstance(value, str):
            raw = value.strip()
            if raw in {"", "/"}:
                return False
            return raw
        text = _normalize_text(value)
        if text in {"", "/"}:
            return False
        return value

    def _parse_float(self, value):
        value = self._clean_value(value)
        if value is False:
            return 0.0

        text = (
            str(value)
            .replace(",", "")
            .replace("\uff0c", "")
            .replace("\u4e07\u5143", "")
            .replace("\u4e07", "")
            .replace("\u5143", "")
            .replace("\u7a0e\u7387", "")
            .replace("%", "")
            .strip()
        )
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else 0.0

    def _parse_money(self, value, source_unit="元"):
        amount = self._parse_float(value)
        if source_unit == "万元":
            return amount * 10000.0
        return amount

    def _parse_date(self, value):
        value = self._clean_value(value)
        if value is False:
            return False
        text = str(value)
        match = re.search(r"(\d{4})[.\-/\u5e74](\d{1,2})[.\-/\u6708](\d{1,2})", text)
        if not match:
            return False
        year, month, day = map(int, match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _extract_contract_key(self, value):
        value = self._clean_value(value)
        if value is False:
            return False
        match = re.search(r"(\d{5}(?:-\d+)?)", str(value))
        return match.group(1) if match else str(value)

    def _first_value(self, row, *keys):
        for key in keys:
            value = row.get(key)
            if self._clean_value(value) is not False:
                return value
        return False

    def _write_import_summary(
        self,
        *,
        total_count,
        imported_count=0,
        unmatched_count=0,
        skipped_count=0,
        issue_lines=None,
    ):
        issue_lines = issue_lines or []
        summary = [
            f"\u8bc6\u522b\u8bb0\u5f55\u6570\uff1a{total_count}",
            f"\u5bfc\u5165\u6210\u529f\u6570\uff1a{imported_count}",
            f"\u672a\u5339\u914d\u5408\u540c\u6570\uff1a{unmatched_count}",
            f"\u8df3\u8fc7/\u95ee\u9898\u8bb0\u5f55\u6570\uff1a{skipped_count}",
        ]
        if issue_lines:
            summary.extend(["", "\u95ee\u9898\u660e\u7ec6\uff1a", *issue_lines[:30]])
        return "\n".join(summary)


def zfmd_col_to_index(ref):
    letters = "".join(ch for ch in ref if ch.isalpha())
    result = 0
    for char in letters:
        result = result * 26 + ord(char.upper()) - 64
    return result - 1


def zfmd_read_workbook_tables(file_bytes):
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append("".join(t.text or "" for t in si.findall(".//a:t", NS)))

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        result = {}
        for sheet in workbook.find("a:sheets", NS):
            name = sheet.attrib["name"]
            rid = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            target = "xl/" + relmap[rid].lstrip("/")
            ws = ET.fromstring(zf.read(target))
            rows = []
            for row in ws.findall(".//a:sheetData/a:row", NS):
                values = {}
                for cell in row.findall("a:c", NS):
                    idx = zfmd_col_to_index(cell.attrib.get("r", "A1"))
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("a:v", NS)
                    value = "" if value_node is None else (value_node.text or "")
                    if cell_type == "s" and value != "":
                        try:
                            value = shared[int(value)]
                        except Exception:
                            pass
                    values[idx] = value
                if values:
                    max_idx = max(values)
                    rows.append([values.get(i, "") for i in range(max_idx + 1)])
            result[name] = rows
    return result


def zfmd_extract_records(file_bytes, required_headers):
    tables = zfmd_read_workbook_tables(file_bytes)
    records = []
    required = {_normalize_text(header) for header in required_headers}
    for sheet_name, rows in tables.items():
        for i, row in enumerate(rows):
            normalized = [_normalize_text(cell) for cell in row]
            if required.issubset(set(normalized)):
                header = normalized
                for data_row in rows[i + 1 :]:
                    if not any(_normalize_text(cell) for cell in data_row):
                        continue
                    row_dict = {}
                    for idx, key in enumerate(header):
                        if key:
                            row_dict[key] = data_row[idx] if idx < len(data_row) else ""
                    row_dict["_sheet_name"] = sheet_name
                    records.append(row_dict)
                break
    return records
