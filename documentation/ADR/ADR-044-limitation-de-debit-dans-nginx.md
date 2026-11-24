# Titre:
Limitation de débit dans nginx, par adresse : administration, authentification, reste de l'API

# Status:
Accepté (24 novembre 2026).

# Contexte :
nginx, devant l'API et le site, ne limitait qu'une route (`/api/csp-report`). Les limites existent dans Django (connexion, inscription, codes, signalements…), par adresse et par compte, mais chaque requête refusée y coûte un travailleur de l'API, qui n'en a que deux. Les routes d'administration (`/api/v1/admin/`, admin Django `/admin/`) ne sont protégées que par l'authentification et le second facteur (ADR-028) : rien ne freine un robot qui les martèle.

Au Togo, les opérateurs mobiles partagent une même adresse publique entre beaucoup de clients (CGNAT) : une limite par adresse trop stricte bloquerait des voyageurs légitimes.

En préprod, nginx est derrière le Caddy du serveur : il voit l'adresse de Caddy pour toutes les requêtes.

# Options
Option 1 : Rien dans nginx, tout dans Django. Chaque requête abusive occupe quand même un travailleur.

Option 2 : Une seule limite pour tout le site. Trop large pour l'administration, ou trop stricte pour le reste.

Option 3 : Trois zones par adresse, larges, adaptées à chaque usage, en plus des limites de Django.

# Décision
Nous retenons l'option 3 (décision de Godwin du 24 novembre 2026).

| Zone | Routes | Débit par adresse | Rafale |
|---|---|---|---|
| `admin` | `/api/v1/admin/`, `/api/proxy/v1/admin/` (back-office du site), `/admin/` (admin Django) | 5 par seconde | 20 |
| `auth` | `/api/v1/auth/` (sauf le renouvellement), `/api/auth/callback/` (connexion du site) | 30 par minute | 20 |
| `api` | le reste de `/api/`, `/api/proxy/`, `/api/auth/` et `/static/` | 20 par seconde | 60 |

- Au-delà : `429`, comme les limites de Django, et une ligne d'avertissement dans le journal de nginx.
- Le renouvellement des jetons (`/api/v1/auth/refresh/`) est dans `api` : l'application le fait toutes les 15 minutes par utilisateur, et beaucoup d'utilisateurs peuvent partager une adresse.
- **Préprod** (mode `proxy`) : nginx prend l'adresse du visiteur dans `X-Forwarded-For` envoyé par Caddy (`real_ip`), en ne faisant confiance qu'aux adresses privées du réseau Docker : en mode `proxy`, aucun port n'est publié, seul Caddy atteint nginx. Sans cela, tous les visiteurs partageraient un seul compteur. Django n'est pas concerné : il lit l'adresse dans `X-Forwarded-For` selon `DJANGO_NUM_PROXIES`.
- Le journal de nginx enregistre aussi `X-Kwaba-Client` et `X-Kwaba-Version` (site ou application, et sa version).

# Conséquences :
positives (bénéfices)
- Un robot qui martèle l'administration ou la connexion est arrêté par nginx, sans occuper l'API.
- Les limites de Django restent la vraie protection par compte (connexion, codes) ; nginx s'ajoute devant.

négatifs (inconvénients)
- Des adresses partagées très chargées pourraient atteindre `api` ; les valeurs se règlent dans `kwa-ba.conf.template`.
- Ces limites ne remplacent ni le second facteur ni les limites par compte.

Impacts futurs
- Si le trafic grandit, une liste d'adresses exemptées (partenaires, supervision) pourra s'ajouter avec une `map`.
