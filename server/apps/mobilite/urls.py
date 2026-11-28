from django.urls import path

from .views import GammesView

urlpatterns = [
    path('gammes/', GammesView.as_view(), name='mobilite-gammes'),
]
