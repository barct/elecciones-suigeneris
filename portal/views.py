from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import render
from django.utils.timezone import localtime

from elections.models import District, List, Scrutiny


MIN_PARTY_THRESHOLD = Decimal("3.00")  # mínimo % para acceder a la distribución de bancas
TOTAL_PERCENTAGE = Decimal("100.00")
PERCENT_TOLERANCE = Decimal("0.01")
DEFAULT_CHAMBER_FILTER = "ambos"
VALID_CHAMBER_FILTERS = {
	DEFAULT_CHAMBER_FILTER,
	List.Chamber.DEPUTIES,
	List.Chamber.SENATORS,
}
FILTER_DETAIL_BY_CHAMBER = {
	DEFAULT_CHAMBER_FILTER: "Incluye todas las fuerzas por distrito",
	List.Chamber.DEPUTIES: "Solo listas de la Cámara de Diputados",
	List.Chamber.SENATORS: "Solo listas de la Cámara de Senadores",
}


def _ensure_full_percentage(entries: list[dict], *, latest_update=None) -> None:
	"""Garantiza que la suma de porcentajes alcance el 100% agregando un item "Otros"."""

	if not entries:
		return

	total = sum(entry.get("percentage", Decimal("0")) for entry in entries)
	remainder = TOTAL_PERCENTAGE - total
	if remainder > PERCENT_TOLERANCE:
		existing_placeholder = next(
			(entry for entry in entries if entry.get("id") is None and entry.get("name") == "Otros"),
			None,
		)
		if existing_placeholder is None:
			entries.append(
				{
					"id": None,
					"code": "-",
					"name": "Otros",
					"alignment": "Otros",
					"percentage": remainder,
					"seats": 0,
					"passes_threshold": False,
					"updated_at": latest_update,
				},
			)
		else:
			existing_placeholder["percentage"] += remainder
			if existing_placeholder.get("updated_at") is None:
				existing_placeholder["updated_at"] = latest_update

	new_total = sum(entry.get("percentage", Decimal("0")) for entry in entries)
	if new_total <= 0:
		for entry in entries:
			entry["percentage_display"] = f"{entry.get('percentage', Decimal('0')):.2f}"
			entry["share"] = Decimal("0")
	else:
		for entry in entries:
			percentage = entry.get("percentage", Decimal("0"))
			entry["percentage_display"] = f"{percentage:.2f}"
			entry["share"] = (percentage / new_total) * TOTAL_PERCENTAGE


def _dhondt_allocation(votes_by_list: dict[int, Decimal], seats: int) -> dict[int, int]:
	"""Aplica el método D'Hondt sobre un mapa de votos y devuelve bancas por lista."""

	allocation = {pk: 0 for pk in votes_by_list}
	if seats <= 0 or not votes_by_list:
		return allocation

	total_votes = sum(votes_by_list.values())
	if not total_votes:
		return allocation

	for _ in range(seats):
		best_list_id = max(
			votes_by_list,
			key=lambda pk: votes_by_list[pk] / (allocation[pk] + 1),
		)
		allocation[best_list_id] += 1

	return allocation


def _senate_allocation(votes_by_list: dict[int, Decimal], seats: int) -> dict[int, int]:
	"""Asigna bancas para senadores: 2 para la mayoría simple, 1 para la primera minoría."""

	allocation = {pk: 0 for pk in votes_by_list}
	if seats <= 0 or not votes_by_list:
		return allocation

	ordered = sorted(votes_by_list.items(), key=lambda item: (-item[1], item[0]))
	top_list_id = ordered[0][0]
	first_award = min(seats, 2)
	allocation[top_list_id] = first_award
	remaining = seats - first_award
	if remaining > 0 and len(ordered) > 1:
		second_list_id = ordered[1][0]
		allocation[second_list_id] = min(remaining, 1)

	return allocation


