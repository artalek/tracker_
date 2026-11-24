from django.contrib import admin

from .models import Conversion, Currency, ExchangeRate, Favorite

admin.site.site_header = "CurrencyTracker · Администрирование"


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("base_currency", "target_currency", "rate", "date", "updated_at")
    list_filter = ("base_currency", "target_currency", "date")
    search_fields = ("base_currency__code", "target_currency__code")
    date_hierarchy = "date"
    autocomplete_fields = ("base_currency", "target_currency")
    readonly_fields = ("updated_at", "latest_checked_at")


@admin.register(Conversion)
class ConversionAdmin(admin.ModelAdmin):
    list_display = ("user", "base_currency", "target_currency", "amount", "result", "created_at")
    search_fields = ("user__username", "base_currency__code", "target_currency__code")
    date_hierarchy = "created_at"
    list_select_related = True
    readonly_fields = ("user", "base_currency", "target_currency", "amount", "rate", "result", "rate_date", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "base_currency", "target_currency", "created_at")
    search_fields = ("user__username", "base_currency__code", "target_currency__code")
    list_select_related = True
    autocomplete_fields = ("user", "base_currency", "target_currency")
