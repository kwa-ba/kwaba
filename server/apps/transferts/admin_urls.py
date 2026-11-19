from django.urls import path

from .admin_views import (
    AeroportView, AeroportsView, ChauffeurPhotoView, ChauffeurView, ChauffeursView, NiveauxChauffeursView,
    SuiviChauffeurView, TarifsView, TransfertAnnulerView, TransfertAttribuerView, TransfertChauffeursView,
    TransfertsView,
)

urlpatterns = [
    path('transferts/aeroports/', AeroportsView.as_view(), name='admin-aeroports'),
    path('transferts/aeroports/<str:pk>/', AeroportView.as_view(), name='admin-aeroport'),
    path('transferts/aeroports/<str:code>/tarifs/', TarifsView.as_view(), name='admin-aeroport-tarifs'),
    path('transferts/chauffeurs/', ChauffeursView.as_view(), name='admin-chauffeurs'),
    path('transferts/chauffeurs/niveaux/', NiveauxChauffeursView.as_view(), name='admin-chauffeurs-niveaux'),
    path('transferts/chauffeurs/<int:pk>/', ChauffeurView.as_view(), name='admin-chauffeur'),
    path('transferts/chauffeurs/<int:pk>/photo/', ChauffeurPhotoView.as_view(), name='admin-chauffeur-photo'),
    path('transferts/chauffeurs/<int:pk>/photo/<str:action>/', ChauffeurPhotoView.as_view(),
         name='admin-chauffeur-photo-action'),
    path('transferts/chauffeurs/<int:pk>/suivi/', SuiviChauffeurView.as_view(), name='admin-chauffeur-suivi'),
    path('transferts/transferts/', TransfertsView.as_view(), name='admin-transferts'),
    path('transferts/transferts/<uuid:pk>/chauffeurs/', TransfertChauffeursView.as_view(), name='admin-transfert-chauffeurs'),
    path('transferts/transferts/<uuid:pk>/attribuer/', TransfertAttribuerView.as_view(), name='admin-transfert-attribuer'),
    path('transferts/transferts/<uuid:pk>/annuler/', TransfertAnnulerView.as_view(), name='admin-transfert-annuler'),
]
