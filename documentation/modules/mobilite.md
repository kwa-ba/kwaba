# Module mobilité (`apps/mobilite`)

Socle commun des deux produits de mobilité, **transferts aéroport** (`apps/transferts`) et **location de voiture** (`apps/locations`), posé par l'harmonisation demandée le 26 novembre 2026 (lot 1 : T-H1, T-H2, T-H3).

## Référentiel unique des gammes (T-H1)

`GammeVehiculeModel` (`mobilite_gamme_vehicule`) : une seule liste de gammes, un seul mot par gamme, en transfert comme en location.

| Code | Nom | Transfert | Location |
|------|-----|-----------|----------|
| `citadine` | Citadine | — | oui |
| `berline` | Berline | oui (3 passagers, 3 valises) | oui |
| `suv` | SUV | oui (4, 4) | oui |
| `4x4` | 4×4 tout-terrain | — | oui |
| `minibus` | Minibus | oui (7, 8) | oui |
| `utilitaire` | Utilitaire | — | oui |

- La **boîte automatique** est un attribut du véhicule, pas une gamme (décision du 28 novembre 2026).
- `places` et `bagages` sont la capacité promise en transfert ; un véhicule loué indique la sienne.
- Les modules gardent un **code** de gamme (`TransfertModel.categorie`, `TarifTransfertModel.categorie`, `ChauffeurModel.categorie`, `CategorieVehiculeModel.gamme`), jamais une clé étrangère (ADR-019), validé par `mobilite.api.existe()`.
- Anciens codes de transfert : `transferts 0009` a renommé `confort` → `suv` et `van` → `minibus` (réversible). L'API accepte encore `confort` et `van` (`mobilite.api.normaliser`) et la liste publique des aéroports expose aussi les prix sous ces clés, **tant que l'app mobile publiée les envoie** : à retirer après sa mise à jour.
- Une gamme rendue « proposée en transfert » dans le back-office reçoit un tarif par aéroport (Transferts → Aéroports et tarifs) et apparaît au voyageur sans redéploiement : les noms et descriptions viennent de l'API (`GET /api/v1/mobilite/gammes/?usage=transfert|location`).
- Back-office : Mobilité → Gammes (`/api/v1/admin/mobilite/gammes/`, le code ne change plus après création). Les noms sont gardés une minute en mémoire (`mobilite.api.nom`), oubliés à chaque modification.

## Registre partagé (T-H2, T-H3)

Les tables restent dans leur module ; le back-office les regroupe dans la section **Mobilité** (`/backoffice/mobilite`) : Chauffeurs, Véhicules, Propriétaires, Gammes, Tarifs & règles.

- **Un registre de chauffeurs** (`transferts.ChauffeurModel`) pour les transferts et les locations avec chauffeur (c'était déjà la même table ; elle quitte l'écran Transferts).
- **Rôles cumulables** (décision 3) : `compte_id` sur la fiche chauffeur et sur la fiche propriétaire (`locations.PartenaireLocationModel`), saisi par l'email du compte (`compte_email`). Un compte a au plus une fiche de chaque ; le champ `role` du compte ne change pas. `mobilite.api.profils_du_compte(compte_id)` → `{chauffeur, proprietaire}`. À la suppression du compte, le lien est effacé et les fiches restent (versements, avis).
- **Le véhicule du chauffeur** n'est plus saisi sur sa fiche : `ChauffeurModel.vehicule_id` désigne une fiche Véhicule (`locations.CategorieVehiculeModel`) qui donne la gamme, le nom et la plaque. Pour un chauffeur qui possède sa voiture, « C'est sa voiture : créer sa fiche Véhicule » (`POST /api/v1/admin/transferts/chauffeurs/<id>/vehicule/`) crée sa fiche propriétaire (même compte, même Mobile Money) et une seule fiche Véhicule, non proposée en location tant que l'équipe ne l'a pas complétée. Les chauffeurs déjà inscrits gardent leurs champs saisis jusqu'à ce rattachement.
- **Une fiche par véhicule réel** (T-H3) : la gamme est un attribut ; plusieurs véhicules d'une gamme et plusieurs propriétaires par gamme. Une immatriculation ne s'enregistre qu'une fois (comparée sans espaces ni tirets, `mobilite.api.plaque`) ; liste filtrable par gamme, propriétaire (`aucun` pour l'ancien catalogue) et statut. La fiche affiche les chauffeurs qui la conduisent.
- **Section d'accès `mobilite`** (`shared/securite/permissions.py`) : `mobilite/`, `transferts/chauffeurs`, `location/categories`, `location/loueurs`, `location/tarifs-mobilite`. `users 0017` l'accorde aux admins limités à « Location » ou « Transferts ».

Les anciens liens (`/backoffice/location?onglet=categories|loueurs`, `/backoffice/transferts?onglet=chauffeurs`) redirigent vers Mobilité.
