from django.db import migrations


CURRENCIES = [
    ("AED", "Дирхам ОАЭ", "د.إ"),
    ("AMD", "Армянский драм", "֏"),
    ("AUD", "Австралийский доллар", "A$"),
    ("BYN", "Белорусский рубль", "Br"),
    ("CAD", "Канадский доллар", "C$"),
    ("CHF", "Швейцарский франк", "Fr"),
    ("CNY", "Китайский юань", "¥"),
    ("EUR", "Евро", "€"),
    ("GBP", "Фунт стерлингов", "£"),
    ("INR", "Индийская рупия", "₹"),
    ("JPY", "Японская иена", "¥"),
    ("KGS", "Кыргызский сом", "с"),
    ("KZT", "Казахстанский тенге", "₸"),
    ("PLN", "Польский злотый", "zł"),
    ("RUB", "Российский рубль", "₽"),
    ("TRY", "Турецкая лира", "₺"),
    ("USD", "Доллар США", "$"),
    ("UZS", "Узбекский сум", "so‘m"),
]


def seed_currencies(apps, schema_editor):
    currency = apps.get_model("tracker", "Currency")
    currency.objects.using(schema_editor.connection.alias).bulk_create(
        [currency(code=code, name=name, symbol=symbol) for code, name, symbol in CURRENCIES],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("tracker", "0001_initial")]
    operations = [migrations.RunPython(seed_currencies, reverse_code=migrations.RunPython.noop)]
