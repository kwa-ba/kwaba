# Titre:
Rubrique Finance : toute la comptabilité et le pilotage de Kwa-Ba au back-office, lus et écrits dans le grand livre

# Status:
Accepté (18 et 19 novembre 2026). Livré en préprod : PR #292 à #301.

# Contexte :
L'ADR-024 a posé le grand livre des mouvements : une ligne par mouvement d'argent, en ajout seul, garantie par la base, avec ses vues de restitution. Mais au 18 novembre 2026, ce moteur n'avait presque pas d'écrans. Il n'y avait aucun avoir, aucun document de caution, aucune dépense, aucun rapprochement avec FedaPay, aucune clôture utilisable. Sans dépenses, le « résultat » affiché n'était que du chiffre d'affaires.

La demande consolidée du référent financier (doc 25, expliquée simplement dans le doc 28) liste 23 tickets, GL-1 à GL-23 :
- GL-1 à GL-14 rendent la comptabilité exacte et conforme : il faut les terminer pour ouvrir le 15 décembre 2026 ;
- GL-15 à GL-23 rendent le pilotage et le reporting exacts : il faut les terminer avant la première clôture, le 31 janvier 2027.

Les associés ont arrêté les décisions en attente les 18 et 19 novembre 2026. Le président a confirmé les choix comptables et juridiques, après relecture des contrats par le juriste.

Quatre règles ne changent pas :
- le grand livre est en ajout seul, et une erreur se corrige par une ligne inverse ;
- une pièce numérotée ne se supprime jamais : une facture annulée reçoit un avoir ;
- aucune valeur métier n'est écrite en dur : elle vit dans la table des paramètres ;
- chaque écriture se fait dans la même transaction que son action.

# Options
Option 1 : Exporter les mouvements vers un logiciel comptable du marché et y tenir la comptabilité. C'est rapide, mais l'argent des tiers, les cautions et le rapprochement FedaPay resteraient hors de l'appli. Il faudrait ressaisir, et le back-office ne saurait pas piloter.

Option 2 : Des écrans qui recalculent les chiffres à partir des réservations et des paiements, comme le faisait la page Finances d'origine. Deux sources pourraient diverger, et rien ne prouverait ce qui a été écrit.

Option 3 : Tout lire et tout écrire dans le grand livre de l'ADR-024.
- Chaque écran est un tri des lignes.
- Chaque opération d'argent saisie au back-office (dépense, régularisation, virement, sinistre, dotation, amortissement) passe par un service du module `finance`. Ce service applique la double validation, exige une pièce justificative et écrit au journal.

# Décision
Nous retenons l'option 3.