def dashboard(request):
	"""Renderiza el portal electoral con datos reales y cálculo de bancas por distrito."""

	chamber_filter = request.GET.get("chamber", DEFAULT_CHAMBER_FILTER).lower()
	if chamber_filter not in VALID_CHAMBER_FILTERS:
		chamber_filter = DEFAULT_CHAMBER_FILTER

	include_deputies = chamber_filter in (DEFAULT_CHAMBER_FILTER, List.Chamber.DEPUTIES)
	include_senators = chamber_filter in (DEFAULT_CHAMBER_FILTER, List.Chamber.SENATORS)

	district_queryset = District.objects.prefetch_related(
		Prefetch(
			"lists",
			queryset=List.objects.prefetch_related(
				Prefetch("scrutiny_records", queryset=Scrutiny.objects.order_by("-updated_at"))
			),
		)
	)

	districts_data = []
	overall_totals = {
		List.Chamber.DEPUTIES: defaultdict(int),
		List.Chamber.SENATORS: defaultdict(int),
	}
	overall_weighted_votes = {
		List.Chamber.DEPUTIES: defaultdict(Decimal),
		List.Chamber.SENATORS: defaultdict(Decimal),
	}
	elector_totals = {
		List.Chamber.DEPUTIES: Decimal("0"),
		List.Chamber.SENATORS: Decimal("0"),
	}
	overall_registered_total = Decimal("0")
	total_deputy_seats = 0
	total_senate_seats = 0
	total_lists_by_chamber = {
		List.Chamber.DEPUTIES: 0,
		List.Chamber.SENATORS: 0,
	}
	latest_update = None
	district_statuses: list[dict] = []

	for district in district_queryset:
		chamber_payload = {
			List.Chamber.DEPUTIES: {
				"seats": district.renewal_seats,
				"lists": [],
				"votes": {},
				"eligible_votes": {},
			},
			List.Chamber.SENATORS: {
				"seats": district.senator_renewal_seats,
				"lists": [],
				"votes": {},
			},
		}
		deputy_minor_total = Decimal("0")
		deputy_minor_latest_update = None
		district_latest_update = None
		voter_base = Decimal(district.registered_voters or 0)
		if voter_base > 0:
			overall_registered_total += voter_base

		for election_list in district.lists.all():
			scrutiny = next(iter(election_list.scrutiny_records.all()), None)
			if scrutiny is None:
				continue

			payload = chamber_payload[election_list.chamber]
			payload["votes"][election_list.id] = scrutiny.percentage
			alignment = election_list.national_alignment.strip() if election_list.national_alignment else ""
			if not alignment:
				alignment = election_list.name
			if (
				election_list.chamber == List.Chamber.DEPUTIES
				and scrutiny.percentage >= MIN_PARTY_THRESHOLD
			):
				payload["eligible_votes"][election_list.id] = scrutiny.percentage

			entry = {
				"id": election_list.id,
				"code": election_list.code,
				"name": election_list.name,
				"alignment": alignment,
				"percentage": scrutiny.percentage,
				"percentage_display": f"{scrutiny.percentage:.2f}",
				"updated_at": scrutiny.updated_at,
			}

			if (
				election_list.chamber == List.Chamber.DEPUTIES
				and scrutiny.percentage < MIN_PARTY_THRESHOLD
			):
				deputy_minor_total += scrutiny.percentage
				if (
					deputy_minor_latest_update is None
					or scrutiny.updated_at > deputy_minor_latest_update
				):
					deputy_minor_latest_update = scrutiny.updated_at
			else:
				payload["lists"].append(entry)

			if latest_update is None or scrutiny.updated_at > latest_update:
				latest_update = scrutiny.updated_at
			if district_latest_update is None or scrutiny.updated_at > district_latest_update:
				district_latest_update = scrutiny.updated_at

		if deputy_minor_total > 0:
			aggregated_entry = {
				"id": None,
				"code": "-",
				"name": "Otros",
				"alignment": "Otros",
				"percentage": deputy_minor_total,
				"percentage_display": f"{deputy_minor_total:.2f}",
				"updated_at": deputy_minor_latest_update or district_latest_update,
			}
			chamber_payload[List.Chamber.DEPUTIES]["lists"].append(aggregated_entry)

		deputy_data = chamber_payload[List.Chamber.DEPUTIES]
		deputy_allocation = _dhondt_allocation(deputy_data["eligible_votes"], deputy_data["seats"])
		for entry in deputy_data["lists"]:
			list_id = entry["id"]
			assigned = deputy_allocation.get(list_id, 0)
			entry["seats"] = assigned
			overall_totals[List.Chamber.DEPUTIES][entry["alignment"]] += assigned

		_ensure_full_percentage(deputy_data["lists"], latest_update=district_latest_update)

		deputy_data["lists"].sort(
			key=lambda entry: (-entry.get("seats", 0), -entry["percentage"], entry["name"])
		)
		has_deputy_data = bool(deputy_data["lists"])
		if has_deputy_data:
			total_deputy_seats += deputy_data["seats"]
			total_lists_by_chamber[List.Chamber.DEPUTIES] += len(deputy_data["lists"])
		if has_deputy_data and voter_base > 0:
			elector_totals[List.Chamber.DEPUTIES] += voter_base
			for entry in deputy_data["lists"]:
				percentage = entry.get("percentage")
				if percentage is None:
					continue
				if not isinstance(percentage, Decimal):
					percentage = Decimal(str(percentage))
				overall_weighted_votes[List.Chamber.DEPUTIES][entry["alignment"]] += percentage * voter_base

		senate_data = chamber_payload[List.Chamber.SENATORS]
		senate_allocation = _senate_allocation(senate_data["votes"], senate_data["seats"])
		for entry in senate_data["lists"]:
			list_id = entry["id"]
			assigned = senate_allocation.get(list_id, 0)
			entry["seats"] = assigned
			overall_totals[List.Chamber.SENATORS][entry["alignment"]] += assigned

		_ensure_full_percentage(senate_data["lists"], latest_update=district_latest_update)

		senate_data["lists"].sort(
			key=lambda entry: (-entry.get("seats", 0), -entry["percentage"], entry["name"])
		)
		has_senate_data = bool(senate_data["lists"])
		if has_senate_data:
			if senate_data["seats"]:
				total_senate_seats += senate_data["seats"]
		total_lists_by_chamber[List.Chamber.SENATORS] += len(senate_data["lists"])
		if has_senate_data and voter_base > 0:
			elector_totals[List.Chamber.SENATORS] += voter_base
			for entry in senate_data["lists"]:
				percentage = entry.get("percentage")
				if percentage is None:
					continue
				if not isinstance(percentage, Decimal):
					percentage = Decimal(str(percentage))
				overall_weighted_votes[List.Chamber.SENATORS][entry["alignment"]] += percentage * voter_base

		district_statuses.append(
			{
				"id": district.id,
				"name": district.name,
				"has_deputies": has_deputy_data,
				"has_senators": has_senate_data,
				"deputy_seats": district.renewal_seats,
				"senator_seats": district.senator_renewal_seats,
				"voter_base": voter_base,
			}
		)

		should_include_district = False
		if include_deputies and has_deputy_data:
			should_include_district = True
		if include_senators and has_senate_data:
			should_include_district = True

		if not should_include_district:
			continue

		districts_data.append(
			{
				"id": district.id,
				"name": district.name,
				"renewal_seats": deputy_data["seats"],
				"senator_renewal_seats": district.senator_renewal_seats,
				"total_senators": district.total_senators,
				"registered_voters": district.registered_voters,
				"deputies": {
					"seats": deputy_data["seats"],
					"lists": deputy_data["lists"],
				},
				"senators": {
					"seats": senate_data["seats"],
					"lists": senate_data["lists"],
				},
			}
		)

	total_districts = len(districts_data)

	overall_distribution_deputies = []
	deputy_denominator = elector_totals[List.Chamber.DEPUTIES]
	deputy_alignments = set(overall_totals[List.Chamber.DEPUTIES].keys()) | set(
		overall_weighted_votes[List.Chamber.DEPUTIES].keys()
	)
	for alignment in sorted(
		deputy_alignments,
		key=lambda name: (
			-overall_totals[List.Chamber.DEPUTIES].get(name, 0),
			-overall_weighted_votes[List.Chamber.DEPUTIES].get(name, Decimal("0")),
			name,
		),
	):
		seats = overall_totals[List.Chamber.DEPUTIES].get(alignment, 0)
		weighted_votes = overall_weighted_votes[List.Chamber.DEPUTIES].get(alignment, Decimal("0"))
		share = weighted_votes / deputy_denominator if deputy_denominator else Decimal("0")
		overall_distribution_deputies.append({"name": alignment, "seats": seats, "share": share})

	overall_distribution_senators = []
	senate_denominator = elector_totals[List.Chamber.SENATORS]
	senate_alignments = set(overall_totals[List.Chamber.SENATORS].keys()) | set(
		overall_weighted_votes[List.Chamber.SENATORS].keys()
	)
	for alignment in sorted(
		senate_alignments,
		key=lambda name: (
			-overall_totals[List.Chamber.SENATORS].get(name, 0),
			-overall_weighted_votes[List.Chamber.SENATORS].get(name, Decimal("0")),
			name,
		),
	):
		seats = overall_totals[List.Chamber.SENATORS].get(alignment, 0)
		weighted_votes = overall_weighted_votes[List.Chamber.SENATORS].get(alignment, Decimal("0"))
		share = weighted_votes / senate_denominator if senate_denominator else Decimal("0")
		overall_distribution_senators.append({"name": alignment, "seats": seats, "share": share})

	for status in district_statuses:
		voter_base = status.pop("voter_base", Decimal("0"))
		status["weight_percentage"] = None
		if voter_base > 0 and overall_registered_total > 0:
			status["weight_percentage"] = (
				voter_base / overall_registered_total
			) * TOTAL_PERCENTAGE

	overall_distributions = []
	if include_deputies:
		overall_distributions.append(
			{
				"label": "Diputados",
				"method": "Método D'Hondt",
				"items": overall_distribution_deputies,
			}
		)
	if include_senators and overall_distribution_senators:
		overall_distributions.append(
			{
				"label": "Senadores",
				"method": "Mayoría 2 + 1 primera minoría",
				"items": overall_distribution_senators,
			}
		)

	if include_senators and not include_deputies:
		overall_distributions = [
			{
				"label": "Senadores",
				"method": "Mayoría 2 + 1 primera minoría",
				"items": overall_distribution_senators,
			}
		]

	stats = [
		{
			"label": "Distritos escrutados",
			"value": total_districts,
			"icon": "fas fa-map",
			"color": "primary",
			"detail": "Datos cargados en el sistema",
		}
	]
	if include_deputies:
		stats.append(
			{
				"label": "Bancas diputados en disputa",
				"value": total_deputy_seats,
				"icon": "fas fa-landmark-flag",
				"color": "success",
				"detail": "Renovación 26 de octubre de 2025",
			}
		)
	if include_senators and total_senate_seats:
		stats.append(
			{
				"label": "Bancas senadores en disputa",
				"value": total_senate_seats,
				"icon": "fas fa-university",
				"color": "info",
				"detail": "Mayoría simple y primera minoría",
			}
		)
	if include_senators and not total_senate_seats:
		stats.append(
			{
				"label": "Bancas senadores en disputa",
				"value": 0,
				"icon": "fas fa-university",
				"color": "info",
				"detail": "Mayoría simple y primera minoría",
			}
		)

	if chamber_filter == DEFAULT_CHAMBER_FILTER:
		total_lists_value = (
			total_lists_by_chamber[List.Chamber.DEPUTIES]
			+ total_lists_by_chamber[List.Chamber.SENATORS]
		)
	elif chamber_filter == List.Chamber.DEPUTIES:
		total_lists_value = total_lists_by_chamber[List.Chamber.DEPUTIES]
	else:
		total_lists_value = total_lists_by_chamber[List.Chamber.SENATORS]

	stats.append(
		{
			"label": "Listas oficializadas",
			"value": total_lists_value,
			"icon": "fas fa-list-ol",
			"color": "warning",
			"detail": FILTER_DETAIL_BY_CHAMBER[chamber_filter],
		}
	)
	stats.append(
		{
			"label": "Última actualización",
			"value": localtime(latest_update).strftime("%d/%m %H:%M") if latest_update else "-",
			"icon": "fas fa-clock",
			"color": "info",
			"detail": "Horario del último escrutinio recibido",
		}
	)

	timeline = [
		{
			"date": date(2025, 10, 26),
			"title": "Elecciones generales",
			"description": "Votación nacional en los 24 distritos electorales",
		},
		{
			"date": date(2025, 10, 27),
			"title": "Escrutinio definitivo",
			"description": "La justicia electoral inicia el cómputo oficial",
		},
		{
			"date": date(2025, 12, 10),
			"title": "Asunción de bancas",
			"description": "Inicio del mandato para las diputadas y diputados electos",
		},
	]

	context = {
		"page_title": "Elecciones Legislativas 2025",
		"stats": stats,
		"overall_distributions": overall_distributions,
		"districts": districts_data,
		"district_statuses": district_statuses,
		"timeline": timeline,
		"chamber_filter": chamber_filter,
		"show_deputies": include_deputies,
		"show_senators": include_senators,
	}
	return render(request, "portal/dashboard.html", context)


