# Module transferts aéroport

Un chauffeur partenaire attend le voyageur à l'aéroport et le conduit à son logement.
Code : `server/apps/transferts/` (backend), `client/src/app/(main)/transfert/` et `client/src/app/(main)/profil/transferts/` (frontend).

## Principe

Kwa-Ba ne gère pas de flotte : il travaille avec des **chauffeurs partenaires indépendants**, enregistrés dans l'admin Django. Le voyageur paie la course en ligne (FedaPay ou PayPal, via `apps.paiements`) ; Kwa-Ba paie le chauffeur par Mobile Money après la course, moins sa commission.

```
Voyageur ──paie 10 000 FCFA──▶ Kwa-Ba
                                 │  chauffeur attribué par l'équipe, payé 24 h après la prise en charge
                                 ├──▶ Chauffeur : 8 000 FCFA (Mobile Money)
                                 └──▶ Kwa-Ba : 2 000 FCFA (commission de 20 %)
```

## Cycle

| Étape | Statut | Qui |
|---|---|---|
| Réservation (vol, véhicule, destination, téléphone) | `en_attente_paiement` — 30 min pour payer | Voyageur |
| Paiement reçu | `confirme` — email au voyageur, alerte « chauffeur à attribuer » aux administrateurs | Worker |
| Chauffeur choisi dans l'admin (`/admin/transferts/transfertmodel/`) | `chauffeur_assigne` — le voyageur reçoit nom, téléphone, véhicule et plaque ; le chauffeur reçoit la course s'il a un email ; son versement est planifié | Admin |
| Versement du chauffeur (arrivée + 24 h) | `termine` | Worker |

- Arrivée dans moins de 24 h sans chauffeur : alerte « URGENT » aux administrateurs.
- L'admin ne propose que les chauffeurs actifs de cet aéroport dont le véhicule est assez grand.
- Pas de chauffeur disponible : action « Annuler et rembourser intégralement » dans la liste des transferts.

## Règles (`tarifs.py`)

| Règle | Valeur |
|---|---|
| Véhicules | Berline (3 passagers, 3 bagages), SUV confort (4, 4), Minibus (7, 8) |
| Majoration de nuit (arrivée entre 22 h et 6 h, heure locale) | +25 %, arrondi aux 500 FCFA |
| Commission Kwa-Ba | 20 % du prix de la course |
| Délai minimum de réservation | 6 h avant l'atterrissage |
| Annulation gratuite | jusqu'à 24 h avant l'arrivée ; ensuite rien n'est remboursé (le chauffeur reste payé) |
| Attente incluse | 60 min après l'heure d'arrivée |
| Versement au chauffeur | arrivée + 24 h |

Les **prix de base** par aéroport et par véhicule sont dans l'admin (Aéroports → tarifs). La migration `0002_aeroports_tarifs` crée les aéroports de lancement avec des **tarifs indicatifs à valider** :

| Aéroport | Berline | SUV | Minibus |
|---|---|---|---|
| Lomé (LFW), Cotonou (COO), Ouagadougou (OUA) | 10 000 | 15 000 | 25 000 |
| Niamey (NIM) | 12 000 | 18 000 | 30 000 |
| Bamako (BKO) | 15 000 | 22 000 | 35 000 |

## Heures et fuseaux

Le voyageur saisit l'heure de son billet (heure locale de l'aéroport). Elle est enregistrée avec le fuseau de l'aéroport (`AeroportModel.fuseau`) : Lomé, Ouagadougou et Bamako sont en UTC+0, Cotonou et Niamey en UTC+1. L'API renvoie `arrivee` (UTC) et `arrivee_locale` (heure du billet).

