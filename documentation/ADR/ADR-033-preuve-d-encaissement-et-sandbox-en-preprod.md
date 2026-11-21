# Titre:
Preuve d'encaissement : la préprod passe par la sandbox FedaPay, la simulation reste en développement (décision D1, DEV-F4)

# Status:
Accepté (21 novembre 2026).

# Contexte :
Une réservation se confirme de deux façons : le webhook de FedaPay, ou la page de retour du voyageur, qui interroge l'API. Dans les deux cas, le serveur ne fait confiance qu'à l'identifiant de la transaction et relit son statut chez FedaPay (`paiements.services.synchroniser_paiement`).

Le 18 novembre, une réservation est passée « Payé » en préprod sans passer par FedaPay. La recette du 19 a donné le garde-fou DEV-L3 (Fadel) :
- le contrôle `paiements.E001` arrête le déploiement si `PAIEMENT_HORS_LIGNE` (la simulation) est actif **en production** ;
- un webhook non signé est refusé, et un webhook signé envoyé deux fois n'écrit l'encaissement qu'une fois.

La décision D1 sur le mode de paiement de la préprod restait ouverte, et le contrôle laissait donc la préprod simuler. Le document consolidé (doc 37, F4) demande en plus la **preuve** de bout en bout : un encaissement sandbox qui confirme et écrit l'encaissement puis les frais D01, et aucune réservation « Payé » sans encaissement.

# Options
Option 1 : La préprod simule les paiements. La recette n'y prouve jamais le vrai circuit.

Option 2 : La préprod passe par la sandbox FedaPay, et la simulation n'est permise qu'en développement.

# Décision
Nous retenons l'option 2 (décision D1, KPOGLO Godwin, 21 novembre 2026).

- La préprod utilise la sandbox FedaPay : vrais webhooks signés, vraie relecture du statut, frais D01 écrits au rapprochement. C'est déjà sa configuration (kwa-ba-infra : `FEDAPAY_ENV=sandbox`, clés et secret du webhook dans le vault).
- `paiements.E001` arrête le déploiement si `PAIEMENT_HORS_LIGNE` est actif **hors développement** (`DEBUG` faux) : en production comme en préprod.
- Des tests couvrent la preuve : un webhook signé ne confirme rien tant que FedaPay ne dit pas « approuvé » (en attente, refusé), la page de retour suit la même règle, un webhook suivi de la page de retour n'écrit qu'un encaissement, un identifiant inconnu n'écrit rien.

# Conséquences :
positives (bénéfices)
- La recette finale en préprod passe par le même circuit que la production.
- Une préprod mal configurée ne peut plus confirmer de réservation gratuitement : le déploiement s'arrête.

négatifs (inconvénients)
- Un test de bout en bout en préprod demande un paiement sandbox (numéro de test FedaPay), et non plus un simple clic.

Impacts futurs
- Avant le Go, la production passe de `FEDAPAY_ENV=sandbox` à `live`, avec ses clés live (kwa-ba-infra).
- Complète DEV-L3 (recette du 19 novembre) et ADR-026.
