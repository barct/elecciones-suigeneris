from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from elections.models import District, List, Scrutiny


class DataEntryViewTests(TestCase):
	def setUp(self):
		self.district = District.objects.create(
			name="Distrito Test",
			renewal_seats=3,
			total_deputies=6,
			registered_voters=1000,
		)
		self.list_a = List.objects.create(
			district=self.district,
			chamber=List.Chamber.DEPUTIES,
			order=1,
			code="A01",
			name="Lista A",
		)
		self.list_b = List.objects.create(
			district=self.district,
			chamber=List.Chamber.DEPUTIES,
			order=2,
			code="B01",
			name="Lista B",
		)

	def test_get_with_selection_returns_lists(self):
		response = self.client.get(
			reverse("ingest:data-entry"),
			{
				"district": self.district.pk,
				"chamber": List.Chamber.DEPUTIES,
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Lista A")
		self.assertContains(response, "Lista B")

	def test_post_updates_scrutiny_records(self):
		Scrutiny.objects.create(election_list=self.list_b, percentage=Decimal("10.00"))

		response = self.client.post(
			reverse("ingest:data-entry"),
			{
				"district": self.district.pk,
				"chamber": List.Chamber.DEPUTIES,
				f"{self.list_a.id}-percentage": "55.50",
				f"{self.list_b.id}-percentage": "",
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		stored_messages = list(get_messages(response.wsgi_request))
		self.assertTrue(any("Escrutinio" in str(message) for message in stored_messages))
		self.assertTrue(
			Scrutiny.objects.filter(election_list=self.list_a, percentage=Decimal("55.50")).exists()
		)
		self.assertFalse(Scrutiny.objects.filter(election_list=self.list_b).exists())
