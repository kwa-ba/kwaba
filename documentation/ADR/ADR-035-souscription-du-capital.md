# Titre:
Capital social : la souscription au bilan d'ouverture (DEV-F6)

# Status:
Accepté (21 novembre 2026). Compte des apports à confirmer par l'expert-comptable.

# Contexte :
Le capital de Kwa-Ba SAS est de 500 000 F (paramètre `capital_social`, décision D4). Le module le lit pour les documents (factures, mentions légales), et chaque associé a sa part (`capital_souscrit`, fiche des associés, GL-16). Mais aucune écriture ne le porte : le compte 101 est à zéro, et le bilan d'ouverture est faux.

Les statuts de Kwa-Ba SAS ont été signés chez le notaire le **16 novembre 2026**. À cette date, les associés s'engagent à apporter le capital : c'est la souscription. Le capital n'est pas encore versé (21 novembre 2026).

# Options
Option 1 : Attendre le versement et n'écrire qu'une ligne de capital libéré. Le bilan resterait faux d'ici là, et la souscription n'apparaîtrait nulle part.

Option 2 : Écrire la souscription à la date des statuts, puis la libération quand l'argent arrive.

# Décision
Nous retenons l'option 2.

- Un compte d'argent technique `APPORTS`, « Associés, capital souscrit non versé » (compte **4611**, type `apport`), sans relevé de prestataire, exclu du rapprochement.
- **Souscription** : une ligne `F01` (capital, compte 101) par associé, pour sa part, sur le compte `APPORTS`, datée du jour des statuts : débit 4611 / crédit 101, 500 000 F au total.
- Une commande serveur, `manage.py subscribe_capital --date 2026-11-16`, lancée une fois par environnement (les associés diffèrent entre la préprod et la production). Elle refuse si la somme des parts n'est pas exactement le capital, si la souscription est déjà écrite, ou si le mois est clôturé. Elle est journalisée.
- **Libération** : le jour où l'argent arrive, un virement interne (`V01`, existant) du compte `APPORTS` vers le compte bancaire : débit banque / crédit 4611. Aucun code de plus.

# Conséquences :
positives (bénéfices)
- Le compte 101 porte le capital dès la date des statuts, et le bilan d'ouverture est juste.
- Ce que chaque associé doit encore apporter se lit sur le compte 4611.

négatifs (inconvénients)
- La commande doit être lancée sur chaque environnement, après la saisie des parts des associés.

Impacts futurs
- Pour des apports en numéraire non encore versés, le plan SYSCOHADA propose aussi le compte **4613** (apporteurs, capital appelé non versé). Si l'expert-comptable le préfère au 4611 du doc 37, une migration change le compte du compte d'argent `APPORTS`, sans toucher au code.
- Complète ADR-026 (rubrique Finance) et GL-16 (comptes des associés).
