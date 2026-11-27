# Titre:
Frais FedaPay (D01) recalés sur le relevé à chaque import

# Status:
Accepté (27 novembre 2026).

# Contexte :
Les frais réels d'une opération FedaPay sont écrits au grand livre à l'import du rapprochement (D01, compte 6317, GL-12). Ils ne sont jamais estimés à l'encaissement : la ligne D01 est écrite au montant lu chez FedaPay.

Mais elle n'est écrite qu'une fois : l'unicité sur la référence externe fait ignorer les imports suivants. Si FedaPay donne un autre frais plus tard (statut qui se stabilise, première lecture fausse, démo reconstruite), le grand livre garde le premier montant et l'opération reste en écart pour toujours. C'est ce que la recette du 22 novembre a montré (RES-AF2026-61FB : D01 11 262 F au grand livre, 6 758 F au relevé, 6 journées en écart, I5 non nul). Le bouton « Réimporter » ne pouvait rien y faire.

Le grand livre est en ajout seul : on ne modifie pas la ligne d'origine.

# Options
Option 1 : Contre-passer la ligne D01 et la réécrire au nouveau montant (`rectifier`). Deux lignes de plus à chaque changement, et la ligne réécrite perd sa référence externe, donc son rattachement à l'opération dans le rapprochement.

Option 2 : Une ligne d'ajustement de la différence, avec une colonne `frais_releve_applique` sur l'opération pour ne pas l'écrire deux fois (proposition du doc 39). La colonne peut ne plus dire la même chose que le grand livre.

Option 3 : Une ligne d'ajustement de la différence, calculée à chaque import comme `frais du relevé − somme des D01 déjà écrits pour l'opération`. Le grand livre est la seule mémoire : rejouer l'import donne une différence nulle, donc aucune ligne.

# Décision
Nous retenons l'option 3 (décision de Godwin du 27 novembre 2026).

- À chaque import d'une journée, pour chaque opération dont l'argent est au grand livre : `delta = frais du relevé − D01 déjà écrits`.
- `delta > 0` : D01 en sortie du compte FEDAPAY (frais sous-estimés). `delta < 0` : D01 en entrée du compte FEDAPAY (frais surestimés, la charge baisse).
- La première ligne garde la référence de l'opération. Un ajustement porte la référence `frais:<opération>:<n>`, que le rapprochement rattache à l'opération (comme une régularisation, sans en être une). Le doc 39 proposait de lier l'ajustement à la ligne d'origine comme une contre-passation partielle. Nous ne le faisons pas : le rapprochement exclut les corrections du total d'une opération, et l'ajustement serait sorti de l'opération.
- Même transaction que l'import et le calcul de la journée. Un mois clôturé ne se réimporte pas : ses frais ne bougent plus.
- Une opération illisible chez FedaPay n'est pas ajustée. Un frais lu à 0 ramène les D01 à 0.

# Conséquences :
positives (bénéfices)
- « Réimporter » solde l'écart d'une opération dont le frais a changé : D01 = relevé, écart nul, I5 à zéro sur une base propre.
- Idempotent sans nouvelle colonne : rejouer l'import n'écrit rien.
- La ligne d'origine et chaque ajustement restent visibles.

négatifs (inconvénients)
- Une nouvelle forme de référence externe (`frais:`) que la clé d'opération du rapprochement doit connaître.
- Le module finance est touché (port du rapprochement, service) : relecture demandée à Fadel.

Impacts futurs
- Si FedaPay change un frais après la clôture du mois, l'écart se traite par une régularisation sur le mois ouvert, comme aujourd'hui.
