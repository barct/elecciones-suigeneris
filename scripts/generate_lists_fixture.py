from __future__ import annotations

import csv
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = BASE_DIR / "docs" / "listas_con_filo.csv"
DISTRICT_OUTPUT_PATH = BASE_DIR / "elections" / "fixtures" / "districts.json"
LIST_OUTPUT_PATH = BASE_DIR / "elections" / "fixtures" / "lists.json"
DEPUTIES_CSV_PATH = BASE_DIR / "docs" / "diputados 2025.csv"
SENATORS_CSV_PATH = BASE_DIR / "docs" / "senadores 2025.csv"

DISTRICT_NAME_MAP = {
    "BUENOS AIRES": "Buenos Aires",
    "CABA": "Ciudad Autónoma de Buenos Aires",
    "CIUDAD AUTONOMA DE BUENOS AIRES": "Ciudad Autónoma de Buenos Aires",
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


def read_semicolon_csv(path: Path) -> list[dict[str, str]]:
    encodings = ("utf-8-sig", "utf-8", "latin-1")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                rows: list[dict[str, str]] = []
                for raw_row in reader:
                    row: dict[str, str] = {}
                    for key, value in raw_row.items():
                        if key is None:
                            continue
                        row[key.strip()] = "" if value is None else str(value).strip()
                    rows.append(row)
                return rows
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Could not decode CSV file {path} using expected encodings") from last_error


def parse_int(value: str | None) -> int:
    if value is None:
        return 0
    text = value.strip()
    if not text:
        return 0
    cleaned = text.replace(".", "").replace(",", "")
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"Could not parse integer from '{value}'") from exc


def normalise_code(raw_code: str, counters: dict[str, int], label: str) -> str:
    code = raw_code.strip()
    if code and code not in {"—", "--", "-"}:
        return code
    counters[label] += 1
    return f"SC{counters[label]:02d}"


def load_rows() -> list[tuple[str, dict[str, str]]]:
    records: list[tuple[str, dict[str, str]]] = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            district_label = pick_value(row, "distrito", "Provincia")
            internal_name = normalise_label(district_label)
            records.append((internal_name, row))
    if not records:
        raise RuntimeError("CSV file appears to be empty")
    return records


def load_deputy_metrics() -> dict[str, tuple[int, int, int]]:
    path = DEPUTIES_CSV_PATH
    if not path.exists():
        raise FileNotFoundError(f"Missing deputies CSV at {path}")
    metrics: dict[str, tuple[int, int, int]] = {}
    for row in read_semicolon_csv(path):
        district_label = pick_value(row, "Provincia", "Distrito")
        internal_name = normalise_label(district_label)
        renewal = parse_int(row.get("Bancas en juego (2025)") or row.get("Renuevan diputados"))
        total = parse_int(row.get("Bancas totales (Diputados)") or row.get("Total diputados"))
        voters = parse_int(row.get("Electores"))
        metrics[internal_name] = (renewal, total, voters)
    if not metrics:
        raise RuntimeError(f"No deputy data found in {path}")
    return metrics


def load_senator_metrics() -> dict[str, tuple[int, int]]:
    path = SENATORS_CSV_PATH
    if not path.exists():
        raise FileNotFoundError(f"Missing senators CSV at {path}")
    metrics: dict[str, tuple[int, int]] = {}
    for row in read_semicolon_csv(path):
        district_label = pick_value(row, "Provincia", "Distrito")
        internal_name = normalise_label(district_label)
        renewal = parse_int(row.get("Senadores_en_juego_2025") or row.get("Renuevan senadores"))
        total = parse_int(row.get("Senadores_totales") or row.get("Total senadores"))
        metrics[internal_name] = (renewal, total)
    if not metrics:
        raise RuntimeError(f"No senator data found in {path}")
    return metrics


def build_district_fixture(records: list[tuple[str, dict[str, str]]]) -> tuple[dict[str, int], list[dict]]:
    deputy_data = load_deputy_metrics()
    senator_data = load_senator_metrics()

    referenced_districts = {name for name, _ in records}
    combined_names = sorted(set(deputy_data) | set(senator_data) | referenced_districts)

    mapping: dict[str, int] = {}
    fixture: list[dict] = []

    for index, district_name in enumerate(combined_names, start=1):
        dep_renewal, dep_total, voters = deputy_data.get(district_name, (0, 0, 0))
        sen_renewal, sen_total = senator_data.get(district_name, (0, 0))
        mapping[district_name] = index
        fixture.append(
            {
                "model": "elections.district",
                "pk": index,
                "fields": {
                    "name": district_name,
                    "renewal_seats": dep_renewal,
                    "total_deputies": dep_total,
                    "registered_voters": voters,
                    "senator_renewal_seats": sen_renewal,
                    "total_senators": sen_total,
                },
            }
        )

    missing = sorted(referenced_districts - set(mapping))
    if missing:
        raise RuntimeError(
            "Districts present in list CSV but missing metrics: " + ", ".join(missing)
        )

    return mapping, fixture


def build_list_fixture(records: list[tuple[str, dict[str, str]]], district_ids: dict[str, int]) -> list[dict]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for internal_name, row in records:
        grouped[internal_name].append(row)

    fixture: list[dict] = []
    pk_counter = 1
    used_codes: dict[str, set[str]] = defaultdict(set)
    duplicate_counters: dict[str, int] = defaultdict(int)
    recorded_details: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)

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

            existing_details = recorded_details[district_name].get(code)
            if existing_details:
                if existing_details == (name, alignment):
                    # Duplicate row already captured; skip to avoid uniqueness clash.
                    continue
                duplicate_counters[district_name] += 1
                suffix = duplicate_counters[district_name]
                base_code = code or f"SC{missing_codes[district_name]:02d}"
                candidate = f"{base_code}-ALT{suffix:02d}"
                while candidate in used_codes[district_name]:
                    duplicate_counters[district_name] += 1
                    suffix = duplicate_counters[district_name]
                    candidate = f"{base_code}-ALT{suffix:02d}"
                code = candidate

            used_codes[district_name].add(code)
            recorded_details[district_name][code] = (name, alignment)

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


def write_fixture(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> None:
    records = load_rows()
    district_ids, district_entries = build_district_fixture(records)
    list_entries = build_list_fixture(records, district_ids)
    write_fixture(DISTRICT_OUTPUT_PATH, district_entries)
    write_fixture(LIST_OUTPUT_PATH, list_entries)


if __name__ == "__main__":
    main()
