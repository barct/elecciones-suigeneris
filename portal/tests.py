from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from elections.models import District, List, Scrutiny


class DashboardViewTests(TestCase):
	def setUp(self):
		district = District.objects.create(
			name="Distrito Test",
			renewal_seats=3,
			total_deputies=6,
			registered_voters=100000,
		)
		lista_a = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="A01",
			name="Lista A",
			national_alignment="Alianza A",
		)
		lista_b = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=2,
			code="B01",
			name="Lista B",
			national_alignment="Alianza B",
		)
		lista_c = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=3,
			code="C01",
			name="Lista C",
			national_alignment="",
		)

		Scrutiny.objects.create(election_list=lista_a, percentage=Decimal("50.00"))
		Scrutiny.objects.create(election_list=lista_b, percentage=Decimal("30.00"))
		Scrutiny.objects.create(election_list=lista_c, percentage=Decimal("20.00"))

	def test_dashboard_renders_successfully(self):
		response = self.client.get(reverse("portal:dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "portal/dashboard.html")

		districts = response.context["districts"]
		self.assertEqual(len(districts), 1)
		self.assertEqual(districts[0]["name"], "Distrito Test")

		seats_by_list = {
			entry["name"]: entry["seats"] for entry in districts[0]["deputies"]["lists"]
		}
		self.assertEqual(seats_by_list["Lista A"], 2)
		self.assertEqual(seats_by_list["Lista B"], 1)
		self.assertEqual(seats_by_list["Lista C"], 0)

	def test_lists_below_threshold_receive_no_seats(self):
		district = District.objects.create(
			name="Distrito Umbral",
			renewal_seats=3,
			total_deputies=6,
			registered_voters=80000,
		)
		major = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="M01",
			name="Mayoritaria",
		)
		minor = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=2,
			code="m02",
			name="Minoritaria",
		)
		Scrutiny.objects.create(election_list=major, percentage=Decimal("94.00"))
		Scrutiny.objects.create(election_list=minor, percentage=Decimal("2.50"))

		response = self.client.get(reverse("portal:dashboard"))
		self.assertEqual(response.status_code, 200)
		district_data = next(entry for entry in response.context["districts"] if entry["name"] == "Distrito Umbral")
		seats = {
			entry["name"]: entry["seats"] for entry in district_data["deputies"]["lists"]
		}
		self.assertEqual(seats["Mayoritaria"], 3)
		self.assertNotIn("Minoritaria", seats)
		self.assertEqual(seats["Otros"], 0)
		otros_entry = next(entry for entry in district_data["deputies"]["lists"] if entry["name"] == "Otros")
		self.assertEqual(otros_entry["percentage_display"], "6.00")

	def test_senate_allocation_majority_and_first_minority(self):
		district = District.objects.create(
			name="Distrito Senado",
			renewal_seats=0,
			total_deputies=3,
			registered_voters=50000,
			senator_renewal_seats=3,
			total_senators=3,
		)
		lista_mayoria = List.objects.create(
			district=district,
			chamber=List.Chamber.SENATORS,
			order=1,
			code="S01",
			name="Mayoría",
			national_alignment="Bloque Mayoritario",
		)
		lista_minoritaria = List.objects.create(
			district=district,
			chamber=List.Chamber.SENATORS,
			order=2,
			code="S02",
			name="Minoría",
			national_alignment="Bloque Minoritario",
		)
		lista_tercera = List.objects.create(
			district=district,
			chamber=List.Chamber.SENATORS,
			order=3,
			code="S03",
			name="Tercera",
			national_alignment="",
		)
		Scrutiny.objects.create(election_list=lista_mayoria, percentage=Decimal("55.00"))
		Scrutiny.objects.create(election_list=lista_minoritaria, percentage=Decimal("35.00"))
		Scrutiny.objects.create(election_list=lista_tercera, percentage=Decimal("10.00"))

		response = self.client.get(reverse("portal:dashboard"))
		self.assertEqual(response.status_code, 200)
		district_data = next(entry for entry in response.context["districts"] if entry["name"] == "Distrito Senado")
		seats = {entry["name"]: entry["seats"] for entry in district_data["senators"]["lists"]}
		self.assertEqual(seats["Mayoría"], 2)
		self.assertEqual(seats["Minoría"], 1)
		self.assertEqual(seats["Tercera"], 0)

	def test_overall_distributions_respect_deputies_filter(self):
		district = District.objects.create(
			name="Distrito Filtro",
			renewal_seats=5,
			total_deputies=10,
			registered_voters=150000,
			senator_renewal_seats=3,
			total_senators=3,
		)
		lista_diputados = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="D01",
			name="Diputados Unidos",
			national_alignment="Unidos",
		)
		lista_senadores = List.objects.create(
			district=district,
			chamber=List.Chamber.SENATORS,
			order=1,
			code="S11",
			name="Senadores Unidos",
			national_alignment="Unidos",
		)
		Scrutiny.objects.create(election_list=lista_diputados, percentage=Decimal("60.00"))
		Scrutiny.objects.create(election_list=lista_senadores, percentage=Decimal("60.00"))

		response = self.client.get(f"{reverse('portal:dashboard')}?chamber=diputados")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["chamber_filter"], "diputados")
		self.assertTrue(response.context["show_deputies"])
		self.assertFalse(response.context["show_senators"])
		labels = [item["label"] for item in response.context["overall_distributions"]]
		self.assertEqual(labels, ["Diputados"])
		stats_labels = [item["label"] for item in response.context["stats"]]
		self.assertIn("Bancas diputados en disputa", stats_labels)
		self.assertNotIn("Bancas senadores en disputa", stats_labels)

	def test_overall_distributions_respect_senators_filter(self):
		district = District.objects.create(
			name="Distrito Senado Filtro",
			renewal_seats=0,
			total_deputies=6,
			registered_voters=80000,
			senator_renewal_seats=3,
			total_senators=3,
		)
		lista_mayoria = List.objects.create(
			district=district,
			chamber=List.Chamber.SENATORS,
			order=1,
			code="SF1",
			name="Frente Provincial",
			national_alignment="Frente Provincial",
		)
		lista_minoritaria = List.objects.create(
			district=district,
			chamber=List.Chamber.SENATORS,
			order=2,
			code="SF2",
			name="Alianza Popular",
			national_alignment="Alianza Popular",
		)
		Scrutiny.objects.create(election_list=lista_mayoria, percentage=Decimal("55.00"))
		Scrutiny.objects.create(election_list=lista_minoritaria, percentage=Decimal("45.00"))

		response = self.client.get(f"{reverse('portal:dashboard')}?chamber=senadores")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["chamber_filter"], "senadores")
		self.assertFalse(response.context["show_deputies"])
		self.assertTrue(response.context["show_senators"])
		labels = [item["label"] for item in response.context["overall_distributions"]]
		self.assertEqual(labels, ["Senadores"])
		stats_labels = [item["label"] for item in response.context["stats"]]
		self.assertIn("Bancas senadores en disputa", stats_labels)
		self.assertNotIn("Bancas diputados en disputa", stats_labels)

	def test_invalid_filter_falls_back_to_default(self):
		response = self.client.get(f"{reverse('portal:dashboard')}?chamber=invalid")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["chamber_filter"], "ambos")

	def test_district_detail_deputies_shows_all_lists(self):
		district = District.objects.create(
			name="Distrito Detalle",
			renewal_seats=5,
			total_deputies=10,
			registered_voters=120000,
		)
		major = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="DD01",
			name="Mayoritaria",
			national_alignment="Bloque Mayoritario",
		)
		minor = List.objects.create(
			district=district,
			chamber=List.Chamber.DEPUTIES,
			order=2,
			code="DD02",
			name="Minoritaria",
			national_alignment="Bloque Mayoritario",
		)
		Scrutiny.objects.create(election_list=major, percentage=Decimal("80.00"))
		Scrutiny.objects.create(election_list=minor, percentage=Decimal("2.00"))

		response = self.client.get(
			reverse("portal:district_detail", args=[district.id, "diputados"])
		)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "portal/district_detail.html")
		self.assertEqual(len(response.context["lists"]), 3)
		minor_entry = next(item for item in response.context["lists"] if item["name"] == "Minoritaria")
		self.assertFalse(minor_entry["passes_threshold"])
		self.assertEqual(minor_entry["seats"], 0)
		placeholder = response.context["lists"][-1]
		self.assertEqual(placeholder["name"], "Otros")
		self.assertEqual(placeholder["percentage"], Decimal("18.00"))
		self.assertEqual(placeholder["percentage_display"], "18.00")
		self.assertEqual(placeholder["seats"], 0)

	def test_district_detail_invalid_chamber_returns_404(self):
		district = District.objects.create(
			name="Distrito Cámara",
			renewal_seats=3,
			total_deputies=6,
			registered_voters=50000,
		)
		response = self.client.get(
			reverse("portal:district_detail", args=[district.id, "concejo"])
		)
		self.assertEqual(response.status_code, 404)

	def test_overall_totals_group_by_alignment(self):
		first_district = District.objects.create(
			name="Distrito Norte",
			renewal_seats=3,
			total_deputies=6,
			registered_voters=120000,
		)
		second_district = District.objects.create(
			name="Distrito Sur",
			renewal_seats=2,
			total_deputies=4,
			registered_voters=90000,
		)

		alianza_norte = List.objects.create(
			district=first_district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="N01",
			name="Alianza Federal Norte",
			national_alignment="Alianza Federal",
		)
		provincias_norte = List.objects.create(
			district=first_district,
			chamber=List.Chamber.DEPUTIES,
			order=2,
			code="N02",
			name="Provincias Unidas",
			national_alignment="Provincias Unidas",
		)
		alianza_sur = List.objects.create(
			district=second_district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="S01",
			name="Alianza Federal Sur",
			national_alignment="Alianza Federal",
		)
		autonomista_sur = List.objects.create(
			district=second_district,
			chamber=List.Chamber.DEPUTIES,
			order=2,
			code="S02",
			name="Autonomista",
			national_alignment="Autonomista",
		)

		Scrutiny.objects.create(election_list=alianza_norte, percentage=Decimal("60.00"))
		Scrutiny.objects.create(election_list=provincias_norte, percentage=Decimal("40.00"))
		Scrutiny.objects.create(election_list=alianza_sur, percentage=Decimal("70.00"))
		Scrutiny.objects.create(election_list=autonomista_sur, percentage=Decimal("30.00"))

		response = self.client.get(reverse("portal:dashboard"))
		self.assertEqual(response.status_code, 200)

		overall_distributions = response.context["overall_distributions"]
		self.assertTrue(overall_distributions)
		deputies_distribution = next(
			item for item in overall_distributions if item["label"] == "Diputados"
		)
		seats_by_alignment = {entry["name"]: entry["seats"] for entry in deputies_distribution["items"]}
		self.assertEqual(seats_by_alignment["Alianza Federal"], 4)
		self.assertGreaterEqual(seats_by_alignment["Provincias Unidas"], 1)
