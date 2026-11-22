# Module avis

Avis vérifiés des voyageurs sur les logements : un avis par séjour terminé, dans les 14 jours après le départ, avec une réponse publique de l'hôte. La note affichée d'un logement ne vient que de ces avis.

Décision liée : [ADR-040](../ADR/ADR-040-signalement-des-avis.md) (signalement des avis).

## Routes

| Route | Rôle |
|---|---|
| `GET /api/v1/avis/?hebergement=<id>` | Avis publics d'un logement et leur résumé (moyenne, critères, répartition) |
| `POST /api/v1/avis/` | Laisser un avis sur un séjour terminé |
| `GET /api/v1/avis/a-laisser/` | Séjours que le voyageur peut encore évaluer |
| `POST /api/v1/avis/<id>/reponse/` | Réponse de l'hôte, une seule fois |
| `POST /api/v1/avis/<id>/report/` | Signaler un avis (ADR-040) |
| `GET /api/v1/admin/avis/` | Back-office : liste, filtres `q`, `note`, `reported=1` |
| `DELETE /api/v1/admin/avis/<id>/?motif=…` | Back-office : supprimer un avis, la note du logement est recalculée |
| `POST /api/v1/admin/avis/<id>/reports/dismiss/` | Back-office : garder l'avis, classer ses signalements |

## Signalement d'un avis

`POST /api/v1/avis/<id>/report/`, connecté :

```json
{"reason": "personal_data", "details": "Le numéro de l'hôte est cité."}
```

- `reason` : `offensive` (injurieux), `fake` (faux avis), `personal_data` (données personnelles), `off_topic` (hors sujet), `other` (autre, `details` obligatoire). `details` : 1000 caractères au plus.
- `201 {"id": "…"}` ; `409 {"code": "already_reported"}` : ce compte a déjà signalé cet avis ; `403 {"code": "own_review"}` : l'auteur ne signale pas son propre avis ; `404` : avis inconnu ; `400` : motif inconnu ou précisions manquantes.
- Tout compte connecté peut signaler, y compris l'hôte du logement.

Au premier signalement en attente d'un avis, les administrateurs de la section « Avis » reçoivent un e-mail. Dans le back-office, page « Avis », filtre « Signalés, à traiter » :

- **Supprimer l'avis** (avec un motif) : ses signalements disparaissent avec lui ;
- **Classer sans suite** : l'avis reste, ses signalements sont marqués traités (`dismissed_at`, `dismissed_by_id`).

Aucun avis n'est masqué automatiquement : seule l'équipe décide. Journal : `review_reported`, `review_reports_dismissed`, `avis_supprime`.

Code : `apps/avis/reports.py` (règles et alerte), `report_views.py` (route publique), `admin_views.py` (back-office).
