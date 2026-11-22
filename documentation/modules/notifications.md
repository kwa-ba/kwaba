# Noyau notifications

`shared.notifications` (ADR-029) : le seul passage des e-mails et des notifications push. Il n'importe aucun module métier ; les modules l'appellent par `shared.notifications.api`.

## E-mails

- `send_mail` : envoi direct, texte et HTML aux couleurs de Kwa-Ba.
- `demander_email(routing_key, data)` : demande publiée sur RabbitMQ et traitée par `consume_events` ; sans RabbitMQ, envoi direct.

## Notifications push de l'application mobile (ADR-042)

### Routes

| Route | Rôle |
|---|---|
| `POST /api/v1/notifications/devices/` `{"token": "ExponentPushToken[…]", "platform": "ios"}` | L'appareil reçoit les notifications du compte connecté (`204`). Un jeton déjà connu passe au compte courant. |
| `DELETE /api/v1/notifications/devices/` `{"token": "…"}` | À la déconnexion (`204`). |
| `GET /api/v1/users/me/notifications/` | `{"bookings_payments": true, "messages": true, "offers": false}` |
| `PATCH /api/v1/users/me/notifications/` | Mêmes clés, booléens ; renvoie les préférences à jour. |

### Envoi

```python
from shared.notifications.api import push

push(user_id, category='bookings_payments', title='Séjour confirmé', body=nom_du_logement,
     data={'screen': 'reservation', 'id': str(reservation.id)})
```

- Rien n'est envoyé si le compte n'a pas d'appareil ou a désactivé la catégorie.
- La demande passe par RabbitMQ (`notifications.push_requested`), puis le consommateur appelle le service d'Expo par lots de 100. Les jetons refusés (`DeviceNotRegistered`) sont effacés.
- Jamais le texte d'un message ni un montant : la notification s'affiche sur un écran verrouillé et transite par Expo.
- `EXPO_ACCESS_TOKEN` : seulement si la « sécurité renforcée des notifications » est activée dans le projet Expo.

### Événements branchés

| Événement | Destinataire | Catégorie | `data` |
|---|---|---|---|
| Séjour payé et confirmé | Voyageur | `bookings_payments` | `{"screen": "reservation", "id"}` |
| Nouvelle réservation payée | Hôte | `bookings_payments` | `{"screen": "host"}` |
| Chauffeur attribué | Voyageur | `bookings_payments` | `{"screen": "transfer", "id"}` |
| Nouveau message (même règle que l'e-mail) | Destinataire | `messages` | `{"screen": "conversation", "id"}` |

La suppression d'un compte efface ses appareils et ses préférences (ADR-039).
