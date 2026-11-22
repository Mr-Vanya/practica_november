from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0006_customerorder_return_product_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerorder",
            name="checkout_token",
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
                unique=True,
                verbose_name="Ключ отправки формы",
            ),
        ),
    ]