## Architecture
- **Un seul grand livre.** Les livres de l'article 19 de l'AUDCIF (livre-journal, grand-livre par compte, balance, livre d'inventaire), l'export comptable, la synthèse, le tableau de bord, les relevés et les rapports sont tous des requêtes sur `finance_mouvement` ou sur sa partie double (`finance_ecriture`). Aucun chiffre n'est recalculé à partir des réservations.
- **Partie double.** Chaque ligne a deux faces : le compte de sa nature et le compte du compte d'argent. Les « comptes d'argent » sans relevé servent de contrepartie :
  - `ASSOCIES` (471) : le passage des avances des associés ;
  - `GARANTIE` (192) : le fonds de garantie ;
  - `AMORTISSEMENTS` (2813) : les amortissements.

  Ces trois comptes ne sont jamais rapprochés.
- **Module `finance` hexagonal.** Chaque besoin a son port et son adaptateur. Les autres modules ne passent que par `finance.api` (ADR-019) :
  - `paiements` écrit les frais réels, les versements et les remboursements ;
  - `documents` produit les PDF et range les justificatifs ;
  - `transferts` et `locations` lisent leurs paramètres.
- **Double validation** (`ValidationService`). À partir d'un seuil, une deuxième personne approuve l'opération, qui s'exécute alors dans la transaction de l'approbation. Chaque module déclare ses opérations au démarrage. Seuils :

  | Opérations | Seuil |
  |---|---|
  | Remboursements, versements, régularisations, virements | 250 000 F |
  | Dépenses | 50 000 F |
- **Permissions.**
  - Le rôle Finance lit tout et n'écrit rien.
  - Les opérations d'argent demandent la permission « Opérations financières ».
  - La clôture d'un mois, la modification d'un paramètre, l'ouverture du compte bancaire et les écritures d'inventaire sont réservées aux super administrateurs.
- **Pièces et justificatifs.**
  - Une dépense, une régularisation ou un virement n'est pas accepté sans pièce jointe.
  - Les séries sont continues, sans trou : FAC, AVO, REC, RET, DEP, VIR, DOT et INV.
- **Référentiel des paramètres** (`finance_parametre` et son historique).
  - **Source unique :** toutes les valeurs décidées y vivent, et chaque changement est daté et signé avec son motif.
  - **Valeur à une date :** `parametre_au(cle, moment)` donne la valeur en vigueur à un moment donné. Une réservation garde ainsi le délai de versement de sa date.
  - **Valeur à 0 :** elle rend sa règle inerte.
  - **Page Tarifs :** elle recopie au référentiel les taux qu'elle modifie.
- **Garanties en base.** Les vues de restitution sont recréées à chaque migration (ADR-024).
  - Invariants I5 et I8 à I17 : rapprochement fait, cautions, partie double équilibrée, comptes SYSCOHADA renseignés, monnaie électronique jamais créditrice, comptes courants d'associés jamais débiteurs, fonds de garantie jamais négatif, compte 585 soldé.
  - Dix contrôles de clôture.
  - Un mois verrouillé ne se rouvre jamais.

## Décisions par ticket
| Ticket | Décision |
| --- | --- |
| GL-1 à GL-7, GL-19 | Rubrique Finance, livres de l'article 19, export SYSCOHADA, clôture mensuelle par un super administrateur, rapports enregistrés et rapport libre |
| GL-8 | Avoir AVO continu sur toute vente remboursée : avoir du montant remboursé, ou du total si le remboursement est complet |
| GL-9 | Remboursement calculé sur l'instantané des tarifs, jamais sur les taux du jour |
| GL-10 | Rôle Finance en lecture seule, permission « Opérations financières », double validation, journal |
| GL-11 | Page des versements aux partenaires : retard au-delà de 24 h, relance des versements en échec, alerte quotidienne |
| GL-12 | Rapprochement à trois côtés par opération, chaque nuit et à la demande. Frais FedaPay absorbés par Kwa-Ba : une ligne D01 par transaction au montant réel. Argent hors grand livre montré à part. Écart inexpliqué fermé par une régularisation motivée, avec pièce |
| GL-13, GL-14 | Registre des cautions. Reçu REC à la restitution. Avis RET à une retenue, avec motif, article des CGV et pièce |
| GL-15 | Dépenses avancées par un associé (D contre F03, compte courant 462). Pas de plafond, double validation à partir de 50 000 F, annuaire des fournisseurs |
| GL-16 | Comptes courants d'associés jamais débiteurs. Capital de 500 000 F affiché avec la part de chacun, écriture d'ouverture avec l'expert-comptable. Remboursement des avances avec le compte bancaire |
| GL-17 | Fonds de garantie : 10 % du revenu net de chaque mois. Provision 6911 / 192 / 7911. Un sinistre est une dépense D04 couverte avec la référence de la décision. Alerte sous la cible |
| GL-18 | Tableau de bord : résultat, quatre poches de trésorerie, annulations (FF-05), impôt estimé, seuils des associés, export CSV |
| GL-20 | Page des paramètres avec historique. Versement à l'hôte 48 h après l'arrivée pour les réservations faites depuis le 19 novembre 2026 (CGV 2.5, contrats hôte et hôtel), les réservations antérieures gardant 24 h. Tarifs des locations lus au référentiel |
| GL-21 | Relevés des partenaires et rapport mensuel aux associés, en consultation et en PDF. Rien n'est envoyé automatiquement |
| GL-22 | Virements internes : paires V01, compte 585 soldé. Import du relevé bancaire en CSV, rapproché des virements. Le compte bancaire reste fermé jusqu'à son ouverture réelle, rapproché à partir de ce jour |
| GL-23 | Séjour annulé après le versement à l'hôte : retenue sur ses versements suivants, sinon demande de remboursement tracée. Une clause de compensation est ajoutée au contrat. Amortissement linéaire de la Solution (D20 / 2813), livre d'inventaire, à-nouveaux |

## Plan de comptes retenu (SYSCOHADA révisé)
| Rôle | Comptes |
| --- | --- |
| Argent détenu | 554 FedaPay (monnaie électronique), 5211 banque d'exploitation, 5212 banque des fonds de tiers |
| Argent des tiers | Sous-comptes 4712x de chaque partenaire, 165 cautions des voyageurs |
| Produits de Kwa-Ba | 706x : frais de service et commissions, la part qui revient à Kwa-Ba en tant que mandataire |
| Charges | 6317 frais FedaPay, 6xx dépenses, 681 amortissement, 6911 dotation au fonds de garantie |
| Associés et capital | 462 comptes courants, 101 capital, 131 / 139 résultat en attente d'affectation |
| Passage et virements | 471 avances des associés, 585 virements de fonds |
| Fonds de garantie | 192 provision pour garanties données aux clients, 7911 reprise |

Deux points restent à traiter à la clôture annuelle :
- la dotation forfaitaire au fonds est réintégrée au résultat fiscal ;
- la provision est ajustée au risque probable. La part attendue dans l'année peut être reclassée en 499.

Les comptes sont arrêtés et visés par l'expert-comptable inscrit à l'Ordre.

# Conséquences :
positives (bénéfices)
- **Tout au back-office :** la comptabilité, la trésorerie et le pilotage de Kwa-Ba s'y trouvent, avec une seule source de chiffres.
- **Clôture vérifiée :** un mois ne se clôture que si le grand livre est juste, rapproché et équilibré.
- **Traçabilité :** chaque opération d'argent a sa pièce, sa personne, son motif et sa ligne au journal.
- **Évolution sans code :** les décisions des associés changent par un paramètre historisé, sans nouvelle version de l'appli.

négatifs (inconvénients)
- **Mise en place :** le module `finance` devient le plus gros du projet, avec 18 migrations.
- **Pages Tarifs et Finances d'origine :** les taux du site restent lus dans `ReglagesTarifsModel` (cache) et sont recopiés au référentiel. La page Finances d'origine (`paiements`) existe encore à côté des livres.
- **Saisie manuelle :** un hôte qui rembourse Kwa-Ba par un autre moyen n'est pas encore saisi dans l'appli. Les dépenses payées par la banque ne sont pas encore ouvertes.

Impacts futurs
- **Paramètres à fixer par les associés** (aujourd'hui à 0, donc sans effet) :
  - la cible du fonds de garantie ;
  - le revenu du scénario prudent ;
  - la valeur, la durée et le mois de mise en service de la Solution.
- **Le jour où le compte bancaire existe :** l'ouvrir depuis Finance → Virements et banque, puis importer ses relevés. Ouvrir alors les dépenses payées par la banque et le remboursement des avances aux associés.
- **Clôtures :**
  - la première clôture mensuelle a lieu le 31 janvier 2027 ;
  - la première clôture annuelle de l'exercice demande les écritures d'inventaire, les à-nouveaux et le visa de l'expert-comptable. Le premier bilan est à déposer au plus tard le 30 avril 2028.
- **Liens avec les autres ADR :** complète l'ADR-024 (grand livre) et l'ADR-025 (toutes ces actions arrivent au journal d'activité), et respecte l'ADR-019 (les modules ne se parlent que par leur `api`).
- **Référence :** le détail de chaque écran, règle et test est dans `documentation/modules/finance.md` et `paiements.md`.
