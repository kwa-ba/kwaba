# Module users

Comptes de Kwa-Ba : inscription, connexion (mot de passe ou Google), jetons, profil, rôles, second facteur du back-office et suppression du compte.

Décisions liées : [ADR-028](../ADR/) (second facteur du back-office), [ADR-039](../ADR/ADR-039-suppression-du-compte-par-anonymisation.md) (suppression du compte).

## Architecture

Le module est en couches hexagonales.

```
apps/users/
├── domain/              User, objets valeur (Email, PhoneNumber…), exceptions, port UserRepository
├── application/         UserService, TwoFactorService, AccountDeletionService, événements, ports
├── infrastructure/      modèles Django, dépôts, contrôleurs HTTP, bus d'événements
├── account_deletion.py  registre de la suppression du compte (ADR-039)
└── api.py               interface lue par les autres modules
```

Les autres modules ne gardent que l'identifiant d'un compte (`<rôle>_id`) et le lisent par `users.api` (`compte`, `comptes`, `attacher`).

## Suppression du compte

Le voyageur ou l'hôte supprime son compte depuis « Mon profil → Mes informations » (web) ou « Profil → Paramètres » (application).

### Routes

| Route | Rôle | Réponses |
|---|---|---|
| `POST /api/v1/users/me/deletion-code/` | Envoie un code à 6 chiffres par e-mail, valable 10 minutes | `204` ; `409` si la suppression serait refusée (aucun code envoyé) |
| `DELETE /api/v1/users/me/` avec `{"code": "123456"}` | Supprime le compte | `204` ; `400 {"code": [...]}` si le code manque, est faux ou expiré ; `409` si quelque chose est en cours ; `429` après 10 essais dans l'heure |

Refus (`409`) :

```json
{
  "code": "account_deletion_blocked",
  "detail": "Votre compte ne peut pas encore être supprimé.",
  "blockers": [{"code": "upcoming_stays", "detail": "Vous avez un séjour à venir ou en cours : annulez-le ou attendez sa fin."}]
}
```

Codes possibles : `staff_account`, `upcoming_stays`, `upcoming_transfers`, `upcoming_rentals`, `open_deposit`, `pending_refunds`, `upcoming_bookings`, `upcoming_visit`, `pending_payouts`, `host_debt`. Chaque `detail` est affichable tel quel.

Après cinq codes faux, le code en cours est effacé : il faut en redemander un.

### Déroulé

1. `AccountDeletionService.delete` vérifie le code.
2. Il interroge les blocages de tous les modules inscrits au registre.
3. Dans une seule transaction : chaque module efface ce qu'il garde (`erase`), puis le compte est anonymisé (`anonymization.anonymize_account`) et toutes ses sessions sont révoquées.
4. Un e-mail confirme la suppression à l'ancienne adresse. Le journal enregistre `account_deleted`, sans l'ancienne adresse.

Le compte anonymisé s'appelle « Compte supprimé », son adresse devient `deleted-<id>@invalid` (l'ancienne adresse est libre pour un nouveau compte), il ne peut plus se connecter et porte sa date de suppression (`deleted_at`).

### Inscrire un module

Un module qui garde des données sur un compte s'inscrit dans son `AppConfig.ready` :

```python
from apps.users.api import register_account_deletion

from . import account_deletion

register_account_deletion('mon_module', blockers=account_deletion.blockers, erase=account_deletion.erase)
```

- `blockers(user_id) -> dict[str, str]` : `{code: message}`, vide quand rien n'est en cours ;
- `erase(user_id) -> None` : efface ou détache ses données, dans la transaction de la suppression. Un fichier se supprime avec `shared.media.files.delete_after_commit`, pour qu'un retour arrière garde la ligne et son fichier.

Le test `tests/unit/architecture/test_account_deletion_coverage.py` liste tous les champs qui gardent l'identifiant d'un compte. Un nouveau champ doit y être décidé (effacé, bloquant, gardé avec sa raison, ou rempli par l'équipe), sinon la CI échoue.

Modules inscrits aujourd'hui : `users`, `reservations`, `transferts`, `locations`, `paiements`, `hebergements`, `verifications`, `favoris`, `concierge`, `messaging`.

## Compte de relecture des stores

Apple et Google demandent un compte pour tester l'application. C'est un voyageur ordinaire, créé en production au lancement (pas pendant le pré-lancement : aucune annonce n'y serait visible) :

```bash
python manage.py create_review_account <email>
```

- Le mot de passe est saisi deux fois au clavier, ou lu dans `REVIEW_ACCOUNT_PASSWORD`. Il n'est ni affiché ni écrit dans le dépôt : il va seulement dans les notes de revue des stores.
- Relancer la commande remet le mot de passe et ferme les sessions ouvertes avec l'ancien.
- Elle refuse un compte administrateur, agent, hôte ou supprimé.
- Aucune fausse réservation : le relecteur parcourt les vraies annonces et s'arrête à la page de paiement.
- Procédure en production : dépôt d'infrastructure (`docs/admins.md`).
