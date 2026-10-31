# Décisions de conception (Module 0)

Pour chaque choix : ce qu'on a retenu, l'alternative rejetée et pourquoi. Les définitions complètes sont dans `CONTRAT_DONNEES.md`.

| Décision | Retenu | Alternative rejetée | Pourquoi |
|---|---|---|---|
| Granularité | Deux tables : `commandes` (un ticket) et `lignes_commande` (un produit dans un ticket) | Une seule table plate, une ligne par produit | Une table plate répète la commande sur chaque ligne et fausse le panier moyen. Avec deux tables, on somme par `commande_id` avant de moyenner. |
| Identifiants | Texte préfixé (`CMD0000001`) | Noms ou numéros nus | Deux clients homonymes seraient fusionnés ; un préfixe permet de reconnaître l'entité d'un coup d'œil. |
| Argent | XOF en entier | Décimal ou flottant | Le franc CFA n'a pas de centimes ; un flottant accumule des erreurs d'arrondi. |
| Prix | Prix payé dans `lignes_commande`, prix catalogue dans `produits` | Un seul prix, lu dans le catalogue | Le catalogue change : le prix payé doit rester figé pour ne pas réécrire l'historique. |
| Cohérence produit/catégorie | Catalogue de référence `{catégorie: [produits]}` + un test | Tirer nom et catégorie au hasard, séparément | Sinon on obtient « sucre » dans « vêtements ». La construction empêche l'erreur, le test détecte une régression. *(Appliqué dans `generateur.py`, vérifié par `test_generateur.py`.)* |
| Définition du CA | « CA commandé » comme référence, avec « CA réalisé » et « CA encaissé » nommés à côté | Un seul « CA » sans qualificatif | Une commande annulée est comptée dans le CA commandé : ce n'est pas de l'argent encaissé. On nomme l'écart au lieu de le cacher (il sert au Module 1). |
| Statuts | Statut de commande dans `commandes`, statut de paiement dans `paiements` | Un statut unique | Une commande peut être livrée avec un paiement en attente : ce sont deux états différents. |
| Format de sortie | CSV pour lire à l'œil, Parquet pour garder les types, JSON Lines pour l'ingestion | Un seul format | Chaque format a un usage. *(Compléter avec tes mesures de temps et de taille sur 200 000 lignes avant de défendre ce choix.)* |
| Clé dupliquée | Toutes les occurrences rejetées | Garder la première | Si les contenus diffèrent, aucune règle ne permet de choisir laquelle est la bonne. (Une copie *identique* est écartée, la première est gardée.) |
| Ville manquante | Client conservé avec « Inconnue » | Supprimer le client | Supprimer un client ferait disparaître ses commandes en aval et fausserait le CA. |
| Écriture des sorties | Tout calculer en mémoire, vérifier, puis écrire | Écrire au fil de l'eau | Un échec en cours de route ne doit laisser aucune sortie à moitié écrite. |
