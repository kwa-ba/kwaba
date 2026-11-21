# Titre:
Caution des séjours courte durée : trois options au choix de l'hôte (DEV-F1, décision caution v3)

# Status:
Accepté (21 novembre 2026). Option c (caution séquestrée) livrée désactivée jusqu'à la confirmation écrite de FedaPay.

# Contexte :
Les associés ont arrêté le régime de la caution des séjours le 18 novembre 2026 (« Décisions sur la caution : hébergement courte durée », version 3 ; décision D5a/D5b). Seule la location de voiture sans chauffeur garde aujourd'hui une caution en ligne : le registre générique des cautions (GL-13) et les documents REC/RET (GL-14) sont prêts à recevoir celle des séjours.

Ce que fixe la décision v3 :
- **Périmètre** : les hôtes **particuliers** (offre `COURTE_DUREE`) ; un hôtel ou une résidence ne perçoit aucune caution par la plateforme.
- **Kwa-Ba seul séquestre** : l'hôte ne détient jamais ni caution ni forfait, et rien n'est exigé du voyageur hors de ce qui est affiché avant le paiement.
- **Trois options au libre choix de l'hôte** :
  - **a) sans caution** ;
  - **b) Garantie Kwa-Ba renforcée** : un forfait non remboursable fixé par l'hôte (indicatif 1 000 à 10 000 F), payé avec le séjour, qui couvre les dommages mineurs jusqu'à 5 fois le forfait ; recette de Kwa-Ba (`R07`, 7067) ;
  - **c) caution séquestrée** : un taux choisi par l'hôte (10 % proposé, 40 % au plus, avertissement au-delà de 20 %) appliqué au **prix des nuitées seules**, arrondi à 500 F, borné par un filet absolu de 150 000 F ; sous 5 000 F, pas de caution. Restitution 72 h après le départ sans dommage ; codes `C01`, `C02`, `C03` (165), jamais une recette.
- **Annulation** : la caution est rendue à 100 % ; le forfait b reste acquis, sauf annulation du fait de l'hôte.
- **Réserve** : l'option c suppose un séquestre sans frais (empreinte de carte, ou frais rendus par FedaPay). À confirmer par écrit avec FedaPay avant sa mise en production. Le référent financier précise : empreinte de carte si possible, sinon encaissement.

# Options
Option 1 : Un mécanisme propre aux séjours. C'est ce que la décision interdit : « réutiliser exactement le séquestre des véhicules, ne pas créer de second système ».

Option 2 : Brancher les séjours sur le registre des cautions et les documents existants, avec le réglage par annonce, le calcul figé à la réservation et la restitution automatique.

# Décision
Nous retenons l'option 2, livrée en trois étapes.

1. **Réglage par l'hôte** : chaque annonce porte son option (`none`, `enhanced_guarantee`, `escrow`), son taux (option c) ou son forfait (option b). Le serveur refuse une annonce d'hôtel avec caution, un taux au-delà du plafond et l'option c tant qu'elle est désactivée ; il signale un taux au-delà du seuil d'alerte. L'espace hôte montre l'exemple du montant pour quelques nuits.
2. **Réservation et paiement** : le montant (caution ou forfait) est calculé et figé à la réservation, affiché au voyageur avant le paiement, et encaissé dans la même opération que le séjour. Lignes `C01` (caution, fonds des voyageurs) ou `R07` (forfait, recette), et inscription au registre des cautions.
3. **Restitution et dommages** : restitution automatique 72 h après le départ (document REC) ; retenue motivée avec pièces (document RET), selon la procédure de la location ; caution rendue en entier sur tous les chemins d'annulation.

Règles communes :
- Tous les taux, montants et délais sont lus au référentiel : `caution_pct_plafond` (40), `caution_pct_reco` (10), `caution_pct_alerte` (20), `caution_min_fcfa` (5 000), `caution_plafond_fcfa` (150 000), `caution_arrondi_fcfa` (500), `caution_restitution_heures` (72), `garantie_renforcee_multiple` (5), `garantie_renforcee_beneficiaire` (1 = Kwa-Ba) ; `caution_plafond_nuits` est désactivé.
- **L'option c est désactivée** (`caution_sequestre_active` = 0) jusqu'à la confirmation de FedaPay. Tant que l'empreinte de carte n'est pas confirmée, la caution est **encaissée** puis **remboursée**, par carte comme par Mobile Money.
- Une réservation garde son instantané : changer l'option ou le taux d'une annonce ne touche pas les réservations déjà faites.
- La recette `R07` est activée.

# Conséquences :
positives (bénéfices)
- Le voyageur sait, avant de payer, ce qu'il verse en plus et ce qui lui sera rendu.
- Un seul système de cautions pour les séjours et les locations : registre, documents, procédure de retenue.

négatifs (inconvénients)
- Tant que l'empreinte n'existe pas, une caution encaissée puis remboursée peut coûter des frais de paiement : d'où l'option c désactivée.
- La garantie renforcée s'apparente à une logique d'assurance : textes à faire valider par le juriste (CGV art. 13.5, 13.6).

Impacts futurs
- L'empreinte de carte, une fois confirmée par FedaPay, remplacera l'encaissement pour les paiements par carte.
- Les plafonds Evasion (`caution_evasion_*`) relèveront le filet quand ils seront fixés.
- Complète ADR-026 (rubrique Finance), GL-13 et GL-14 (registre et documents des cautions).
