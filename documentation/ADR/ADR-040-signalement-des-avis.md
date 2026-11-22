# Titre:
Signalement des avis : un signalement par compte, une alerte à l'équipe, une décision dans le back-office

# Status:
Accepté (22 novembre 2026).

# Contexte :
Les avis des voyageurs sont publiés tels quels sur la fiche des logements. Apple exige, pour une application qui publie le contenu de ses utilisateurs (règle 1.2), un moyen de signaler un contenu choquant et une réaction rapide de l'équipe. L'application mobile ouvre aujourd'hui un e-mail prérempli, en attendant une route.

Le back-office sait déjà supprimer un avis, avec un motif journalisé (`avis_supprime`), et la note du logement est alors recalculée. Il ne sait pas qu'un avis pose problème tant que personne ne le regarde.

La messagerie a sa propre modération (ADR-021), avec une échelle de sanctions. Un avis est un contenu public et unique par séjour : une échelle de sanctions n'a pas de sens ici.

# Options
Option 1 : Garder l'e-mail prérempli. Rien à coder, mais aucun suivi, et Apple attend un mécanisme dans l'application.

Option 2 : Masquer automatiquement un avis à partir de quelques signalements. Réaction immédiate, mais trois comptes suffiraient à faire disparaître un avis négatif légitime.

Option 3 : Un signalement enregistré, une alerte à l'équipe, et une décision humaine dans le back-office (supprimer l'avis ou classer les signalements).

# Décision
Nous retenons l'option 3 (décision de Godwin du 22 novembre 2026).

- **Route** : `POST /api/v1/avis/<id>/report/`, connecté, `{"reason": "...", "details": "..."}`.
  - Motifs : `offensive` (injurieux), `fake` (faux avis), `personal_data` (données personnelles), `off_topic` (hors sujet), `other` (autre, qui exige `details`). `details` : 1000 caractères au plus.
  - Réponses : `201 {"id"}` ; `409 already_reported` si ce compte a déjà signalé cet avis ; `403` pour l'auteur de l'avis ; `404` si l'avis n'existe pas.
  - Tout compte connecté peut signaler, y compris l'hôte du logement.
- **Alerte** : au premier signalement en attente d'un avis, un e-mail aux administrateurs de la section « Avis ». Les signalements suivants du même avis n'en envoient pas.
- **Back-office**, page « Avis » : filtre « Signalés », signalements en attente sous chaque avis (motif, précisions, date, compte), et deux décisions :
  - supprimer l'avis (circuit existant, avec motif) : ses signalements disparaissent avec lui ;
  - classer les signalements sans suite : ils sont marqués traités, avec la personne et la date, et l'avis reste.
- **Journal** : `review_reported`, `review_reports_dismissed`.
- Aucun masquage automatique.

# Conséquences :
positives (bénéfices)
- L'application répond à la règle 1.2 d'Apple avec un vrai suivi.
- Un avis négatif légitime ne peut pas disparaître sous des signalements : seule l'équipe décide.
- Un signalement par compte et par avis : un même compte ne peut pas insister.

négatifs (inconvénients)
- La réaction dépend de l'équipe : l'alerte doit être lue.
- Une table de plus dans le module `avis`.

Impacts futurs
- Un bouton « Signaler » pourra être ajouté sur la fiche du site, avec la même route.
- Si les signalements deviennent nombreux, un tri par nombre de signalements pourra être ajouté au back-office.
