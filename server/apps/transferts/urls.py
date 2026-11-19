from django.urls import path

from .views import (
    AeroportsView, AvisChauffeurTransfertView, CompteRemboursementTransfertView, DevisView, PayerTransfertView,
    TransfertsView, TransfertView,
)

urlpatterns = [
    path('aeroports/', AeroportsView.as_view(), name='transferts-aeroports'),
    path('devis/', DevisView.as_view(), name='transferts-devis'),
    path('', TransfertsView.as_view(), name='transferts'),
    path('<uuid:pk>/', TransfertView.as_view(), name='transfert'),
    path('<uuid:pk>/payer/', PayerTransfertView.as_view(), name='transfert-payer'),
    path('<uuid:pk>/avis-chauffeur/', AvisChauffeurTransfertView.as_view(), name='transfert-avis-chauffeur'),
    path('<uuid:pk>/compte-remboursement/', CompteRemboursementTransfertView.as_view(), name='transfert-compte-remboursement'),
]
