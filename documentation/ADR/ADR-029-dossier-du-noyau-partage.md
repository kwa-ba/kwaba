# Titre:
Le noyau partagé du serveur dans son propre dossier racine, `server/shared/`

# Status:
Accepté (20 novembre 2026).

# Contexte :
ADR-019 a défini un noyau partagé que tous les modules peuvent importer et qui n'importe aucun module métier. Il compte aujourd'hui quatre modules :
- `securite` : limites, permissions et briques du back-office, connexion à l'admin Django, double authentification ;
- `notifications` : envoi des emails ;
- `export` : fichiers CSV, PDF et ICS ;
- `activity` : journal d'activité (ADR-025).

La règle est déjà vérifiée par l'outil : le contrat `noyau-partage` de `server/.importlinter` fait échouer la CI si l'un d'eux importe un module métier. Mais rien ne la montre dans l'arborescence : ces quatre dossiers sont rangés à côté de `reservations` ou de `give`, et rien ne distingue un module du socle d'un module métier. Le client, lui, sépare déjà ce qui est partagé (`client/src/shared/`, ADR-020).

# Options
Option 1 : Ne rien déplacer. La règle est imposée par l'import-linter, et on la documente seulement.

Option 2 : Un dossier `apps/common/`. Le nom invite à y ranger tout ce qu'on ne sait pas classer.

Option 3 : Un dossier `apps/shared/`. Il serait rangé au même niveau que les modules métier sans en être un : `apps/` mélangerait des modules et un regroupement de modules.

Option 4 : Un dossier racine `server/shared/`, à côté de `server/apps/` (métier) et `server/config/` (projet), du même nom que côté client.

# Décision
Nous retenons l'option 4.

- `securite`, `notifications`, `export` et `activity` vont dans `server/shared/`. On les importe par `shared.<module>`.
- Le déplacement est mécanique : aucune logique ne change, et chaque module garde son contenu.
- Les **labels Django ne changent pas** (`securite`, `notifications`, `export`, `activity`) : mêmes tables, mêmes migrations, mêmes droits en base. `notifications` reçoit un label explicite, comme les trois autres, pour que cela reste vrai si le dossier bouge encore.
- Chaque dossier racine du serveur a un seul rôle : `apps/` le métier, `shared/` le socle, `config/` le projet. Django accepte une app hors de `apps/` : `server/` est déjà dans le chemin Python.
- L'import-linter analyse les deux racines (`root_packages = apps shared`), et le contrat `noyau-partage` vise tout `shared`. Un module ajouté dans ce dossier est donc couvert d'office.
- La mesure de couverture inclut `shared` (`server/.coveragerc`).
- N'entre dans `shared/` qu'un module qui sert à plusieurs modules métier et n'en importe aucun. Un module qui ne sert qu'à un seul autre reste à côté de lui.

# Conséquences :
positives (bénéfices)
- L'architecture se lit dans l'arborescence et dans les imports : `from shared.activity import api` dit d'emblée « socle ».
- Le contrat de l'import-linter couvre tout le dossier, sans liste à tenir à jour.
- Même organisation que le client (`src/features/` et `src/shared/`).

négatifs (inconvénients)
- Environ 190 fichiers changent leurs imports : une branche ouverte en même temps aurait des conflits. Le déplacement se fait quand aucune branche n'est en cours, et il est fusionné vite.
- `git blame` doit suivre les déplacements (`git log --follow`).

Impacts futurs
- `securite` fait beaucoup de choses (limites, permissions, briques des écrans du back-office, admin Django, double authentification). Sortir les briques du back-office dans leur propre module de `shared/` sera traité à part.
- Complète ADR-019 (noyau partagé), ADR-020 (`shared/` côté client) et ADR-025 (journal d'activité).
