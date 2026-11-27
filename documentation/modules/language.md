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

with in_language(compte.language):
    sujet = t('reservations.confirmed_subject')
```

Les e-mails destinés à l'équipe restent en français.
