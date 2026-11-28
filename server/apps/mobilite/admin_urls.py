from django.urls import path

from .admin_views import GammeView, GammesView

urlpatterns = [
    path('mobilite/gammes/', GammesView.as_view(), name='admin-mobilite-gammes'),
    path('mobilite/gammes/<slug:code>/', GammeView.as_view(), name='admin-mobilite-gamme'),
]
