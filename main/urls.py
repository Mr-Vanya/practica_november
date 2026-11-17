from django.urls import path

from . import views

app_name = "main"
urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("product/<int:product_id>/", views.product_detail, name="product_detail"),
    path("how-to-choose/", views.help_page, name="help"),
    path("account/login/", views.login_view, name="login"),
    path("account/register/", views.register_view, name="register"),
    path("account/logout/", views.logout_view, name="logout"),
    path("account/orders/", views.order_list, name="orders"),
    path("account/orders/<int:order_id>/", views.order_detail, name="order_detail"),
]
