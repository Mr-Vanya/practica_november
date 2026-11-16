from django.db import migrations


CATEGORIES = [
    ("Стратегические игры", "strategy"),
    ("Кооперативные игры", "cooperative"),
    ("Игры для вечеринок", "party"),
    ("Детские игры", "kids"),
    ("Карточные игры", "card"),
    ("Абстрактные игры", "abstract"),
]


def add_categories(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    for name, slug in CATEGORIES:
        Category.objects.get_or_create(slug=slug, defaults={"name": name})


def keep_categories(apps, schema_editor):
    # Preserve categories if this data migration is rolled back after products use them.
    pass


class Migration(migrations.Migration):
    dependencies = [("main", "0001_initial")]

    operations = [
        migrations.RunPython(add_categories, keep_categories),
    ]
