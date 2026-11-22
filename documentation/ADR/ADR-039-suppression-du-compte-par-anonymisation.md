# Titre:
Suppression du compte : anonymisation immédiate, confirmée par un code, avec un registre où chaque module efface ses données

# Status:
Accepté (22 novembre 2026).

# Contexte :
`DELETE /api/v1/users/me/` désactive le compte (`is_active = False`), révoque ses jetons et journalise `compte_desactive`. Rien n'est effacé. Apple refuse une application qui ne permet pas de supprimer réellement son compte (règle 5.1.1(v)), et l'application mobile en dépend pour être soumise. Le web a le même bouton (« Fermer mon compte »).

On ne peut pas effacer la ligne du compte :
- factures, paiements, remboursements, cautions et écritures du grand livre doivent être conservés (obligation comptable) ;
- les autres modules gardent l'identifiant du compte (`<objet>_id`, ADR-019) : réservations, messages, avis, dons.

La plupart des modules ne gardent que cet identifiant et lisent le nom et l'adresse par `users.api`. Quelques-uns gardent eux-mêmes des données personnelles : pièces d'identité (`verifications`), favoris, alertes de disponibilité, conversations avec le concierge, numéro et permis du voyageur sur un transfert ou une location, profil de versement de l'hôte.

Le module `users` n'a pas le droit de connaître ces modules (ADR-019).

# Options
Option 1 : Supprimer la ligne du compte. Impossible : les identifiants gardés par les autres modules ne mèneraient plus à rien, et les pièces comptables doivent rester.

Option 2 : Un délai de 30 jours, pendant lesquels une reconnexion annule la demande. Un état « suppression programmée » que tous les modules devraient comprendre, une tâche planifiée pour finir le travail, des règles pour l'annulation : beaucoup de code pour peu de gain.

Option 3 : Anonymiser tout de suite, après une confirmation, en laissant chaque module effacer ce qu'il garde lui-même, et refuser tant qu'un engagement est en cours.

Pour faire participer les modules, un événement « compte supprimé » écouté par chacun a été écarté : il arrive après coup (il ne peut pas refuser une suppression) et se traite hors de la transaction (un module en échec laisserait ses données sans que personne le voie).

# Décision
Nous retenons l'option 3 (décision de Godwin du 22 novembre 2026).

**Confirmation.** La suppression demande un code à 6 chiffres envoyé par e-mail (`POST /v1/users/me/deletion-code/`), valable 10 minutes, avec les mêmes limites de tentatives que les autres codes. Le même moyen sert aux comptes à mot de passe et aux comptes Google. Une session volée ne suffit donc pas pour détruire un compte.

**Qui peut supprimer son compte.** Le voyageur et l'hôte. Un administrateur ou un agent reçoit un refus (`staff_account`) : son départ passe par les super admins.

**Registre.** `users.api.register_account_deletion(module, blockers=…, erase=…)`, appelé par chaque module concerné dans son `AppConfig.ready`, comme `paiements/registre.py` :
- `blockers(user_id) -> dict[str, str]` : les raisons de refuser, `{code: message affiché à la personne}` ; chaque module garde ainsi ses propres textes ;
- `erase(user_id) -> None` : efface ou détache ce que le module garde lui-même.

**Déroulé de `DELETE /v1/users/me/`** (corps `{"code": "123456"}`) :
1. Le code est vérifié.
2. Tous les `blockers` sont interrogés. S'il y en a, réponse `409 {"code": "account_deletion_blocked", "detail": "…", "blockers": [{"code": "…", "detail": "…"}]}`, avec toutes les raisons à la fois ; rien ne change.
3. Sinon, dans une seule transaction : tous les `erase`, puis l'anonymisation du compte, puis la révocation des jetons. Une erreur annule tout.
4. Un e-mail confirme la suppression à l'ancienne adresse, après la transaction. L'activité `account_deleted` est journalisée sans donnée personnelle.

La demande de code (`deletion-code`) interroge aussi les `blockers` : on n'envoie pas de code pour une suppression qui serait refusée.

**Blocages.**

