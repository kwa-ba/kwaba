# Titre:
Briques des écrans du back-office et traitement des photos hors de `securite`

# Status:
Accepté (20 novembre 2026).

# Contexte :
`shared/securite` (noyau partagé, ADR-029) contient, en plus de la sécurité :
- les briques communes des écrans du back-office (`backoffice.py` : `VueAdmin`, `ListeAdmin`, `FicheAdmin`, `Journalise`, `ChampPhoto`, `paginer`, `motif`, `nom`…), importées par une trentaine de fichiers ;
- le contrôle et le réencodage des photos envoyées (`photos.py`), qui est du traitement d'image.

Un développeur qui cherche comment écrire un écran du back-office ne pense pas à regarder dans `securite`. Et `securite` grossit à chaque sujet : limites, permissions, admin Django, double authentification, modération.

# Options
Option 1 : Tout laisser dans `securite`.

Option 2 : Sortir les briques du back-office et les photos dans deux modules du noyau partagé, et laisser à `securite` ce qui protège l'accès.

Option 3 : Sortir aussi la modération et l'anti-fraude (`moderation.py`, `fraude.py`, `coordonnees.py`). Ce bloc a des tables : il faudrait une migration qui les change d'app (`SeparateDatabaseAndState`), des droits en base et la conservation légale (ADR-021) à revoir.

# Décision
Nous retenons l'option 2.

- `shared/backoffice_kit/views.py` reçoit le contenu de `securite/backoffice.py`. Le nom `backoffice_kit` évite la confusion avec le module métier `apps/backoffice`.
- `shared/media/photos.py` reçoit le contenu de `securite/photos.py`.
- Déplacement pur : aucune logique ne change, seuls les imports suivent.
- Restent dans `securite` : les limites et compteurs, le captcha, les permissions du back-office (`EstAdministrateur`, sections, permissions spéciales), la double authentification, l'admin Django, le contrôle des adresses d'images (`images.py`, qui bloque les pixels de suivi) et la modération.
- Ni l'un ni l'autre n'a de table ni d'`AppConfig` : ce sont de simples paquets Python, couverts par le contrat `noyau-partage` comme tout `shared`.

# Conséquences :
positives (bénéfices)
- `securite` ne contient plus que ce qui protège l'accès et les données.
- Les briques d'un écran du back-office se trouvent sous un nom qui le dit.

négatifs (inconvénients)
- Une trentaine de fichiers changent un import.

Impacts futurs
- La modération et l'anti-fraude (option 3) pourront former leur propre module le jour où ce domaine évoluera, avec leur propre ADR.
- Complète ADR-019 et ADR-029 (noyau partagé).
