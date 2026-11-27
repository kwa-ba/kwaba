# Titre:
Langues de l'API : un module partagé `shared/language`, des clés dans le code et un fichier JSON par module et par langue

# Status:
Accepté (27 novembre 2026).

# Contexte :
Le site et l'application mobile existent en français et en anglais, et envoient leur langue à l'API (`Accept-Language`). L'API, elle, répond toujours en français : environ 650 messages destinés aux voyageurs et aux hôtes, et 75 gabarits d'e-mails, sans aucun mécanisme de traduction (pas de `LocaleMiddleware`, pas de `gettext`). Trois modules gèrent déjà une langue à leur manière (pré-inscription, Concierge, alertes de disponibilité).

Le site range déjà ses textes par clés, dans un fichier par langue (`client/messages/fr.json`, `en.json`). On veut pouvoir ajouter une langue (l'espagnol, par exemple) sans toucher au code.

# Options
Option 1 : Les traductions standard de Django (`gettext`, catalogues `.po`), avec le texte français comme référence dans le code. Outillage standard, mais un format différent de celui du site, et le texte de référence lié au français.

Option 2 : Un module partagé qui porte des clés et un fichier par langue, comme le site. Le code ne contient que des clés ; une langue de plus, ce sont des fichiers de plus.

# Décision
Nous retenons l'option 2 (décision de Godwin du 27 novembre 2026).

- **Module** : `shared/language`, dans le noyau partagé (ADR-029) : il n'importe aucun module métier, tous peuvent l'utiliser par `shared.language.api`.
- **Clés** : `<module>.<sens_en_anglais>`, par exemple `reservations.not_found`. Variables entre accolades (`{minutes}`), remplacées à l'appel ; pluriel par deux clés (`_one`, `_other`), comme sur le site.
- **Fichiers** : `shared/language/locales/<langue>/<module>.json`, un par module et par langue. Le français est la langue de référence : toutes les clés y sont. Une clé absente d'une autre langue retombe sur le français.
- **Langue d'une réponse** : celle de `Accept-Language`, parmi les langues qui ont des fichiers ; le français sinon. Le même intergiciel active les traductions intégrées de Django et de DRF (« Ce champ est obligatoire »…).
- **Langue d'un e-mail** : celle de son destinataire, gardée sur le compte (`language`), mise à jour à l'inscription et à chaque connexion d'après `Accept-Language`, et modifiable par `PATCH /api/v1/users/me/`. Les gabarits d'e-mails ont un dossier par langue.
- **Hors du périmètre** : le back-office, l'espace agent, les commandes `manage.py`, les journaux et les e-mails destinés à l'équipe restent en français.
- **Garde-fous** (tests) : toute clé utilisée dans le code existe en français ; chaque autre langue a les mêmes clés et les mêmes variables que le français.

# Conséquences :
positives (bénéfices)
- Le site, l'application et l'API répondent dans la langue de la personne, avec le même principe de clés que le site.
- Une langue de plus se limite à des fichiers JSON (et à ses gabarits d'e-mails).

négatifs (inconvénients)
- Le code montre une clé et non le texte : il faut des clés parlantes et le fichier français à côté.
- Un mécanisme maison : pas d'outils de traduction standard (`.po`), et des pluriels limités à deux formes.

Impacts futurs
- Une langue à plus de deux formes de pluriel demanderait d'étendre les clés de pluriel.
