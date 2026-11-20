# Titre:
Double authentification (TOTP) obligatoire pour tous les comptes du back-office

# Status:
Accepté (20 novembre 2026), relu par MENDE Fadel.

# Contexte :
La recette finance du 19 novembre demande, au ticket DEV-L11 (P1, avant la première clôture du 31 janvier 2027), une « 2FA exigée » pour tout accès financier. Aujourd'hui, un admin entre dans le back-office avec un seul facteur : mot de passe, compte Google ou code reçu par email. Si ce facteur fuit, quelqu'un d'autre peut lire les finances, valider une opération ou modifier des droits.

Ce qui existe déjà :
- `EstAdministrateur` (`apps/securite/permissions.py`) relit le rôle et les sections en base à chaque requête du back-office ;
- les jetons SimpleJWT tournent à chaque renouvellement (`RefreshWithGracePeriodSerializer`) et sont révoqués quand le mot de passe change (`CHECK_REVOKE_TOKEN`) ;
- `Tentatives` (`apps/securite/limites.py`) limite les essais, et le journal d'activité (ADR-025) trace les actions sensibles ;
- les super admins ont aussi accès à l'admin Django (`ADMIN_URL`), qui fonctionne par session, avec un mot de passe seul.

La note technique de MENDE Fadel du 19 novembre 2026 fixe les choix fonctionnels. Cet ADR les reprend, avec des noms en anglais pour le code (convention du dépôt). Il s'en écarte sur quatre points :
- il ajoute l'admin Django et l'espace agent, que la note ne couvrait pas ;
- le 403 ne dit pas si la 2FA est active ;
- la confirmation ne renvoie pas de jetons ;
- la connexion à l'admin Django vérifie le code par un registre.

Les raisons sont données plus bas.

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
- **L'espace agent** (`/api/v1/agent/`, module `terrain`) quand le compte est admin : les admins y traitent les pièces d'identité et les visites.
- **L'admin Django** (`ADMIN_URL`).
- Les voyageurs, hôtes, partenaires et agents de terrain ne sont pas concernés. Un admin sans 2FA garde l'accès au reste du site, comme tout compte.

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
- L'ancien refresh, sans marque, est mis en liste noire. La nouvelle paire est écrite dans le cache de grâce de `RefreshWithGracePeriodSerializer` sous l'empreinte de l'ancien refresh : un renouvellement lancé au même moment avec l'ancien refresh reçoit la paire marquée au lieu de fermer la session.
- **Un seul chemin marque les jetons : `verify/`.**

## Contrôle par l'API
- Une fonction de `securite` vérifie la marque : `request.auth.get('two_factor_verified_at')` présente et plus récente que `TWO_FACTOR_VALIDITY_HOURS` (réglage, 12 par défaut).
- `EstAdministrateur.has_permission` l'appelle après le contrôle du rôle et avant celui des sections. La permission de l'espace agent l'appelle aussi quand le compte est admin.
- Sinon, la réponse est **403** `{"code": "two_factor_required"}`. Le front lit alors l'état (`GET two-factor/`) pour choisir entre l'écran d'activation et celui du code.
- Le 403 ne dit pas si la 2FA est active : `securite` appartient au noyau partagé et n'importe pas `users` (contrat `noyau-partage` de `.importlinter`). Le contrôle lit le jeton seulement, sans requête en base.
- La durée est un réglage de sécurité (`settings`), pas un paramètre du référentiel financier. `securite` et `users` ne dépendent pas de `finance`.

## API (module `users`)
Les routes vivent sous `/api/v1/auth/two-factor/`, hors de `/api/v1/admin/`. Elles exigent un compte admin connecté, mais pas la marque.

| Route | Rôle |
|---|---|
| `GET two-factor/` | État : `enabled`, `verified_at`, `expires_at`, `backup_codes_left`. |
| `POST two-factor/setup/` | Crée un secret en attente et renvoie l'URI `otpauth://` (le secret y figure, pour la saisie manuelle). Refusé si la 2FA est déjà active. Un nouvel appel remplace le secret en attente. |
| `POST two-factor/confirm/` | Premier code juste : le secret devient actif, son pas est retenu comme dernier pas accepté, et les 10 codes de secours sont renvoyés une seule fois. **Aucun jeton n'est renvoyé.** |
| `POST two-factor/verify/` | Code TOTP ou code de secours (consommé), et le refresh de la session. Renvoie la paire marquée. Seul le serveur Next l'appelle (voir Client). |

