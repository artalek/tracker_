from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q


class Currency(models.Model):
    code = models.CharField(
        "код", max_length=3, unique=True,
        validators=[RegexValidator(r"^[A-Z]{3}\Z", "Введите три заглавные латинские буквы.")],
    )
    name = models.CharField("название", max_length=100)
    symbol = models.CharField("символ", max_length=8, blank=True)
    is_active = models.BooleanField("доступна для операций", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "валюта"
        verbose_name_plural = "валюты"

    def __str__(self):
        return f"{self.code} · {self.name}"


class ExchangeRate(models.Model):
    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    target_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    rate = models.DecimalField(max_digits=23, decimal_places=12)
    date = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)
    latest_checked_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "курс"
        verbose_name_plural = "курсы"
        constraints = [
            models.UniqueConstraint(
                fields=["base_currency", "target_currency", "date"], name="unique_pair_date",
            ),
            models.CheckConstraint(condition=Q(rate__gt=0), name="exchange_rate_positive"),
            models.CheckConstraint(
                condition=~Q(base_currency=F("target_currency")), name="exchange_pair_distinct",
            ),
        ]

    def __str__(self):
        return f"{self.base_currency.code}/{self.target_currency.code} · {self.date}"


class Conversion(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    target_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=16, decimal_places=6)
    result = models.DecimalField(max_digits=28, decimal_places=6)
    rate = models.DecimalField(max_digits=23, decimal_places=12)
    rate_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "конвертация"
        verbose_name_plural = "конвертации"
        indexes = [models.Index(fields=["user", "-created_at", "-id"], name="conversion_user_recent")]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="conversion_amount_positive"),
            models.CheckConstraint(condition=Q(rate__gt=0, result__gte=0), name="conversion_values_valid"),
        ]

    def __str__(self):
        return f"{self.amount} {self.base_currency.code} → {self.result} {self.target_currency.code}"


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    target_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "избранная пара"
        verbose_name_plural = "избранные пары"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "base_currency", "target_currency"], name="unique_user_pair",
            ),
            models.CheckConstraint(
                condition=~Q(base_currency=F("target_currency")), name="favorite_pair_distinct",
            ),
        ]

    def __str__(self):
        return f"{self.base_currency.code}/{self.target_currency.code}"
