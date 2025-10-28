from __future__ import annotations

import argparse
import csv
import json
import string
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parents[1]
ESCRUTINIO_CSV_PATH = BASE_DIR / "docs" / "escrutinio.csv"
OUTPUT_DIR = BASE_DIR / "elections" / "fixtures"
DISTRICTS_FILENAME = "districts.json"
LISTS_FILENAME = "lists.json"
SCRUTINY_FILENAME = "scrutiny.json"
REQUEST_TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    ),
    "Referer": "https://resultados.elecciones.gob.ar/total/diputado/0/6/30",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

DISTRICT_NAME_MAP = {
    "BUENOS AIRES": "Buenos Aires",
    "CABA": "Ciudad Aut\u00f3noma de Buenos Aires",
    "CIUDAD AUTONOMA DE BUENOS AIRES": "Ciudad Aut\u00f3noma de Buenos Aires",
    "CATAMARCA": "Catamarca",
    "CHACO": "Chaco",
    "CHUBUT": "Chubut",
    "CORDOBA": "C\u00f3rdoba",
    "C\u00d3RDOBA": "C\u00f3rdoba",
    "CORRIENTES": "Corrientes",
    "ENTRE RIOS": "Entre R\u00edos",
    "ENTRE R\u00cdOS": "Entre R\u00edos",
    "FORMOSA": "Formosa",
    "JUJUY": "Jujuy",
    "LA PAMPA": "La Pampa",
    "LA RIOJA": "La Rioja",
    "MENDOZA": "Mendoza",
    "MISIONES": "Misiones",
    "NEUQUEN": "Neuqu\u00e9n",
    "NEUQU\u00c9N": "Neuqu\u00e9n",
    "RIO NEGRO": "R\u00edo Negro",
    "R\u00cdO NEGRO": "R\u00edo Negro",
    "SALTA": "Salta",
    "SAN JUAN": "San Juan",
    "SAN LUIS": "San Luis",
    "SANTA CRUZ": "Santa Cruz",
    "SANTA FE": "Santa Fe",
    "SANTIAGO DEL ESTERO": "Santiago del Estero",
    "TIERRA DEL FUEGO": "Tierra del Fuego",
    "TIERRA DEL FUEGO AEIAS": "Tierra del Fuego",
    "TUCUMAN": "Tucum\u00e1n",
    "TUCUM\u00c1N": "Tucum\u00e1n",
}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalise_label(raw: str) -> str:
    base = strip_accents(raw).strip().upper()
    if base in DISTRICT_NAME_MAP:
        return DISTRICT_NAME_MAP[base]
    raise ValueError(f"Unknown district label '{raw}' in CSV")


