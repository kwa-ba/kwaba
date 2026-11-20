# Titre:
Double authentification (TOTP) obligatoire pour tous les comptes du back-office

# Status:
Accepté (20 novembre 2026).

# Contexte :
La recette finance du 19 novembre demande, au ticket DEV-L11 (P1, avant la première clôture du 31 janvier 2027), une « 2FA exigée » pour tout accès financier. Aujourd'hui, un admin entre dans le back-office avec un seul facteur : mot de passe, compte Google ou code reçu par email. Si ce facteur fuit, quelqu'un d'autre peut lire les finances, valider une opération ou modifier des droits.

Ce qui existe déjà :
- `EstAdministrateur` (`apps/securite/permissions.py`) relit le rôle et les sections en base à chaque requête du back-office ;
- les jetons SimpleJWT tournent à chaque renouvellement (`RefreshWithGracePeriodSerializer`) et sont révoqués quand le mot de passe change (`CHECK_REVOKE_TOKEN`) ;
- `Tentatives` (`apps/securite/limites.py`) limite les essais, et le journal d'activité (ADR-025) trace les actions sensibles ;
- les super admins ont aussi accès à l'admin Django (`ADMIN_URL`), qui fonctionne par session, avec un mot de passe seul.

La note technique de MENDE Fadel du 19 novembre 2026 fixe les choix fonctionnels. Cet ADR les reprend, avec des noms en anglais pour le code (convention du dépôt), et ajoute l'admin Django, que la note ne couvrait pas.

# Options
Option 1 : 2FA seulement sur la rubrique Finance. Elle répond à la lettre de la recette, mais un admin d'une autre section peut toujours modifier des droits ou des comptes de versement, ce qui ouvre un accès indirect aux finances.

Option 2 : 2FA imposée par le front (garde dans `AdminShell`). Rien de plus simple, mais un appel direct à l'API la contourne.

Option 3 : 2FA par code envoyé par SMS ou par email. Le code par email est déjà l'un des modes de connexion : il ne serait pas un second facteur. Le SMS coûte de l'argent et s'expose au détournement de carte SIM.

Option 4 : 2FA par application TOTP (Google Authenticator, Microsoft Authenticator, 2FAS…), imposée par l'API sur tout le back-office et l'admin Django, avec une marque dans le jeton.

# Décision
Nous retenons l'option 4.

## Périmètre
- **Tous les comptes du back-office** (rôle `admin`), super admins et admins temporaires compris, quelles que soient leurs sections.
- **Toutes les vues protégées par `EstAdministrateur`**, qu'elles soient sous `/api/v1/admin/` ou non (contrats, documents, lancement).
- **L'admin Django** (`ADMIN_URL`).
- Les voyageurs, hôtes, partenaires et agents de terrain ne sont pas concernés.

## Quand
- À chaque connexion, après le premier facteur (mot de passe, Google ou code par email, inchangés).
- De nouveau **12 h au plus** après la dernière vérification, même si la session est restée ouverte.
- Après un changement de mot de passe : tous les jetons sont déjà révoqués, la 2FA est donc redemandée.

## Second facteur
- Code TOTP à 6 chiffres, pas de 30 s, fenêtre de ±1 pas (horloges du téléphone et du serveur légèrement décalées).
- **10 codes de secours** à usage unique, générés à l'activation, montrés une seule fois.
- Le QR code est dessiné par le client à partir de l'URI `otpauth://` (émetteur « Kwa-Ba », compte = email).

## Marque dans le jeton
- Après un code juste, l'API renvoie une nouvelle paire SimpleJWT. Le refresh porte la revendication `two_factor_verified_at` (horodatage Unix).
- SimpleJWT recopie les revendications du refresh dans l'access et les garde à chaque rotation : la marque suit la session sans requête en base de plus. L'horodatage ne change pas au renouvellement : 12 h après la vérification, la marque expire même si le jeton a tourné entre-temps.
- L'ancien refresh, sans marque, est mis en liste noire.

## Contrôle par l'API
- `EstAdministrateur.has_permission` lit `request.auth.get('two_factor_verified_at')`, après le contrôle du rôle et avant celui des sections.
- Si la marque est absente ou plus vieille que `TWO_FACTOR_VALIDITY_HOURS` (réglage, 12 par défaut), la réponse est **403** `{"code": "two_factor_required", "enabled": true|false}`. Le front sait alors s'il doit afficher l'écran d'activation ou celui du code.
- La durée est un réglage de sécurité (`settings`), pas un paramètre du référentiel financier. Le module `users` appartient au socle et ne dépend pas de `finance`.

## API (module `users`)
Les routes vivent sous `/api/v1/auth/two-factor/`, hors de `/api/v1/admin/`. Elles exigent un compte admin connecté, mais pas la marque.

