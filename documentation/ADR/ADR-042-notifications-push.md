# Titre:
Notifications push de l'application mobile : appareils et préférences dans le noyau des notifications, envoi par le service d'Expo

# Status:
Accepté (22 novembre 2026).

# Contexte :
L'application mobile doit prévenir le voyageur ou l'hôte quand elle est fermée : paiement confirmé, nouvelle réservation, nouveau message, chauffeur attribué. Seuls les services d'Apple (APNs) et de Google (FCM) peuvent réveiller un téléphone ; l'application est construite avec Expo, qui fournit un service d'envoi unique pour les deux (`exp.host`) et des jetons `ExponentPushToken[...]`.

Les e-mails passent déjà par un seul noyau, `shared.notifications` (ADR-029), qui n'importe aucun module métier. Une connexion permanente (SSE, WebSocket) a été écartée : elle ne fonctionne que tant que l'application est ouverte, et le serveur est en WSGI.

# Options
Option 1 : Chaque module enregistre ses appareils et appelle Expo lui-même. Duplication, et le noyau des notifications ne serait plus le seul passage.

Option 2 : Le noyau `shared.notifications` garde les appareils et les préférences, et offre une fonction d'envoi ; les modules l'appellent à côté de leurs e-mails. L'envoi part par RabbitMQ, comme les e-mails, avec le même repli direct.

# Décision
Nous retenons l'option 2 (décision de Godwin du 22 novembre 2026).

- **Appareils** : `POST /api/v1/notifications/devices/` `{"token", "platform"}` enregistre le jeton (un jeton déjà connu passe au compte courant) ; `DELETE /api/v1/notifications/devices/` `{"token"}` le retire, à la déconnexion.
- **Préférences** : `GET` et `PATCH /api/v1/users/me/notifications/` `{"bookings_payments", "messages", "offers"}` ; `offers` est désactivé par défaut. Ce qui touche la sécurité du compte n'est pas une notification push.
- **Envoi** : `shared.notifications.api.push(user_id, category=..., title=..., body=..., data=...)` publie une demande ; le consommateur l'envoie par lots de 100 au service d'Expo et efface les jetons refusés (`DeviceNotRegistered`). Sans RabbitMQ, envoi direct.
- **Contenu minimal** : ce qui passe par Expo et s'affiche sur un écran verrouillé ne contient jamais le texte d'un message, ni un montant : un titre, le nom du logement ou de l'expéditeur, et de quoi ouvrir le bon écran (`data`: `{"screen": "reservation", "id": "..."}`).
- **Événements branchés** :

| Événement | Destinataire | Catégorie | `data.screen` |
|---|---|---|---|
| Séjour payé et confirmé | Voyageur | `bookings_payments` | `reservation` |
| Nouvelle réservation payée | Hôte | `bookings_payments` | `host` |
| Chauffeur attribué | Voyageur | `bookings_payments` | `transfer` |
| Nouveau message (même règle que l'e-mail : premier non lu, après le délai) | Destinataire | `messages` | `conversation` |

- **Suppression du compte** (ADR-039) : appareils et préférences effacés.

# Conséquences :
positives (bénéfices)
- Un seul endroit pour les appareils, les préférences et l'envoi ; les modules ajoutent une ligne à côté de leur e-mail.
- Le contenu qui transite par Expo reste minimal.

négatifs (inconvénients)
- Dépendance au service d'Expo ; en cas de panne, la notification est perdue (l'e-mail part quand même).
- Les notifications ne sont testables que sur un build de développement ou installé (pas dans Expo Go).

Impacts futurs
- Un rappel la veille de l'arrivée pourra s'ajouter quand il existera côté e-mail.
- Les reçus d'Expo (confirmation de livraison) pourront être lus plus tard pour nettoyer les jetons morts.
