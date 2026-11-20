# Titre:
Fonds de garantie : une réserve, pas une provision (DEV-C1)

# Status:
Accepté (21 novembre 2026). Comptes à confirmer par l'expert-comptable inscrit au Togo (question Q6).

# Contexte :
Le fonds de garantie (GL-17, ADR-026) reçoit chaque mois 10 % du revenu net (`fonds_garantie_taux`) et couvre les sinistres que Kwa-Ba paie au titre de sa garantie. Les décisions du 19 novembre 2026 (migrations `0013` et `0015`), sur une proposition de l'expert-comptable (doc 26), l'ont traité comme une **provision** :
- dotation `G01` : débit 6911 (charge) / crédit 192 (provision) ;
- utilisation `G02` : débit 192 / crédit 7911 (reprise, produit) ;
- sinistre `D04` : 659.

La recette live du 20 novembre (doc 36) a fait ressortir ce traitement : 769 598 F de charge en 6911. La réponse de l'expert-comptable (doc 32, Q6) et le document consolidé (doc 37, DEV-C1) recommandent l'inverse. Une dotation **forfaitaire** (un pourcentage du revenu, avant tout sinistre, pour un risque non individualisé) n'est pas une provision. En charge, elle diminue le résultat et la base de l'IS, et une provision pour risque général est en principe non déductible : c'est un risque de redressement.

# Options
Option 1 : Garder la provision (6911 / 192 / 7911) et réintégrer la dotation au résultat fiscal. Le résultat comptable du mois reste diminué, ce qui est contraire au doc 32.

Option 2 : Une réserve. La dotation est une affectation du résultat (classe 1) ; seul le sinistre payé est une charge.

Option 3 : Une provision calculée sur une estimation statistique des sinistres probables. Kwa-Ba n'a pas encore d'historique de sinistres pour la fonder.

# Décision
Nous retenons l'option 2. Chaque mouvement donne deux lignes : le compte de sa nature et, en contrepartie, celui du compte d'argent.

| Mouvement | Écriture |
|---|---|
| Dotation `G01` | débit **1301** (résultat en instance d'affectation) / crédit **118** (réserve du fonds de garantie) |
| Utilisation `G02` | débit **118** / crédit **1301** : la réserve couvre le sinistre, hors résultat |
| Sinistre payé `D04` | **658** (charges diverses, au lieu de 659) : c'est la seule charge liée au fonds |

- La dotation ne touche plus aux classes 6 à 8 : **le « Résultat du mois » ne change pas** quand on la passe.
- Le compte d'argent `GARANTIE` devient une **réserve** (type `reserve`, compte 118), toujours sans relevé de prestataire, hors trésorerie libre : c'est une poche fléchée de l'argent que Kwa-Ba détient.
- Les lignes de la famille `G` vont au journal des opérations diverses (OD), et non plus à la trésorerie (TR).
- L'invariant I7 compare désormais R − D au résultat de la balance (classes 6 à 8), sans la famille `G`.
- Le taux reste un paramètre (`fonds_garantie_taux`). Les comptes sont des correspondances historisées (`finance_correspondance_histo`) : si l'expert-comptable choisit d'autres numéros, une migration les change sans toucher au code.
- Les dotations déjà écrites ne sont pas contre-passées : la base de préprod est remise à zéro avant la recette finale (H2), et aucune n'existe en production.

# Conséquences :
positives (bénéfices)
- Le résultat du mois et la base de l'IS ne sont plus diminués par une dotation forfaitaire.
- Le fonds reste visible, séparé de la trésorerie libre, et l'invariant « fonds ≥ 0 » est inchangé.

négatifs (inconvénients)
- Une affectation en réserve se décide en principe en assemblée, sur le résultat de l'exercice. Ici elle est suivie mois par mois, comme un fléchage de gestion : l'expert-comptable doit valider cette présentation, et l'écriture définitive d'affectation à la clôture annuelle.
- La décision du 19 novembre est remplacée : les recettes et documents qui citent 6911, 192 et 7911 sont à mettre à jour.

Impacts futurs
- Si un historique de sinistres permet un jour une estimation fiable, une provision (option 3) pourra compléter la réserve.
- Remplace, pour le fonds de garantie, la décision du 19 novembre (ADR-026, migrations `0013` et `0015`). Carte de recette C.1 (doc 35).
