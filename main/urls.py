from django.urls import path
from . import views

app_name = "main"
urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("product/<int:product_id>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/item/<int:item_id>/", views.cart_update, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("account/login/", views.login_view, name="login"),
    path("account/register/", views.register_view, name="register"),
    path("account/logout/", views.logout_view, name="logout"),
    path("account/orders/", views.order_list, name="orders"),
    path("account/orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("account/orders/<int:order_id>/export.csv", views.order_export_csv, name="order_export_csv"),
    path("account/orders/<int:order_id>/cancel/", views.order_cancel, name="order_cancel"),
    path("account/orders/<int:order_id>/return/", views.order_return_request, name="order_return_request"),
    path("account/notifications/", views.notification_list, name="notifications"),
    path("account/notifications/<int:notification_id>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("account/notifications/read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
    path("help/", views.help_page, name="help"),
    path("help/rules/", views.rules_help_page, name="rules_help"),
    path("manager/products/", views.manager_products, name="manager_products"),
    path("manager/products/new/", views.manager_product_create, name="manager_product_create"),
    path("manager/products/<int:product_id>/edit/", views.manager_product_edit, name="manager_product_edit"),
    path("manager/orders/", views.manager_orders, name="manager_orders"),
    path("manager/orders/<int:order_id>/return/", views.manager_return_decision, name="manager_return_decision"),
    path("manager/statistics/", views.manager_statistics, name="manager_statistics"),
    path("api/catalog/", views.catalog_json, name="catalog_json"),
]
