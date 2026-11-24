from base64 import b64decode
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ConversionForm
from .models import Conversion, Currency, ExchangeRate, Favorite
from .services import FrankfurterClient, RateError, RateService


def mock_response(*, rows=(), status=200):
    response = Mock(status_code=status)
    response.json.return_value = list(rows)
    return response


def observation(base="USD", quote="EUR", rate="0.925123456789", days_ago=0):
    return {
        "base": base, "quote": quote, "rate": Decimal(rate),
        "date": (timezone.localdate() - timedelta(days=days_ago)).isoformat(),
    }


class FrankfurterTests(TestCase):
    @patch("tracker.services.requests.get")
    def test_v2_history_params_and_decimal(self, get):
        get.return_value = mock_response(rows=[observation(days_ago=1)])
        start, end = timezone.localdate() - timedelta(days=6), timezone.localdate()
        entries = FrankfurterClient().rates("USD", ["EUR"], start=start, end=end)
        self.assertEqual(entries[0].rate, Decimal("0.925123456789"))
        self.assertEqual(get.call_args.kwargs["params"], {
            "base": "USD", "quotes": "EUR", "from": start.isoformat(), "to": end.isoformat(),
        })
        get.return_value.json.assert_called_once_with(parse_float=Decimal)
        self.assertEqual(get.call_args.kwargs["timeout"], (3, 5))

    @patch("tracker.services.requests.get")
    def test_malformed_http_error_and_timeout(self, get):
        for response in (
            mock_response(status=429),
            mock_response(rows=[{"unexpected": True}]),
            mock_response(rows=[observation(rate="NaN")]),
            mock_response(rows=[observation(quote="GBP")]),
            mock_response(rows=[observation(rate="0.0000000000001")]),
        ):
            with self.subTest(response=response):
                get.return_value = response
                with self.assertRaises(RateError):
                    FrankfurterClient().rates("USD", ["EUR"])
        get.side_effect = requests.Timeout
        with self.assertRaises(RateError):
            FrankfurterClient().rates("USD", ["EUR"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TrackerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usd = Currency.objects.get(code="USD")
        cls.eur = Currency.objects.get(code="EUR")
        cls.jpy = Currency.objects.get(code="JPY")
        cls.owner = get_user_model().objects.create_user("owner", password="long-test-password42")
        cls.other = get_user_model().objects.create_user("other")

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @patch("tracker.services.requests.get")
    def test_latest_is_cached_and_falls_back_after_timeout(self, get):
        get.return_value = mock_response(rows=[observation()])
        service = RateService()
        first = service.latest(self.usd, [self.eur])["EUR"]
        self.assertFalse(first.stale)
        get.assert_called_once()
        self.assertEqual(service.latest(self.usd, [self.eur])["EUR"], first)
        get.assert_called_once()
        ExchangeRate.objects.update(latest_checked_at=timezone.now() - timedelta(hours=7))
        get.side_effect = requests.Timeout
        result = service.latest(self.usd, [self.eur])["EUR"]
        self.assertTrue(result.stale)
        self.assertEqual(result.rate, first.rate)
        self.assertEqual(result.date, first.date)
        self.assertTrue(service.latest(self.usd, [self.eur])["EUR"].stale)
        self.assertEqual(get.call_count, 2)

    @patch("tracker.services.requests.get")
    def test_list_rates_distinguishes_missing_pairs(self, get):
        get.return_value = mock_response(rows=[observation()])
        response = self.client.get(reverse("tracker:rates"), {"base": "USD"})
        self.assertContains(response, "0,925123")
        self.assertNotContains(response, "0,9251234")
        self.assertContains(response, "Недоступен")
        self.assertContains(response, "График")
        self.assertEqual(get.call_args.kwargs["params"]["base"], "USD")

    @patch("tracker.services.requests.get")
    def test_chart_png_cache_and_fallback(self, get):
        get.return_value = mock_response(rows=[observation(days_ago=3), observation()])
        url = reverse("tracker:chart")
        params = {"base": "USD", "target": "EUR", "days": 7}
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Rate-Points"], "2")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))
        get.assert_called_once()
        self.client.get(url, params)
        get.assert_called_once()
        cache.clear()
        get.side_effect = requests.Timeout
        response = self.client.get(url, params)
        self.assertEqual(response["X-Rate-Stale"], "1")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self.client.get(url, params)["X-Rate-Stale"], "1")
        self.assertEqual(get.call_count, 2)
        self.assertEqual(self.client.get(url, {**params, "target": "JPY"}).status_code, 503)
        self.assertEqual(self.client.get(url, {**params, "days": 700}).status_code, 400)

    @patch("tracker.services.requests.get")
    def test_interactive_chart_uses_exact_observation_dates_and_at_most_three_decimals(self, get):
        get.return_value = mock_response(rows=[
            observation(days_ago=3, rate="0.90123"),
            observation(rate="0.912345"),
        ])
        response = self.client.get(reverse("tracker:chart"), {
            "base": "USD", "target": "EUR", "days": 7, "format": "interactive",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(b64decode(data["image"]).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(len(data["points"]), 2)
        first, last = data["points"]
        self.assertEqual(last["date"], timezone.localdate().strftime("%d.%m.%Y"))
        self.assertEqual(last["rate"], "0,912")
        self.assertEqual(first["rate"], "0,901")
        self.assertLess(first["x"], last["x"])
        self.assertGreater(first["y"], last["y"])
        for point in data["points"]:
            self.assertLessEqual(data["bounds"]["left"], point["x"])
            self.assertLessEqual(point["x"], data["bounds"]["right"])
            self.assertLessEqual(data["bounds"]["top"], point["y"])
            self.assertLessEqual(point["y"], data["bounds"]["bottom"])
        get.assert_called_once()

    @override_settings(PRIVACY_OPERATOR_NAME="Пример оператора", PRIVACY_CONTACT_EMAIL="contact@example.com")
    def test_legal_pages_are_public_and_linked_from_registration(self):
        for name in ("privacy", "consent"):
            url = reverse(f"tracker:{name}")
            response = self.client.get(url)
            self.assertContains(response, "Пример оператора")
            self.assertContains(response, 'href="mailto:contact@example.com"')
            self.assertContains(response, "© AAC. Все права защищены.")
            self.assertContains(self.client.get(reverse("tracker:register")), f'href="{url}"')

    @patch("tracker.services.requests.get")
    def test_conversion_prg_guest_and_history_owner(self, get):
        get.return_value = mock_response(rows=[observation(rate="0.925")])
        url = reverse("tracker:home")
        data = {"amount": "12,50", "base": "USD", "target": "EUR"}
        guest = self.client.post(url, data, follow=True)
        self.assertContains(guest, "11,563")
        self.assertFalse(Conversion.objects.exists())

        self.client.force_login(self.owner)
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, "11,563")
        operation = Conversion.objects.get(user=self.owner)
        self.assertEqual(operation.amount, Decimal("12.50"))
        self.assertEqual(operation.result, Decimal("11.562500"))
        self.assertEqual(operation.rate, Decimal("0.925"))
        self.client.get(response.redirect_chain[-1][0])
        self.assertEqual(Conversion.objects.count(), 1)
        account = reverse("tracker:dashboard")
        self.assertContains(self.client.get(account), "11,563")
        self.client.force_login(self.other)
        own_page = self.client.get(account)
        self.assertNotContains(own_page, "11,563")
        self.assertIn("no-store", own_page["Cache-Control"])

    @patch("tracker.services.requests.get")
    def test_unavailable_conversion_has_feedback_and_no_history(self, get):
        get.side_effect = requests.Timeout
        self.client.force_login(self.owner)
        response = self.client.post(reverse("tracker:home"), {"amount": "12", "base": "JPY", "target": "EUR"})
        self.assertContains(response, "Курс для этой пары сейчас недоступен.")
        self.assertFalse(Conversion.objects.exists())

    def test_decimal_and_currency_validation(self):
        values = {"base": "USD", "target": "EUR"}
        for amount in ("0", "-1", "NaN", "Infinity", "0.0000001", "10000000000", "oops"):
            with self.subTest(amount=amount):
                self.assertFalse(ConversionForm({**values, "amount": amount}).is_valid())
        self.assertTrue(ConversionForm({**values, "amount": "1,125"}).is_valid())
        self.assertFalse(ConversionForm({**values, "base": "XYZ", "amount": "1"}).is_valid())

    def test_same_currency_uses_identity_without_api(self):
        from .services import CurrencyConverter

        rates = Mock()
        result = CurrencyConverter(rates).convert(Decimal("12.50"), self.usd, self.usd)
        self.assertEqual(result.result, Decimal("12.50"))
        self.assertEqual(result.rate, Decimal("1"))
        rates.latest.assert_not_called()

    def test_registration_login_logout_and_dashboard_redirect(self):
        dashboard = reverse("tracker:dashboard")
        self.assertRedirects(self.client.get(dashboard), f"{reverse('tracker:login')}?next={dashboard}")
        password = "demo_user-password-918!"
        self.assertRedirects(self.client.post(reverse("tracker:register"), {
            "username": "newstudent", "email": "student@example.com",
            "password1": password, "password2": password,
        }), dashboard)
        self.assertEqual(self.client.get(reverse("tracker:logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("tracker:logout")), reverse("tracker:home"), fetch_redirect_response=False)
        self.assertRedirects(self.client.post(reverse("tracker:login"), {
            "username": "newstudent", "password": password,
        }), dashboard)

    def test_favorites_are_private_idempotent_and_post_only(self):
        add = reverse("tracker:add_favorite")
        dashboard = reverse("tracker:dashboard")
        self.client.force_login(self.owner)
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse("tracker:home"), {}).status_code, 403)
        self.assertEqual(self.client.get(add).status_code, 405)
        for _ in range(2):
            self.assertRedirects(self.client.post(add, {"base": "USD", "target": "EUR"}), dashboard)
        pair = Favorite.objects.get()
        self.assertEqual(pair.user, self.owner)
        self.assertContains(self.client.get(dashboard), "USD / EUR")
        remove = reverse("tracker:remove_favorite", args=[pair.pk])
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(dashboard), "USD / EUR")
        self.assertEqual(self.client.post(remove).status_code, 404)
        self.assertTrue(Favorite.objects.filter(pk=pair.pk).exists())
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(remove).status_code, 405)
        self.assertRedirects(self.client.post(remove), dashboard)
        self.assertFalse(Favorite.objects.exists())

    def test_unique_pair_date_database_constraint(self):
        values = {"base_currency": self.usd, "target_currency": self.eur, "date": timezone.localdate(), "rate": 1}
        ExchangeRate.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExchangeRate.objects.create(**values)

    @patch("tracker.services.requests.get")
    def test_update_rates_idempotence_and_failure(self, get):
        get.return_value = mock_response(rows=[observation()])
        for _ in range(2):
            call_command("update_rates", base="usd", quotes="eur", stdout=StringIO())
        self.assertEqual(ExchangeRate.objects.count(), 1)
        self.assertEqual(get.call_count, 2)
        get.return_value = mock_response(status=503)
        with self.assertRaises(CommandError):
            call_command("update_rates", base="USD", quotes="EUR", stderr=StringIO())
        self.assertEqual(ExchangeRate.objects.count(), 1)
