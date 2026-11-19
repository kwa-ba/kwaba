from django.urls import path

from .admin_remboursements import (ApercuRemboursementView, RembourserSejourView, RemboursementActionView,
                                   RemboursementsView)
from .admin_versements import RecuperationRelanceView, VersementRelanceView, VersementsView
from .admin_views import FinancesExportView, FinancesView, RapprochementImportView, TarifsView

urlpatterns = [
    path('tarifs/', TarifsView.as_view(), name='admin-tarifs'),
    path('finances/', FinancesView.as_view(), name='admin-finances'),
    # Refunds (GL-9), before the export route that would catch them
    path('finances/remboursements/', RemboursementsView.as_view(), name='admin-remboursements'),
    path('finances/remboursements/apercu/', ApercuRemboursementView.as_view(), name='admin-remboursement-apercu'),
    path('finances/remboursements/sejour/', RembourserSejourView.as_view(), name='admin-remboursement-sejour'),
    path('finances/remboursements/<uuid:pk>/<str:action>/', RemboursementActionView.as_view(),
         name='admin-remboursement-action'),
    # Payouts to the partners (GL-11) and recoveries (GL-23), before the export route
    path('finances/versements/', VersementsView.as_view(), name='admin-versements'),
    path('finances/versements/<str:type_versement>/<uuid:pk>/relancer/', VersementRelanceView.as_view(),
         name='admin-versement-relancer'),
    path('finances/recuperations/<uuid:pk>/relancer/', RecuperationRelanceView.as_view(),
         name='admin-recuperation-relancer'),
    # Reconciliation with FedaPay (GL-12): reading the provider belongs here
    path('rapprochement/importer/', RapprochementImportView.as_view(), name='admin-rapprochement-importer'),
    path('finances/<str:format_export>/', FinancesExportView.as_view(), name='admin-finances-export'),
]
