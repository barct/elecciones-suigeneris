from django.contrib import admin

from .models import District, List, Scrutiny


class ScrutinyInline(admin.TabularInline):
	model = Scrutiny
	extra = 1
	fields = ("percentage",)


class ListInline(admin.TabularInline):
	model = List
	extra = 1
	fields = ("chamber", "order", "code", "name", "national_alignment")


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
	list_display = (
		"name",
		"renewal_seats",
		"total_deputies",
		"registered_voters",
	)
	search_fields = ("name",)
	inlines = [ListInline]


@admin.register(List)
class ListAdmin(admin.ModelAdmin):
	list_display = ("code", "name", "national_alignment", "district", "chamber", "order")
	list_filter = ("district", "chamber", "national_alignment")
	search_fields = ("code", "name", "national_alignment")
	ordering = ("district__name", "chamber", "order", "code")
	inlines = [ScrutinyInline]


@admin.register(Scrutiny)
class ScrutinyAdmin(admin.ModelAdmin):
	list_display = ("election_list", "percentage", "updated_at")
	list_filter = ("election_list__district",)
	search_fields = ("election_list__name", "election_list__code")
