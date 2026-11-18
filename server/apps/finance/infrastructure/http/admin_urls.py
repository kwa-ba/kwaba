from django.urls import path

from .admin_views import (AuxiliairesView, BalanceView, ClotureMoisView, ClotureView, ComptesView,
                          ExportComptableView, GrandLivreCompteView, GrandLivreView, LivreJournalView, MouvementsView,
                          PilotageView, RapportExportView, RapportResultatView, RapportsView, ReferentielsView)

urlpatterns = [
    path('grand-livre/', GrandLivreView.as_view(), name='admin-finance-grand-livre'),
    path('pilotage/', PilotageView.as_view(), name='admin-finance-pilotage'),
    path('referentiels/', ReferentielsView.as_view(), name='admin-finance-referentiels'),
    path('mouvements/', MouvementsView.as_view(), name='admin-finance-mouvements'),
    path('livre-journal/', LivreJournalView.as_view(), name='admin-finance-livre-journal'),
    path('comptes/', ComptesView.as_view(), name='admin-finance-comptes'),
    path('comptes/<str:compte>/auxiliaires/', AuxiliairesView.as_view(), name='admin-finance-auxiliaires'),
    path('grand-livre-compte/', GrandLivreCompteView.as_view(), name='admin-finance-grand-livre-compte'),
    path('balance/', BalanceView.as_view(), name='admin-finance-balance'),
    path('export/ecritures/', ExportComptableView.as_view(), name='admin-finance-export-ecritures'),
    path('cloture/', ClotureView.as_view(), name='admin-finance-cloture'),
    path('cloture/<str:mois>/', ClotureMoisView.as_view(), name='admin-finance-cloture-mois'),
    path('rapports/', RapportsView.as_view(), name='admin-finance-rapports'),
    path('rapports/resultat/', RapportResultatView.as_view(), name='admin-finance-rapport-resultat'),
    path('rapports/export/', RapportExportView.as_view(), name='admin-finance-rapport-export'),
]
