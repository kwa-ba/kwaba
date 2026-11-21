# Titre:
Chauffeurs partenaires : photo de profil obligatoire, avis des voyageurs et niveaux d'excellence validés par l'équipe

# Status:
Accepté (19 novembre 2026).

# Contexte :
Les chauffeurs partenaires (transferts aéroport, locations avec chauffeur) sont enregistrés par l'équipe au back-office, et les courses leur sont attribuées à la main. Le statut « Excellence » donne 6 500 F par jour au lieu de 6 000. C'était une simple case cochée à la main, « revue chaque trimestre », sans aucun chiffre pour l'appuyer.

Aucune note des chauffeurs n'existait : les avis ne portent que sur les séjours. Le voyageur qui attend à l'aéroport recevait le nom et le téléphone de son chauffeur, mais pas sa photo.

Les associés veulent deux choses :
- une photo de profil dans la fiche du chauffeur ;
- un classement des chauffeurs selon leur excellence.

# Options
Option 1 : Un classement public des chauffeurs (n° 1, n° 2…). Il découragerait ceux du bas, pousserait à contester les notes et exposerait les chauffeurs.

Option 2 : Des niveaux qui changent seuls selon des seuils. Le niveau Excellence change la paie : une erreur de données ferait varier la paie d'un chauffeur sans qu'un humain l'ait vue.

Option 3 : Trois niveaux, Standard, Confirmé et Excellence.
- Chaque trimestre, l'appli les propose d'après des chiffres mesurés.
- L'équipe les valide ou les corrige, avec un motif.
- Les chiffres viennent de l'avis des voyageurs, à créer, et des incidents notés par l'équipe.

# Décision
Nous retenons l'option 3.

## Photo de profil
- **Obligatoire.** L'équipe l'ajoute sur la fiche du chauffeur. La photo est contrôlée (400 px au moins) et réencodée sans métadonnées. Elle est ensuite validée par une personne de l'équipe, qui vérifie un visage net, celui du chauffeur.
- **Sans photo validée, aucune course.** Le chauffeur n'est plus proposé à l'attribution des transferts ni des locations avec chauffeur, et l'attribution est refusée. Une nouvelle photo attend une nouvelle validation.
- **Ce que voit le voyageur.** Il voit la photo et le niveau une fois le chauffeur attribué :
  - pour un transfert : sur la page du transfert, et le niveau dans l'email d'attribution ;
  - pour une location : sur la page de la location. Le nom et le téléphone du chauffeur restent dans l'email.
- **Consentement.** Il se recueille à l'enregistrement du chauffeur (loi togolaise n° 2019-014 sur les données personnelles).

## Avis des voyageurs
- **Demande.** Après chaque course (transfert effectué, location avec chauffeur terminée), un email demande une fois son avis au voyageur. Il note de 1 à 5 :
  - la note générale ;
  - la ponctualité ;
  - la conduite ;
  - l'amabilité.

  Il peut ajouter un commentaire.
- **Un avis par course**, donné par le voyageur de la course, et vu par l'équipe seulement (`transferts_avis_chauffeur`).

## Incidents
L'équipe enregistre un incident grave, un retard ou une absence sur la fiche du chauffeur (`transferts_incident_chauffeur`).

## Niveaux
- **Calcul.** Chaque trimestre, l'appli calcule un niveau d'après les 3 derniers mois : les courses (transferts et locations), la note moyenne et les incidents.

  | Niveau | Conditions |
  | --- | --- |
  | Confirmé | 15 courses et une note d'au moins 4,3 |
  | Excellence | 40 courses, une note d'au moins 4,7, ni retard ni absence |

  - Un incident grave fait descendre d'un niveau.
  - Un chauffeur sans aucun avis reste Standard.
- **Seuils.** Ce sont des paramètres du référentiel (Finance → Paramètres, ADR-026), modifiables avec leur historique.
- **Validation par l'équipe.** L'équipe valide le niveau proposé, ou en garde un autre en écrivant son motif. L'historique garde l'avant, l'après, la proposition, le motif et les chiffres (`transferts_niveau_chauffeur`).
- **Paie.** Le niveau Excellence donne la part de 6 500 F par jour, et le champ `excellence` le suit. La paie d'un chauffeur ne change donc jamais sans qu'une personne l'ait vue. Le niveau ne se modifie plus depuis la fiche.
- **Rappel.** Au début de chaque trimestre, l'équipe reçoit un rappel si aucun niveau n'a encore été validé.

# Conséquences :
positives (bénéfices)
- **Le voyageur** reconnaît son chauffeur à l'aéroport et sait son niveau.
- **Le niveau Excellence** repose sur des chiffres, et chaque changement est motivé et tracé.
- **Les meilleurs chauffeurs** apparaissent en premier à l'attribution des locations et sont mieux payés. Les autres savent ce qui leur manque.

négatifs (inconvénients)
- **Le jour du déploiement**, aucun chauffeur existant n'a de photo : aucun ne peut recevoir de course avant que l'équipe ait ajouté et validé leurs photos.
- **La revue trimestrielle** reste un travail de l'équipe.
- **La ponctualité** ne se mesure que par les avis et les incidents signalés, car aucun espace chauffeur ne confirme encore la prise en charge.

Impacts futurs
- **Espace chauffeur :** il permettra d'accepter une course et de confirmer la prise en charge, donc de mesurer la ponctualité réelle.
- **Badge public de niveau :** il pourrait figurer sur l'offre de transfert, si les associés le souhaitent.
- **Liens avec les autres ADR :** s'appuie sur l'ADR-026 pour les paramètres et l'ADR-025 pour le journal d'activité. Le détail est dans `documentation/modules/transferts.md`.
