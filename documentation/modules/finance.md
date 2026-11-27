# Module finance : le grand livre des mouvements

Chaque mouvement d'argent est écrit **une seule fois**, dans une table en ajout seul, avec un code de nature et ses axes d'analyse (offre, tiers, moyen de paiement, compte d'argent, période, pièce). Tous les documents financiers sont des tris de ces lignes : aucune restitution ne recalcule depuis les réservations.

- Décision d'architecture : [ADR-024](../ADR/ADR-024-module-finance-grand-livre.md).
- Rubrique Finance complète (GL-1 à GL-23), décisions des associés et plan de comptes : [ADR-026](../ADR/ADR-026-rubrique-finance-comptabilite-complete.md).
- Référence métier : dossier DAF du référent financier (10 et 11 novembre 2026) : cahier des charges FIN-01 à FIN-17, schéma `07_Schema_base_de_donnees.sql`, référentiel des paramètres, plan de test d'audit (séries FA à FJ).
- Code : `server/apps/finance/`. Seule interface pour les autres modules : `apps/finance/api.py` (ADR-019).

## Architecture (hexagonale, comme `agenda`)

| Couche | Contenu |
| --- | --- |
| `domain/` | `entities.py` (`Ligne`, `Ecriture`, `Mouvement`, `Referentiels`, sens, états d'un mois), `rules.py` (contrôle d'une ligne, ligne inverse, mois comptable), `exceptions.py` (`MouvementRefuse`, `RestitutionRefusee`). Python pur, sans Django |
| `application/` | `ports/` (`GrandLivre`, `Parametres`, `Restitutions`, `Alertes`, `Journal`, `TransactionManager`, `Clock`…), `service/` (`GrandLivreService`, `RestitutionService`, `DepenseService`…) |
| `infrastructure/` | `persistence/models/` (tables), `persistence/repositories/` (écriture, idempotence, verrous consultatifs, traduction des refus de la base), `persistence/sql_restitutions.py` (vues et fonctions SQL, source unique), `persistence/restitutions.py` (leur lecture), `notifications/alertes.py` (emails par `notifications.api`), `journal.py` (journal d'activité, module `activity`), `checks.py` (contrôle `finance.E001`), `clock.py`, `container.py` |
| `api.py` | fonctions simples qui délèguent aux services ; données simples en entrée et en sortie |
| `migrations/` | `0001` tables, `0002` référentiels du fichier, `0003` garde-fous (triggers). Les vues et fonctions ne sont pas dans une migration : supprimées avant chaque `migrate`, recréées après depuis `sql_restitutions.py` (`apps.py`) |

`server/.importlinter` (contrat `finance-couches`) interdit au domaine et à l'application d'importer l'infrastructure.

### Un fichier par sous-domaine

Les paquets `application/service/`, `application/ports/`, `infrastructure/persistence/models/`, `infrastructure/persistence/repositories/` et `infrastructure/http/admin_views/` ont un fichier par sous-domaine, avec les mêmes noms d'une couche à l'autre :

| Fichier | Sous-domaine |
| --- | --- |
| `ledger.py` | grand livre, mois comptables, paramètres |
| `reporting.py`, `reports.py`, `books.py`, `closing.py` | restitutions, rapports, livres de l'article 19, clôture |
| `validations.py` | double validation |
| `deposits.py` | registre des cautions |
| `reconciliation.py` | rapprochement FedaPay et régularisations |
| `expenses.py`, `current_accounts.py` | dépenses, fournisseurs, associés et comptes courants |
| `guarantee_fund.py` | fonds de garantie |
| `parameters.py` | paramètres pilotés |
| `transfers.py`, `treasury.py` | virements internes, comptes d'argent et relevés bancaires |
| `core.py`, `common.py`, `reference_tables.py`, `dashboards.py` | pièces partagées, référentiels, tableaux de bord |

Le `__init__.py` de chaque paquet réexporte ses noms publics : on importe toujours `apps.finance.application.service`, `…ports`, `…persistence.models`, etc., jamais un fichier du paquet depuis l'extérieur de sa couche. Un nouveau sous-domaine ajoute son fichier dans chaque couche qui le concerne.

`api.py` reste un seul fichier : c'est la seule porte d'entrée du module pour les autres (ADR-019), et il ne fait que déléguer.

### SQL brut

Les agrégats comptables (balance, grand livre, invariants, pilotage) sont écrits en SQL : l'ORM les exprimerait mal et plus lentement, et ce sont eux qui garantissent l'exactitude des comptes. Règles :

- le SQL brut ne vit que dans `infrastructure/persistence/` (`sql_restitutions.py` pour les vues et fonctions, `restitutions.py` et `pilotage.py` pour leur lecture, quelques requêtes dans `repositories/`), jamais dans le domaine, l'application ou les vues ;
- chaque requête est couverte par un test d'intégration sur PostgreSQL (`server/tests/integration/finance/`) : une requête modifiée sans test qui la couvre ne passe pas la relecture ;
- les paramètres passent toujours par `%s` (jamais de f-string avec une valeur venue de l'extérieur).

## Ce qui écrit dans le grand livre aujourd'hui : les séjours (FIN-03)

Chaque événement d'argent d'un séjour payé en ligne écrit ses lignes dans la transaction de l'action (`apps/paiements/grand_livre.py`) :

| Événement | Lignes | Où |
| --- | --- | --- |
| Paiement accepté | T01 prix des nuits et T02 ménage (dus à l'hôte ou à l'hôtel), R01 frais de service, C01 caution séquestrée (argent du voyageur, inscrite au registre des cautions), R07 forfait de la garantie renforcée ; référence de la transaction FedaPay, moyen (Moov, Mixx, carte) | `reservations/paiement.py`, `paiement_recu` |
| Paiement refusé tout de suite (payé deux fois, réservation annulée entre-temps, dates prises) | T05 entrée : dû au voyageur | `paiements.services.rembourser` |
| Arrivée du voyageur (14 h le jour d'arrivée) | T01 sortie et R02 (particulier) ou R03 (hôtel) : la commission devient un produit | `reservations/paiement.py`, `constater_commissions`, une fois par séjour (`commission_constatee_le`) |
| Annulation | T02 et T01 sortie de ce qui est rendu, R01 rectifié si les frais sont rendus, C02 sortie de toute la caution (REC émis, registre soldé), R07 rectifié si l'hôte ou Kwa-Ba annule, R08 pour la part de Kwa-Ba sur les nuits retenues (cas FF-02), puis T05 entrée | `paiements.services.annuler_paiement_reservation` |
| Caution soldée après le départ (délai `caution_restitution_heures` passé) | C02 sortie de ce qui est rendu, puis T05 entrée ; C03 sortie de ce qui est retenu (motif et décision) et T10 entrée, due à l'hôte ([ADR-038](../ADR/ADR-038-retenue-sur-caution-versee-a-l-hote.md)) ; REC ou RET émis, registre soldé | `reservations/deposit.py`, `return_due_deposits` (worker) |
| Frais réduits après le paiement (Pack Séjour + Chauffeur) | R01 rectifié (ligne inverse puis nouveau montant), puis T05 entrée de la différence | `reservations.api.reduire_frais_pack_sejour` |
| Remboursement envoyé | T05 sortie | `paiements.services` (FedaPay et PayPal) |
| Versement à l'hôte envoyé | T09 sortie | `paiements.services.synchroniser_payout` |
| Indemnité de dommage versée à l'hôte | T09 sortie | `paiements/damage_payouts.py`, `synchronise` |

Les montants sont ceux figés sur la réservation à sa création : un taux changé ensuite ne modifie rien (FA-11). Un séjour payé avant le grand livre, ou payé hors ligne, n'y a aucune ligne : il n'en reçoit jamais après coup (aucune sortie de ce qui n'est jamais entré). Les réservations existantes sont marquées par la migration `reservations 0012`.

À venir, sur le même modèle : transferts (chauffeur « à désigner » jusqu'à son attribution) et locations de voiture (propriétaire, chauffeur, caution C01 à C03). Kwa-Ba Give n'écrit rien tant que ses natures ne sont pas décidées.

## Back-office : la rubrique Finance

Une seule rubrique **Finance** dans le menu (GL-1, section de droits « finances ») ; ses pages s'ouvrent sous elle. Tout est lu dans le grand livre, sauf « Encaissements et versements » (calculé depuis les paiements, gardé pour comparer). Les seules écritures sont la clôture d'un mois et l'enregistrement d'un rapport, toutes deux au journal d'activité.

| Page | Ticket | Contenu | API (`/api/v1/admin/finance/…`) |
| --- | --- | --- | --- |
| Tableau de bord | GL-18 | activité, chiffre d'affaires et résultat du mois et de l'année, revenu et marge par offre, taux de frais réel, trésorerie en quatre poches, dû aux associés, annulations (FF-05), impôt estimé et seuil de TVA, seuils des associés, qualité ; export CSV | `tableau-de-bord/?mois=[&export=csv]` |
| Relevés des partenaires | GL-21 | par partenaire : dû, versé, commissions de Kwa-Ba, solde du mois, récapitulatif de l'année ; PDF | `releves-partenaires/[?tiers_type=&tiers_id=&mois=&export=pdf]` |
| Rapport aux associés | GL-21 | les chiffres du mois et le commentaire du référent ; PDF (consultation, rien n'est envoyé) | `rapport-associes/?mois=[&export=pdf]` |
| Livre d'inventaire | GL-23 | amortissement de la Solution, écritures d'inventaire, résultat, bilan, à-nouveaux de l'année suivante ; export CSV | `inventaire/?annee=[&export=csv]` |
| Synthèse | — / GL-18 (partiel) | invariants, soldes qui ne se mélangent jamais, comptes d'argent, sommes dues par partenaire, marge par offre, taux de frais réel et fonds de garantie du mois | `grand-livre/`, `pilotage/?mois=` |
| Grand livre | GL-2 | toutes les lignes, du plus récent au plus ancien ; filtres combinés (période, famille, nature, offre, type et identifiant de tiers, compte d'argent, pièce, sens) ; pagination | `mouvements/`, `referentiels/` |
| Livre-journal | GL-3 | deux écritures par mouvement, débit et crédit, par date ; filtre par journal (VT, AC, TR, OD) ; totaux de la période | `livre-journal/` |
| Grand-livre par compte | GL-4 | un compte général, ou un tiers (compte auxiliaire), avec son solde progressif, d'ouverture et de clôture | `comptes/`, `comptes/<compte>/auxiliaires/`, `grand-livre-compte/` |
| Balance générale | GL-5 | par compte : solde d'ouverture, débits, crédits, solde de clôture ; totaux et équilibre | `balance/` |
| Rapprochement FedaPay | GL-12 | chaque journée terminée sur trois colonnes (Kwa-Ba, grand livre, FedaPay net et frais réels), verte, rouge ou non importée ; détail opération par opération ; importer ou réimporter une journée ou le mois ; régulariser un écart avec pièces | `rapprochement/?mois=`, `rapprochement/<AAAA-MM-JJ>/`, `rapprochement/<jour>/regulariser/` ; import : `paiements/rapprochement/importer/` (module `paiements`) |
| Comptes des associés | GL-16 | ce que Kwa-Ba doit à chaque associé (avancé, remboursé, solde), son relevé avec le solde après chaque ligne, le capital social et la part de chacun (modifiable) | `associes/comptes/`, `associes/<id>/releve/`, `associes/<id>/` |
| Fonds de garantie | GL-17 | solde, cible et alerte, poches de la trésorerie (dû aux partenaires, aux voyageurs, cautions, fonds, trésorerie libre), dotation de chaque mois, sinistres couverts et leur annulation | `fonds-garantie/`, `fonds-garantie/doter/`, `fonds-garantie/sinistres/`, `fonds-garantie/sinistres/<id>/annuler/` |
| Dépenses | GL-15 | les charges de Kwa-Ba avec leur justificatif : liste filtrée (période, nature, statut) et total écrit, saisie (date, nature D, offre, montant TTC, fournisseur, associé qui a avancé, n° de facture, pièces), annulation motivée ; onglets Fournisseurs et Associés | `depenses/`, `depenses/<id>/annuler/`, `fournisseurs/`, `associes/` |
| Versements aux partenaires | GL-11, GL-23 | chaque versement dû (hôtes, chauffeurs, propriétaires), date prévue, retard, échec et relance ; séjours annulés après leur versement (retenue, demande de remboursement) | `paiements/finances/versements/` |
| Encaissements et versements | (AN-B2) | page Finances d'origine (module `paiements`) : période, rapprochement jour par jour, versements, exports CSV et PDF | `paiements/finances/` |
| Remboursements | GL-9 | rembourser un séjour payé depuis ses montants figés (conditions du voyageur, ou intégral par Kwa-Ba) ; suivre chaque remboursement, saisir le compte Mobile Money, relancer, enregistrer un remboursement fait à la main (carte) | `paiements/finances/remboursements/` (module `paiements`) |
| Validations | GL-10 | les opérations à partir du seuil qui attendent une deuxième personne ; approuver ou refuser (motif) | `validations/`, `validations/<id>/approuver|refuser/` |
| Virements et banque | GL-22 | comptes d'argent (ouverture du compte bancaire par un super administrateur, rapproché à partir de ce jour), virements internes avec leur preuve, double validation, annulation ; import du relevé bancaire CSV, rapproché jour par jour | `virements/`, `virements/<id>/annuler/`, `comptes-argent/<code>/activation/`, `releves-bancaires/` |
| Paramètres | GL-20 | le référentiel des paramètres (taux, forfaits, plafonds, délais, seuils) avec leur source, recherche et filtres, l'historique daté de chacun (qui, quand, avant, après, pourquoi) ; modification par un super administrateur avec son motif | `parametres/`, `parametres/<cle>/` |
| Rapports | GL-19 | les rapports enregistrés, un rapport libre sur un ou deux axes, l'enregistrement d'un nouveau rapport (une ligne de `finance_rapport`) ; export CSV | `rapports/`, `rapports/resultat/`, `rapports/export/` |
| Clôture mensuelle | GL-7 | les dix contrôles d'un mois, et son verrouillage | `cloture/`, `cloture/<AAAA-MM>/` |
| Export comptable | GL-6 | le fichier des écritures (CSV `;`, UTF-8 avec BOM) pour le cabinet | `export/ecritures/` |

Règles :

- **Périodes** : `?debut=&fin=` (AAAA-MM-JJ, bornes comprises), ce mois-ci par défaut, un an au plus. **Listes** : `page`, `page_size` (20 par défaut, 100 au plus), réponse `{results, count, page, page_size}` comme le reste du back-office.
- **Comptes de résultat** (classes 6, 7, 8) : leur solde repart de zéro au 1er janvier (exercice civil) ; les comptes de bilan (1 à 5) reprennent leur solde depuis la première écriture. En attendant les écritures d'à-nouveaux (GL-23), c'est la balance et le grand-livre par compte qui l'appliquent.
- **Clôture** : un mois se clôture une fois terminé, dans l'ordre (le plus ancien mois ouvert d'abord), quand les dix contrôles de `finance_peut_on_cloturer` sont verts (la clôture écrit d'abord la dotation du mois au fonds de garantie, GL-17), par un **super administrateur** (décision du 18 novembre 2026), qui saisit le mois (« 10/2026 ») pour confirmer. Les clôtures simultanées s'attendent (verrou consultatif). Un mois verrouillé ne reçoit plus aucune écriture et **ne se rouvre jamais** : la base refuse toute modification ou suppression d'un mois verrouillé (trigger de la migration `0007`). Journal : `periode_cloturee`.
- **Exports** : écritures et rapports en CSV, cellules protégées contre l'injection de formules ; chaque export va au journal (`finances_exportees`, format `ecritures` ou `rapport`).
- **Rapports** : code de 3 à 40 caractères (minuscules, chiffres, `_`), titre de 3 à 120, axes de `finance_axe`, filtres de familles et d'offres en codes ; un axe inconnu est refusé par la base. Journal : `rapport_cree`.
- **Rapprochement** : le contrôle 4 de la clôture exige chaque journée du mois rapprochée (état `fait`, écart nul). Une journée jamais importée reste « non importée », jamais un écart nul (FIN-02.7). Voir la section suivante.

L'ancienne adresse `/backoffice/grand-livre` redirige vers `/backoffice/finances/grand-livre`.

## Rapprochement avec FedaPay (GL-12)

Décisions du 19 novembre 2026 : les frais FedaPay restent **à la charge de Kwa-Ba** (H-2, confirme la décision du 13 novembre) ; les données viennent de **l'API FedaPay**, relue chaque nuit, et d'un bouton « Réimporter » ; l'argent d'un produit pas encore au grand livre est **montré à part**, hors écart ; un écart inexpliqué se ferme par une **écriture de régularisation** motivée, avec pièce, validée par une deuxième personne à partir du seuil.

- **Import** (module `paiements`, `rapprochement.py`, le seul qui parle à FedaPay) : pour une journée terminée, chaque paiement, remboursement et versement de Kwa-Ba proche de ce jour est relu chez FedaPay (montant, frais réels, statut, date). La journée d'une opération est celle de FedaPay (approbation, envoi). Les transactions FedaPay inconnues de Kwa-Ba sont cherchées au mieux (`GET /transactions/search`, peu documentée : quelques pages, filtrées sur le jour ; si la recherche échoue, la journée le dit sans être bloquée).
- **Frais réels** : une ligne **D01** (compte 6317) par opération dont l'argent est au grand livre, au montant du relevé, sortie du compte FEDAPAY, sous la référence de l'opération. Elle alimente le taux de frais réel de la Synthèse. Recalés à chaque import (ADR-047) : si le relevé donne un autre frais, un frais plus haut ajoute la différence, un frais plus bas contre-passe les D01 en vigueur et réécrit le montant du relevé ; ces lignes portent la référence `frais:<opération>:<n>` et comptent dans l'opération, contre-passations comprises. Réimporter sans changement n'écrit rien.
- **Trois colonnes** (module `finance`, `RapprochementService`) : par opération, Kwa-Ba (le montant enregistré), le grand livre (somme signée des lignes du compte FEDAPAY de cette référence, régularisations comprises, corrections exclues sauf celles des frais D01) et FedaPay (montant moins les frais pour un encaissement, montant plus les frais pour une sortie). États : `concorde`, `ecart` (avec la raison : inconnue d'un côté, montants différents, frais pas au grand livre…), `regularisee`, `hors_livre`. Les autres lignes du compte ce jour-là (arrivée, annulation, corrections : des passages d'une nature à l'autre) forment les **mouvements internes**, qui doivent faire zéro.
- **Journée** (`finance_rapprochement_jour`) : `fait` seulement si toutes les opérations concordent et que l'écart est nul ; `en_erreur` sinon, ou si FedaPay était injoignable ; `non_fait` tant que rien n'est importé. Colonnes ajoutées : `solde_kwaba`, `frais`, `hors_grand_livre`, `internes`, `nb_operations`, `nb_anomalies`. Les opérations sont dans `finance_rapprochement_ligne` (données dérivées, recalculées à chaque import) et le relevé brut dans `finance_releve_externe`. Un import recalcule aussi les journées voisines déjà importées (trois jours de part et d'autre).
- **Hors grand livre** : Kwa-Ba Give, et plus tard transferts et locations, ainsi que l'argent payé avant l'existence du grand livre : colonne à part, sans D01, hors écart. Ils rejoindront l'écart quand leur produit écrira au grand livre.
- **Chaque nuit** (worker des paiements, après 3 h) : les trois dernières journées terminées sont réimportées, une fois par jour ; FedaPay injoignable est retenté une heure plus tard. Un mois clôturé ne se réimporte plus.
- **Régularisation** (`finance_regularisation`) : un admin avec « Opérations financières » choisit la nature, l'offre, le sens, le montant, écrit le motif (10 caractères au moins) et joint au moins une pièce (justificatifs du module `documents`, type `regularisation`). La ligne est datée du jour régularisé à midi, référence externe `regul:<opération>:<id>` (ou `regul:jour:<AAAA-MM-JJ>:<id>`), pièce `REGUL-…`. À partir de 250 000 F, elle attend une deuxième personne (Finance → Validations, opération `regularisation_rapprochement`) et n'est écrite qu'à l'approbation. Journal : `rapprochement_importe` (import par un admin), `regularisation_demandee`, `regularisation_ecrite`.
- **Préprod** : les opérations de démonstration (`demo-…`) n'existent pas dans le sandbox FedaPay ; leur relevé est reconstitué depuis la base (`paiements/demo.py`, frais affichés par moyen, jamais en production). `seed_finance_demo` rapproche chaque journée qu'il remplit ; `manage.py rapprocher_fedapay --debut AAAA-MM-JJ [--fin …]` rapproche une période déjà en base.

## Dépenses de Kwa-Ba (GL-15)

Décisions du 19 novembre 2026 : aujourd'hui, **chaque dépense est avancée par un associé** (le compte bancaire reste inactif) ; une dépense de **50 000 F ou plus** attend une deuxième personne (les remboursements et versements gardent 250 000 F) ; **annuaire léger** des fournisseurs ; **liste des associés** au back-office, reprise par GL-16.

- **Saisie** (`DepenseService`, permission « Opérations financières ») : date (pas à venir), nature active de la famille D, offre (`STRUCTURE` par défaut), montant TTC entier, libellé, fournisseur actif de l'annuaire, associé qui a avancé, n° de facture du fournisseur, et **au moins un justificatif** (PDF, JPEG, PNG ou WebP, module `documents`, type `depense`). Numéro continu `DEP-AAAA-NNNNN`.
- **Grand livre** : deux lignes sur le compte d'argent de passage **`ASSOCIES`** (« Avances des associés », 471, type `avance_associe`, toujours à zéro), datées du jour de la dépense à midi, pièce `DEP-…`, référence `depense:<id>` : la **charge** (nature D, sortie, tiers `fournisseur`) et l'**avance de l'associé** (F03, entrée, tiers `associe`). En partie double : débit du compte de charge (634, 627…) au nom du fournisseur, crédit du compte courant 462 au nom de l'associé ; 471 se solde. Le compte de passage n'a pas de relevé : il est exclu du rapprochement (I5, contrôle 4 de la clôture).
- **Double validation** : à partir de `depense_double_validation_seuil` (50 000 F, migration `0012`, avec son historique), la dépense attend dans Finance → Validations (opération `depense`) et n'est écrite qu'à l'approbation d'une autre personne. Refusée : elle reste visible « Refusée », sans ligne.
- **Annulation** : une dépense écrite s'annule avec un motif ; ses deux lignes reçoivent leur ligne inverse (datée du jour), elle reste visible « Annulée ». On saisit ensuite la bonne dépense.
- **Annuaire** (`finance_fournisseur`, `finance_associe`) : nom unique sans tenir compte des majuscules, NIF et contact facultatifs pour un fournisseur, email et compte du site facultatifs pour un associé ; désactiver plutôt que supprimer.
- **Journal** : `depense_saisie`, `depense_ecrite`, `depense_annulee`, `fournisseur_enregistre`, `associe_enregistre`.
- **Limites** : montants TTC (TVA non suivie, natures I inactives) ; le remboursement des avances aux associés et leurs comptes courants viennent avec GL-16 ; une dépense payée par la banque, FedaPay ou en espèces n'est pas encore ouverte. Quand le compte bancaire sera activé, la clôture exigera chaque fin de mois le solde du relevé bancaire, saisi avec le relevé en pièce jointe, jusqu'à l'import du relevé (GL-22).
- **Préprod** : `seed_finance_demo` saisit cinq dépenses par mois (fournisseurs et associés « démo », un PDF chacune) ; `--depenses-seulement` ajoute les dépenses sans nouvelles réservations (`scripts/maintenance.sh seed-finance --depenses-seulement`).

## Comptes courants d'associés (GL-16)

Décisions du 19 novembre 2026 : **pas de plafond** sur les dépenses d'un associé (au-delà de 50 000 F, c'est la double validation de GL-15) ; **pas encore de remboursement** des avances (il viendra avec le compte bancaire) ; le **capital** (500 000 F) est affiché avec la part de chaque associé.

**Capital au bilan d'ouverture** ([ADR-035](../ADR/ADR-035-souscription-du-capital.md), DEV-F6) : la **souscription** est écrite à la date des statuts (signés chez le notaire le 16 novembre 2026), une ligne `F01` par associé pour sa part, sur le compte d'argent technique `APPORTS` (« capital souscrit non versé », compte **4611**, type `apport`, exclu du rapprochement) : débit 4611 / crédit 101. Commande à lancer une fois par environnement, après la saisie des parts : `python manage.py subscribe_capital --date 2026-11-16` ; elle refuse si les parts ne font pas exactement `capital_social`, si la souscription est déjà écrite ou si le mois est clôturé, et elle est journalisée (`capital_souscrit`). La **libération** se fait le jour où l'argent arrive, par un virement interne (`V01`) du compte `APPORTS` vers le compte bancaire. Compte 4611 du doc 37 à confirmer par l'expert-comptable (4613 possible pour des apports en numéraire).

- **Solde** (`ComptesCourantsService`, lu au grand livre) : par associé, ses lignes de tiers `associe` en F02 (avance en compte courant), F03 (dépense avancée, GL-15) et F04 (remboursement) ; avancé = F02 + F03, remboursé = F04, solde = ce que Kwa-Ba lui doit (compte 462, sous-compte `ASSOCIE-<id>`). Le relevé donne chaque ligne, lignes inverses comprises, avec le solde après elle.
- **Jamais débiteur** (statuts, art. 19) : `GrandLivreService` refuse toute ligne, écrite ou inverse, qui rendrait un compte courant débiteur (un remboursement au-delà du solde, l'annulation d'une dépense déjà remboursée), avec un verrou consultatif par associé. Invariant **I15** et contrôle **8** de la clôture.
- **Capital** : `finance_associe.capital_souscrit` (migration `0013`) ; les parts des associés actifs ne dépassent jamais `capital_social`. Une modification (PATCH) ne change que les champs envoyés.

## Cut-off des frais de service (DEV-C2)

[ADR-034](../ADR/ADR-034-cut-off-des-frais-de-service-et-parametres-fiscaux.md). La commission d'un séjour entre déjà au résultat à l'arrivée (R02, R03) ; seuls les **frais de service du voyageur** (R01, 7061) entrent au paiement. À la fin de chaque mois terminé et ouvert, ceux d'un séjour ni commencé ni annulé passent en **produits constatés d'avance** : nature **R19**, sortie, sur le compte d'argent technique `PCA` (type `regularisation`, compte **477**, sans relevé, exclu du rapprochement), donc D 7061 / C 477, datée du dernier jour du mois. Le mois de l'arrivée ou de l'annulation, **R20** les rend au résultat (D 477 / C 7061), à la date de l'événement. Seul l'écart est écrit (fonction SQL `finance_ecarts_cut_off`), ce qui suit aussi les frais réduits et les annulations.

- Écrit chaque heure par le worker des paiements (`regulariser_cut_off_si_du`), et avant la clôture du mois.
- Contrôle de clôture 11 : « aucun frais de service d'une arrivée postérieure au mois dans le résultat (477) ».
- Les invariants de l'encaissement (I1 à I3, origine `paiement`) ne sont pas touchés ; I7 reste juste.
- Paramètres fiscaux (règle 4 du doc 37) : `tva_seuil` actif (alerte du tableau de bord), `impot_minimum` inactif jusqu'à la confirmation de l'OTR (l'impôt estimé ne retient que l'IS).

## Fonds de garantie (GL-17)

Décisions des 18 et 19 novembre 2026 : dotation de **10 % du revenu net du mois** (famille R : frais de service et commissions, moins les remises) ; le fonds est distinct de la caution du voyageur.

- **Traitement comptable** ([ADR-031](../ADR/ADR-031-fonds-de-garantie-en-reserve.md), DEV-C1, à confirmer par l'expert-comptable) : une **réserve**, hors résultat. La dotation G01 est une affectation, **1301 / 118** (compte d'argent `GARANTIE`, type `reserve`) : elle ne change pas le résultat du mois. Quand le fonds couvre un sinistre, la réserve est reprise (G02, **118 / 1301**), et seul le sinistre payé (D04, **658**) est une charge. Les lignes G vont au journal OD. Le traitement du 19 novembre (provision 6911 / 192 / 7911) est remplacé ; chaque changement de compte est dans `finance_correspondance_histo` (migrations `0013` puis `0019`). Le fonds n'a pas de relevé : il est exclu du rapprochement (I5, contrôle 4).
- **Dotation** (`FondsGarantieService.doter`) : pour un mois terminé et ouvert, la vue `finance_dotation_garantie` donne l'assiette, le taux (`fonds_garantie_taux`), la dotation due (arrondie au franc) et celle déjà écrite ; le service écrit ce qui manque, une ligne G01 datée du dernier jour du mois, pièce `DOT-AAAA-MM`, référence `garantie:dotation:AAAA-MM:<n>`. Jamais moins : un mois dont le revenu baisse après coup garde sa dotation (prudence). Elle est écrite **chaque nuit** (worker, une fois par heure au plus), **à la clôture** (avant ses contrôles) ou par le bouton. Contrôle **7** de la clôture : dotation du mois écrite.
- **Sinistre** : il est d'abord saisi comme une dépense **D04** (« Litige pris en charge par la Garantie Kwa-Ba ») avec sa facture (GL-15) ; le fonds le couvre ensuite (`imputer`), avec la **référence de la décision** et le récit, au plus la dépense et le solde du fonds : ligne G02 sur `GARANTIE`, pièce = n° de la dépense (`finance_sinistre`). Une dépense couverte ne s'annule pas avant l'annulation de sa couverture (ligne inverse). Invariant **I16** et contrôle **9** : le fonds n'est jamais négatif.
- **Trésorerie libre** : l'argent des comptes réels moins ce qui est dû aux partenaires et aux voyageurs, les cautions détenues et le fonds.
- **Cible** : `fonds_garantie_cible` (0 tant que les associés ne l'ont pas fixée : pas d'alerte). En dessous, après une dotation ou un sinistre, l'équipe finance reçoit un email, sans montant.
- **Journal** : `fonds_garantie_dotation`, `fonds_garantie_sinistre_impute`, `fonds_garantie_sinistre_annule`.
- **Préprod** : `seed_finance_demo` donne leurs parts aux associés démo (200 000, 150 000, 150 000 F, seulement si personne n'a de part), écrit les dotations et un sinistre D04 du mois dernier couvert par le fonds.

## Lot UI-A : avoirs, remboursements, rôle Finance, double validation

### Avoirs (GL-8, module `documents`)

Une facture ne se supprime ni ne se modifie (LPF Togo art. 64) : une vente rendue est neutralisée par une **facture d'avoir**, série `AVO-AAAA-NNNNN`, numérotation continue sans trou (`SequencePieceModel`, verrou à chaque émission), PDF figé, qui cite la facture d'origine (numéro, date, montant). `AvoirModel` : montants positifs, à déduire ; jamais plus que ce que la facture contient encore.

- **Quand** : à chaque remboursement décidé (`paiements.services.rembourser`), et à l'émission d'une facture d'un objet déjà remboursé. Le produit payé dit ce qui a été rendu (`Produit.rembourse`, `paiements.api.total_rembourse`, sur le **premier paiement réussi** de l'objet seulement : un paiement fait deux fois et rendu n'est pas une vente annulée).
- **Montant** (décision du 18/11) : le montant remboursé. Annulation totale : un avoir du total qui reprend les lignes de la facture. Remboursement partiel (nuits retenues) : un avoir du montant rendu, une ligne ; la facture reste valable pour la part conservée. Un séjour annulé jamais facturé n'a ni facture ni avoir.
- **Idempotent** : `documents.api.regulariser_avoirs` émet la différence entre ce qui a été rendu et les avoirs déjà émis ; un second appel n'émet rien. Un échec (société non renseignée) n'empêche jamais le remboursement : la facture apparaît dans **Documents → Avoirs**, « factures remboursées sans avoir », avec un bouton « Émettre l'avoir ».
- **Factures antérieures** (F-2026-00006) : `manage.py regulariser_avoirs` (`--simulation` pour voir sans émettre), relançable sans doublon.

### Remboursements (GL-9, module `paiements`)

**Finance → Remboursements** : chercher un séjour par sa référence (`RES-KB2026-3A43`, ou son identifiant si deux réservations partagent la référence) ; l'aperçu donne, depuis les **montants figés** de la réservation (`tarifs.montants_de`, jamais les taux courants), ce que rendrait l'annulation selon les conditions du voyageur et en intégral. Rembourser annule la réservation par le parcours habituel : lignes du grand livre (T01, T02, R01, R08, T05), versement de l'hôte réduit ou annulé, avoir si la vente était facturée. La liste suit chaque remboursement ; actions : saisir le compte Mobile Money (voyageur joint par téléphone), relancer un envoi en échec, enregistrer un remboursement fait depuis le tableau de bord FedaPay (carte : T05 sort du compte d'argent). Journal : `remboursement_traite`.

### Rôle Finance et permission (GL-10)

- **Lecture seule** (`admin_lecture_seule`, réglé par un super admin dans *Utilisateurs → Droits*) : l'admin voit ses sections (toutes par défaut) et l'API refuse toute écriture (`EstAdministrateur`, 403 « Compte en lecture seule »). Un super admin n'est jamais en lecture seule.
- **Permission « Opérations financières »** (`finance_operations`) : nécessaire pour rembourser, agir sur un remboursement et décider une validation. Jamais incluse d'office.

### Double validation (GL-10, module `finance`)

À partir du **seuil** (`double_validation_seuil` = 250 000 F, décision du 18/11 ; 0 rend la règle inerte), une opération d'argent attend une deuxième personne (`finance_validation`) :

- **Remboursement d'un séjour** décidé au back-office (Finance → Remboursements, et aussi l'annulation depuis Réservations, qui répond alors 202) : la personne qui demande ne peut pas valider ; une autre personne valide, et l'annulation s'exécute dans la même transaction.
- **Versement automatique à un hôte** : le worker ne l'envoie pas, il crée une demande « Système » ; **deux** personnes différentes doivent l'accepter, puis il part au passage suivant.
- La base refuse elle-même qu'une même personne demande et valide, ou valide deux fois (contraintes de `finance_validation`) ; une seule demande en attente par objet. Une exécution en échec est annulée et la demande garde la raison (`echouee`). Refus : motif obligatoire.
- Les modules déclarent leurs opérations au démarrage (`finance.api.declarer_operation`) : `remboursement_sejour` (réservations), `versement_hote` (paiements). Journal : `validation_demandee`, `validation_premiere`, `validation_accordee`, `validation_refusee`, `validation_echouee`.

## Registre et documents des cautions (GL-13, GL-14)

Décisions du 18 et du 19 novembre 2026 : registre générique et documents REC/RET, branchés dès maintenant sur la seule caution réelle, celle de la **location de voiture sans chauffeur** payée en ligne ; la caution des séjours (projet séparé, empreinte FedaPay) s'y branchera quand elle existera. Une retenue exige un motif, l'article des CGV (14.3 par défaut) et **au moins une pièce justificative** ; le reçu ou l'avis est joint à l'email du voyageur, l'avis de retenue aussi au propriétaire du véhicule.

- **Registre** (`finance_caution`, module `finance`) : une caution par objet, reçue (montant, date, date limite de restitution), puis soldée une fois : `restituee` (tout rendu) ou `retenue` (une part gardée sur décision motivée). Pendant un litige de dommage sur un séjour (ADR-048), l'état est `litige` : `montant_conteste` reste gardé, et `montant_rendu` cumule ce qui est rendu avant le solde (la part non contestée à la fin du délai de signalement, puis ce que la décision écarte). La base refuse un solde dont les montants ne font pas la caution, un solde sans document, une retenue au-delà de la caution ou sans motif ni article, et une restitution qui entame le montant réclamé ou retenu. API : `enregistrer_caution`, `declarer_litige_caution`, `rendre_caution_en_partie`, `decider_retenue`, `solder_caution`, `caution`, `registre_cautions`. Écran **Finance → Cautions** : total détenu (argent des voyageurs, jamais un revenu ; caution moins ce qui est déjà rendu), cautions en litige, cautions en retard, retenues avec leur motif, PDF du document et pièces justificatives.
- **Documents** (module `documents`) : **reçu de restitution** `REC-AAAA-NNNNN` (tout rendu) ou **avis de retenue** `RET-AAAA-NNNNN` (motif, fondement CGV, auteur et date de la décision, pièces citées, montant retenu et rendu) ; numérotation continue par série, PDF figé, un document par caution, contrôles en base. Pièces justificatives (`JustificatifCautionModel`) : PDF, JPEG, PNG ou WebP reconnus à leur signature, 10 Mo au plus, 10 par caution, stockage privé, jamais supprimées. Le voyageur télécharge son document par `/api/v1/documents/location/<id>/caution/`. Routes du back-office `documents/cautions/…` et `documents/justificatifs/…` rattachées à la section « finances ».
- **Séjour** (`reservations/deposit.py`, [ADR-036](../ADR/ADR-036-caution-des-sejours.md)) : la caution séquestrée entre au registre au paiement, avec la date limite départ + `caution_restitution_heures` ; toute annulation d'un séjour payé la rend en entier avec un REC. Une fois le délai passé après le départ (heure de départ de la réservation, midi à défaut), le worker la solde : remboursement de la caution moins la retenue, REC (ou RET s'il y a une retenue), registre soldé, email au voyageur avec le document, et à l'hôte avec l'avis de retenue. **Retenue** ([ADR-038](../ADR/ADR-038-retenue-sur-caution-versee-a-l-hote.md), `reservations/deposit_withholding.py`) : saisie au back-office sur le détail de la réservation (`POST /api/v1/admin/reservations/<id>/caution/`, multipart : `montant`, `motif`, `cgv_article`, `justificatifs`) une fois le séjour commencé et avant la restitution ; motif, article des CGV et au moins une pièce exigés ; 0 l'annule ; une annulation du séjour la fait tomber. La retenue est versée à l'hôte par un versement dédié (`DamagePayoutModel`, `paiements/damage_payouts.py`), envoyé par le worker sur son profil de versement et visible sur la page des versements (type `indemnite`).
- **Location** (`locations/cautions.py`) : la caution entre au registre au paiement ; la retenue (back-office, multipart avec `justificatifs`) est inscrite au registre ; à la fin du délai de signalement, le remboursement part, puis le REC ou le RET est émis et le registre soldé, dans la même transaction. Une annulation rend toute la caution avec un REC. Si le document ne peut être émis (retenue ancienne sans pièce), **le remboursement part quand même** : la caution reste « détenue » et apparaît en retard au registre, à régulariser.
- **Grand livre** : les locations n'y écrivent pas encore (FIN-03 couvre les séjours) ; les lignes C01, C02, C03 viendront avec elles. Le plafond « 2 nuits, 150 000 F » et le délai « départ + 72 h » du doc 25 concernent la caution des séjours : à appliquer quand elle existera (paramètres `caution_evasion_*`).

## Écrire une ligne

```python
from apps.finance import api as finance

finance.enregistrer([
    finance.Ligne(nature='T01', offre='COURTE_DUREE', montant=250_000, sens=finance.ENTREE, compte_argent='FEDAPAY',
                  tiers_type='hote', tiers_id=hote_id, moyen_paiement='MOOV', reservation_id=reservation.id,
                  piece_reference=reservation.reference, externe_reference=transaction_id),
    ...
], origine='paiement', par_id=None)
```

- **Dans la transaction de l'action** (FIN-01.6) : un paiement ne réussit pas sans ses lignes, ni une ligne n'existe sans son paiement. `enregistrer` écrit tout ou rien ; c'est un appel direct, pas un événement (ADR-024).
- **Montants** : entiers en F CFA, strictement positifs ; le sens porte le signe. Un montant à décimales est refusé : l'arrondi revient à celui qui calcule la ventilation (au franc, jamais au détriment du partenaire).
- **Refus** : code inconnu ou inactif, sens contraire à la nature, offre non ouverte, fonds de tiers sans tiers, caution sans réservation ni location, C03 sans motif, mois verrouillé. `MouvementRefuse` est levée et l'équipe finance est alertée.
- **Idempotence** (FIN-01.7) : une même notification reçue trois fois donne une ligne. La clé est la référence externe, la nature, le sens, le compte d'argent, le tiers et la ligne de panier. Un événement rejoué avec un autre montant n'est pas écrit et déclenche une alerte.
- **Correction** : `finance.contre_passer(id, motif=..., par_id=...)` écrit la ligne inverse, datée du jour, avec son motif. Les deux lignes restent visibles. Une ligne se corrige une fois au plus, une correction ne se corrige pas, et chaque correction va au journal d'audit (`ecriture_corrigee`).

## Modules qui écrivent : déclaration et contrôle

Chaque module qui écrit dans le grand livre se déclare au démarrage (`AppConfig.ready`) :

```python
finance.declarer_ecritures('sejours', offres={'COURTE_DUREE', 'HOTEL'}, natures={'T01', 'T02', 'R01', 'R02', 'R03'},
                           ouvert=lambda: True)
```

Si un module ouvert écrirait dans une offre ou une nature inactive, ses paiements seraient refusés. Le contrôle Django `finance.E001` le détecte à chaque `migrate`, donc à chaque déploiement, qui s'arrête ; `manage.py check --database default` le joue aussi. L'écran de contrôle le montre en invariant I14 (par exemple si une offre est désactivée au back-office pendant que son module reste ouvert).

## Alertes et journal

| Événement | Où il part |
| --- | --- |
| Mouvement refusé (FIN-01.4) | email « [Kwa-Ba Finance] Mouvement refusé par le grand livre » via `notifications.api.send_mail`, gabarit `templates/emails/finance/mouvement_refuse.txt` |
| Événement du prestataire rejoué avec un autre montant | email « Événement de paiement rejoué avec un autre montant », gabarit `evenement_rejoue.txt` |
| Correction d'une ligne | journal d'activité (module `activity`, `activity.api.record`), action `ecriture_corrigee` (auteur, ligne, ligne inverse, motif), lisible dans Back-office → Journal d'activité |

Destinataires des emails : les administrateurs actifs qui voient la section « Finances » du back-office (`users.api.emails_admins_section('finances')` : super admins, admins sans limite, admins à qui la section est ouverte, accès non expiré). Pour que le référent financier les reçoive, lui ouvrir un compte admin limité à cette section. Les emails partent tout de suite (un refus annule en général la transaction de l'appelant) ; un échec d'envoi ne fait jamais échouer l'action. Ils ne contiennent ni montant ni nom de personne (NFF-05) ; la trace technique reste dans le journal des conteneurs (logger `apps.finance`).

## Garde-fous en base

La base refuse elle-même, quel que soit l'auteur (application, script, psql) :

- toute modification ou suppression d'une ligne du grand livre et des historiques (paramètres, correspondance comptable) ;
- une ligne dont un code est inconnu ou inactif, ou dont le sens contredit la nature ;
- une ligne inverse qui ne reprend pas la nature, l'offre, le tiers, le compte et le montant de la ligne corrigée ;
- une ligne dans un mois verrouillé, ou dont le mois comptable n'est pas celui de l'événement (sauf écriture d'inventaire, `origine='calcul'`).

`deploy/postgres/roles.sql` retire aussi `UPDATE` et `DELETE` sur ces tables au rôle `kwaba_app`. À rejouer sur chaque serveur après la première migration du module. Sans `UPDATE`, ce rôle ne peut pas non plus verrouiller une ligne (`SELECT … FOR UPDATE`) : le code ne le fait jamais.

Les vues dépendent des colonnes du grand livre, mais une migration n'a pas à s'en occuper : elles sont supprimées avant chaque `migrate` et recréées après. Pour changer une vue, on modifie `sql_restitutions.py` ; le déploiement suivant la recrée.

Concurrence : pas de verrou de ligne sur le grand livre (le rôle de l'application n'a pas `UPDATE`), mais des verrous consultatifs (`pg_advisory_xact_lock`) : deux corrections simultanées de la même ligne s'attendent, et la seconde est refusée proprement.

## Restitutions (`api.py`)

| Fonction | Contenu |
| --- | --- |
| `controle_invariants()` | I5, I8 à I13, I15 (comptes courants jamais débiteurs), I16 (fonds de garantie jamais négatif) et I14 (modules ouverts : offres et natures actives) : nombre d'anomalies, 0 = respecté |
| `peut_on_cloturer(mois)` | les dix contrôles, OK ou REFUSE, et quoi faire |
| `comptes_courants()`, `releve_compte_courant(id)` | ce que Kwa-Ba doit à chaque associé, et son relevé (GL-16) |
| `fonds_garantie()`, `dotations_fonds_garantie()`, `doter_fonds_garantie(mois)`, `imputer_sinistre(…)`, `annuler_sinistre(…)` | le fonds de garantie (GL-17) |
| `synthese(debut, fin, axe1, axe2, familles, offres)`, `rapport(code, debut, fin)` | le moteur unique des rapports ; un rapport de plus est une ligne de `finance_rapport` |
| `du_aux_partenaires()`, `cautions_detenues()`, `soldes_comptes_argent()` | les trois soldes, jamais mélangés |
| `balance_generale(mois)`, `ecritures(mois)`, `controle_equilibre()`, `marge_par_offre(mois)` | partie double et pilotage |
| `parametre(cle)` | valeur en vigueur ; une clé inactive est une erreur |

## Exigences du cahier des charges : où on en est

| Exigence | État |
| --- | --- |
| FIN-01.1 une ligne par événement d'argent | Séjours : fait (paiement, arrivée, annulation, remboursement, versement). Transferts et locations : PR suivante |
| FIN-01.2 axes de chaque ligne | Fait |
| FIN-01.3 ajout seul, correction par ligne inverse | Fait, refus par la base (trigger et droits) |
| FIN-01.4 code inconnu refusé, alerte | Fait, alerte aux admins « Finances » |
| FIN-01.5 entiers, arrondi chez Kwa-Ba | Entiers : fait. L'arrondi appartient au calcul de la ventilation (FIN-03) : il arrondit au franc le plus proche, comme les neuf cas de référence |
| FIN-01.6 même transaction | Fait pour les séjours (testé : une action qui échoue ne laisse aucune ligne) |
| FIN-01.7 idempotence | Fait |
| FIN-02 rapprochement à trois voies | Fait (GL-12) : import FedaPay chaque nuit et à la demande, frais réels D01, trois colonnes par opération et par journée, régularisation motivée avec pièce et double validation. Transactions inconnues : recherche FedaPay au mieux. Banque : fait (GL-22), relevé CSV importé et rapproché des virements, compte ouvert à la demande |
| FIN-03 ventilation figée au paiement | Séjours : fait (FIN-03.1, 03.3, 03.5 ; les montants figés à la réservation tiennent lieu d'instantané, FA-11). Écran du détail d'une réservation (FIN-03.4) : à venir |
| FIN-04 sommes dues aux partenaires | Fait (GL-11) : page des versements, échéances et retards, relance des échecs, alerte quotidienne ; récupération sur les versements suivants après une annulation (GL-23). Gel des versements par partenaire : à faire |
| FIN-05 registre des cautions | Fait pour la location : registre `finance_caution`, écran, alertes de retard, reçus REC et avis RET avec pièces (GL-13, GL-14). Séjours : projet séparé. Lignes C du grand livre : avec FIN-03 des locations |
| FIN-06 fonds de garantie | Fait (GL-17) : dotation mensuelle de 10 % du revenu net (nuit, clôture, bouton), sinistres couverts avec la référence de la décision, solde séparé de la trésorerie libre, alerte sous la cible (cible à fixer). Réserve hors résultat (1301 / 118, sinistre en 658 : ADR-031), comptes à confirmer par l'expert-comptable |
| FIN-07 livres comptables et export | Fait : vues (partie double, livre-journal, grand-livre, balance, contrôles), écrans Livre-journal, Grand-livre par compte, Balance générale et fichier CSV des écritures (GL-3 à GL-6). À-nouveaux et livre d'inventaire : GL-23 |
| FIN-08 clôture mensuelle | Fait : refus en base dans un mois verrouillé, `peut_on_cloturer`, écran et verrouillage par un super admin, dans l'ordre, définitif en base (GL-7). Contrôle « toute facture annulée a son avoir » : avec GL-8 |
| FIN-09 facturation | Factures (module `documents`) ; avoirs AVO sur toute vente remboursée (GL-8). Documents de caution REC/RET : GL-14 |
| FIN-10 tarifs complets et historique | Fait (GL-20) : page Tarifs avec l'historique de ses taux et les autres taux du référentiel ; historique daté de chaque changement ; une réservation garde ses montants et son délai de versement |
| FIN-11 dépenses, comptes courants | Dépenses (FIN-11.1) : faites (GL-15), avancées par un associé, justificatif obligatoire, double validation à partir de 50 000 F. Comptes courants d'associés (FIN-11.2 à 11.4) : faits (GL-16), soldes et relevés, jamais débiteurs, capital et parts. Remboursement des avances : avec le compte bancaire |
| FIN-12 tableau de bord | Fait (GL-18) : tableau de bord du mois et de l'année, quatre poches, annulations, fiscalité, seuils (scénario prudent à fixer), export CSV |
| FIN-13 rôle Finance, double validation, journal | Fait : rôle Finance en lecture seule, permission « Opérations financières », double validation à partir de 250 000 F des remboursements et des versements, garantie en base, journal (GL-10) |
| FIN-16 référentiel unique des paramètres | Fait (GL-20) : page Paramètres, modification motivée et historisée, valeur à une date, valeurs métier des locations et du versement lues au référentiel. Les taux de la page Tarifs restent lus dans `ReglagesTarifsModel` (cache du site) et sont recopiés au référentiel à chaque changement |
| FIN-17 restitution générique | Fait : vue pivot, axes, rapports, moteur, écran Rapports avec rapport libre, création d'un rapport sans développement et export CSV (GL-19) |
| Invariants | Les 13 invariants du brief et I14 à I17 sont nommés sur l'écran de contrôle, dans l'ordre, chacun OK ou en anomalie (recette du 19 novembre 2026, DEV-L5). I1 : un encaissement n'est ventilé qu'en R, T et C. I2 : sur chaque encaissement rapproché, le montant que Kwa-Ba a enregistré égale sa ventilation. I3 : pour chaque journée rapprochée, encaissé − remboursé − versé selon Kwa-Ba égale les lignes du grand livre (hors frais D01 et régularisations). I4 : toute ligne T porte son type de tiers, donc la somme par tiers égale le total dû. I6 : débit = crédit sur chaque journal (VT, AC, OD, TR) de chaque mois. I7 : R − D − G égale le résultat de la balance (classes 6 à 8). La Synthèse montre aussi l'identité des soldes de chaque compte d'argent : revenu + dû partenaires + dû voyageurs + cautions − frais D01 + autres lignes = solde (vue `finance_identite_soldes`) |

## Écarts par rapport au fichier SQL du 10 novembre

Le fichier a été traduit dans notre architecture : modèles Django et migrations, aucune clé étrangère vers un autre module (comptes, réservations, transferts, locations gardés en UUID), types `ENUM` remplacés par des colonnes texte contrôlées. Les noms des tables et des colonnes sont ceux du fichier. Les écarts de fond :

| Écart | Pourquoi |
| --- | --- |
| T01 à T04 et T06 à T08 acceptent les deux sens (le fichier : entrée seulement) | Le fichier écrit lui-même une sortie T01 à l'arrivée du voyageur (la commission passe au produit, cas FA-01) et au remboursement : sa propre règle les refusait. T05 et T09 restent en sortie seulement |
| Une ligne inverse échappe au sens attendu de sa nature, mais doit être le miroir exact de la ligne corrigée | Sinon aucune ligne R ou T ne pouvait être corrigée (cas FB-03) |
| Monnaie électronique (I13, contrôle 3 de clôture) et cautions (I8, contrôle 5) jugées sur le solde **cumulé** | Mois par mois, un mois qui verse ce que le précédent a encaissé paraissait créditeur, et sa clôture était refusée à tort |
| Un jour sans rapprochement compte comme une anomalie (I5, contrôle 4) | Le fichier ne comptait que les rapprochements écrits : un mois jamais rapproché se clôturait (contraire à FIN-02.7) |
| Codes inconnus refusés tout de suite par le trigger ; offre, compte d'argent, type de tiers et moyen inactifs refusés comme une nature inactive | Django déclare ses clés étrangères `DEFERRABLE` (refus reporté au commit) ; FIN-01.4 |
| Clé d'idempotence élargie au sens, au compte d'argent, au tiers et à la ligne de panier ; corrections hors clé | Un panier Évasion doit la même nature à plusieurs prestataires, un virement V01 écrit deux lignes de même référence |
| Cautions suivies par réservation **ou** par location | La caution de location de voiture est aujourd'hui la seule réelle |
| `finance_synthese` cite la colonne de l'axe (`%I`) | Une ligne de `finance_axe` est une donnée, pas du code |
| Invariant I10 ajouté à la vue de contrôle (ligne écrite dans un mois après son verrouillage) | Il figurait au cahier, pas dans la vue |
| Fonds de tiers sans tiers, caution sans réservation ni location : refusés | Compte auxiliaire (FIN-07.1), registre des cautions (FIN-05.1) |
| Rapprochement du jour : identifiant propre et unicité (jour, compte) au lieu d'une clé primaire double | Habitude de nos modèles |
| `tiers_id` en texte (le fichier : entier) | Un compte est un UUID, un chauffeur ou un loueur un numéro ; le grand livre ne connaît pas leurs modules |
| T05 accepte les deux sens (le fichier : sortie seulement) | L'argent d'un remboursement décidé est dû au voyageur (entrée) jusqu'à son envoi (sortie) |
| Un fonds de tiers peut attendre la personne (type obligatoire, identifiant facultatif) | Le chauffeur d'un transfert n'est attribué qu'après le paiement |
| Compte d'argent et moyen PayPal présents, inactifs | PayPal est éteint au lancement : un paiement PayPal est refusé plutôt que laissé hors du grand livre |
| Journal des actions : le journal d'activité (module `activity`) au lieu de `finance_journal_action` | Un seul journal d'audit, en ajout seul pour l'application |
| Pas de `finance_sequence_piece` ni de `finance_prochain_numero` | Les numéros de facture viennent déjà de `documents` (`SequenceFactureModel`, verrou à chaque émission) ; le lot F3 l'étend aux autres séries |
| Pas encore de `finance_caution`, `finance_validation`, ni de `tarifs_snapshot` | Créés avec leur brique : cautions de location (F2), double validation (FIN-13), ventilation au paiement (FIN-03) |

## Décisions prises le 2026-11-13

- Le module est déployé d'abord en préprod seulement ; la production suivra sur décision. Le même manifest ira ensuite en prod (tables vides : prélancement, FedaPay en sandbox).
- Les frais FedaPay sont une charge de Kwa-Ba, jamais payés par le voyageur ni imputés aux partenaires (note 01, section 3.1) : une ligne D01 par transaction, au montant du relevé FedaPay (lot F2). Le réglage « frais à la charge du marchand » est à basculer dans le tableau de bord FedaPay.
- PayPal est retiré au lancement : pas de moyen de paiement PayPal dans le grand livre.
- La caution des séjours est un projet séparé, après la réponse de FedaPay sur l'empreinte de carte.
- Ordre : FIN-03 (ventilation au paiement), puis le lot F2, puis FIN-13.
- Location sans chauffeur : le module est fermé en production (inventaire `kwa-ba-infra`) plutôt que d'ouvrir l'offre `VOITURE_SANS`.
- Gel des versements (FIN-04.6) : un interrupteur « versements gelés » par partenaire, au back-office, journalisé.
- Petites sommes de moins de 5 000 F : pas de versement groupé le vendredi pour l'instant ; l'échéance de chaque somme est affichée.

## Décisions prises le 2026-11-18

- La rubrique Finance regroupe toutes les pages d'argent et de comptabilité du back-office (GL-1) ; livraison par lots : d'abord les livres (GL-2 à GL-7, GL-19), puis les écritures du lot UI-A (GL-8 avoirs, GL-9 remboursements, GL-10 rôle Finance, GL-14 documents de caution), puis le reste.
- Clôture d'un mois : super administrateurs seulement.
- Lot UI-A : seuil de double validation **250 000 F** (H-4), appliqué aux remboursements décidés au back-office **et** aux versements automatiques aux hôtes ; avoir d'un remboursement partiel = le montant remboursé ; rôle Finance = admin en lecture seule, opérations d'argent sous la permission « Opérations financières ».
- Fonds de garantie : **10 %** (au lieu de 5 ou 7 % ; d'abord fixé à 8 %, corrigé le même jour). Il est distinct de la caution du voyageur, qui garde sa règle propre. Capital social : **500 000 F CFA**. Ils entreront dans `finance_parametre`, avec leur historique, avec GL-17 et GL-16 (fait le 19 novembre : voir GL-16 et GL-17).
- Données de test de la préprod : par les vrais parcours (réservation, paiement, arrivée, annulation, versement), comptes `*.demo@`. Le grand livre étant en ajout seul, elles y restent : la base de production est distincte.

## Décisions prises le 2026-11-19

- Frais FedaPay (H-2) : à la charge de Kwa-Ba, une ligne D01 par transaction au montant réel du relevé.
- Dépenses (GL-15) : avancées par un associé (compte courant 462) ; double validation à partir de 50 000 F ; annuaire léger des fournisseurs ; liste des associés au back-office. Compte bancaire, quand il sera activé : solde du relevé de fin de mois exigé à la clôture jusqu'à GL-22.
- Comptes courants (GL-16) : pas de plafond sur les dépenses (au-delà de 50 000 F, la double validation suffit) ; remboursements des avances pas encore ouverts (avec le compte bancaire) ; capital affiché avec la part de chaque associé, écriture d'ouverture avec l'expert-comptable.
- Fonds de garantie (GL-17) : 10 % du revenu net de chaque mois terminé.
- Rapprochement : API FedaPay chaque nuit et bouton « Réimporter » ; argent hors grand livre montré à part, hors écart ; écart inexpliqué fermé par une écriture de régularisation (motif, pièce, double validation à partir de 250 000 F, journal).

## Virements internes et relevé bancaire (GL-22)

Décision du 19 novembre 2026 : tout est prêt, mais le **compte bancaire reste fermé** tant qu'il n'existe pas.

- **Ouvrir le compte bancaire** (Finance → Virements et banque, super administrateur, journal `tresorerie_compte_active`) : `finance_compte_argent.actif_depuis` reçoit la date du jour. Le compte est rapproché à partir de ce jour seulement (I5 et contrôle 4 ne demandent pas ses journées d'avant). Un compte sans ligne se désactive.
- **Virement** (`VirementService`, permission « Opérations financières ») : date (pas à venir, pas avant l'ouverture du compte), compte de départ et d'arrivée, ouverts et réels (ni le compte de passage des associés, ni le fonds de garantie), montant, motif, **preuve obligatoire** (justificatif `virement`), et la **référence du prestataire** obligatoire quand FedaPay est d'un côté (le rapprochement de FedaPay retrouve le retrait par elle). Numéro `VIR-AAAA-NNNNN`. Deux lignes **V01** de même montant, sortie du compte de départ et entrée du compte d'arrivée, de même référence : le compte **585** se solde (invariant **I17**, contrôle **10** de la clôture). À partir du seuil des versements (250 000 F), une deuxième personne valide (opération `virement_interne`). Annulation par lignes inverses. Journal `virement_demande`, `virement_ecrit`, `virement_annule`.
- **Relevé bancaire** (`TresorerieService.importer_releve`) : un fichier CSV exporté par la banque, jusqu'à hier ; la personne indique le nom des colonnes (date, libellé, débit et crédit, ou un montant signé, référence si la banque en donne). Montants en francs entiers (« 1 234 567 », « 1.234.567 », « 1234567,00 »). Chaque ligne est rapprochée du virement qu'elle est : par sa référence, sinon par son montant dans le même sens à 3 jours près, le plus proche d'abord, chaque virement une fois. Puis chaque journée couverte est rapprochée comme celles de FedaPay (`RapprochementService.importer`). Une ligne que rien n'explique (frais bancaires, versement inconnu) laisse sa journée en écart : elle se **régularise** dans Finance → Rapprochement, compte bancaire (frais bancaires en D13). Le fichier est gardé tel quel (`finance_releve_import`) ; journal `tresorerie_releve_importe`. Refusé : un relevé qui touche aujourd'hui, une date d'avant l'ouverture du compte, un mois clôturé.
- **Rapprochement** : l'écran choisit le compte (`?compte=`), FedaPay ou le compte bancaire ouvert. FedaPay se lit par son API, la banque par son relevé importé.
- **Limites** : pas encore de dépense payée par la banque (GL-15 : avancées par un associé) ; le compte bancaire des fonds de tiers (`BANQUE_FT`) s'ouvre de la même façon quand il existera.

## Tableau de bord, relevés, rapport aux associés, inventaire (GL-18, GL-21, GL-23)

Tout est lu au grand livre (`application/pilotage.py`, `persistence/pilotage.py`).

- **Tableau de bord** (GL-18, FIN-12) : pour un mois et l'année jusqu'à ce mois, le chiffre d'affaires (comptes 70), les produits, les charges et le résultat (classes 6, 7, 8), les réservations payées et le volume encaissé, le revenu et la marge par offre, le **taux de frais réel** (D01 sur le chiffre d'affaires), la **trésorerie en quatre poches** (dû aux partenaires et aux voyageurs, cautions, fonds de garantie, trésorerie libre), le dû aux associés, l'**indicateur d'annulation** (FF-05 : nombre et taux, remboursé, frais FedaPay perdus, somme conservée R08), l'**impôt estimé** de l'année (le plus haut de l'IS à `impot_societes` du résultat et du minimum à `impot_minimum` du chiffre d'affaires), la part du **seuil de TVA**, la qualité (anomalies des invariants, journées en écart) et les **seuils des associés** : point mort (`charges_fixes_mois`), scénario prudent (`scenario_prudent_revenu_mois`, à fixer), publicité par réservation (`publicite_par_reservation`), solde chez le prestataire (`prestataire_solde_alerte`), TVA (`tva_seuil`). Export CSV du mois : les mêmes chiffres.
- **Relevés des partenaires** (GL-21) : la liste des partenaires qui ont de l'argent au grand livre ; pour l'un d'eux et un mois, le solde au début, le dû, le versé (T09), les commissions de Kwa-Ba sur ses réservations, le solde à la fin, chaque opération, et le récapitulatif de l'année ; en PDF. Consultation : rien n'est envoyé (décision du 19 novembre 2026).
- **Rapport aux associés** (GL-21, pacte art. 2.4) : le tableau de bord du mois et le **commentaire du référent** (`finance_rapport_associes`, journal `tresorerie_rapport_commente`), en PDF à remettre aux associés au plus tard le 10.
- **Inventaire** (GL-23, FIN-07) : l'**amortissement de la Solution** en linéaire (`solution_valeur`, `solution_duree_mois`, `solution_mise_en_service` en AAAAMM ; à 0, rien), **écrit chaque mois** ([ADR-037](../ADR/ADR-037-amortissement-mensuel-de-la-solution.md), DEV-C6) : une ligne **D20** (681) sur le compte `AMORTISSEMENTS` (2813), datée du dernier jour du mois, pièce `AMO-AAAA-MM`, par le worker des paiements (chaque heure) et avant la clôture du mois (`application/amortisation.py`). Le dû est cumulé (valeur × mois écoulés / durée, arrondi au franc) : les arrondis ne dérivent pas et le dernier mois prend le reste. L'écriture de fin d'exercice (pièce `INV-AAAA`, par un super administrateur) ne sert plus qu'à rattraper un manque. Le **livre d'inventaire** de l'exercice : écritures d'inventaire (amortissement, dotations au fonds), compte de résultat, bilan (actif, passif), et les **à-nouveaux** au 1er janvier suivant (comptes de bilan, et le résultat en 131 ou 139 en attente d'affectation) ; export CSV. Le grand livre par compte reporte déjà les soldes des comptes de bilan d'une année sur l'autre.

## Paramètres pilotés et historique (GL-20)

- **Référentiel** (`ParametreService`, Finance → Paramètres) : chaque paramètre, sa valeur, son unité, sa catégorie, son offre et sa source ; « À fixer » quand il vaut 0 (règle inerte). Une valeur change **tout de suite**, par un **super administrateur**, avec un **motif** (10 caractères au moins) : `finance_parametre_histo` garde la valeur avant, la valeur après, la date d'effet, l'auteur et le motif ; journal `parametre_modifie`. Bornes : un pourcentage entre 0 et 100, un montant en francs entiers, jamais négatif.
- **Taux de la page Tarifs** (frais de service, commissions des hôtes, des hôtels, des fondateurs et des transferts, frais de ménage) : le site les lit à chaque réservation dans `ReglagesTarifsModel` ; la page Tarifs les écrit aussi au référentiel, avec leur historique (`enregistrer_taux_de_la_page_tarifs`), et la page Paramètres les montre sans les modifier. La page Tarifs affiche l'historique de ses taux et, en lecture, les autres taux et délais du référentiel.
- **Valeur à une date** (`parametre_au(cle, moment)`) : la valeur en vigueur à ce moment, d'après l'historique. Une réservation garde ainsi le délai de versement de sa date.
- **Plus de valeur métier dans le code** : le délai de versement à l'hôte (`versement_hote_heures`), les commissions des propriétaires fondateurs et fidèles (`commission_vehicule_fondateur`, `commission_vehicule_fidele`), le prix et la part du chauffeur par jour (`chauffeur_prix_jour`, `chauffeur_part_jour`, `chauffeur_part_excellence`) et ses primes (`chauffeur_prime_pays`, `chauffeur_prime_hors_pays`) sont lus au référentiel ; la valeur du code ne sert que si le paramètre ne se lit pas. Le périmètre de la commission fondateur des hôtes aussi (DEV-F3, migration `0020`) : `fondateurs_places` (50) et `fondateurs_duree_mois` (6), contrôlés quand l'équipe inscrit un hôte au programme.
- **Versement à l'hôte 48 h après l'arrivée** (décision du 19 novembre 2026, migration `0015`) : pour les réservations faites depuis ; celles d'avant gardent 24 h. CGV version 2.5 (art. 8.1), contrats hôte et hôtel (migration `contrats/0010`, avec la compensation d'un séjour annulé après son versement), pages remboursement, aide et espace hôte mis à jour.

## Paramètres à zéro, en attente de décision

`fonds_garantie_cible` (à fixer : l'alerte sous la cible reste inerte), `fonds_garantie_taux` (10 % décidé, appliqué par GL-17), `double_validation_seuil` (250 000 F décidé, appliqué au lot UI-A), `garantie_renforcee_beneficiaire`, `prime_verification`, `experience_commission`, `experience_apporteur_hote`, `caution_evasion_plafond`, `caution_evasion_nuits`, `pack_remise_max`. Une valeur à zéro rend la règle inerte : le module tourne, mais ne produit aucun montant pour elle.

Les natures G01 et G02 (fonds de garantie) ont reçu le 19 novembre 2026 les comptes 6911 et 7911 (migration `0013`), remplacés le 21 novembre par 1301 (réserve, ADR-031, migration `0019`) ; D04 passe de 659 à 658. Historique dans `finance_correspondance_histo`. Jusqu'au 19 novembre, une ligne G aurait bloqué la clôture (I12).

## Tests

- `server/tests/unit/finance/` : règles du domaine et cas d'usage avec des adaptateurs factices, sans base ; `test_livres.py` : pagination, périodes, comptes de résultat, clôture (mois en cours, ordre, contrôles), rapports.
- `server/tests/unit/finance/test_cautions.py` : caution reçue une fois, retenue motivée et bornée, solde cohérent avec son document et unique, retard signalé. `server/tests/integration/locations/test_locations.py` : registre au paiement, retenue refusée sans pièce ou avec un fichier non reconnu, avis RET joint au voyageur et au propriétaire, REC à l'annulation.
- `server/tests/unit/finance/test_rapprochement.py` : une opération juge ses trois côtés (frais manquants nommés, inconnue d'un côté, montants différents, régularisée, hors grand livre) ; une journée n'est verte que si tout concorde et que les mouvements internes font zéro. `server/tests/integration/finance/test_rapprochement.py` : par le vrai parcours d'un séjour, journée payée verte une fois les frais écrits (une seule fois), journée jamais importée, aujourd'hui refusé, annulation et remboursement équilibrés, montants différents et transaction inconnue en rouge (clôture refusée), argent antérieur au grand livre à part, régularisation avec pièce qui ferme l'écart, régularisation au-dessus du seuil validée par une autre personne, écran et import du back-office, import de nuit une fois par jour.
- `server/tests/integration/finance/test_associes_fonds.py` : solde et relevé d'un associé (dépense annulée comprise), compte courant jamais débiteur (remboursement au-delà du solde, annulation d'une avance remboursée), parts du capital bornées par le capital social, PATCH partiel qui garde les autres champs ; dotation de 10 % du revenu net (1301 au débit, 118 au crédit, résultat du mois inchangé : carte C.1), sinistre en 658 et reprise 118 / 1301, écrite une fois, complétée par une ligne tardive du mois, refusée pour le mois en cours ou un mois clôturé, écrite par le worker une fois par heure, alerte sous la cible sans montant ; sinistre D04 couvert au plus du solde, une seule fois, dépense non annulable avant l'annulation de la couverture ; seule une D04 se couvre ; poches de la trésorerie ; permission exigée.
- `server/tests/unit/finance/test_service.py` et `test_regles.py` : garde du compte courant (lot d'écritures, ligne inverse) et calcul de la dotation (arrondi au franc, rien sans revenu).
- `server/tests/integration/finance/test_depenses.py` : dépense sous le seuil écrite (charge au nom du fournisseur, dû à l'associé, compte de passage à zéro, balance équilibrée, numérotation continue), refus sans justificatif ou avec un champ faux, permission, double validation à partir de 50 000 F, refus affiché, annulation par lignes inverses, filtres et total, annuaire, compte de passage hors rapprochement.
- `server/tests/unit/finance/test_validations.py` : deux personnes différentes, deux accords quand le système demande, exécution par le dernier accord, échec enregistré, refus motivé, seuil à zéro inerte.
- `server/tests/integration/finance/test_lot_ui_a.py` : par le vrai parcours d'un séjour, avoirs (annulation totale et partielle, facture émise après l'annulation, factures à régulariser), remboursement sous et au-dessus du seuil, contrainte en base, annulation depuis Réservations, refus, versement retenu puis accepté par deux personnes, compte en lecture seule.
- `server/tests/integration/finance/test_livres.py` : la rubrique Finance sur une vraie base (filtres du grand livre, livre-journal équilibré, solde progressif d'un compte et d'un tiers, balance, report d'un exercice, fichier CSV, clôture et son trigger, rapports, droits).
- `server/tests/integration/finance/test_sejours.py` : un séjour à travers le vrai parcours de paiement (paiement, arrivée, annulation gratuite et tardive, annulation après l'arrivée, paiement après annulation, versement, Pack Séjour, taux changé ensuite, argent antérieur au grand livre) ; `test_backoffice.py` : l'écran et ses droits.
- `server/tests/integration/finance/test_schema.py` : chaque vue, fonction et trigger existe et répond ; les vues disparaissent avant un `migrate` et reviennent après ; contrôle `finance.E001` et invariant I14.
- `server/tests/integration/finance/` (PostgreSQL réelle) : série FB (immuabilité, idempotence, refus, y compris par un `INSERT`, `UPDATE` ou `DELETE` direct en base), FI-02, destinataires des alertes, journal des corrections, les neuf cas de référence du prompt développeurs au franc près, les trois soldes, la partie double du cas de référence (note 12, section 8.4), les invariants et la clôture.
