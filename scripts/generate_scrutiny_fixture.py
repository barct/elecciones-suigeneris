from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parents[1]
ESCRUTINIO_CSV_PATH = BASE_DIR / "docs" / "escrutinio.csv"
DISTRICTS_FIXTURE_PATH = BASE_DIR / "elections" / "fixtures" / "districts.json"
LISTS_FIXTURE_PATH = BASE_DIR / "elections" / "fixtures" / "lists.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "elections" / "fixtures" / "scrutiny.json"
REQUEST_TIMEOUT = 20
STOPWORDS = {"de", "del", "la", "las", "los", "y", "e", "el", "para", "por", "a", "en"}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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


def slugify(value: str) -> str:
    ascii_value = strip_accents(value).lower()
    tokens = re.findall(r"[a-z0-9]+", ascii_value)
    return "_".join(tokens) or "resultado"


def normalise_label(raw: str) -> str:
    base = strip_accents(raw).strip().upper()
    if base in DISTRICT_NAME_MAP:
        return DISTRICT_NAME_MAP[base]
    raise ValueError(f"Unknown district label '{raw}' in CSV")


def read_escrutinio_rows() -> List[dict]:
    if not ESCRUTINIO_CSV_PATH.exists():
        raise FileNotFoundError(f"Missing escrutinio CSV at {ESCRUTINIO_CSV_PATH}")
    with ESCRUTINIO_CSV_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if row.get("url")]


def load_district_ids() -> Dict[str, int]:
    with DISTRICTS_FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    mapping: Dict[str, int] = {}
    for entry in payload:
        name = entry.get("fields", {}).get("name")
        pk = entry.get("pk")
        if name and pk is not None:
            mapping[name] = pk
    if not mapping:
        raise RuntimeError("District fixture is empty or missing required fields")
    return mapping


def load_lists_by_district() -> Dict[int, List[dict]]:
    with LISTS_FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        raw_entries: List[dict] = json.load(handle)
    grouped: Dict[int, List[dict]] = defaultdict(list)
    for entry in raw_entries:
        fields = entry.get("fields", {})
        if fields.get("chamber") != "diputados":
            continue
        district_id = fields.get("district")
        if district_id is None:
            continue
        grouped[district_id].append(entry)
    if not grouped:
        raise RuntimeError("No list entries found for diputados in lists fixture")
    return grouped


def normalise_code(raw: str) -> str:
    text = raw.strip()
    if not text:
        return text
    if text.endswith(".0"):
        text = text[:-2]
    try:
        return str(int(text))
    except ValueError:
        return text


def normalise_tokens(text: str) -> str:
    base = re.sub(r"\(.*?\)", " ", text)
    normalised = unicodedata.normalize("NFKD", base)
    ascii_text = "".join(ch for ch in normalised if not unicodedata.combining(ch))
    tokens = re.findall(r"[a-z0-9]+", ascii_text.lower())
    filtered = [token for token in tokens if token not in STOPWORDS]
    if not filtered:
        filtered = tokens
    return " ".join(sorted(filtered))


def build_lookup(entries: Iterable[dict]) -> tuple[Dict[str, dict], Dict[str, List[dict]]]:
    code_lookup: Dict[str, dict] = {}
    token_lookup: Dict[str, List[dict]] = {}
    for entry in entries:
        code = normalise_code(str(entry["fields"].get("code", "")))
        if code:
            code_lookup[code] = entry
        token_key = normalise_tokens(entry["fields"].get("name", ""))
        token_lookup.setdefault(token_key, []).append(entry)
    return code_lookup, token_lookup


def normalise_timestamp(raw: str) -> str:
    if not raw:
        return raw
    if raw.endswith("Z"):
        if "." in raw:
            base = raw.split(".", 1)[0]
            return f"{base}Z"
        return raw
    return raw


