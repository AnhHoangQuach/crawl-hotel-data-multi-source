import csv
import json

NAME_HEADER_ALIASES = {"name", "hotel_name", "hotel", "ten", "ten_khach_san"}
ADDRESS_HEADER_ALIASES = {"address", "city", "location", "dia_chi", "diachi"}


def _find_column(fieldnames, aliases):
    lowered = {f.strip().lower(): f for f in fieldnames}
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    return None


def read_hotels_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        name_col = _find_column(reader.fieldnames, NAME_HEADER_ALIASES)
        addr_col = _find_column(reader.fieldnames, ADDRESS_HEADER_ALIASES)
        if not name_col:
            raise ValueError(
                f"Khong tim thay cot ten khach san trong CSV. Cac cot hien co: {reader.fieldnames}"
            )

        hotels = []
        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            address = (row.get(addr_col) or "").strip() if addr_col else ""
            hotels.append((name, address))
        return hotels


def write_results_json(results, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