| Route | Rôle |
|---|---|
| `GET two-factor/` | État : `enabled`, `verified_at`, `expires_at`, `backup_codes_left`. |
| `POST two-factor/setup/` | Crée un secret en attente et renvoie l'URI `otpauth://`. Refusé si la 2FA est déjà active. Un nouvel appel remplace le secret en attente. |
| `POST two-factor/confirm/` | Premier code juste : le secret devient actif, les 10 codes de secours sont renvoyés une seule fois, avec la paire marquée. |
| `POST two-factor/verify/` | Code TOTP ou code de secours (consommé). Renvoie la paire marquée. |
| `POST /api/v1/admin/droits/<id>/two-factor/reset/` | Téléphone perdu. Super admin seulement, motif obligatoire, journalisé. Efface la 2FA d'un autre admin, qui la réactive à sa connexion suivante. Un admin ne réinitialise jamais la sienne par cette route. |

Si le dernier super admin perd son téléphone, la commande serveur `manage.py reset_two_factor <email>` fait la même chose. Elle est lancée sur le serveur, comme `super_admin`, et journalisée.

## Stockage
- `users_two_factor` : compte, secret chiffré, secret en attente chiffré, activé le, dernier pas TOTP accepté.
- `users_backup_code` : compte, code haché (`make_password`), utilisé le.
- Le **secret est chiffré au repos** avec Fernet (paquet `cryptography`). La clé vient de `TWO_FACTOR_ENCRYPTION_KEY`, ou par défaut d'une dérivation HMAC de `SECRET_KEY` propre à cet usage, comme `JWT_SIGNING_KEY`. Une fuite de la base seule ne donne pas les codes.
- Changer `SECRET_KEY` sans clé dédiée rend tous les secrets illisibles : chaque admin devra être réinitialisé. En production, `TWO_FACTOR_ENCRYPTION_KEY` est donc fixée à part, dans le dépôt d'infra.

## Sécurité
- **Anti-rejeu** : un code du même pas que le dernier accepté, ou d'un pas antérieur, est refusé.
- **Anti-force brute** : `Tentatives`, 5 essais par 15 minutes et par compte, codes TOTP et codes de secours confondus, comme pour le code par email. Un succès remet le compteur à zéro.
- **Journal d'activité** (`activity.api.record`, niveau sensible, catégorie Connexions) : activation, vérification réussie, échec, blocage, code de secours utilisé, réinitialisation (auteur, cible et motif). Jamais le code, le secret ni l'URI.
- Dépendances ajoutées : `pyotp` et `cryptography`.

## Admin Django
- Le formulaire de connexion (`connexion_admin`) demande, en plus du mot de passe, un code TOTP ou un code de secours. Il applique les mêmes contrôles : anti-rejeu, `Tentatives`, journal.
- Un super admin sans 2FA active ne peut pas y entrer : il l'active d'abord depuis le back-office.
- La session de l'admin Django dure 12 h au plus.

## Client (Next.js)
- **Garde** dans `AdminShell.tsx` : elle lit l'état de la 2FA. Si la 2FA n'est pas active, elle affiche l'écran d'activation (QR code, premier code, codes de secours à noter). Si la vérification a expiré, elle affiche l'écran du code. Rien du back-office ne s'affiche avant.
- **Jetons** : ils restent dans le cookie chiffré de NextAuth. Une route Next côté serveur appelle `confirm/` ou `verify/` avec le jeton de la session et écrit la paire marquée dans le jeton NextAuth. La paire ne passe jamais par le navigateur.
- **Intercepteur** (`lib/api.ts`) : un 403 `two_factor_required` reçu pendant la session relit l'état, et la garde réaffiche l'écran du code sans perdre la page.
- Textes en français seulement, comme tout le back-office.

## Mise en service
- La règle s'applique dès le déploiement : chaque admin active sa 2FA à sa connexion suivante. Il n'y a pas de période de transition sans 2FA.
- Préprod d'abord. Avant la production, au moins un super admin a activé sa 2FA et sait réinitialiser celle des autres.
- `documentation/securite.md` et la page du module `users` sont mises à jour.

# Conséquences :
positives (bénéfices)
- Un mot de passe, un compte Google ou une boîte mail volés ne suffisent plus pour entrer dans le back-office ni dans l'admin Django.
- La règle est appliquée par l'API, à un seul endroit : une nouvelle vue du back-office est protégée d'office.
- Pas de requête en base de plus par appel : la marque voyage dans le jeton.
- Le critère « 2FA exigée » de DEV-L11 est couvert au-delà de la rubrique Finance.

négatifs (inconvénients)
- Un admin doit avoir son téléphone pour travailler, et saisir un code au moins toutes les 12 h.
- Un téléphone perdu sans code de secours bloque l'admin jusqu'à la réinitialisation par un super admin.
- La perte de la clé de chiffrement oblige à réinitialiser tous les admins.
- La 2FA n'est vérifiée qu'à la connexion et toutes les 12 h : un jeton marqué volé reste utilisable jusqu'à son expiration (15 min pour l'access, la session NextAuth pour le refresh).

Impacts futurs
- Régénérer ses codes de secours (avec un code TOTP valide) depuis l'écran de la 2FA.
- Étendre la 2FA, en option, aux hôtes et aux partenaires qui reçoivent des versements.
- Clés matérielles (WebAuthn) si l'équipe grandit.
- Complète ADR-023 (permissions du back-office), ADR-025 (journal d'activité) et ADR-026 (rubrique Finance).
