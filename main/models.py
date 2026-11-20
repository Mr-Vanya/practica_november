from django.conf import settings
from django.core.validators import (
    MinValueValidator, MaxValueValidator, RegexValidator
)
from django.db import models
from django.db.models import Q


class Category(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    slug = models.SlugField("Адрес", max_length=120, unique=True)

    class Meta:
        verbose_name = "категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Manufacturer(models.Model):
    name = models.CharField("Производитель", max_length=120, unique=True)

    class Meta:
        verbose_name = "производитель"
        verbose_name_plural = "Производители"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT,
        related_name="products", verbose_name="Категория"
    )
    manufacturer = models.ForeignKey(
        Manufacturer, on_delete=models.PROTECT,
        related_name="products", verbose_name="Производитель"
    )
    name = models.CharField("Название", max_length=200)
    sku = models.CharField("Артикул", max_length=40, unique=True)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField(
        "Цена", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    min_age = models.PositiveSmallIntegerField(
        "Возраст от", validators=[MinValueValidator(0), MaxValueValidator(99)]
    )
    min_players = models.PositiveSmallIntegerField("Игроков от")
    max_players = models.PositiveSmallIntegerField("Игроков до")
    duration_min = models.PositiveSmallIntegerField(
        "Длительность, минут", null=True, blank=True
    )
    language = models.CharField("Язык", max_length=40, blank=True)
    image = models.ImageField("Изображение", upload_to="products/", blank=True)
    is_active = models.BooleanField("Показывать в каталоге", default=True)

    class Meta:
        verbose_name = "товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0), name="product_price_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(max_players__gte=models.F("min_players")),
                name="product_players_range_valid"
            ),
        ]

    def __str__(self):
        return self.name


class Stock(models.Model):
    product = models.OneToOneField(
        Product, on_delete=models.CASCADE,
        related_name="stock", verbose_name="Товар"
    )
    quantity = models.PositiveIntegerField("Остаток", default=0)

    class Meta:
        verbose_name = "остаток"
        verbose_name_plural = "Остатки"
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product}: {self.quantity} шт."


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="cart", verbose_name="Покупатель"
    )
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "корзина"
        verbose_name_plural = "Корзины"

    def __str__(self):
        return f"Корзина: {self.user}"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE,
        related_name="items", verbose_name="Корзина"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name="cart_items", verbose_name="Товар"
    )
    quantity = models.PositiveSmallIntegerField(
        "Количество", validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = "позиция корзины"
        verbose_name_plural = "Позиции корзины"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"], name="unique_product_in_cart"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1), name="cart_item_quantity_positive"
            ),
        ]

    def __str__(self):
        return f"{self.product} × {self.quantity}"


class OrderStatus(models.Model):
    name = models.CharField("Статус", max_length=40, unique=True)

    class Meta:
        verbose_name = "статус заказа"
        verbose_name_plural = "Статусы заказов"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PromoCode(models.Model):
    code = models.CharField("Промокод", max_length=30, unique=True)
    discount_percent = models.PositiveSmallIntegerField(
        "Скидка, %", validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "промокод"
        verbose_name_plural = "Промокоды"

    def __str__(self):
        return self.code


class CustomerOrder(models.Model):
    RETURN_STATUS_CHOICES = [
        ("", "Возврат не запрошен"),
        ("pending", "Ожидает решения менеджера"),
        ("approved", "Возврат одобрен"),
        ("rejected", "Возврат отклонён"),
    ]

    number = models.CharField("Номер заказа", max_length=30, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="orders", verbose_name="Покупатель"
    )
    status = models.ForeignKey(
        OrderStatus, on_delete=models.PROTECT,
        related_name="orders", verbose_name="Статус"
    )
    promo_code = models.ForeignKey(
        PromoCode, on_delete=models.SET_NULL,
        related_name="orders", null=True, blank=True, verbose_name="Промокод"
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    total = models.DecimalField(
        "Сумма", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    contact_name = models.CharField("Получатель", max_length=120)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("Электронная почта")
    pickup_point = models.CharField("Пункт выдачи", max_length=200)
    return_status = models.CharField(
        "Статус возврата", max_length=20, choices=RETURN_STATUS_CHOICES, blank=True
    )
    return_reason = models.TextField("Причина возврата", blank=True)

    class Meta:
        verbose_name = "заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0), name="order_total_nonnegative"
            ),
        ]

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(
        CustomerOrder, on_delete=models.CASCADE,
        related_name="items", verbose_name="Заказ"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name="order_items", verbose_name="Товар"
    )
    quantity = models.PositiveSmallIntegerField(
        "Количество", validators=[MinValueValidator(1)]
    )
    unit_price = models.DecimalField(
        "Цена на момент заказа", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    class Meta:
        verbose_name = "позиция заказа"
        verbose_name_plural = "Позиции заказа"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "product"], name="unique_product_in_order"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1), name="order_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="order_item_price_nonnegative"
            ),
        ]

    def __str__(self):
        return f"{self.product} × {self.quantity}"


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="reviews", verbose_name="Покупатель"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        related_name="reviews", verbose_name="Товар"
    )
    rating = models.PositiveSmallIntegerField(
        "Оценка", validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    body = models.TextField("Отзыв", blank=True)
    created_at = models.DateTimeField("Дата", auto_now_add=True)

    class Meta:
        verbose_name = "отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="one_review_per_user_product"
            ),
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5),
                name="review_rating_1_to_5"
            ),
        ]

    def __str__(self):
        return f"{self.product}: {self.rating}/5"
