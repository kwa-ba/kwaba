"""Back-office routes, mounted under /api/v1/admin/documents/."""
from django.urls import path

from .views import (AvoirPdfView, AvoirsARegulariserView, AvoirsView, DocumentCautionPdfView, DocumentsCautionView,
                    JustificatifsView, FacturePdfView, FacturesView,
                    RegulariserFactureView, SignatureRepresentantView, SocieteView)

urlpatterns = [
    path('societe/', SocieteView.as_view(), name='documents-societe'),
    path('societe/signature/', SignatureRepresentantView.as_view(), name='documents-societe-signature'),
    path('factures/', FacturesView.as_view(), name='documents-factures'),
    path('factures/<uuid:pk>/pdf/', FacturePdfView.as_view(), name='documents-facture-pdf'),
    path('factures/<uuid:pk>/avoir/', RegulariserFactureView.as_view(), name='documents-facture-avoir'),
    path('avoirs/', AvoirsView.as_view(), name='documents-avoirs'),
    path('avoirs/a-regulariser/', AvoirsARegulariserView.as_view(), name='documents-avoirs-a-regulariser'),
    path('avoirs/<uuid:pk>/pdf/', AvoirPdfView.as_view(), name='documents-avoir-pdf'),
    path('cautions/', DocumentsCautionView.as_view(), name='documents-cautions'),
    path('cautions/<str:numero>/pdf/', DocumentCautionPdfView.as_view(), name='documents-caution-pdf'),
    path('justificatifs/', JustificatifsView.as_view(), name='documents-justificatifs'),
    path('justificatifs/<uuid:pk>/', JustificatifsView.as_view(), name='documents-justificatif'),
]