def to_decimal(value: float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        value = f"{value}"
    return Decimal(str(value))


def fetch_payload(url: str, province: str) -> dict:
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} fetching data for {province}: {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error fetching data for {province}: {url}") from exc
    return json.loads(data)


def select_entry(
    name: str,
    raw_code: str,
    code_lookup: Dict[str, dict],
    token_lookup: Dict[str, List[dict]],
    province: str,
) -> dict:
    code = normalise_code(raw_code)
    if code and code in code_lookup:
        return code_lookup[code]

    token_key = normalise_tokens(name)
    options = token_lookup.get(token_key, [])
    if len(options) == 1:
        return options[0]

    available = ", ".join(
        sorted(entry["fields"].get("name", "") for entry in code_lookup.values())
    )
    raise KeyError(
        "Unable to resolve list for party "
        f"name='{name}' code='{raw_code}' province='{province}'. "
        f"Available local lists: {available}"
    )


def iter_selected_provinces(all_rows: Sequence[dict], provinces: Sequence[str] | None) -> Iterator[dict]:
    if not provinces:
        yield from all_rows
        return
    wanted = {normalise_label(name) for name in provinces}
    for row in all_rows:
        if normalise_label(row["provincia"]) in wanted:
            yield row


def build_fixture(selected_rows: Sequence[dict]) -> List[dict]:
    district_ids = load_district_ids()
    lists_by_district = load_lists_by_district()
    lookup_cache: Dict[int, tuple[Dict[str, dict], Dict[str, List[dict]]]] = {}

    fixture: List[dict] = []
    pk_counter = 1

    for row in selected_rows:
        province_name = normalise_label(row["provincia"])
        district_id = district_ids.get(province_name)
        if district_id is None:
            raise RuntimeError(f"District '{province_name}' is missing from districts fixture")

        lists = lists_by_district.get(district_id, [])
        if not lists:
            raise RuntimeError(f"No list entries found for province '{province_name}'")

        if district_id not in lookup_cache:
            lookup_cache[district_id] = build_lookup(lists)
        code_lookup, token_lookup = lookup_cache[district_id]

        payload = fetch_payload(row["url"], province_name)
        parties = payload.get("partidos")
        if not parties:
            raise RuntimeError(f"No party data found for province '{province_name}'")

        timestamp = normalise_timestamp(payload.get("date", ""))

        provisional: List[tuple[Decimal, dict, dict]] = []
        for party in parties:
            list_entry = select_entry(
                name=party.get("name", ""),
                raw_code=str(party.get("codTel", "")),
                code_lookup=code_lookup,
                token_lookup=token_lookup,
                province=province_name,
            )
            percentage = to_decimal(party.get("perc", 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            provisional.append((percentage, party, list_entry))

        provisional.sort(key=lambda item: item[0], reverse=True)

        for percentage, _, entry in provisional:
            fixture.append(
                {
                    "model": "elections.scrutiny",
                    "pk": pk_counter,
                    "fields": {
                        "election_list": entry["pk"],
                        "percentage": format(percentage, ".2f"),
                        "updated_at": timestamp,
                    },
                }
            )
            pk_counter += 1

    return fixture


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate scrutiny fixtures from the official election service"
    )
    parser.add_argument(
        "--province",
        action="append",
        help="Process only the specified province (can be used multiple times)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path for the generated fixture",
    )
    return parser.parse_args()


def determine_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        return args.output
    if args.province and len(args.province) == 1:
        slug = slugify(normalise_label(args.province[0]))
        return BASE_DIR / "elections" / "fixtures" / f"scrutiny_{slug}.json"
    return DEFAULT_OUTPUT_PATH


def main() -> None:
    args = parse_arguments()
    rows = read_escrutinio_rows()
    selected_rows = list(iter_selected_provinces(rows, args.province))
    if not selected_rows:
        raise RuntimeError("No provinces matched the given filters")

    fixture = build_fixture(selected_rows)
    output_path = determine_output_path(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(fixture, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    processed = {normalise_label(row["provincia"]) for row in selected_rows}
    print(
        f"Wrote {len(fixture)} scrutiny entries for {len(processed)} provinces to {output_path}"
    )


if __name__ == "__main__":
    main()
