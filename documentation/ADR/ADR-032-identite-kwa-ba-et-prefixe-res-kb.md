# Titre:
Identité Kwa-Ba : préfixe des réservations RES-KB (décision D6, DEV-F2)

# Status:
Accepté (21 novembre 2026).

# Contexte :
Le projet s'appelait AfriStay avant de devenir Kwa-Ba. Il en restait :
- le préfixe des références de réservation, `RES-AF2026-3A43`, affiché sur les reçus, les factures, les emails et dans le grand livre (`piece_reference`) ;
- l'ancien logo AfriStay, servi publiquement à `/logo.png` (`client/public/logo.png`) alors qu'aucune page ne l'utilise.

Les associés ont tranché la décision D6 (doc 37, F2) : tout ce qui est montré porte l'identité Kwa-Ba, avant la remise à zéro de la préprod et le lancement.

# Options
Option 1 : Garder `RES-AF`, déjà connu de l'équipe.

Option 2 : Passer à `RES-KB` et accepter encore `RES-AF` à la recherche.

Option 3 : Passer à `RES-KB` et refuser `RES-AF`.

# Décision
Nous retenons l'option 2.

- Les références deviennent `RES-KB<année>-<4 caractères>` (constante `REFERENCE_PREFIX` de `apps/reservations/models.py`). La référence est calculée, jamais stockée : toutes les réservations l'affichent d'office.
- La recherche par référence (`reservations.api.par_reference` : remboursements, réclamations, back-office) accepte encore `RES-AF`, inscrit sur les documents et emails déjà envoyés.
- Les lignes du grand livre déjà écrites gardent leur `piece_reference` (grand livre en ajout seul). La préprod est remise à zéro avant la recette finale, et la production n'a pas encore de réservation payée.
- L'ancien logo `client/public/logo.png` est supprimé.
- Le nom du marchand FedaPay se règle dans le tableau de bord FedaPay, hors du code. Les libellés de paiement envoyés aux prestataires disent déjà « Kwa-Ba ».

# Conséquences :
positives (bénéfices)
- Plus aucune trace d'AfriStay à l'écran, sur les documents ni à une adresse publique.
- Un voyageur qui donne une ancienne référence est toujours retrouvé.

négatifs (inconvénients)
- Pendant la transition, une même réservation peut être citée sous deux préfixes (documents anciens et nouveaux).

Impacts futurs
- Le jour où plus aucun document `RES-AF` n'est en circulation, la recherche pourra le refuser.