## API (`/api/v1/transferts/`)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `aeroports/` | Aéroports ouverts (public) |
| GET | `devis/?aeroport=LFW&arrivee=2026-11-02T23:30&passagers=2&bagages=3` | Véhicules, prix, disponibilité (public) |
| GET / POST | `` | Mes transferts (`?reservation=<id>` pour ceux d'un séjour) / réserver |
| GET / DELETE | `<id>/` | Détail (relit le paiement en attente) / annuler → `{rembourse, numero_requis}` |
| POST | `<id>/payer/` | `{moyen}` → `{url}` de la page de paiement |
| PUT | `<id>/compte-remboursement/` | Compte Mobile Money pour le remboursement |

## Photo, niveaux et avis des chauffeurs (décisions du 19 novembre 2026)

Décision : [ADR-027](../ADR/ADR-027-chauffeurs-photo-avis-niveaux.md).

- **Photo de profil obligatoire** : l'équipe l'ajoute dans le back-office (Transferts → Chauffeurs, fiche du chauffeur ; JPEG, PNG ou WebP, 400 px au moins, réencodée sans métadonnées), puis la **valide** (un visage net, celui du chauffeur). Sans photo validée, un chauffeur ne reçoit **aucune course ni mission** : il n'est pas proposé à l'attribution (transferts et locations avec chauffeur), et l'attribution est refusée. Une nouvelle photo attend une nouvelle validation.
- **Ce que voit le voyageur** : une fois le chauffeur attribué, sa photo et son niveau sur la page du transfert (et de la location avec chauffeur, sans son nom ni son numéro, qui restent dans l'email), et son niveau dans l'email d'attribution.
- **Avis du voyageur** : après la course (transfert effectué, location avec chauffeur terminée), un email lui demande une fois une note de 1 à 5, la ponctualité, la conduite, l'amabilité et un commentaire facultatif (`POST /api/v1/transferts/<id>/avis-chauffeur/`, `POST /api/v1/locations/<id>/avis-chauffeur/`). Un seul avis par course, vu par l'équipe seulement (`transferts_avis_chauffeur`).
- **Incidents** : l'équipe enregistre un incident grave, un retard de plus de 15 min, une absence, une plainte fondée, un accident responsable ou un autre fait (fiche du chauffeur, « Suivi » : `POST /api/v1/admin/transferts/chauffeurs/<id>/suivi/`). Un **incident grave retire l'Excellence immédiatement** (ligne d'historique signée par l'agent qui l'enregistre).
- **Niveaux** Standard et Excellence, règle du livre (charte B6, résolution 4 ; décision du 26 novembre 2026, T-H24 : le niveau Confirmé est retiré, migration `transferts 0008` qui repasse les Confirmé en Standard avec une ligne d'historique) (`niveaux.py`) : chaque trimestre, l'appli propose le niveau de chaque chauffeur d'après les 3 derniers mois (`chauffeur_niveau_periode_mois`) : ses missions (transferts effectués et locations terminées), sa note moyenne, ses incidents. **Excellence** : 20 missions (`chauffeur_excellence_courses`), 10 pendant le **Programme Fondateurs** (`chauffeur_excellence_courses_fondateur` ; dates `fondateur_debut` / `fondateur_fin` sur la fiche, préremplies pour les 10 premiers chauffeurs sur 6 mois), une note de 4,7 (`chauffeur_excellence_note`) et, sur la période, aucun retard > 15 min, absence, plainte fondée, accident responsable ni incident grave. Sinon Standard ; sans avis, Standard. L'équipe **valide** ou corrige chaque proposition (un motif quand elle s'en écarte) : `transferts_niveau_chauffeur` garde l'avant, l'après, la proposition, le motif et les chiffres ; journal `backoffice_modification`. Le niveau Excellence donne la part de 6 500 F par jour (le champ `excellence` le suit) ; le niveau ne se change plus depuis la fiche. Au début de chaque trimestre, l'équipe reçoit un rappel si aucun niveau n'a encore été validé. Les seuils sont des paramètres (Finance → Paramètres, migrations finance `0018` et `0028`).

## Paiement

Les tables de `apps.paiements` servent aussi aux transferts : `PaiementModel` et `RemboursementModel` portent soit une `reservation`, soit un `transfert` (contrainte en base). Les versements aux chauffeurs (`VersementChauffeurModel`) utilisent les mêmes fonctions d'envoi que ceux des hôtes (`envoyer_payout`, nouveaux essais progressifs, alerte aux administrateurs en cas d'échec). Le worker `traiter_paiements` traite aussi les transferts.

## Configuration

```
ASSISTANCE_CONTACT=+228 …   # contact d'assistance donné au voyageur avec les coordonnées du chauffeur
```

## Prochaines étapes possibles

- Suivi du vol en temps réel et ajustement automatique de l'heure de prise en charge (API de statut de vol).
- Espace chauffeur (accepter une course, confirmer la prise en charge) au lieu de l'attribution manuelle.
- Ajout du transfert au même paiement que le séjour.

## Tests

`server/tests/unit/transferts/` (prix, nuit, capacité) et `server/tests/integration/transferts/` (devis, fuseaux, règles de création, cycle complet jusqu'au versement du chauffeur, annulations, expiration, accès).
