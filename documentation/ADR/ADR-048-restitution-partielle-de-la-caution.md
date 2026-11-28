# Titre:
Caution d'un séjour : restitution partielle pendant un litige de dommage (CGV art. 13.6)

# Status:
Accepté (27 novembre 2026).

# Contexte :
Les décisions du 22 novembre (D-CGV-2) fixent les délais de la procédure de dommage : l'hôte déclare sous 48 h après le départ, le client répond sous 48 h, puis Kwa-Ba rend un avis motivé, que le client peut contester sous 7 jours. La part non contestée de la caution est rendue 72 h après le départ ; seul le montant en litige est gardé au-delà.

Aujourd'hui (ADR-038), l'équipe doit saisir la retenue avant la fin du délai de 72 h, et le worker solde alors la caution en une fois. Avec 48 h + 48 h, la décision arrive forcément après 72 h : le circuit actuel rendrait toute la caution avant la décision, ou la bloquerait en entier.

# Options
Option 1 : Allonger le délai de restitution jusqu'à la décision. Simple, mais toute la caution reste bloquée : contraire à l'article 13.6.

Option 2 : Séparer le montant réclamé de la retenue décidée, et rendre la caution en plusieurs fois : la part non contestée à 72 h, la part écartée par la décision dès la décision, le reste à l'hôte une fois le délai de contestation passé.

# Décision
Nous retenons l'option 2 (décision de Godwin du 27 novembre 2026). L'équipe saisit tout au back-office, comme dans ADR-038 (l'hôte la prévient par la messagerie).

1. **Réclamation** : dans les `dommage_delai_hote_h` heures (48) après le départ, l'équipe saisit le montant réclamé par l'hôte, son motif et au moins une pièce. 0 la retire.
2. **À la fin du délai de restitution** (`caution_restitution_heures`, 72 h) : le worker rend la caution moins le montant encore en jeu (le montant réclamé, ou la retenue si elle est déjà décidée). Sans réclamation, la caution est soldée comme avant (REC).
3. **Décision** : après la réponse du client, l'équipe fixe la retenue R (0 ≤ R ≤ montant réclamé) avec son motif et l'article des CGV. La part réclamée mais écartée est rendue tout de suite si les 72 h sont passées. Le client et l'hôte reçoivent la décision par email.
4. **Contestation** : pendant `dommage_contestation_j` jours (7), R reste gardée. Le client conteste par la messagerie ; l'équipe peut alors rendre une nouvelle décision, qui ne peut que baisser R (ce qui est rendu ne se reprend pas) et rouvre le délai.
5. **Solde** : une fois le délai de contestation passé, le worker verse R à l'hôte (C03 + T10, versement d'indemnité de ADR-038) et émet l'avis RET (ou le reçu REC si R = 0).

- **Grand livre** : chaque part rendue est une sortie `C02` (clé propre à chaque restitution) ; la retenue `C03` + `T10` s'écrit au solde. Le compte 165 ne garde que ce qui est en jeu.
- **Registre des cautions** (module finance) : nouvel état `litige` et colonne `montant_conteste` ; `montant_rendu` cumule les restitutions. Le total détenu est la caution moins ce qui est déjà rendu.
- **Document** : un seul document par caution, émis au solde (règle GL-14 : un document par caution, numérotation continue). Les restitutions partielles sont confirmées par email. Le doc 39 prévoyait un REC dès 72 h : ce serait deux documents par caution et un changement de la règle partagée avec la location de voiture. Nous ne le faisons pas pour l'instant.

# Conséquences :
positives (bénéfices)
- Le client récupère la part non contestée à 72 h, comme le veut l'article 13.6.
- L'hôte n'est payé qu'une fois la décision définitive : rien à reprendre si le réexamen donne raison au client.

négatifs (inconvénients)
- Une caution peut se rendre en trois fois (72 h, décision, solde) : trois remboursements FedaPay, donc trois frais.
- Le module finance est touché (registre des cautions) : relecture demandée à Fadel.

Impacts futurs
- Hors périmètre : le recouvrement d'un dommage supérieur à la caution, ou sans caution (art. 13.6, paiement sous 7 jours, sinon suspension du compte). Il demande un encaissement hors réservation.
- Un bouton de réclamation dans l'espace hôte pourra venir plus tard, sans changer ce circuit.