Après la confirmation, l'admin note ses codes de secours puis saisit un nouveau code dans `verify/`. Grâce à l'anti-rejeu, le code de la confirmation ne peut pas resservir. Les codes de secours ne transitent ainsi jamais par la session NextAuth, et l'admin prouve que son appli génère bien les codes.
| `POST /api/v1/admin/droits/<id>/two-factor/reset/` | Téléphone perdu. Super admin seulement, motif obligatoire, journalisé. Efface la 2FA d'un autre admin, qui la réactive à sa connexion suivante. Un admin ne réinitialise jamais la sienne par cette route. |

Si le dernier super admin perd son téléphone, la commande serveur `manage.py reset_two_factor <email>` fait la même chose. Elle est lancée sur le serveur, comme `super_admin`, et journalisée.

## Stockage
- `users_two_factor` : compte, secret chiffré, secret en attente chiffré, activé le, dernier pas TOTP accepté.
- `users_backup_code` : compte, empreinte du code, utilisé le. L'empreinte est un HMAC-SHA256 avec une clé secrète, comme celle des codes reçus par email (`hacher_code`), et non `make_password`. `make_password` est lent par conception (environ 0,3 s) et salé, et il faudrait comparer le code saisi aux 10 codes un par un. Les codes de secours sont aléatoires (40 bits) et limités à 5 essais par 15 minutes : sans la clé, une empreinte ne sert à rien.
- Le **secret est chiffré au repos** avec Fernet (paquet `cryptography`). La clé vient de `TWO_FACTOR_ENCRYPTION_KEY`, ou par défaut d'une dérivation HMAC de `SECRET_KEY` propre à cet usage, comme `JWT_SIGNING_KEY`. Une fuite de la base seule ne donne pas les codes.
- Changer `SECRET_KEY` sans clé dédiée rend tous les secrets illisibles : chaque admin devra être réinitialisé. En production, `TWO_FACTOR_ENCRYPTION_KEY` est donc fixée à part, dans le dépôt d'infra.

## Sécurité
- **Anti-rejeu** : un code du même pas que le dernier accepté, ou d'un pas antérieur, est refusé.
- **Anti-force brute** : `Tentatives`, 5 essais par 15 minutes et par compte, codes TOTP et codes de secours confondus, comme pour le code par email. Un succès remet le compteur à zéro.
- **Journal d'activité** (`activity.api.record`), avec les niveaux de la connexion existante, pour ne pas noyer le bandeau des événements sensibles sous une vérification toutes les 12 h par admin :
  - vérification réussie : courant ;
  - échec : important ;
  - activation, blocage, code de secours utilisé et réinitialisation (auteur, cible et motif) : sensibles.

  Jamais le code, le secret ni l'URI.
- Dépendances ajoutées : `pyotp` et `cryptography`.

## Admin Django
- Le formulaire de connexion (`connexion_admin`) demande, en plus du mot de passe, un code TOTP ou un code de secours. Il applique les mêmes contrôles : anti-rejeu, `Tentatives`, journal.
- `connexion_admin` vit dans `securite`, qui n'importe pas `users`. La vérification du code passe donc par un **registre** (ADR-019) : `securite` expose un point d'entrée « second facteur », et `users` s'y déclare dans `AppConfig.ready`. Sans vérificateur déclaré, la connexion est refusée.
- Un super admin sans 2FA active ne peut pas y entrer : il l'active d'abord depuis le back-office.
- La session de l'admin Django dure 12 h au plus.

