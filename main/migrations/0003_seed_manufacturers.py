from django.db import migrations


MANUFACTURERS = [
    "Производитель1",
    "Производитель2",
    "Производитель3",
    "Производитель4",
    "Производитель5",
]


def add_manufacturers(apps, schema_editor):
    Manufacturer = apps.get_model("main", "Manufacturer")
    for name in MANUFACTURERS:
        Manufacturer.objects.get_or_create(name=name)


def keep_manufacturers(apps, schema_editor):
    # Keep the rows on rollback so products using them are not affected.
    pass


class Migration(migrations.Migration):
    dependencies = [("main", "0002_seed_game_categories")]

    operations = [
        migrations.RunPython(add_manufacturers, keep_manufacturers),
    ]
