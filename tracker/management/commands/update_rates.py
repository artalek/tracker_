from django.core.management.base import BaseCommand, CommandError

from tracker.models import Currency, Favorite
from tracker.services import RateError, RateService


class Command(BaseCommand):
    help = "Обновляет курсы выбранной базы или основных и избранных пар."

    def add_arguments(self, parser):
        parser.add_argument("--base", help="Базовая валюта, например USD.")
        parser.add_argument("--quotes", help="Коды через запятую. Требует --base.")

    def handle(self, *args, **options):
        currencies = {currency.code: currency for currency in Currency.objects.filter(is_active=True)}
        base = (options["base"] or "").strip().upper()
        quotes = {code.strip().upper() for code in (options["quotes"] or "").split(",") if code.strip()}
        if options["quotes"] is not None and (not base or not quotes):
            raise CommandError("--quotes требует --base и хотя бы один код.")
        unknown = (quotes | ({base} if base else set())) - currencies.keys()
        if unknown:
            raise CommandError(f"Неизвестные или отключённые валюты: {', '.join(sorted(unknown))}.")
        if base:
            groups = {base: (quotes or currencies.keys()) - {base}}
        else:
            groups = {
                code: set(currencies) - {code} for code in ("USD", "EUR") if code in currencies
            }
            favorites = Favorite.objects.filter(base_currency__is_active=True, target_currency__is_active=True)
            for source, target in favorites.values_list("base_currency__code", "target_currency__code").distinct():
                groups.setdefault(source, set()).add(target)
        if not any(groups.values()):
            raise CommandError("Нет пар для обновления.")

        service = RateService()
        incomplete = False
        for source, codes in groups.items():
            if not codes:
                continue
            try:
                snapshots = service.latest(currencies[source], [currencies[code] for code in sorted(codes)], force=True)
            except RateError as exc:
                self.stderr.write(f"{source}: {exc}")
                incomplete = True
                continue
            missing = codes - {code for code, value in snapshots.items() if not value.stale}
            self.stdout.write(f"{source}: обновлено {len(codes) - len(missing)} из {len(codes)}")
            if missing:
                self.stderr.write(f"{source}: нет новых данных для {', '.join(sorted(missing))}")
                incomplete = True
        if incomplete:
            raise CommandError("Не все пары обновлены. Доступные курсы сохранены.")
