import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Cart, CartItem, Category, CustomerOrder, Manufacturer, Notification,
    OrderItem, Product, Stock,
)


class ExceptionHandlingTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Стратегические", slug="strategicheskie")
        self.manufacturer = Manufacturer.objects.create(name="Тестовый издатель")
        self.admin = get_user_model().objects.create_user(
            username="manager", password="Strong-Test-Password-42", is_staff=True,
        )

    def make_product(self, *, sku, name, price="1000.00"):
        return Product.objects.create(
            category=self.category,
            manufacturer=self.manufacturer,
            name=name,
            sku=sku,
            description="Тестовая игра",
            price=Decimal(price),
            min_age=8,
            min_players=1,
            max_players=4,
            duration_min=30,
            language="русский",
            is_active=True,
        )

    def test_missing_product_returns_404(self):
        response = self.client.get(reverse("main:product_detail", args=[999999]))

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "404", status_code=404)

    def test_anonymous_order_access_returns_403(self):
        response = self.client.get(reverse("main:orders"))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Доступ запрещён", status_code=403)

    def test_invalid_product_form_does_not_create_product_and_shows_field_error(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("main:manager_product_create"), {
            "category": self.category.pk,
            "manufacturer": self.manufacturer.pk,
            "name": "Неверный диапазон",
            "sku": "BAD-RANGE-1",
            "description": "",
            "price": "1000.00",
            "min_age": "8",
            "min_players": "5",
            "max_players": "2",
            "duration_min": "30",
            "language": "русский",
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        self.assertContains(response, "Число игроков «до» меньше значения «от»")
        self.assertContains(response, "Неверный диапазон")

    def test_failure_mid_checkout_rolls_back_all_changes(self):
        first = self.make_product(sku="ROLLBACK-1", name="Первая игра")
        second = self.make_product(sku="ROLLBACK-2", name="Вторая игра")
        first_stock = Stock.objects.create(product=first, quantity=5)
        second_stock = Stock.objects.create(product=second, quantity=7)
        cart = Cart.objects.create(user=self.admin)
        CartItem.objects.create(cart=cart, product=first, quantity=2)
        CartItem.objects.create(cart=cart, product=second, quantity=3)
        original_create = OrderItem.objects.create
        created_items = 0

        def create_first_then_fail(**kwargs):
            nonlocal created_items
            if created_items == 1:
                raise RuntimeError("Искусственный сбой при создании второй позиции")
            created_items += 1
            return original_create(**kwargs)

        failure_client = Client(raise_request_exception=False)
        failure_client.force_login(self.admin)
        with patch.object(OrderItem.objects, "create", side_effect=create_first_then_fail):
            response = failure_client.post(reverse("main:checkout"), {
                "checkout_token": str(uuid.uuid4()),
                "contact_name": "Иван Покупатель",
                "phone": "+7 900 123 45 67",
                "email": "ivan@example.com",
                "pickup_point": "Самара, тестовый пункт",
            })

        self.assertEqual(response.status_code, 500)
        self.assertEqual(CustomerOrder.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        first_stock.refresh_from_db()
        second_stock.refresh_from_db()
        self.assertEqual(first_stock.quantity, 5)
        self.assertEqual(second_stock.quantity, 7)
        self.assertEqual(CartItem.objects.filter(cart=cart).count(), 2)

    def test_empty_statistics_selection_returns_success(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("main:manager_statistics"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Статистика")
        self.assertEqual(response.context["order_status_bars"], [])
        self.assertEqual(response.context["category_bars"], [])
