from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "districts/<int:district_id>/<str:chamber>/",
        views.district_detail,
        name="district_detail",
    ),
]