def normalise_code(raw: object) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def to_title_caps(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    return string.capwords(stripped.lower())


def normalise_timestamp(raw: str) -> str:
    if not raw:
        return raw
    text = raw.strip()
    if text.endswith("Z"):
        if "." in text:
            text = text.split(".", 1)[0] + "Z"
        return text
    return text


def quantize_percentage(value: object) -> str:
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        decimal_value = Decimal(str(value or 0))
    return format(decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def parse_int(value: object) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError as exc:
        raise ValueError(f"Could not parse integer from '{value}'") from exc


def read_escrutinio_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing escrutinio CSV at {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if row.get("url")]


def fetch_payload(url: str, province: str) -> dict:
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} fetching data for {province}: {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error fetching data for {province}: {url}") from exc


def iter_selected_rows(rows: Iterable[dict[str, str]], provinces: list[str] | None) -> list[dict[str, str]]:
    if not provinces:
        return list(rows)
    wanted = {normalise_label(name) for name in provinces}
    selected: list[dict[str, str]] = []
    for row in rows:
        province_name = normalise_label(row["provincia"])
        if province_name in wanted:
            selected.append(row)
    return selected


def collect_district_data(rows: list[dict[str, str]]) -> dict[str, dict]:
    collected: dict[str, dict] = {}
    for row in rows:
        province_name = normalise_label(row["provincia"])
        url = row["url"].strip()
        payload = fetch_payload(url, province_name)

        registered_voters = parse_int(payload.get("census"))
        renewal_seats = parse_int(payload.get("cargos"))
        timestamp = normalise_timestamp(payload.get("date", ""))

        parties_payload = payload.get("partidos") or []
        parties: list[dict] = []
        for party in parties_payload:
            code = normalise_code(party.get("codTel") or party.get("code"))
            name = to_title_caps(party.get("name", ""))
            votes = float(party.get("votos") or 0)
            percentage = quantize_percentage(party.get("perc") or 0)
            parties.append(
                {
                    "code": code or f"SC{len(parties) + 1:02d}",
                    "name": name,
                    "alignment": name,
                    "votes": votes,
                    "percentage": percentage,
                }
            )

        if not parties:
            raise RuntimeError(f"No party data returned for province '{province_name}'")

        collected[province_name] = {
            "registered_voters": registered_voters,
            "renewal_seats": renewal_seats,
            "total_deputies": renewal_seats,
            "senator_renewal_seats": 0,
            "total_senators": 0,
            "timestamp": timestamp,
            "parties": parties,
        }
    return collected


def build_district_fixture(collected: dict[str, dict]) -> tuple[dict[str, int], list[dict]]:
    mapping: dict[str, int] = {}
    fixture: list[dict] = []
    for index, (name, data) in enumerate(sorted(collected.items()), start=1):
        mapping[name] = index
        fixture.append(
            {
                "model": "elections.district",
                "pk": index,
                "fields": {
                    "name": name,
                    "renewal_seats": data["renewal_seats"],
                    "total_deputies": data["total_deputies"],
                    "registered_voters": data["registered_voters"],
                    "senator_renewal_seats": data["senator_renewal_seats"],
                    "total_senators": data["total_senators"],
                },
            }
        )
    return mapping, fixture


def build_lists_fixture(collected: dict[str, dict], district_ids: dict[str, int]) -> tuple[dict[tuple[str, str], int], list[dict]]:
    fixture: list[dict] = []
    pk_counter = 1
    lookup: dict[tuple[str, str], int] = {}

    for district_name in sorted(collected.keys()):
        district_data = collected[district_name]
        parties = sorted(
            district_data["parties"],
            key=lambda item: (-item["votes"], item["code"]),
        )

        used_codes: set[str] = set()
        for order, party in enumerate(parties, start=1):
            code = party["code"] or f"SC{order:02d}"
            base_code = code
            suffix = 1
            while code in used_codes:
                suffix += 1
                code = f"{base_code}-ALT{suffix:02d}"
            used_codes.add(code)
            party["code"] = code

            fixture.append(
                {
                    "model": "elections.list",
                    "pk": pk_counter,
                    "fields": {
                        "district": district_ids[district_name],
                        "chamber": "diputados",
                        "order": order,
                        "code": code,
                        "name": party["name"],
                        "national_alignment": party["alignment"],
                    },
                }
            )
            lookup[(district_name, code)] = pk_counter
            pk_counter += 1

    return lookup, fixture


def build_scrutiny_fixture(collected: dict[str, dict], lookup: dict[tuple[str, str], int]) -> list[dict]:
    fixture: list[dict] = []
    pk_counter = 1

    for district_name in sorted(collected.keys()):
        district_data = collected[district_name]
        timestamp = district_data["timestamp"]
        for party in sorted(
            district_data["parties"],
            key=lambda item: (-item["votes"], item["code"]),
        ):
            district_code = party["code"]
            list_pk = lookup.get((district_name, district_code))
            if list_pk is None:
                continue
            fixture.append(
                {
                    "model": "elections.scrutiny",
                    "pk": pk_counter,
                    "fields": {
                        "election_list": list_pk,
                        "percentage": party["percentage"],
                        "updated_at": timestamp,
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


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate districts, lists and scrutiny fixtures from the official service",
    )
    parser.add_argument(
        "--province",
        action="append",
        help="Process only the specified province (can be used multiple times)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory for the generated fixtures",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    rows = read_escrutinio_rows(ESCRUTINIO_CSV_PATH)
    selected_rows = iter_selected_rows(rows, args.province)
    if not selected_rows:
        raise RuntimeError("No provinces matched the given filters")

    collected = collect_district_data(selected_rows)
    district_ids, district_fixture = build_district_fixture(collected)
    list_lookup, list_fixture = build_lists_fixture(collected, district_ids)
    scrutiny_fixture = build_scrutiny_fixture(collected, list_lookup)

    output_dir = args.output_dir or OUTPUT_DIR
    write_fixture(output_dir / DISTRICTS_FILENAME, district_fixture)
    write_fixture(output_dir / LISTS_FILENAME, list_fixture)
    write_fixture(output_dir / SCRUTINY_FILENAME, scrutiny_fixture)

    print(
        "Generated "
        f"{len(district_fixture)} districts, "
        f"{len(list_fixture)} lists and "
        f"{len(scrutiny_fixture)} scrutiny entries "
        f"in {output_dir}"
    )


if __name__ == "__main__":
    main()
