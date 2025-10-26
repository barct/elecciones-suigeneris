from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from elections.models import District, List, Scrutiny

from .forms import ScrutinyForm, SelectionForm


class DataEntryView(View):
	template_name = "ingest/data_entry.html"

	def get(self, request):
		selection_form = SelectionForm(request.GET or None)
		list_forms = []
		selected_district = None
		selected_chamber = None

		if selection_form.is_valid():
			selected_district = selection_form.cleaned_data["district"]
			selected_chamber = selection_form.cleaned_data["chamber"]
			lists = (
				selected_district.lists.filter(chamber=selected_chamber)
				.order_by("order", "code")
				.prefetch_related("scrutiny_records")
			)
			scrutinies = {
				record.election_list_id: record
				for record in Scrutiny.objects.filter(election_list__in=lists)
			}
			for election_list in lists:
				scrutiny = scrutinies.get(election_list.id)
				initial_percentage = scrutiny.percentage if scrutiny else None
				form = ScrutinyForm(
					prefix=str(election_list.id),
					initial={"percentage": initial_percentage},
				)
				list_forms.append((election_list, form))

		context = {
			"page_title": "Carga de escrutinios",
			"selection_form": selection_form,
			"list_forms": list_forms,
			"selected_district": selected_district,
			"selected_chamber": selected_chamber,
		}
		return render(request, self.template_name, context)

	def post(self, request):
		selection_form = SelectionForm(request.POST)
		if not selection_form.is_valid():
			return self._render_with_forms(request, selection_form, [], None, None)

		selected_district = selection_form.cleaned_data["district"]
		selected_chamber = selection_form.cleaned_data["chamber"]

		lists = (
			selected_district.lists.filter(chamber=selected_chamber)
			.order_by("order", "code")
			.prefetch_related("scrutiny_records")
		)

		forms_by_list = []
		has_errors = False
		for election_list in lists:
			form = ScrutinyForm(
				data=request.POST,
				prefix=str(election_list.id),
			)
			forms_by_list.append((election_list, form))
			if not form.is_valid():
				has_errors = True

		if has_errors:
			return self._render_with_forms(
				request,
				selection_form,
				forms_by_list,
				selected_district,
				selected_chamber,
			)

		with transaction.atomic():
			for election_list, form in forms_by_list:
				percentage = form.cleaned_data["percentage"]
				Scrutiny.objects.filter(election_list=election_list).delete()
				if percentage is not None:
					Scrutiny.objects.create(
						election_list=election_list,
						percentage=percentage,
					)

		messages.success(request, "Escrutinio actualizado correctamente.")
		redirect_url = f"{reverse('ingest:data-entry')}?district={selected_district.pk}&chamber={selected_chamber}"
		return redirect(redirect_url)

	def _render_with_forms(self, request, selection_form, forms_by_list, district, chamber):
		context = {
			"page_title": "Carga de escrutinios",
			"selection_form": selection_form,
			"list_forms": forms_by_list,
			"selected_district": district,
			"selected_chamber": chamber,
		}
		return render(request, self.template_name, context)
