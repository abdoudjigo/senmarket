# Décisions du Module 1 : où vit chaque donnée de SenMarket

## 1. Matrice de placement

| Donnée | Base | Pourquoi | Alternative rejetée | Si la base tombe |
|---|---|---|---|---|
| Clients, commandes, lignes, paiements | PostgreSQL | Argent : cohérence stricte, clés étrangères, transactions | Fichiers : aucune protection contre l'incohérence | On ne peut plus vendre (arrêt total) |
| Stock | PostgreSQL | Une erreur coûte de l'argent : mise à jour atomique dans la transaction de commande | Redis : redémarre vide, jamais la seule copie | Idem : plus de vente |
| Fiche produit | MongoDB | Un téléphone et un sac de riz n'ont pas les mêmes attributs (20 produits sur 40 n'ont pas `poids_kg`) | Tableau relationnel : colonnes vides | Catalogue indisponible, les commandes en cours restent possibles |
| Avis | MongoDB | Nombreux, croissants, rattachés à un produit | Dans la fiche produit : document qui grossit sans limite | Plus d'affichage des avis, rien de critique |
| Panier, session | Redis | Petit objet à durée de vie limitée, lecture très rapide (TTL) | PostgreSQL : trop lent pour chaque clic | Paniers perdus : le client les refait |
| Top produits (cache) | Redis | Évite d'interroger PostgreSQL à chaque affichage | Pas de cache : PostgreSQL s'effondre au Black Friday | Plus lent, mais tout fonctionne : on retombe sur PostgreSQL |
| Analyses sur gros volumes | DuckDB sur Parquet | Exploration sans serveur, sans toucher à la production | Requêtes sur PostgreSQL de production | Aucun impact sur les clients |

## 2. Trois mesures de mon travail

- **Index** (PostgreSQL, 199 997 lignes) : Seq Scan 32,2 ms → Bitmap Index Scan 1,9 ms, soit environ x17.
- **Cache Redis** : top produits en 52,9 ms depuis PostgreSQL contre 6,2 ms depuis Redis.
- **Double vente** : A_COMPLETER (chiffre de mon MESURES.md) avant la transaction, 0 après.

## 3. Cohérence ou disponibilité pendant une coupure réseau

- Stock : cohérence. Mieux vaut refuser une commande que vendre deux fois le dernier article.
- Panier : disponibilité. Une copie un peu en retard n'a aucune conséquence grave.
- Avis : disponibilité. Un avis qui arrive plus tard n'est pas un problème.

## 4. Pannes

- Redis tombe : tout continue, en plus lent (retour sur PostgreSQL) ; les paniers sont perdus.
- MongoDB tombe : plus de fiches ni d'avis, mais on peut encore enregistrer des commandes.
- PostgreSQL tombe : plus aucune commande ni paiement. C'est la base la plus critique.

## 5. Pourquoi ne pas tout mettre dans PostgreSQL ?

On pourrait (il a JSONB et peut servir de cache), et ajouter une base coûte une panne de plus à superviser. Ici je garde MongoDB pour la forme variable des fiches et Redis pour la vitesse des paniers. DuckDB n'est pas un gain de vitesse sur 200 000 lignes (189 ms contre 85 ms, une seule mesure à froid) : il sert à explorer les fichiers sans serveur.

## 6. Ma réponse initiale sur le stock

Stock dans PostgreSQL, car il touche à l'argent. Je n'ai pas changé d'avis : Redis redémarre vide et ne doit jamais détenir la seule copie.
