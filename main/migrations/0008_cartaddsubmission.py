import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0007_customerorder_checkout_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="CartAddSubmission",
            fields=[
                (
                    "token",
                    models.UUIDField(
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="Ключ отправки",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "cart",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="add_submissions",
                        to="main.cart",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cart_add_submissions",
                        to="main.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "отправка добавления в корзину",
                "verbose_name_plural": "Отправки добавления в корзину",
            },
        ),
    ]
