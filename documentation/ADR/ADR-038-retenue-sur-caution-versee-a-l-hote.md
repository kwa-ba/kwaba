# Titre:
Retenue sur la caution d'un séjour : versée à l'hôte par un versement dédié (nature T10)

# Status:
Accepté (22 novembre 2026).

# Contexte :
La caution séquestrée d'un séjour (ADR-036, option c) peut être retenue en partie pour un dommage, sur une décision motivée de l'équipe avec pièces justificatives (avis RET, GL-14). La somme retenue revient à l'hôte, dont le logement a subi le dommage.

Mais le versement de l'hôte part 48 h après l'arrivée (CGV art. 8.1), donc bien avant la fin du délai de signalement (72 h après le départ). Et une réservation n'a qu'un versement (`VersementModel`, unique par réservation). La location de voiture ne connaît pas ce problème : le versement du propriétaire attend que la caution soit soldée.

Le grand livre n'a pas non plus de nature pour une somme due à l'hôte au titre d'un dommage : T01 est le prix des nuits, T02 le ménage.

# Options
Option 1 : Ajouter la retenue au prochain versement de l'hôte. C'est simple, mais l'hôte n'est jamais payé s'il n'a pas d'autre séjour.

Option 2 : Inscrire la retenue comme due à l'hôte, et la faire payer à la main par l'équipe. Aucun code de versement, mais un paiement hors du worker, sans reprise automatique en cas d'échec.

Option 3 : Un versement dédié « indemnité de dommage », envoyé par le worker une fois la caution soldée, avec une nature propre au grand livre.

# Décision
Nous retenons l'option 3 (décision de Godwin du 22 novembre 2026). Le signalement passe par le back-office seul : l'hôte prévient l'équipe par la messagerie, et l'équipe saisit la retenue.

- **Retenue** : saisie au back-office sur la réservation (montant, motif, article des CGV, au moins une pièce), pendant le délai de signalement, comme pour la location. 0 l'annule.
- **Solde** : à la fin du délai, le worker rend au voyageur la caution moins la retenue et émet le RET (ou le REC s'il n'y a pas de retenue).
- **Grand livre** :
  - `C02` sortie pour ce qui est rendu, puis `T05` ;
  - `C03` sortie pour ce qui est retenu, avec le motif et la référence de la décision ;
  - **`T10` « Indemnité de dommage due à l'hôte »** (fonds de tiers, compte 47121) en entrée du même montant ;
  - `T09` sortie quand le versement part, comme pour le versement du séjour.
- **Versement** : un `VersementIndemniteModel` par réservation (module `paiements`), envoyé sur le profil de versement de l'hôte, suivi comme les autres versements (tentatives, échec signalé, page des versements).
- L'avis RET est envoyé au voyageur et à l'hôte.

# Conséquences :
positives (bénéfices)
- L'hôte reçoit l'indemnité même sans autre séjour, et l'envoi est repris automatiquement en cas d'échec.
- Le grand livre distingue le prix des nuits de l'indemnité d'un dommage.

négatifs (inconvénients)
- Une nature et un type de versement de plus.
- Le module finance est touché (nature T10) : relecture demandée à Fadel.

Impacts futurs
- Un bouton de signalement dans l'espace hôte pourra venir plus tard, sans changer ce circuit.
- Les dommages couverts par la garantie renforcée (option b) passent par le fonds de garantie, pas par ce circuit.
