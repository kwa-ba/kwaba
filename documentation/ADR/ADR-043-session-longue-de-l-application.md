# Titre:
Session de l'application mobile : 60 jours glissants, et réutilisation d'un jeton renouvelé qui ferme toutes les sessions

# Status:
Accepté (22 novembre 2026).

# Contexte :
Le jeton de renouvellement (refresh) dure 1 jour (`JWT_REFRESH_DAYS`), avec rotation et liste noire. Sur le site, c'est le serveur Next qui le garde, et la session se ferme 5 minutes après avoir quitté le site. Sur l'application, la personne s'attend à rester connectée des semaines : avec 1 jour, elle devrait se reconnecter presque à chaque ouverture.

L'application garde ses jetons dans le trousseau du téléphone (Keychain, Keystore) et envoie `X-Kwaba-Client: mobile-ios` ou `mobile-android`. Cet en-tête est falsifiable. Le document de décisions du 17 novembre proposait de lier la session longue à un appareil enregistré plutôt qu'à cet en-tête.

# Options
Option 1 : 60 jours pour tout le monde. Le site n'en a pas besoin, et un jeton volé sur le serveur du site resterait utilisable longtemps.

Option 2 : Une session longue seulement après l'enregistrement d'un appareil (notifications push). Mais une personne qui refuse les notifications n'aurait pas de session longue, et l'enregistrement d'un appareil est tout aussi déclaratif que l'en-tête.

Option 3 : Une session longue demandée par l'application à la connexion (`X-Kwaba-Client: mobile-…`), glissante, avec détection de la réutilisation d'un jeton déjà renouvelé.

# Décision
Nous retenons l'option 3 (décision de Godwin du 22 novembre 2026).

- **Pourquoi un en-tête suffit ici** : il ne donne aucun droit et ne contourne aucun contrôle. Pour l'obtenir, il faut déjà le bon mot de passe (ou Google, ou le code de vérification), et il ne fait que prolonger une session que la personne aurait pu rouvrir elle-même. L'en-tête reste interdit pour tout ce qui accorde un droit (Turnstile, par exemple).
- **Durée** : une connexion depuis l'application (mot de passe, Google, code de vérification, changement du mot de passe) reçoit un refresh marqué « session longue », valable `MOBILE_REFRESH_DAYS` jours (60). Chaque renouvellement repart pour 60 jours : sans ouverture de l'application pendant 60 jours, il faut se reconnecter.
- **Réutilisation** : un refresh de session longue déjà renouvelé, présenté après le délai de grâce (`JWT_REFRESH_GRACE_SECONDS`), signifie qu'une copie circule. Toutes les sessions du compte sont alors fermées et l'événement est journalisé (`refresh_reused`).
- Le site garde `JWT_REFRESH_DAYS` (1 jour), sans changement.

# Conséquences :
positives (bénéfices)
- La personne reste connectée sur son téléphone tant qu'elle ouvre l'application au moins une fois tous les 60 jours.
- Un jeton volé puis utilisé fait tomber toutes les sessions, y compris celle du voleur.

négatifs (inconvénients)
- Une application qui renouvelle son jeton, perd la réponse et réessaie après le délai de grâce est déconnectée partout. Le délai de grâce (60 s) couvre les nouvelles tentatives normales.
- Un refresh de 60 jours reste valable longtemps s'il est volé et jamais présenté deux fois : le changement du mot de passe ou la suppression du compte le révoquent.

Impacts futurs
- Une liste des appareils connectés, révocables un par un, pourra s'ajouter dans les paramètres.
