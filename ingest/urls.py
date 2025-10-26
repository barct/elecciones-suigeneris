from django.urls import path

from .views import DataEntryView

app_name = "ingest"

urlpatterns = [
    path("", DataEntryView.as_view(), name="data-entry"),
]
