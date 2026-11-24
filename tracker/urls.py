from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "tracker"
urlpatterns = [
    path("", views.home, name="home"),
    path("rates/", views.rates, name="rates"),
    path("chart.png", views.chart_image, name="chart"),
    path("privacy/", views.legal_page, {"template_name": "tracker/privacy.html"}, name="privacy"),
    path("consent/", views.legal_page, {"template_name": "tracker/consent.html"}, name="consent"),
    path("account/", views.dashboard, name="dashboard"),
    path("account/favorites/add/", views.add_favorite, name="add_favorite"),
    path("account/favorites/<int:pk>/remove/", views.remove_favorite, name="remove_favorite"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="tracker/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
