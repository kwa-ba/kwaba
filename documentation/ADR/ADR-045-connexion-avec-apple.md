# Titre:
Se connecter avec Apple : jeton d'identité vérifié par les clés publiques d'Apple, compte retrouvé par son identifiant Apple, révocation à la suppression

# Status:
Accepté (25 novembre 2026).

# Contexte :
L'application mobile va proposer la connexion Google (`POST /api/v1/auth/google/`). Apple impose qu'une application iOS qui propose une connexion par un tiers propose aussi « Se connecter avec Apple » (règle 4.8), et que la suppression du compte révoque les jetons Apple de la personne (règle 5.1.1(v)).

Ce que l'application reçoit d'Apple à la connexion :
- un jeton d'identité (JWT signé par Apple) : `sub` (identifiant stable de la personne pour notre équipe), `email` (parfois une adresse relais `…@privaterelay.appleid.com`), `email_verified`, `aud` (identifiant de l'application) ;
- un code d'autorisation, valable 5 minutes, qui s'échange contre un jeton de rafraîchissement Apple ;
- le prénom et le nom, seulement à la toute première connexion, et seulement côté application.

# Options
Option 1 : Faire confiance à l'application et ne recevoir que l'adresse. N'importe qui pourrait ouvrir n'importe quel compte.

Option 2 : Vérifier le jeton d'identité avec les clés publiques d'Apple, comme on vérifie celui de Google, et garder le jeton de rafraîchissement Apple chiffré pour pouvoir le révoquer.

# Décision
Nous retenons l'option 2 (décision de Godwin du 25 novembre 2026).

- **Route** : `POST /api/v1/auth/apple/` `{"identity_token", "authorization_code", "first_name", "last_name"}`. Même réponse que `auth/google/` : jetons (session longue de l'application, ADR-043) et utilisateur.
- **Vérification** : signature par une clé de `https://appleid.apple.com/auth/keys`, émetteur `https://appleid.apple.com`, audience dans `APPLE_CLIENT_ID` (`com.kwaba.app`, `com.kwaba.app.preprod`), expiration, adresse vérifiée. Sans `APPLE_CLIENT_ID`, la connexion Apple est indisponible.
- **Compte** : retrouvé par `apple_id` (`sub`). Sinon par l'adresse, que le compte rattache, avec la même règle que Google : un compte dont l'adresse n'avait jamais été vérifiée perd son mot de passe, que quelqu'un d'autre a pu choisir. Sinon, un voyageur vérifié est créé avec le prénom et le nom envoyés par l'application.
- **Révocation** : quand `APPLE_TEAM_ID`, `APPLE_KEY_ID` et `APPLE_PRIVATE_KEY` (clé « Sign in with Apple », secrète) sont réglés, le code d'autorisation est échangé contre un jeton de rafraîchissement Apple, gardé chiffré (Fernet, `APPLE_TOKEN_ENCRYPTION_KEY`, dérivée de `SECRET_KEY` par défaut). La suppression du compte (ADR-039) efface `apple_id` et ce jeton, puis le révoque auprès d'Apple après la transaction. Sans ces réglages, la connexion fonctionne mais rien n'est révocable : ils sont obligatoires avant la soumission à l'App Store.
- **Adresses relais** : Apple ne les livre que si le domaine d'envoi (`kwa-ba.com`) est déclaré dans son portail, avec un SPF valide. C'est de la configuration, hors du code.

# Conséquences :
positives (bénéfices)
- L'application peut être publiée sur iOS avec la connexion Google.
- Un jeton d'Apple émis pour une autre application est refusé (audience).

négatifs (inconvénients)
- Une dépendance de plus au réseau à la connexion (clés d'Apple, mises en cache) et à la suppression (révocation).
- Une personne qui masque son adresse a un compte à l'adresse relais : elle ne retrouve pas un compte créé avec sa vraie adresse.

Impacts futurs
- « Se connecter avec Apple » sur le site demanderait un identifiant de services Apple et une adresse de retour : non prévu.
- **Mise à jour du 26 novembre 2026 (Fadel)** : le site le propose aussi, sur la connexion et l'inscription. Fenêtre d'Apple (Apple JS, `usePopup`), même route `auth/apple/` par next-auth (`apple-id-token`). L'identifiant de services du site (`APPLE_SERVICES_ID` de `client.env`) s'ajoute à `APPLE_CLIENT_ID` ; l'adresse de retour est la page d'accueil du site, déclarée dans le portail d'Apple, et l'API ne renvoie à Apple que celle-ci (`web_redirect_uri`) à l'échange du code. Bouton caché tant que `APPLE_SERVICES_ID` est vide. Pas de bouton Apple dans l'application Android.
