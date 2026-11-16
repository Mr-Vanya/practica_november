from django.urls import path

from . import views

app_name = "main"
urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("how-to-choose/", views.help_page, name="help"),
    path("account/login/", views.login_view, name="login"),
]
