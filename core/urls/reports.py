from django.urls import path

from core import views

urlpatterns = [
    path("", views.report_overview, name="overview"),
    path("time-travel/", views.time_travel_report, name="time_travel"),
    path("daily/", views.report_daily, name="daily"),
    path("weekly/", views.report_weekly, name="weekly"),
    path("monthly/", views.report_monthly, name="monthly"),
    path("custom/", views.report_custom, name="custom"),
    path("export/csv/", views.export_report_csv, name="export_csv"),
]


