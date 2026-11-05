

# Fiche de décision — Module 1 : où vit chaque donnée de SenMarket ?

## Objectif

Choisir une base de données adaptée à chaque type de donnée de SenMarket, puis justifier ces choix par des expériences reproductibles.

Pour chaque donnée, quatre questions guident la décision :

- Quelle est sa forme ?
- Comment y accède-t-on ?
- Quel niveau de cohérence exige-t-elle ?
- Que se passe-t-il si la base devient indisponible ?

## 1. Décisions d’architecture

| Donnée | Base retenue | Justification | Alternative écartée | Comportement en cas de panne |
|---|---|---|---|---|
| Clients et vendeurs | PostgreSQL | Données structurées, contraintes et relations avec les commandes | MongoDB, moins adapté aux relations transactionnelles nécessaires ici | La prise de commande est indisponible |
| Commandes, lignes et paiements | PostgreSQL | Les opérations doivent être atomiques et préserver l’intégrité référentielle | Fichiers, qui ne fournissent pas les mêmes garanties transactionnelles | Le paiement est interrompu plutôt que de risquer une incohérence |
| Stock | PostgreSQL | Une erreur de concurrence peut vendre un article qui n’est plus disponible | Redis, dont la persistance et les garanties doivent être configurées et vérifiées | Les ventes sont refusées si le stock ne peut pas être vérifié |
| Fiches produits | MongoDB | Les attributs varient selon les catégories | Une table relationnelle comportant de nombreuses colonnes peu utilisées | Une fiche minimale peut être affichée depuis PostgreSQL ; le prix reste dans PostgreSQL |
| Avis | MongoDB | Les avis sont des documents autonomes, nombreux et consultés par produit | Les intégrer directement à la fiche produit, qui deviendrait volumineuse | Les avis peuvent être temporairement indisponibles sans bloquer les commandes |
| Panier et session | Redis | Accès rapide et expiration automatique avec TTL | PostgreSQL, moins adapté à ce type d’accès temporaire fréquent | Le panier peut être perdu et recréé par le client |
| Cache des produits populaires | Redis | Évite de recalculer ou relire les mêmes données à chaque affichage | Recalculer à chaque requête | Les pages peuvent ralentir, mais les données principales restent disponibles |

**Règle de conception :** chaque base supplémentaire apporte une capacité utile, mais aussi une panne et une dépendance supplémentaires. On ne l’ajoute que si son bénéfice justifie cette complexité.

## 2. Preuves expérimentales

### 2.1 Chargement PostgreSQL

Les données du Parquet ont été chargées dans deux schémas : `principal` et `volume`.

| Indicateur | `principal` | `volume` |
|---|---:|---:|
| Clients | 3 333 | 50 000 |
| Commandes | 4 084 | 80 876 |
| Lignes de commande | 9 995 | 199 997 |
| Paiements | 4 002 | 79 264 |
| Somme des montants | 163 011 763 XOF | 3 130 055 446 XOF |
| Durée du chargement | 0,6 s | 8,5 s |

**Observation :** les comptes affichés par PostgreSQL correspondent aux comptes du Parquet. La somme des montants est également identique pour chaque chargement.

**Conclusion :** le chargement est cohérent pour les indicateurs vérifiés. Ces résultats ne constituent pas, à eux seuls, une preuve de validation de chaque colonne ou de chaque règle métier.

### 2.2 Concurrence et double vente

Le test simule deux acheteurs qui tentent d’acheter le dernier exemplaire du produit `PRO0025`.

| Scénario | Doubles ventes sur 200 essais | Refus |
|---|---:|---:|
| Version naïve | 200 | 0 |
| Version sûre | 0 | 200 |

Un second test simule un plantage entre la création de la commande et le paiement.

| Scénario | Commandes sans paiement sur 50 essais | Stock débité sans paiement |
|---|---:|---:|
| Version naïve | 50 | 50 |
| Version sûre | 0 | 0 |

**Conclusion :** les résultats démontrent, dans les scénarios testés, le risque d’une mise à jour du stock non protégée contre la concurrence et d’une opération répartie sans gestion transactionnelle adéquate.