| Code | Module | Condition |
|---|---|---|
| `staff_account` | `users` | Compte administrateur ou agent |
| `upcoming_stays` | `reservations` | Séjour en attente de paiement ou confirmé, pas encore terminé |
| `upcoming_transfers` | `transferts` | Transfert en attente de paiement, payé ou attribué, pas encore effectué |
| `upcoming_rentals` | `locations` | Location en attente de paiement, payée ou attribuée, pas encore terminée |
| `open_deposit` | `reservations`, `locations` | Caution encore détenue pour un séjour ou une location (lue par `finance.api.caution`) |
| `pending_refunds` | `paiements` | Remboursement dû au payeur, pas encore envoyé |
| `upcoming_visit` | `verifications` | Visite d'un agent prévue sur un logement de l'hôte |
| `upcoming_bookings` | `hebergements` | Séjour payé à venir sur un logement de l'hôte |
| `pending_payouts` | `paiements` | Versement à l'hôte (séjour ou indemnité) pas encore envoyé |
| `host_debt` | `paiements` | Somme à récupérer auprès de l'hôte |

Un séjour à venir est refusé plutôt qu'annulé : une annulation entraîne un remboursement et les conditions d'annulation, qu'on ne déclenche pas par effet de bord.

**Ce qui est effacé.**

| Module | Effacé |
|---|---|
| `users` | Prénom et nom (remplacés par « Compte supprimé »), adresse e-mail (remplacée par `deleted-<uuid>@invalid`, ce qui libère l'adresse), téléphone, photo et son fichier, identifiant Google, mot de passe (rendu inutilisable), second facteur, codes en cours, motif de candidature. Le compte reste désactivé, avec sa date de suppression (`deleted_at`). |
| `verifications` | Pièce d'identité non vérifiée et son fichier ; invitations à réserver une visite |
| `favoris` | Favoris |
| `hebergements` | Alertes de disponibilité, brouillons d'annonce, inscription à l'ouverture ; les logements de l'hôte sont archivés (circuit existant `archivage.archiver`) |
| `concierge` | Conversations avec le concierge |
| `messaging` | E-mails de nouveaux messages encore en file (ils gardent une copie de l'adresse) |
| `reservations` | Message laissé à l'hôte lors de la réservation |
| `transferts` | Téléphone et message du voyageur |
| `locations` | Téléphone et permis du voyageur |
| `paiements` | Profil de versement de l'hôte (numéro Mobile Money) |

**Ce qui est gardé**, détaché du profil puisque l'identifiant ne mène plus qu'à « Compte supprimé » :
- factures, avoirs, reçus et cautions, avec le nom du client imprimé au moment de l'émission (pièce comptable) ;
- paiements, remboursements et versements, avec le numéro qui a servi (rapprochement avec le prestataire) ;
- écritures du grand livre ;
- contrats signés par l'hôte (preuve) ;
- pièce d'identité d'un hôte vérifiée par un agent : la politique de confidentialité la garde pendant la relation, puis 5 ans ;
- réservations, transferts et locations, sans contact : dates, trajet, véhicule, montants ;
- messages et avis, affichés sous « Compte supprimé » ;
- journal d'activité et alertes de fraude, purgés selon leur propre durée de conservation.

**Garde-fou.** Un test d'architecture liste les modèles qui gardent l'identifiant d'un compte. Chaque champ doit être soit traité par un module inscrit, soit marqué comme gardé volontairement, avec la raison. Un nouveau champ oublié fait échouer la CI.

# Conséquences :
positives (bénéfices)
- La suppression est réelle et immédiate : l'application peut être soumise à Apple, et le droit à l'effacement est respecté.
- Les pièces comptables et les données des autres utilisateurs (messages reçus, avis) restent cohérentes.
- `users` ne connaît aucun module : chacun efface ses propres données, et un module nouveau s'inscrit lui-même.
- Tout ou rien : une suppression ne s'arrête jamais à moitié.

négatifs (inconvénients)
- La route change de forme (code obligatoire) : le web et l'application doivent suivre. L'application n'est pas encore publiée, et le web est déployé avec le back.
- Un compte supprimé ne peut pas être restauré.
- Le module `finance` est lu (cautions détenues), sans être modifié.

Impacts futurs
- Les appareils et préférences des notifications push (lot à venir) s'inscriront au registre.
- Le départ d'un administrateur ou d'un agent pourra passer par le même registre, depuis le back-office.
- La politique de confidentialité doit décrire ce qui est effacé et ce qui est gardé.
