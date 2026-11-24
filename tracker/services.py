import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

import requests
from django.core.cache import cache
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from .models import Conversion, ExchangeRate

logger = logging.getLogger(__name__)
RATE_STEP = Decimal("0.000000000001")
RESULT_STEP = Decimal("0.000001")
REFRESH_INTERVAL = timedelta(hours=6)
RETRY_DELAY_SECONDS = 60


class RateError(Exception):
    """Ошибка источника курсов или неподдерживаемая пара."""


@dataclass(frozen=True)
class RatePoint:
    date: date
    quote: str
    rate: Decimal


@dataclass(frozen=True)
class RateSnapshot:
    rate: Decimal
    date: date
    stale: bool = False


class FrankfurterClient:
    url = "https://api.frankfurter.dev/v2/rates"

    def rates(self, base, quotes, *, start=None, end=None):
        params = {"base": base, "quotes": ",".join(quotes)}
        if start is not None:
            params.update({"from": start.isoformat(), "to": end.isoformat()})
        try:
            response = requests.get(
                self.url, params=params, timeout=(3, 5), allow_redirects=False,
            )
            if response.status_code != 200:
                raise RateError(f"Frankfurter HTTP {response.status_code}")
            payload = response.json(parse_float=Decimal)
            if not isinstance(payload, list):
                raise ValueError("expected a list of rates")
            points = {}
            today = timezone.localdate()
            for row in payload:
                quote = row["quote"]
                day = date.fromisoformat(row["date"])
                rate = Decimal(str(row["rate"]))
                if (
                    row["base"] != base or quote not in quotes
                    or day > today
                    or (start is not None and not start <= day <= end)
                    or not rate.is_finite() or not 0 < rate < Decimal("1e11")
                ):
                    raise ValueError("invalid rate")
                rate = rate.quantize(RATE_STEP, rounding=ROUND_HALF_UP)
                if not 0 < rate < Decimal("1e11"):
                    raise ValueError("rate outside storage precision")
                points[day, quote] = RatePoint(day, quote, rate)
        except (requests.RequestException, ValueError, TypeError, KeyError, InvalidOperation) as exc:
            raise RateError("Ошибка ответа Frankfurter.") from exc
        return sorted(points.values(), key=lambda point: (point.date, point.quote))


class RateService:
    def __init__(self, client=None):
        self.client = client if client is not None else FrankfurterClient()

    def _save(self, base, targets, points, *, latest=False):
        now = timezone.now() if latest else None
        fields = ["rate", "updated_at"]
        if latest:
            fields.append("latest_checked_at")
        ExchangeRate.objects.bulk_create(
            [
                ExchangeRate(
                    base_currency=base, target_currency=targets[point.quote],
                    date=point.date, rate=point.rate, latest_checked_at=now,
                )
                for point in points
            ],
            update_conflicts=True, update_fields=fields,
            unique_fields=["base_currency", "target_currency", "date"],
        )

    def latest(self, base, currencies, *, force=False):
        targets = {currency.code: currency for currency in currencies if currency.pk != base.pk}
        if not targets:
            return {}
        queryset = ExchangeRate.objects.filter(base_currency=base, target_currency__in=targets.values())
        newest = queryset.filter(target_currency_id=OuterRef("target_currency_id")).order_by("-date")
        rows = queryset.filter(pk=Subquery(newest.values("pk")[:1])).select_related("target_currency")
        saved = {row.target_currency.code: row for row in rows}
        cutoff = timezone.now() - REFRESH_INTERVAL
        pending = [
            code for code in targets
            if force or code not in saved
            or not saved[code].latest_checked_at or saved[code].latest_checked_at < cutoff
        ]
        retry_keys = {code: f"tracker:latest-retry:{base.code}:{code}" for code in pending}
        retry_later = cache.get_many(retry_keys.values()) if retry_keys and not force else {}
        requested = [code for code in pending if retry_keys[code] not in retry_later]
        downloaded = {}
        if requested:
            try:
                points = self.client.rates(base.code, requested)
                self._save(base, targets, points, latest=True)
                downloaded = {point.quote: point for point in points}
            except RateError as exc:
                if force:
                    raise
                logger.warning("Не удалось обновить курсы %s: %s", base.code, exc)
            missing = {retry_keys[code]: True for code in requested if code not in downloaded}
            if missing:
                cache.set_many(missing, timeout=RETRY_DELAY_SECONDS)
            if force and downloaded:
                cache.delete_many([retry_keys[code] for code in downloaded])
        snapshots = {}
        for code, row in saved.items():
            snapshots[code] = RateSnapshot(row.rate, row.date, code in pending)
        for code, point in downloaded.items():
            if code not in saved or point.date >= saved[code].date:
                snapshots[code] = RateSnapshot(point.rate, point.date)
        return snapshots

    def history(self, base, target, days):
        end = timezone.localdate()
        start = end - timedelta(days=days - 1)
        key = f"tracker:history:{base.code}:{target.code}:{days}:{end}"
        rows = ExchangeRate.objects.filter(
            base_currency=base, target_currency=target, date__range=(start, end),
        ).order_by("date")
        refreshed = cache.get(key)
        if refreshed is None:
            try:
                points = self.client.rates(base.code, [target.code], start=start, end=end)
                if not points:
                    raise RateError("За этот период нет опубликованных курсов.")
                self._save(base, {target.code: target}, points)
                cache.set(key, True, timeout=int(REFRESH_INTERVAL.total_seconds()))
                refreshed = True
            except RateError as exc:
                logger.warning("Не удалось обновить историю %s/%s: %s", base.code, target.code, exc)
                cache.set(key, False, timeout=RETRY_DELAY_SECONDS)
                refreshed = False
        return list(rows.values_list("date", "rate")), not refreshed


@dataclass(frozen=True)
class ConversionResult:
    amount: Decimal
    result: Decimal
    rate: Decimal
    rate_date: date
    stale: bool


class CurrencyConverter:
    def __init__(self, rates=None):
        self.rates = rates if rates is not None else RateService()

    def convert(self, amount, base, target, *, user=None):
        if base.pk == target.pk:
            snapshot = RateSnapshot(Decimal(1), timezone.localdate())
        else:
            snapshot = self.rates.latest(base, [target]).get(target.code)
            if snapshot is None:
                raise RateError("Курс для этой пары сейчас недоступен. Попробуйте позже.")
        with localcontext() as context:
            context.prec = 45
            result = (amount * snapshot.rate).quantize(RESULT_STEP, rounding=ROUND_HALF_UP)
        if user is not None and user.is_authenticated:
            Conversion.objects.create(
                user=user, base_currency=base, target_currency=target,
                amount=amount, result=result, rate=snapshot.rate, rate_date=snapshot.date,
            )
        return ConversionResult(amount, result, snapshot.rate, snapshot.date, snapshot.stale)
