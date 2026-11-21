# Titre:
Cut-off des frais de service (477) et paramètres fiscaux dormants (DEV-C2, DEV-C8, DEV-C9)

# Status:
Accepté (21 novembre 2026). Comptes à confirmer par l'expert-comptable inscrit au Togo.

# Contexte :
Un produit entre au résultat de la période où le service est rendu : pour un séjour, à l'arrivée du voyageur. Le doc 37 (DEV-C2) et la carte de recette C.2 demandent qu'un séjour payé en novembre avec une arrivée en janvier ne pèse pas sur le résultat de novembre, et qu'à la clôture aucune ligne de revenu ne concerne une arrivée postérieure à la période.

Le grand livre des séjours (FIN-03) fait déjà une partie du travail :
- au paiement, les nuits et la commission de l'hôte restent dans l'argent de l'hôte (T01), et seuls les **frais de service du voyageur** (R01, compte 7061) entrent au revenu ;
- à l'arrivée, la commission passe en revenu (R02 ou R03, ligne de clé `arrivee:<réservation>`).

Seuls les frais de service R01 entrent donc au résultat avant le séjour.

Pour la fiscalité, le doc 37 demande aussi que les taux non confirmés par l'OTR restent désactivés (règle 4) et que le tableau de bord alerte à l'approche du seuil de la TVA (DEV-C8). Or `impot_minimum` (minimum forfaitaire, 1 %) était actif, et `tva_seuil` (100 000 000 F) inactif, ce qui rendait l'alerte muette. L'impôt estimé (DEV-C9 : le plus élevé de l'IS et du minimum forfaitaire) existe déjà au tableau de bord.

# Options
Option 1 : Écrire les frais de service à l'arrivée, comme la commission. Ils resteraient en fonds de tiers jusque-là, ce qui change le cœur du circuit des séjours et la définition des fonds de tiers.

Option 2 : Une régularisation de fin de mois : les frais de service d'un séjour pas encore commencé passent en produits constatés d'avance (477), puis reviennent au résultat le jour de l'arrivée.

# Décision
Nous retenons l'option 2 (KPOGLO Godwin, 21 novembre 2026).

- Un compte d'argent technique `PCA`, « Produits constatés d'avance » (compte **477**, type `regularisation`), sans relevé de prestataire, exclu du rapprochement comme la réserve du fonds de garantie.
- À la fin de chaque mois terminé et non verrouillé, pour chaque réservation, la part de ses frais de service en 477 doit valoir :
  - ses frais de service R01 nets du mois et des précédents, si ni l'arrivée ni l'annulation n'ont eu lieu à la fin du mois ;
  - 0 sinon.

  Seul l'écart est écrit, en R01 sur le compte `PCA` : débit **7061** / crédit **477** pour mettre en attente, datée du dernier jour du mois ; l'inverse pour remettre au résultat, datée de l'arrivée ou de l'annulation. Les frais réduits après coup et les annulations sont donc suivis sans règle à part.
- La régularisation passe chaque heure avec le worker des paiements, comme la dotation du fonds de garantie, et avant chaque clôture.
- La clôture d'un mois refuse tout reste : « aucun frais de service d'une arrivée postérieure au mois dans le résultat ».
- Les invariants de l'encaissement (I1 à I3) ne regardent que les lignes d'origine `paiement` : la régularisation (origine `cut_off`) ne les touche pas. I7 reste juste, puisque les lignes R01 et la balance bougent ensemble.
- `tva_seuil` devient actif : l'alerte du tableau de bord fonctionne. Aucune TVA n'est facturée tant que Kwa-Ba n'est pas assujettie.
- `impot_minimum` devient inactif jusqu'à la confirmation de l'OTR : l'impôt estimé ne retient alors que l'IS (27 %).

# Conséquences :
positives (bénéfices)
- Le résultat d'un mois ne contient que des séjours commencés, ce que la clôture vérifie.
- Le circuit du paiement et ses invariants ne changent pas.

négatifs (inconvénients)
- Une ligne de plus par séjour réservé un mois avant son arrivée, et une autre à l'arrivée.
- Le résultat du mois en cours, avant sa fin, montre encore les frais de service des arrivées futures : la régularisation est une écriture de fin de mois.

Impacts futurs
- Les transferts et les locations, le jour où ils écriront au grand livre, suivront la même règle.
- Le minimum forfaitaire se réactive par la page Paramètres, avec un motif, une fois confirmé par l'OTR.
- Cartes de recette C.2 et C.4 (doc 35).