def district_detail(request, district_id: int, chamber: str):
	"""Detalle por distrito y cámara con listas, porcentajes y bancas asignadas."""

	try:
		district = District.objects.prefetch_related(
			Prefetch(
				"lists",
				queryset=List.objects.filter(chamber=chamber).prefetch_related(
					Prefetch(
						"scrutiny_records",
						queryset=Scrutiny.objects.order_by("-updated_at"),
					)
				),
			)
		).get(pk=district_id)
	except District.DoesNotExist as exc:
		raise Http404("Distrito inexistente") from exc

	if chamber not in (List.Chamber.DEPUTIES, List.Chamber.SENATORS):
		raise Http404("Cámara inválida")

	title = "Diputados" if chamber == List.Chamber.DEPUTIES else "Senadores"
	method_description = (
		"Método D'Hondt"
		if chamber == List.Chamber.DEPUTIES
		else "Mayoría 2 + 1 primera minoría"
	)

	lists_payload: list[dict] = []
	votes: dict[int, Decimal] = {}
	eligible: dict[int, Decimal] = {}
	latest_update = None

	for election_list in district.lists.all():
		scrutiny = next(iter(election_list.scrutiny_records.all()), None)
		if scrutiny is None:
			continue

		votes[election_list.id] = scrutiny.percentage
		if chamber == List.Chamber.DEPUTIES and scrutiny.percentage >= MIN_PARTY_THRESHOLD:
			eligible[election_list.id] = scrutiny.percentage

		if latest_update is None or scrutiny.updated_at > latest_update:
			latest_update = scrutiny.updated_at

	allocation: dict[int, int]
	if chamber == List.Chamber.DEPUTIES:
		allocation = _dhondt_allocation(eligible, district.renewal_seats)
	else:
		allocation = _senate_allocation(votes, district.senator_renewal_seats)

	total_votes = sum(votes.values())

	for election_list in sorted(
		district.lists.all(),
		key=lambda lst: (
			-(votes.get(lst.id, Decimal("0"))),
			lst.order,
		),
	):
		scrutiny = next(iter(election_list.scrutiny_records.all()), None)
		if scrutiny is None:
			continue

		passes_threshold = chamber == List.Chamber.SENATORS or scrutiny.percentage >= MIN_PARTY_THRESHOLD

		lists_payload.append(
			{
				"id": election_list.id,
				"code": election_list.code or "-",
				"name": election_list.name,
				"alignment": election_list.national_alignment.strip() or election_list.name,
				"percentage": scrutiny.percentage,
				"seats": allocation.get(election_list.id, 0),
				"passes_threshold": passes_threshold,
				"updated_at": scrutiny.updated_at,
			}
		)

	_ensure_full_percentage(lists_payload, latest_update=latest_update)

	context = {
		"page_title": f"Detalle {title} - {district.name}",
		"district": district,
		"chamber": chamber,
		"chamber_label": title,
		"method": method_description,
		"lists": lists_payload,
		"latest_update": latest_update,
		"threshold": MIN_PARTY_THRESHOLD,
	}
	return render(request, "portal/district_detail.html", context)
