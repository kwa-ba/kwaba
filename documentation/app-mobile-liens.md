# Liens du site ouverts par l'app mobile

L'app Kwa-Ba (dépôt kwa-ba-mobile) ouvre elle-même certains liens du site (fiche d'un logement, paiement par un
tiers, invitation à un voyage, pages destination, espace hôte et espace agent). Le téléphone ne le fait que si le site
publie la preuve que l'app est la sienne.

## Android : 

Servi tel quel par Next à  (le middleware ignore les chemins avec un
point, nginx l'envoie au client comme le reste du site). Une entrée par app :

| App | Paquet | Empreinte SHA-256 du certificat de signature |
|---|---|---|
| Préprod |  |  (clé générée et gardée par Expo, lue sur l'APK du 23/11/2026) |
| Production |  | à ajouter après le premier build de production ( ou ) |

Le même fichier est servi sur les deux domaines ; chaque app ne revendique que le sien ( pour la
préprod,  pour la production).

**Préprod** : le site est derrière l'authentification HTTP de Caddy. Android doit pouvoir lire
 sans mot de passe : ce chemin doit être exempté dans la configuration de Caddy du
serveur de préprod (hors de ce dépôt). Sans cela, les liens de la préprod s'ouvrent dans le navigateur.

## iOS : 

À ajouter avec l'identifiant d'équipe Apple, une fois le compte Apple Developer de l'organisation ouvert.

## Côté app

Les chemins revendiqués et leur traduction en écrans sont dans kwa-ba-mobile (,
). Les liens d'alerte (), le guide du voyage et le back-office restent sur le site.
