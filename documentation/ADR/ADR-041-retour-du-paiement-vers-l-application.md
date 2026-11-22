# Titre:
Retour du paiement vers l'application mobile : une page du site qui renvoie vers l'application

# Status:
Accepté (22 novembre 2026).

# Contexte :
Un paiement en ligne (FedaPay, PayPal) se fait sur la page du prestataire, qui renvoie ensuite le voyageur à une adresse donnée à la création de la transaction (`creer_paiement(..., url_retour)`). Aujourd'hui, c'est toujours une page du site : `/reservation/paiement/<id>`, `/transfert/<id>`, `/location/<id>`.

L'application mobile ouvre la page du prestataire dans un navigateur intégré. À la fin du paiement, le voyageur arrive sur le site, dans ce navigateur, et doit le fermer lui-même pour revenir dans l'application, qui relit alors le statut auprès de l'API.

FedaPay et PayPal attendent une adresse https. Une adresse de retour fournie librement par le client serait une redirection ouverte.

# Options
Option 1 : Laisser l'application recevoir n'importe quelle adresse de retour fournie par le client. Simple, mais c'est une redirection ouverte, et les prestataires refusent un schéma `kwaba://`.

Option 2 : Une page du site, construite par le back, qui renvoie vers l'application avec un schéma et des chemins pris dans une liste fixe.

# Décision
Nous retenons l'option 2 (décision de Godwin du 22 novembre 2026).

- L'application ajoute `"return_to": "app"` à l'appel qui démarre un paiement (séjour, transfert, location). Sans ce champ, rien ne change pour le site.
- Le back construit alors l'adresse `FRONTEND_URL/retour-app/<schéma>/<chemin>`, avec `<schéma>` lu dans le réglage `MOBILE_APP_SCHEME` (`kwaba` en production, `kwaba-preprod` en préprod) et `<chemin>` le même que la page du site (`reservation/paiement/<id>`, `transfert/<id>`, `location/<id>`). Le client ne fournit jamais d'adresse.
- La page du site renvoie vers `<schéma>://<chemin>`, en gardant les paramètres (`?annule=1` quand le voyageur annule). Elle n'accepte que les schémas `kwaba` et `kwaba-preprod` et ces trois formes de chemin ; sinon, elle renvoie à l'accueil. Elle affiche aussi un bouton « Revenir à l'application », au cas où le navigateur bloque la redirection.
- Le résultat du paiement est toujours lu dans l'API (webhook) : l'adresse de retour ne prouve rien.
- Les dons (Give) et le paiement par un tiers ne passent pas par l'application : inchangés.

# Conséquences :
positives (bénéfices)
- Le navigateur intégré se ferme seul (`openAuthSessionAsync` d'Expo détecte le schéma) et le voyageur revient sur le bon écran.
- Aucune redirection ouverte : le back choisit l'adresse, le site vérifie schéma et chemin.

négatifs (inconvénients)
- Un réglage de plus par environnement (`MOBILE_APP_SCHEME`).
- Une page du site sert uniquement à l'application.

Impacts futurs
- Avec les liens universels (iOS) et App Links (Android), l'application pourra ouvrir directement les pages du site ; cette page restera le repli.
