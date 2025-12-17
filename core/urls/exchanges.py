from django.urls import path

from core import views

urlpatterns = [
    path("", views.exchange_list, name="list"),
    path("add/", views.exchange_create, name="add"),
    path("<int:pk>/edit/", views.exchange_edit, name="edit"),
    path("link/<int:client_pk>/", views.client_exchange_create, name="link_to_client"),
    path("client-link/<int:pk>/edit/", views.client_exchange_edit, name="edit_client_link"),
    path("<int:exchange_pk>/report/", views.report_exchange, name="report"),
    path("ajax/exchanges/", views.get_exchanges_for_client, name="ajax_exchanges"),
]


