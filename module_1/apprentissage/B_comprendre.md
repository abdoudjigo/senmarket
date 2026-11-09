# Partie B : comprendre pour devenir opérationnel (le résumé)

## Pourquoi une base de données et pas des fichiers ?
Un fichier ne sait pas refuser une donnée absurde, gérer deux écritures simultanées, ni retrouver une ligne sans tout relire. Une base le sait : contraintes, transactions, index. À l'inverse, un fichier Parquet est excellent pour analyser beaucoup de lignes en lecture seule : c'est le rôle de DuckDB.

## Les cinq familles, et leur rôle dans SenMarket
| Famille | Forme des données | Exemple SenMarket | Outil |
|---|---|---|---|
| Relationnelle | Tables liées par des clés | commandes, paiements, stock | PostgreSQL |
| Documents | JSON de forme variable | fiche produit, avis | MongoDB |
| Clé-valeur | Une clé, une valeur, en mémoire | panier, session, cache | Redis |
| Colonnes larges | Écritures massives | flux de clics | Cassandra (option) |
| Graphes | Nœuds et relations | « acheté ceci, aussi acheté… » | Neo4j (option) |

## PostgreSQL : les idées clés
- **Contraintes** : la base refuse l'incohérence (clé étrangère, `CHECK`, `UNIQUE`, `NOT NULL`).
- **Argent** : un entier (`BIGINT`), jamais un `FLOAT`.
- **Jointures** : `INNER JOIN` garde les paires qui correspondent ; `LEFT JOIN` garde toute la table de gauche. L'anti-jointure (`NOT EXISTS`) répond à « qui n'a pas… ».
- **Fonctions de fenêtre** : calculent sur un groupe sans réduire les lignes (`ROW_NUMBER`, `RANK`, `LAG`, `SUM() OVER`).
- **Index** : la table des matières d'un livre ; il accélère les lectures et ralentit un peu les écritures. `EXPLAIN` montre le chemin choisi.
- **Transaction** : « tout ou rien ». Une mise à jour atomique du stock évite de vendre deux fois le dernier article.

## MongoDB
Une fiche produit varie selon le produit (un téléphone a de la RAM, un sac de riz a un poids). On **embarque** ce qui se lit ensemble et reste petit, on **référence** ce qui grandit sans limite (les avis). Le validateur empêche le désordre.

## Redis
Tout est en mémoire : très rapide, mais il redémarre vide. Le TTL fait disparaître les clés tout seul. **Redis ne détient jamais la seule copie d'une donnée qu'on ne sait pas reconstruire.**

## DuckDB
Un moteur analytique **embarqué** : pas de serveur, il lit les fichiers Parquet tels quels. Il sert à explorer, pas à enregistrer des commandes.

## Le théorème CAP, sans jargon
Si le lien entre deux serveurs est coupé, on ne peut pas tout garder : soit on refuse la commande (cohérence), soit on l'accepte et on réconcilie plus tard (disponibilité). On choisit **par type de donnée** : le stock exige la cohérence, un panier tolère la disponibilité.

## La méthode de choix : quatre questions
1. Quelle **forme** ont les données ?
2. Quel **accès** veut-on (par clé, filtres, agrégations, parcours) ?
3. Quelle **cohérence** : une erreur coûte-t-elle de l'argent ?
4. Quelle **échelle et quelle panne** : que voit le client si cette base tombe ?

Règle d'or : chaque base ajoutée est une panne de plus à superviser. On n'en ajoute une que si on peut nommer ce que PostgreSQL ne ferait pas assez bien.