La version sûre évite les doubles ventes et les commandes sans paiement dans ces essais. La documentation doit décrire précisément les mécanismes utilisés par le script : transaction, verrouillage ou mise à jour atomique.

### 2.3 Index PostgreSQL

Le test porte sur une table de **199 997 lignes** et une recherche retournant **11 450 lignes** pour le produit `PRO0001`.

| Situation | Plan observé | Temps médian |
|---|---|---:|
| Avant index | `Seq Scan` | 21,60 ms |
| Après index sur `produit_id` | `Bitmap Heap Scan` + `Bitmap Index Scan` | 6,91 ms |
| Index présent, filtre avec `lower(produit_id)` | `Seq Scan` | 46,53 ms |

**Gain mesuré :** environ **×3,1** entre le premier et le deuxième scénario.

**Conclusion :** un index peut réduire le coût d’une recherche, mais sa présence ne garantit pas son utilisation. La transformation de la colonne avec `lower()` empêche ici l’utilisation de l’index ordinaire dans le plan observé.

### 2.4 MongoDB

Le script charge **40 produits et 999 avis**.

Les fiches produits illustrent la flexibilité du modèle documentaire :

- Téléphone : `specs.ram_go`, `specs.stockage_go`, `couleurs`, `garantie_mois`
- Riz brisé : `poids_kg`, `origine`

Le validateur refuse un avis ayant une note de **9**.

**Conclusion :** MongoDB permet de représenter des fiches dont les attributs varient selon la catégorie, tout en appliquant une validation aux avis.

### 2.5 Redis

#### Expiration du panier

Le panier de test expire après **2 secondes**. Trois secondes plus tard, il est vide.

**Conclusion :** le TTL permet de gérer automatiquement la durée de vie des données temporaires.

#### Cache devant PostgreSQL

| Appel | Source | Temps mesuré |
|---|---|---:|
| 1 | PostgreSQL | 6,77 ms |
| 2 | Redis | 0,33 ms |

Le second appel est environ **20,5 fois plus rapide** dans cette mesure.

**Limite :** il s’agit d’un résultat obtenu dans l’environnement du TP. Il ne représente pas une garantie générale de performance ni un benchmark complet.

## 3. Choix en cas de coupure réseau

| Donnée | Priorité | Décision |
|---|---|---|
| Stock | Cohérence | Refuser la vente si le stock ne peut pas être vérifié |
| Panier | Disponibilité | Autoriser l’usage du panier lorsque cela est possible |
| Avis | Disponibilité | Tolérer une indisponibilité ou un retard temporaire |

Cette décision reflète une différence de risque métier : une incohérence de stock peut entraîner une vente impossible à honorer, tandis qu’un panier ou un avis peut généralement être récupéré ou affiché ultérieurement.

## 4. Pourquoi ne pas tout mettre dans PostgreSQL ?

PostgreSQL peut également stocker du JSON et prendre en charge des stratégies de cache. Le choix de MongoDB et Redis repose donc sur des besoins précis, et non sur l’idée qu’une base serait systématiquement meilleure qu’une autre.

1. **MongoDB :** les fiches produits ont des attributs variables selon leur catégorie.
2. **Redis :** le panier et le cache nécessitent des accès rapides et, pour le panier, une expiration automatique.

Les mesures du TP montrent un bénéfice dans l’environnement testé. Si ce bénéfice devenait insuffisant au regard de la complexité opérationnelle, une architecture plus simple devrait être envisagée.

## 5. Réponse à la question initiale : où vit le stock ?

**Décision finale :** le stock vit dans PostgreSQL.

La raison principale est la cohérence : plusieurs clients peuvent tenter d’acheter simultanément le dernier exemplaire. Le test a montré que la version naïve produisait des doubles ventes dans les 200 essais, tandis que la version sûre n’en produisait aucune.

Le choix est donc fondé sur une exigence métier : **mieux vaut refuser temporairement une vente que confirmer une vente impossible à honorer.**

