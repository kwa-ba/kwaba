# Liens du site ouverts par l'app mobile

L'app Kwa-Ba (dépôt kwa-ba-mobile) ouvre elle-même certains liens du site : fiche d'un logement, paiement par un
tiers, invitation à un voyage, pages destination, espace hôte et espace agent. Le téléphone ne le fait que si le site
publie la preuve que l'app est la sienne.

## Android : `client/public/.well-known/assetlinks.json`

Servi tel quel par Next à `https://<domaine>/.well-known/assetlinks.json` (le middleware ignore les chemins avec un
point, nginx l'envoie au client comme le reste du site). Une entrée par app :

| App | Paquet | Empreinte SHA-256 du certificat de signature |
|---|---|---|
| Préprod | `com.kwaba.app.preprod` | `BB:00:EC:2F:…:E6:78:08:42` (clé générée et gardée par Expo, lue sur l'APK du 23/11/2026) |
| Production | `com.kwaba.app` | À ajouter après le premier build de production (`eas credentials`, ou `apksigner verify --print-certs` sur l'APK) |

Le même fichier est servi sur les deux domaines ; chaque app ne revendique que le sien (`preprod.kwa-ba.com` pour la
préprod, `kwa-ba.com` pour la production).

**Préprod** : le site est derrière l'authentification HTTP de Caddy. Android doit pouvoir lire
`/.well-known/assetlinks.json` sans mot de passe : ce chemin doit être exempté dans la configuration de Caddy du
serveur de préprod (hors de ce dépôt). Sans cela, les liens de la préprod s'ouvrent dans le navigateur.

## iOS : `apple-app-site-association`

À ajouter avec l'identifiant d'équipe Apple, une fois le compte Apple Developer de l'organisation ouvert.

## Côté app

Les chemins revendiqués et leur traduction en écrans sont dans kwa-ba-mobile (`src/shared/navigation/`,
`docs/liens-universels.md`). Les liens d'alerte (`/alertes`), le guide du voyage et le back-office restent sur le site.
