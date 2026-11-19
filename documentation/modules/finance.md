# Module finance : le grand livre des mouvements

Chaque mouvement d'argent est écrit **une seule fois**, dans une table en ajout seul, avec un code de nature et ses axes d'analyse (offre, tiers, moyen de paiement, compte d'argent, période, pièce). Tous les documents financiers sont des tris de ces lignes : aucune restitution ne recalcule depuis les réservations.

- Décision d'architecture : [ADR-024](../ADR/ADR-024-module-finance-grand-livre.md).
- Référence métier : dossier DAF du référent financier (10 et 11 novembre 2026) : cahier des charges FIN-01 à FIN-17, schéma `07_Schema_base_de_donnees.sql`, référentiel des paramètres, plan de test d'audit (séries FA à FJ).
- Code : `server/apps/finance/`. Seule interface pour les autres modules : `apps/finance/api.py` (ADR-019).

## Architecture (hexagonale, comme `agenda`)

| Couche | Contenu |
| --- | --- |
| `domain/` | `entities.py` (`Ligne`, `Ecriture`, `Mouvement`, `Referentiels`, sens, états d'un mois), `rules.py` (contrôle d'une ligne, ligne inverse, mois comptable), `exceptions.py` (`MouvementRefuse`, `RestitutionRefusee`). Python pur, sans Django |
| `application/` | `ports.py` (`GrandLivre`, `Parametres`, `Restitutions`, `Alertes`, `Journal`, `TransactionManager`, `Clock`), `service.py` (`GrandLivreService`, `RestitutionService`) |
| `infrastructure/` | `persistence/models.py` (tables), `persistence/repositories.py` (écriture, idempotence, verrous consultatifs, traduction des refus de la base), `persistence/sql_restitutions.py` (vues et fonctions SQL, source unique), `persistence/restitutions.py` (leur lecture), `notifications/alertes.py` (emails par `notifications.api`), `journal.py` (journal d'activité, module `activity`), `checks.py` (contrôle `finance.E001`), `clock.py`, `container.py` |
| `api.py` | fonctions simples qui délèguent aux services ; données simples en entrée et en sortie |
| `migrations/` | `0001` tables, `0002` référentiels du fichier, `0003` garde-fous (triggers). Les vues et fonctions ne sont pas dans une migration : supprimées avant chaque `migrate`, recréées après depuis `sql_restitutions.py` (`apps.py`) |

`server/.importlinter` (contrat `finance-couches`) interdit au domaine et à l'application d'importer l'infrastructure.

## Ce qui écrit dans le grand livre aujourd'hui : les séjours (FIN-03)

Chaque événement d'argent d'un séjour payé en ligne écrit ses lignes dans la transaction de l'action (`apps/paiements/grand_livre.py`) :

| Événement | Lignes | Où |
| --- | --- | --- |
| Paiement accepté | T01 prix des nuits et T02 ménage (dus à l'hôte ou à l'hôtel), R01 frais de service ; référence de la transaction FedaPay, moyen (Moov, Mixx, carte) | `reservations/paiement.py`, `paiement_recu` |
| Paiement refusé tout de suite (payé deux fois, réservation annulée entre-temps, dates prises) | T05 entrée : dû au voyageur | `paiements.services.rembourser` |
| Arrivée du voyageur (14 h le jour d'arrivée) | T01 sortie et R02 (particulier) ou R03 (hôtel) : la commission devient un produit | `reservations/paiement.py`, `constater_commissions`, une fois par séjour (`commission_constatee_le`) |
| Annulation | T02 et T01 sortie de ce qui est rendu, R01 rectifié si les frais sont rendus, R08 pour la part de Kwa-Ba sur les nuits retenues (cas FF-02), puis T05 entrée | `paiements.services.annuler_paiement_reservation` |
| Frais réduits après le paiement (Pack Séjour + Chauffeur) | R01 rectifié (ligne inverse puis nouveau montant), puis T05 entrée de la différence | `reservations.api.reduire_frais_pack_sejour` |
| Remboursement envoyé | T05 sortie | `paiements.services` (FedaPay et PayPal) |
| Versement à l'hôte envoyé | T09 sortie | `paiements.services.synchroniser_payout` |

Les montants sont ceux figés sur la réservation à sa création : un taux changé ensuite ne modifie rien (FA-11). Un séjour payé avant le grand livre, ou payé hors ligne, n'y a aucune ligne : il n'en reçoit jamais après coup (aucune sortie de ce qui n'est jamais entré). Les réservations existantes sont marquées par la migration `reservations 0012`.

À venir, sur le même modèle : transferts (chauffeur « à désigner » jusqu'à son attribution) et locations de voiture (propriétaire, chauffeur, caution C01 à C03). Kwa-Ba Give n'écrit rien tant que ses natures ne sont pas décidées.

## Back-office : la rubrique Finance

Une seule rubrique **Finance** dans le menu (GL-1, section de droits « finances ») ; ses pages s'ouvrent sous elle. Tout est lu dans le grand livre, sauf « Encaissements et versements » (calculé depuis les paiements, gardé pour comparer). Les seules écritures sont la clôture d'un mois et l'enregistrement d'un rapport, toutes deux au journal d'activité.

| Page | Ticket | Contenu | API (`/api/v1/admin/finance/…`) |
| --- | --- | --- | --- |
| Synthèse | — / GL-18 (partiel) | invariants, soldes qui ne se mélangent jamais, comptes d'argent, sommes dues par partenaire, marge par offre, taux de frais réel et fonds de garantie du mois | `grand-livre/`, `pilotage/?mois=` |
| Grand livre | GL-2 | toutes les lignes, du plus récent au plus ancien ; filtres combinés (période, famille, nature, offre, type et identifiant de tiers, compte d'argent, pièce, sens) ; pagination | `mouvements/`, `referentiels/` |
| Livre-journal | GL-3 | deux écritures par mouvement, débit et crédit, par date ; filtre par journal (VT, AC, TR, OD) ; totaux de la période | `livre-journal/` |
| Grand-livre par compte | GL-4 | un compte général, ou un tiers (compte auxiliaire), avec son solde progressif, d'ouverture et de clôture | `comptes/`, `comptes/<compte>/auxiliaires/`, `grand-livre-compte/` |
| Balance générale | GL-5 | par compte : solde d'ouverture, débits, crédits, solde de clôture ; totaux et équilibre | `balance/` |
| Rapprochement FedaPay | GL-12 | chaque journée terminée sur trois colonnes (Kwa-Ba, grand livre, FedaPay net et frais réels), verte, rouge ou non importée ; détail opération par opération ; importer ou réimporter une journée ou le mois ; régulariser un écart avec pièces | `rapprochement/?mois=`, `rapprochement/<AAAA-MM-JJ>/`, `rapprochement/<jour>/regulariser/` ; import : `paiements/rapprochement/importer/` (module `paiements`) |
| Dépenses | GL-15 | les charges de Kwa-Ba avec leur justificatif : liste filtrée (période, nature, statut) et total écrit, saisie (date, nature D, offre, montant TTC, fournisseur, associé qui a avancé, n° de facture, pièces), annulation motivée ; onglets Fournisseurs et Associés | `depenses/`, `depenses/<id>/annuler/`, `fournisseurs/`, `associes/` |
| Encaissements et versements | (AN-B2) | page Finances d'origine (module `paiements`) : période, rapprochement jour par jour, versements, exports CSV et PDF | `paiements/finances/` |
| Remboursements | GL-9 | rembourser un séjour payé depuis ses montants figés (conditions du voyageur, ou intégral par Kwa-Ba) ; suivre chaque remboursement, saisir le compte Mobile Money, relancer, enregistrer un remboursement fait à la main (carte) | `paiements/finances/remboursements/` (module `paiements`) |
| Validations | GL-10 | les opérations à partir du seuil qui attendent une deuxième personne ; approuver ou refuser (motif) | `validations/`, `validations/<id>/approuver|refuser/` |
| Rapports | GL-19 | les rapports enregistrés, un rapport libre sur un ou deux axes, l'enregistrement d'un nouveau rapport (une ligne de `finance_rapport`) ; export CSV | `rapports/`, `rapports/resultat/`, `rapports/export/` |
| Clôture mensuelle | GL-7 | les six contrôles d'un mois, et son verrouillage | `cloture/`, `cloture/<AAAA-MM>/` |
| Export comptable | GL-6 | le fichier des écritures (CSV `;`, UTF-8 avec BOM) pour le cabinet | `export/ecritures/` |

Règles :

- **Périodes** : `?debut=&fin=` (AAAA-MM-JJ, bornes comprises), ce mois-ci par défaut, un an au plus. **Listes** : `page`, `page_size` (20 par défaut, 100 au plus), réponse `{results, count, page, page_size}` comme le reste du back-office.
- **Comptes de résultat** (classes 6, 7, 8) : leur solde repart de zéro au 1er janvier (exercice civil) ; les comptes de bilan (1 à 5) reprennent leur solde depuis la première écriture. En attendant les écritures d'à-nouveaux (GL-23), c'est la balance et le grand-livre par compte qui l'appliquent.
- **Clôture** : un mois se clôture une fois terminé, dans l'ordre (le plus ancien mois ouvert d'abord), quand les six contrôles de `finance_peut_on_cloturer` sont verts, par un **super administrateur** (décision du 18 novembre 2026), qui saisit le mois (« 10/2026 ») pour confirmer. Les clôtures simultanées s'attendent (verrou consultatif). Un mois verrouillé ne reçoit plus aucune écriture et **ne se rouvre jamais** : la base refuse toute modification ou suppression d'un mois verrouillé (trigger de la migration `0007`). Journal : `periode_cloturee`.
- **Exports** : écritures et rapports en CSV, cellules protégées contre l'injection de formules ; chaque export va au journal (`finances_exportees`, format `ecritures` ou `rapport`).
- **Rapports** : code de 3 à 40 caractères (minuscules, chiffres, `_`), titre de 3 à 120, axes de `finance_axe`, filtres de familles et d'offres en codes ; un axe inconnu est refusé par la base. Journal : `rapport_cree`.
- **Rapprochement** : le contrôle 4 de la clôture exige chaque journée du mois rapprochée (état `fait`, écart nul). Une journée jamais importée reste « non importée », jamais un écart nul (FIN-02.7). Voir la section suivante.

L'ancienne adresse `/backoffice/grand-livre` redirige vers `/backoffice/finances/grand-livre`.

## Rapprochement avec FedaPay (GL-12)

Décisions du 19 novembre 2026 : les frais FedaPay restent **à la charge de Kwa-Ba** (H-2, confirme la décision du 13 novembre) ; les données viennent de **l'API FedaPay**, relue chaque nuit, et d'un bouton « Réimporter » ; l'argent d'un produit pas encore au grand livre est **montré à part**, hors écart ; un écart inexpliqué se ferme par une **écriture de régularisation** motivée, avec pièce, validée par une deuxième personne à partir du seuil.

- **Import** (module `paiements`, `rapprochement.py`, le seul qui parle à FedaPay) : pour une journée terminée, chaque paiement, remboursement et versement de Kwa-Ba proche de ce jour est relu chez FedaPay (montant, frais réels, statut, date). La journée d'une opération est celle de FedaPay (approbation, envoi). Les transactions FedaPay inconnues de Kwa-Ba sont cherchées au mieux (`GET /transactions/search`, peu documentée : quelques pages, filtrées sur le jour ; si la recherche échoue, la journée le dit sans être bloquée).
- **Frais réels** : une ligne **D01** (compte 6317) par opération dont l'argent est au grand livre, au montant du relevé, sortie du compte FEDAPAY, sous la référence de l'opération (écrite une fois, même réimportée). Elle alimente le taux de frais réel de la Synthèse.
- **Trois colonnes** (module `finance`, `RapprochementService`) : par opération, Kwa-Ba (le montant enregistré), le grand livre (somme signée des lignes du compte FEDAPAY de cette référence, régularisations comprises, corrections exclues) et FedaPay (montant moins les frais pour un encaissement, montant plus les frais pour une sortie). États : `concorde`, `ecart` (avec la raison : inconnue d'un côté, montants différents, frais pas au grand livre…), `regularisee`, `hors_livre`. Les autres lignes du compte ce jour-là (arrivée, annulation, corrections : des passages d'une nature à l'autre) forment les **mouvements internes**, qui doivent faire zéro.
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

## Lot UI-A : avoirs, remboursements, rôle Finance, double validation

### Avoirs (GL-8, module `documents`)

Une facture ne se supprime ni ne se modifie (LPF Togo art. 64) : une vente rendue est neutralisée par une **facture d'avoir**, série `AVO-AAAA-NNNNN`, numérotation continue sans trou (`SequencePieceModel`, verrou à chaque émission), PDF figé, qui cite la facture d'origine (numéro, date, montant). `AvoirModel` : montants positifs, à déduire ; jamais plus que ce que la facture contient encore.

- **Quand** : à chaque remboursement décidé (`paiements.services.rembourser`), et à l'émission d'une facture d'un objet déjà remboursé. Le produit payé dit ce qui a été rendu (`Produit.rembourse`, `paiements.api.total_rembourse`, sur le **premier paiement réussi** de l'objet seulement : un paiement fait deux fois et rendu n'est pas une vente annulée).
- **Montant** (décision du 18/11) : le montant remboursé. Annulation totale : un avoir du total qui reprend les lignes de la facture. Remboursement partiel (nuits retenues) : un avoir du montant rendu, une ligne ; la facture reste valable pour la part conservée. Un séjour annulé jamais facturé n'a ni facture ni avoir.
- **Idempotent** : `documents.api.regulariser_avoirs` émet la différence entre ce qui a été rendu et les avoirs déjà émis ; un second appel n'émet rien. Un échec (société non renseignée) n'empêche jamais le remboursement : la facture apparaît dans **Documents → Avoirs**, « factures remboursées sans avoir », avec un bouton « Émettre l'avoir ».
- **Factures antérieures** (F-2026-00006) : `manage.py regulariser_avoirs` (`--simulation` pour voir sans émettre), relançable sans doublon.

### Remboursements (GL-9, module `paiements`)

**Finance → Remboursements** : chercher un séjour par sa référence (`RES-AF2026-3A43`, ou son identifiant si deux réservations partagent la référence) ; l'aperçu donne, depuis les **montants figés** de la réservation (`tarifs.montants_de`, jamais les taux courants), ce que rendrait l'annulation selon les conditions du voyageur et en intégral. Rembourser annule la réservation par le parcours habituel : lignes du grand livre (T01, T02, R01, R08, T05), versement de l'hôte réduit ou annulé, avoir si la vente était facturée. La liste suit chaque remboursement ; actions : saisir le compte Mobile Money (voyageur joint par téléphone), relancer un envoi en échec, enregistrer un remboursement fait depuis le tableau de bord FedaPay (carte : T05 sort du compte d'argent). Journal : `remboursement_traite`.

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

- **Registre** (`finance_caution`, module `finance`) : une caution par objet, reçue (montant, date, date limite de restitution), puis soldée une fois : `restituee` (tout rendu) ou `retenue` (une part gardée sur décision motivée). La base refuse un solde dont les montants ne font pas la caution, un solde sans document, une retenue au-delà de la caution ou sans motif ni article. API : `enregistrer_caution`, `decider_retenue`, `solder_caution`, `caution`, `registre_cautions`. Écran **Finance → Cautions** : total détenu (argent des voyageurs, jamais un revenu), cautions en retard, retenues avec leur motif, PDF du document et pièces justificatives.
- **Documents** (module `documents`) : **reçu de restitution** `REC-AAAA-NNNNN` (tout rendu) ou **avis de retenue** `RET-AAAA-NNNNN` (motif, fondement CGV, auteur et date de la décision, pièces citées, montant retenu et rendu) ; numérotation continue par série, PDF figé, un document par caution, contrôles en base. Pièces justificatives (`JustificatifCautionModel`) : PDF, JPEG, PNG ou WebP reconnus à leur signature, 10 Mo au plus, 10 par caution, stockage privé, jamais supprimées. Le voyageur télécharge son document par `/api/v1/documents/location/<id>/caution/`. Routes du back-office `documents/cautions/…` et `documents/justificatifs/…` rattachées à la section « finances ».
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
| `controle_invariants()` | I5, I8 à I13, et I14 (modules ouverts : offres et natures actives) : nombre d'anomalies, 0 = respecté |
| `peut_on_cloturer(mois)` | les six contrôles, OK ou REFUSE, et quoi faire |
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
| FIN-02 rapprochement à trois voies | Fait (GL-12) : import FedaPay chaque nuit et à la demande, frais réels D01, trois colonnes par opération et par journée, régularisation motivée avec pièce et double validation. Transactions inconnues : recherche FedaPay au mieux. Banque (relevé importé) : GL-22 |
| FIN-03 ventilation figée au paiement | Séjours : fait (FIN-03.1, 03.3, 03.5 ; les montants figés à la réservation tiennent lieu d'instantané, FA-11). Écran du détail d'une réservation (FIN-03.4) : à venir |
| FIN-04 sommes dues aux partenaires | Vue faite. Écran, échéances, alertes, gel des versements : lot F2 |
| FIN-05 registre des cautions | Fait pour la location : registre `finance_caution`, écran, alertes de retard, reçus REC et avis RET avec pièces (GL-13, GL-14). Séjours : projet séparé. Lignes C du grand livre : avec FIN-03 des locations |
| FIN-06 fonds de garantie | Taux à 0 ; natures G sans compte (bloquent la clôture, I12) : lot F4, après l'expert-comptable |
| FIN-07 livres comptables et export | Fait : vues (partie double, livre-journal, grand-livre, balance, contrôles), écrans Livre-journal, Grand-livre par compte, Balance générale et fichier CSV des écritures (GL-3 à GL-6). À-nouveaux et livre d'inventaire : GL-23 |
| FIN-08 clôture mensuelle | Fait : refus en base dans un mois verrouillé, `peut_on_cloturer`, écran et verrouillage par un super admin, dans l'ordre, définitif en base (GL-7). Contrôle « toute facture annulée a son avoir » : avec GL-8 |
| FIN-09 facturation | Factures (module `documents`) ; avoirs AVO sur toute vente remboursée (GL-8). Documents de caution REC/RET : GL-14 |
| FIN-10 tarifs complets et historique | Paramètres chargés ; page Tarifs : avec FIN-16 |
| FIN-11 dépenses, comptes courants | Dépenses (FIN-11.1) : faites (GL-15), avancées par un associé, justificatif obligatoire, double validation à partir de 50 000 F. Comptes courants d'associés et remboursement des avances : GL-16 |
| FIN-12 tableau de bord | Synthèse : marge par offre, taux de frais réel, fonds de garantie du mois. Tableau de bord DAF complet (quatre poches, seuils, scénario prudent) : GL-18 |
| FIN-13 rôle Finance, double validation, journal | Fait : rôle Finance en lecture seule, permission « Opérations financières », double validation à partir de 250 000 F des remboursements et des versements, garantie en base, journal (GL-10) |
| FIN-16 référentiel unique des paramètres | Table et 95 valeurs (53 actives). Lecture par le site à la place de `ReglagesTarifsModel`, ajout par l'interface, historique écrit : PR dédiée |
| FIN-17 restitution générique | Fait : vue pivot, axes, rapports, moteur, écran Rapports avec rapport libre, création d'un rapport sans développement et export CSV (GL-19) |
| Invariants | I5, I8 à I13 en base, I14 ajouté (modules ouverts et référentiel). I1 à I4, I6 et I7 se comparent aux écrans (page Finances, tableau de bord) quand ils liront le grand livre |

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
- Fonds de garantie : **10 %** (au lieu de 5 ou 7 % ; d'abord fixé à 8 %, corrigé le même jour). Il est distinct de la caution du voyageur, qui garde sa règle propre. Capital social : **500 000 F CFA**. Ils entreront dans `finance_parametre`, avec leur historique, avec GL-17 et GL-16 (le fonds reste à zéro tant que ses natures G n'ont pas de compte SYSCOHADA, sinon il bloquerait la clôture).
- Données de test de la préprod : par les vrais parcours (réservation, paiement, arrivée, annulation, versement), comptes `*.demo@`. Le grand livre étant en ajout seul, elles y restent : la base de production est distincte.

## Décisions prises le 2026-11-19

- Frais FedaPay (H-2) : à la charge de Kwa-Ba, une ligne D01 par transaction au montant réel du relevé.
- Dépenses (GL-15) : avancées par un associé (compte courant 462) ; double validation à partir de 50 000 F ; annuaire léger des fournisseurs ; liste des associés au back-office. Compte bancaire, quand il sera activé : solde du relevé de fin de mois exigé à la clôture jusqu'à GL-22.
- Rapprochement : API FedaPay chaque nuit et bouton « Réimporter » ; argent hors grand livre montré à part, hors écart ; écart inexpliqué fermé par une écriture de régularisation (motif, pièce, double validation à partir de 250 000 F, journal).

## Paramètres à zéro, en attente de décision

`fonds_garantie_taux` (10 % décidé, voir ci-dessus), `double_validation_seuil` (250 000 F décidé, appliqué au lot UI-A), `garantie_renforcee_beneficiaire`, `prime_verification`, `experience_commission`, `experience_apporteur_hote`, `caution_evasion_plafond`, `caution_evasion_nuits`, `pack_remise_max`. Une valeur à zéro rend la règle inerte : le module tourne, mais ne produit aucun montant pour elle.

Les natures G01 et G02 (fonds de garantie) n'ont pas de compte SYSCOHADA : une ligne G apparaîtrait dans `finance_ecritures_sans_compte` et bloquerait la clôture (I12). C'est voulu, jusqu'à l'avis de l'expert-comptable.

## Tests

- `server/tests/unit/finance/` : règles du domaine et cas d'usage avec des adaptateurs factices, sans base ; `test_livres.py` : pagination, périodes, comptes de résultat, clôture (mois en cours, ordre, contrôles), rapports.
- `server/tests/unit/finance/test_cautions.py` : caution reçue une fois, retenue motivée et bornée, solde cohérent avec son document et unique, retard signalé. `server/tests/integration/locations/test_locations.py` : registre au paiement, retenue refusée sans pièce ou avec un fichier non reconnu, avis RET joint au voyageur et au propriétaire, REC à l'annulation.
- `server/tests/unit/finance/test_rapprochement.py` : une opération juge ses trois côtés (frais manquants nommés, inconnue d'un côté, montants différents, régularisée, hors grand livre) ; une journée n'est verte que si tout concorde et que les mouvements internes font zéro. `server/tests/integration/finance/test_rapprochement.py` : par le vrai parcours d'un séjour, journée payée verte une fois les frais écrits (une seule fois), journée jamais importée, aujourd'hui refusé, annulation et remboursement équilibrés, montants différents et transaction inconnue en rouge (clôture refusée), argent antérieur au grand livre à part, régularisation avec pièce qui ferme l'écart, régularisation au-dessus du seuil validée par une autre personne, écran et import du back-office, import de nuit une fois par jour.
- `server/tests/integration/finance/test_depenses.py` : dépense sous le seuil écrite (charge au nom du fournisseur, dû à l'associé, compte de passage à zéro, balance équilibrée, numérotation continue), refus sans justificatif ou avec un champ faux, permission, double validation à partir de 50 000 F, refus affiché, annulation par lignes inverses, filtres et total, annuaire, compte de passage hors rapprochement.
- `server/tests/unit/finance/test_validations.py` : deux personnes différentes, deux accords quand le système demande, exécution par le dernier accord, échec enregistré, refus motivé, seuil à zéro inerte.
- `server/tests/integration/finance/test_lot_ui_a.py` : par le vrai parcours d'un séjour, avoirs (annulation totale et partielle, facture émise après l'annulation, factures à régulariser), remboursement sous et au-dessus du seuil, contrainte en base, annulation depuis Réservations, refus, versement retenu puis accepté par deux personnes, compte en lecture seule.
- `server/tests/integration/finance/test_livres.py` : la rubrique Finance sur une vraie base (filtres du grand livre, livre-journal équilibré, solde progressif d'un compte et d'un tiers, balance, report d'un exercice, fichier CSV, clôture et son trigger, rapports, droits).
- `server/tests/integration/finance/test_sejours.py` : un séjour à travers le vrai parcours de paiement (paiement, arrivée, annulation gratuite et tardive, annulation après l'arrivée, paiement après annulation, versement, Pack Séjour, taux changé ensuite, argent antérieur au grand livre) ; `test_backoffice.py` : l'écran et ses droits.
- `server/tests/integration/finance/test_schema.py` : chaque vue, fonction et trigger existe et répond ; les vues disparaissent avant un `migrate` et reviennent après ; contrôle `finance.E001` et invariant I14.
- `server/tests/integration/finance/` (PostgreSQL réelle) : série FB (immuabilité, idempotence, refus, y compris par un `INSERT`, `UPDATE` ou `DELETE` direct en base), FI-02, destinataires des alertes, journal des corrections, les neuf cas de référence du prompt développeurs au franc près, les trois soldes, la partie double du cas de référence (note 12, section 8.4), les invariants et la clôture.
