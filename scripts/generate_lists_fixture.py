from __future__ import annotations

import csv
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = BASE_DIR / "docs" / "listas_con_filo.csv"
DISTRICT_FIXTURE_PATH = BASE_DIR / "elections" / "fixtures" / "districts.json"
OUTPUT_PATH = BASE_DIR / "elections" / "fixtures" / "lists.json"

DISTRICT_NAME_MAP = {
    "BUENOS AIRES": "Buenos Aires",
    "CABA": "Ciudad Autónoma de Buenos Aires",
    "CATAMARCA": "Catamarca",
    "CHACO": "Chaco",
    "CHUBUT": "Chubut",
    "CORDOBA": "Córdoba",
    "CÓRDOBA": "Córdoba",
    "CORRIENTES": "Corrientes",
    "ENTRE RIOS": "Entre Ríos",
    "ENTRE RÍOS": "Entre Ríos",
    "FORMOSA": "Formosa",
    "JUJUY": "Jujuy",
    "LA PAMPA": "La Pampa",
    "LA RIOJA": "La Rioja",
    "MENDOZA": "Mendoza",
    "MISIONES": "Misiones",
    "NEUQUEN": "Neuquén",
    "NEUQUÉN": "Neuquén",
    "RIO NEGRO": "Río Negro",
    "RÍO NEGRO": "Río Negro",
    "SALTA": "Salta",
    "SAN JUAN": "San Juan",
    "SAN LUIS": "San Luis",
    "SANTA CRUZ": "Santa Cruz",
    "SANTA FE": "Santa Fe",
    "SANTIAGO DEL ESTERO": "Santiago del Estero",
    "TIERRA DEL FUEGO": "Tierra del Fuego",
    "TUCUMAN": "Tucumán",
    "TUCUMÁN": "Tucumán",
}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalise_label(raw: str) -> str:
    base = strip_accents(raw).strip().upper()
    if base in DISTRICT_NAME_MAP:
        return DISTRICT_NAME_MAP[base]
    raise ValueError(f"Unknown district label '{raw}' in CSV")


def pick_value(row: dict[str, str], *candidates: str, allow_empty: bool = False) -> str:
    for column in candidates:
        if column in row and row[column] is not None:
            value = row[column].strip()
            if value or allow_empty:
                return value
    if allow_empty:
        return ""
    raise KeyError(f"Columns {candidates} missing from row {row}")


def load_district_ids() -> dict[str, int]:
    with DISTRICT_FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["fields"]["name"]: entry["pk"] for entry in data}


def normalise_code(raw_code: str, counters: dict[str, int], label: str) -> str:
    code = raw_code.strip()
    if code and code not in {"—", "--", "-"}:
        return code
    counters[label] += 1
    return f"SC{counters[label]:02d}"


def build_fixture() -> list[dict]:
    district_ids = load_district_ids()
    grouped: dict[str, list[dict]] = defaultdict(list)

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            district_label = pick_value(row, "distrito", "Provincia")
            internal_name = normalise_label(district_label)
            if internal_name not in district_ids:
                raise ValueError(f"District '{internal_name}' not present in fixtures")
            grouped[internal_name].append(row)

    fixture: list[dict] = []
    pk_counter = 1

    for district_name in sorted(grouped.keys()):
        rows = grouped[district_name]

        def sort_key(item: dict[str, str]) -> tuple[int, str]:
            raw_number = pick_value(item, "numeroLista", "Nº de lista", allow_empty=True)
            numeric = int(raw_number) if raw_number.isdigit() else 9999
            label = pick_value(item, "agrupacion", "Agrupación").lower()
            return numeric, label

        rows.sort(key=sort_key)
        missing_codes: dict[str, int] = defaultdict(int)

        for order, row in enumerate(rows, start=1):
            raw_code = pick_value(row, "numeroLista", "Nº de lista", allow_empty=True)
            code = normalise_code(raw_code, missing_codes, district_name)
            name = pick_value(row, "agrupacion", "Agrupación")
            alignment = pick_value(row, "agrupacionNacional", "Agrupación nacional (filo)")

            fixture.append(
                {
                    "model": "elections.list",
                    "pk": pk_counter,
                    "fields": {
                        "district": district_ids[district_name],
                        "chamber": "diputados",
                        "order": order,
                        "code": code,
                        "name": name,
                        "national_alignment": alignment,
                    },
                }
            )
            pk_counter += 1

    return fixture


def main() -> None:
    entries = build_fixture()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
