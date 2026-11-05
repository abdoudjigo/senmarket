# Points à expliquer dans la documentation de l'enrichissement

- avis_commentaires : dépend seulement de la note ; ignore produit, client, commande ; phrases génériques
- paiements_references : une référence même si le statut est echoue ou en_attente ; vide pour Espèces ; libellés exacts de methode_paiement
- stock : stock courant inventé, indépendant des ventes ; trois produits flash en Électronique ; 5 ruptures
- catalogue : ni prix ni stock (une seule vérité) ; pas de champ origine en Alimentation ; vrais nombres
- partitions : identifiants répétés avec un autre sens (ex. vendeur_id des produits) : ne pas les mélanger
- reproductibilité : graine = 42 + date + un flux par fichier ; pas de datetime.now() ni hash()
- limites : règles de cohérence avis/commande héritées du module 0, non revérifiées
- question en suspens : plusieurs lignes vides dans une colonne UNIQUE (chapitre 2)
- modèle PostgreSQL : cardinalités de chaque relation (qui peut exister sans qui) ; ON DELETE ne règle que parent supprimé vers enfant, jamais l'inverse
- modèle PostgreSQL : le contrat du module 0 ne correspond pas aux données (statuts avec accents, 5 types d'événements) : les données font foi
- question 1 : une FK garantit qu'une ligne a une commande, pas qu'une commande a des lignes ; la transaction du chapitre 2.4 garantit l'ensemble
- question 2 : les lignes disent ce qui a été commandé, le paiement ce qui a été encaissé ; deux faits différents, pas une redondance
- chargement : TRUNCATE + COPY dans une transaction ; verrou exclusif pendant le chargement ; cree_le est recréé à chaque chargement (l'empreinte ignore les colonnes d'audit)
- chargement : vérification des comptes et des sommes AVANT le commit ; NULL vs chaîne vide pour les références ; fuseau UTC forcé
