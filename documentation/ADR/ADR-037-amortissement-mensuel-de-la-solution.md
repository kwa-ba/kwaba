# Titre:
Amortissement de la Solution écrit chaque mois (DEV-C6)

# Status:
Accepté (21 novembre 2026). Valeur, durée et mise en service à saisir au référentiel par l'équipe.

# Contexte :
La Solution (le logiciel et le site, compte 213) est amortie en linéaire sur sa durée, à partir de sa mise en service (GL-23). Les paramètres `solution_valeur`, `solution_duree_mois` et `solution_mise_en_service` (AAAAMM) la décrivent ; tant qu'ils valent 0, rien ne s'écrit. Aujourd'hui l'amortissement de l'année est écrit en une fois, au 31 décembre, par un super administrateur (écritures d'inventaire) : D20, débit 681 / crédit 2813.

Le document consolidé (doc 37, DEV-C6) demande une dotation **mensuelle**, linéaire sur 3 ans : le résultat de chaque mois porte sa part de l'amortissement, et le tableau de bord en tient compte.

# Options
Option 1 : Garder l'écriture annuelle. Le résultat des onze premiers mois est trop haut, puis décembre absorbe toute l'année.

Option 2 : Une dotation chaque mois, et l'écriture d'inventaire de fin d'exercice en rattrapage seulement.

# Décision
Nous retenons l'option 2.

- Ce qui est dû à la fin d'un mois est calculé en cumulé : `valeur × mois écoulés depuis la mise en service / durée`, arrondi au franc, plafonné à la valeur. Chaque mois reçoit l'écart entre ce cumul et ce qui est déjà écrit : les arrondis ne dérivent pas, et le dernier mois prend exactement le reste.
- La dotation (D20 sur le compte `AMORTISSEMENTS`, débit 681 / crédit 2813) est datée du dernier jour du mois. Elle est écrite chaque heure par le worker des paiements pour les mois terminés et ouverts, et avant la clôture d'un mois.
- Le montant dû pour une année (livre d'inventaire, écriture de fin d'exercice) devient la différence du cumul entre deux 31 décembre : il est égal à la somme des dotations mensuelles, et l'écriture de fin d'exercice ne sert plus qu'à rattraper un manque.
- Rien ne s'écrit tant que les trois paramètres ne sont pas saisis (doc 37 : linéaire 3 ans, donc `solution_duree_mois` = 36).

# Conséquences :
positives (bénéfices)
- Le résultat de chaque mois porte sa part de l'amortissement.
- Une seule règle de calcul pour le mois, l'année et l'inventaire.

négatifs (inconvénients)
- Une ligne D20 de plus chaque mois pendant la durée d'amortissement.

Impacts futurs
- Une autre immobilisation suivrait la même règle, avec ses propres paramètres.
- Complète GL-23 (livre d'inventaire) et ADR-026.
