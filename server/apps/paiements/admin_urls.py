from django.urls import path

from .admin_remboursements import (ApercuRemboursementView, RembourserSejourView, RemboursementActionView,
                                   RemboursementsView)
from .admin_views import FinancesExportView, FinancesView, TarifsView

urlpatterns = [
    path('tarifs/', TarifsView.as_view(), name='admin-tarifs'),
    path('finances/', FinancesView.as_view(), name='admin-finances'),
    # Refunds (GL-9), before the export route that would catch them
    path('finances/remboursements/', RemboursementsView.as_view(), name='admin-remboursements'),
    path('finances/remboursements/apercu/', ApercuRemboursementView.as_view(), name='admin-remboursement-apercu'),
    path('finances/remboursements/sejour/', RembourserSejourView.as_view(), name='admin-remboursement-sejour'),
    path('finances/remboursements/<uuid:pk>/<str:action>/', RemboursementActionView.as_view(),
         name='admin-remboursement-action'),
    path('finances/<str:format_export>/', FinancesExportView.as_view(), name='admin-finances-export'),
]
