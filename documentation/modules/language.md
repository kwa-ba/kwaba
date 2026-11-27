# Module language

`shared/language` (ADR-046) : les textes que l'API renvoie aux voyageurs et aux hôtes, dans leur langue. Module du noyau partagé : il n'importe aucun module métier.

## Utiliser un texte

```python
from shared.language.api import t

return Response({'detail': t('reservations.not_found')}, status=status.HTTP_404_NOT_FOUND)
return Response({'detail': t('users.too_many_attempts', minutes=5)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
```

- **Clé** : `<module>.<sens_en_anglais>`, en minuscules et `_`.
- **Variables** : `{minutes}` dans le texte, passée à l'appel. Une variable oubliée reste affichée telle quelle (`{minutes}`).
- **Pluriel** : deux clés, `<clé>_one` et `<clé>_other`, choisies par le code.

## Ajouter un texte

Dans `shared/language/locales/fr/<module>.json` (référence : toutes les clés y sont), puis dans chaque autre langue (`locales/en/<module>.json`) :

```json
{ "not_found": "Réservation introuvable." }
```

Les tests de `tests/unit/language` échouent si une clé utilisée dans le code manque en français, si une langue n'a pas exactement les mêmes clés que le français, ou si les variables d'une clé diffèrent d'une langue à l'autre.

## Ajouter une langue

Un dossier `locales/<langue>/` avec les mêmes fichiers que `fr/`, et la langue dans `LANGUAGES` (`config/settings.py`) pour les messages de Django et de DRF. Rien d'autre dans le code. Une clé absente d'une langue retombe sur le français.

## Langue d'une réponse

`LanguageMiddleware` lit `Accept-Language` et garde la première langue que l'API connaît (le français sinon). Elle vaut pour nos textes, pour les messages de Django et de DRF (« This field is required. ») et pour les dates. La réponse porte `Content-Language` et `Vary: Accept-Language`.

Le back-office (`/api/v1/admin/`) et l'administration Django (`/admin/`) restent en français, quelle que soit la langue demandée.

## Langue d'un e-mail

Celle de son destinataire, pas de la requête : un e-mail part souvent du worker, ou d'une action de l'équipe. Elle est gardée sur le compte (`language`, lue par `users.api.compte(...).language`) :

- enregistrée à l'inscription et à chaque connexion (mot de passe, Google, Apple, code de vérification), d'après `Accept-Language` ;
- modifiable par `PATCH /api/v1/users/me/` `{"language": "en"}` (`400` pour une langue inconnue).

```python
from shared.language.api import in_language, t

with in_language(voyageur.language):
    _envoyer('reservation_payee_voyageur', t('paiements.email_stay_confirmed', name=annonce['name']),
             [voyageur.email], contexte)
```

Dans le bloc `in_language`, tout suit la langue du destinataire : le sujet (`t`), les montants (`number`, `paiements.fcfa` : « 25 000 » ou « 25,000 »), les dates (`day_and_time` : « samedi 5 décembre 2026 à 14h30 » ou « Saturday 5 December 2026 at 14:30 ») et le gabarit.

- **Gabarits** : le chargeur `shared.language.templates.Loader` cherche d'abord `emails/<langue>/<chemin>` quand la langue active n'est pas le français (`apps/paiements/templates/emails/en/paiements/reservation_payee_voyageur.txt`), et retombe sur le gabarit français s'il n'existe pas. `tests/unit/language/test_translated_templates.py` vérifie que chaque gabarit traduit remplace un gabarit français, avec les mêmes variables.
- **Envoi après le commit** (`transaction.on_commit`) : la langue est lue au moment de l'appel et passée à l'envoi, car le rendu se fait plus tard, hors du bloc (`verifications.services.send_to_host`, `agenda` `_send(..., language)`).
- **Événements** : les événements d'e-mail (`users`, `messaging`, annulation de réservation) portent la langue du destinataire (`language`, `recipient_language`) ; le consommateur RabbitMQ rend l'e-mail dans cette langue.

Restent en français : les e-mails destinés à l'équipe, aux agents, aux chauffeurs et aux partenaires (même quand une action d'un hôte anglophone les déclenche), et ceux des contrats, dont le texte juridique est en français.