## Client (Next.js)
### Interface
- **Garde plein écran** : sur toute page du back-office et de l'espace agent, tant que la 2FA n'est pas vérifiée, une carte centrée, sans menu, remplace l'écran, dans le style de la page de connexion. L'adresse demandée ne change pas : une fois le code accepté, l'admin arrive sur la page qu'il voulait ouvrir. Il n'y a pas d'étape dans `/login`, qui est commune à tous les comptes et passe par une redirection pour Google.
- **Écran d'activation**, tant que la 2FA n'est pas active. Il ne laisse que deux choix, activer ou se déconnecter. Il se fait en trois étapes :
  1. ajouter Kwa-Ba à l'appli, de trois façons : QR code (depuis un PC), bouton « Ouvrir dans l'application » (lien `otpauth://`, depuis le téléphone), ou clé de configuration à copier ;
  2. saisir le premier code ;
  3. noter les 10 codes de secours (copier ou télécharger, case « J'ai noté mes codes »), puis saisir un nouveau code.

  Sur téléphone, le bouton passe avant le QR code. On peut donc tout faire sans PC.
- **Écran du code**, à la connexion et après 12 h : code à 6 chiffres, lien « Utiliser un code de secours », rappel « Téléphone perdu ? Contactez un super admin », déconnexion. Après 12 h, il s'affiche par-dessus la page en cours, qui est retrouvée intacte.
- **Page « Sécurité du compte »**, au bas du menu du back-office : date d'activation, prochaine vérification, codes de secours restants, avec une alerte sous 3.
- **Réinitialisation** : un bouton dans l'écran des droits (`DroitsAdmin`), visible des super admins, motif obligatoire.
- Le QR code est dessiné dans le navigateur (`qrcode.react`), sans appel externe.
- Textes en français seulement, comme tout le back-office.

### Code
- Les écrans vivent dans `features/users/admin/two-factor/` (module `users`, comme côté serveur ; `admin/` regroupe les écrans du back-office, en français seulement). La garde `TwoFactorGate` enveloppe `AdminShell` et `AgentShell` dans les layouts `app/backoffice` et `app/agent` : les coques, leur menu et leurs requêtes d'admin (droits, compteurs) attendent la vérification, et la feature `verifications` n'importe pas `users`.
- **Jetons** : ils restent dans le cookie chiffré de NextAuth. Le navigateur appelle `update({ twoFactorCode })`, et le callback `jwt` de `src/auth.ts`, côté serveur, appelle `verify/` avec le jeton de la session puis écrit la paire marquée dans le cookie. La paire ne passe jamais par le navigateur. Le résultat (code faux, blocage et délai) remonte par la session.
- `setup/` et `confirm/` passent par le proxy habituel (`app/api/proxy`) : ils ne renvoient pas de jetons.
- **Intercepteur** (`lib/api.ts`) : un 403 `two_factor_required` reçu pendant la session émet un signal (`lib/two-factor-signal.ts`, car `lib/` ne connaît pas les features). La garde relit alors l'état et réaffiche l'écran du code.

## Mise en service
Trois livraisons, dans cet ordre, pour qu'aucun admin ne soit bloqué sans écran pour activer sa 2FA :
1. **API sans blocage** : modèles, routes, réinitialisation, commande serveur.
2. **Écrans** : garde, activation, saisie du code, page « Sécurité du compte ». Chaque admin peut activer sa 2FA à son rythme.
3. **Blocage** : contrôle dans `EstAdministrateur` et dans l'espace agent, admin Django. Dès ce déploiement, chaque admin qui n'a pas encore activé sa 2FA le fait à sa connexion suivante, sans période de transition.

- Préprod d'abord. L'équipe est prévenue quelques jours avant la troisième livraison, pour installer une appli d'authentification.
- Avant la production, au moins un super admin a activé sa 2FA et sait réinitialiser celle des autres.
- `documentation/securite.md` et la page du module `users` sont mises à jour.

# Conséquences :
positives (bénéfices)
- Un mot de passe, un compte Google ou une boîte mail volés ne suffisent plus pour entrer dans le back-office ni dans l'admin Django.
- La règle est appliquée par l'API, à un seul endroit : une nouvelle vue du back-office est protégée d'office.
- Pas de requête en base de plus par appel : la marque voyage dans le jeton.
- Le critère « 2FA exigée » de DEV-L11 est couvert au-delà de la rubrique Finance.

négatifs (inconvénients)
- Un admin doit avoir son téléphone pour travailler, et saisir un code au moins toutes les 12 h.
- Un admin qui se connecte depuis le téléphone qui porte l'appli a ses deux facteurs sur le même appareil : un mot de passe volé ne suffit plus, mais la protection est moindre qu'avec deux appareils.
- Un téléphone perdu sans code de secours bloque l'admin jusqu'à la réinitialisation par un super admin.
- La perte de la clé de chiffrement oblige à réinitialiser tous les admins.
- La 2FA n'est vérifiée qu'à la connexion et toutes les 12 h : un jeton marqué volé reste utilisable jusqu'à son expiration (15 min pour l'access, la session NextAuth pour le refresh).

Impacts futurs
- Régénérer ses codes de secours (avec un code TOTP valide) depuis l'écran de la 2FA.
- Étendre la 2FA, en option, aux hôtes et aux partenaires qui reçoivent des versements.
- Clés matérielles (WebAuthn) si l'équipe grandit.
- Complète ADR-019 (registre du second facteur dans le noyau partagé), ADR-020 (écrans dans `features/users`), ADR-023 (permissions du back-office), ADR-025 (journal d'activité) et ADR-026 (rubrique Finance).
