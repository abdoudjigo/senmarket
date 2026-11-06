# Partie A : vérifier le sol avant de construire

**L'idée :** un module sur les bases de données échoue rarement à cause du SQL. Il échoue parce que les données de départ sont bancales, ou qu'un outil n'est pas prêt. La partie A vérifie ça avant de construire.

## A1. Ce que le Module 0 nous a laissé

Au Module 0, nous avons fabriqué les données de SenMarket (une marketplace sénégalaise fictive), volontairement sales, puis nous les avons nettoyées. Il nous reste :
- un **pipeline** qui génère puis nettoie les données de bout en bout ;
- **8 tables propres en Parquet** (clients, vendeurs, produits, commandes, lignes_commande, paiements, avis, navigation), rangées par date ;
- des **clés primaires uniques** et **aucune clé étrangère orpheline** (pas de paiement qui pointe vers une commande inexistante) ;
- un dépôt **Git propre**, avec le `.env` (les mots de passe) ignoré.

Pourquoi c'est nécessaire : PostgreSQL refuse de charger une ligne dont le « parent » n'existe pas. Si nos Parquet étaient bancals, le chargement échouerait.

## A2. Les outils, en mots simples

| Outil | C'est quoi, simplement |
|---|---|
| **Docker** | Une boîte isolée qui contient un logiciel déjà installé et réglé. On n'installe pas PostgreSQL sur la machine : on lance sa boîte. |
| **Docker Compose** | Un fichier qui décrit plusieurs boîtes (PostgreSQL, MongoDB, Redis) et les démarre ensemble. |
| **psql, mongosh, redis-cli** | Les « télécommandes » de chaque base, déjà dans les boîtes. |
| **psycopg, pymongo, redis, duckdb** | Les bibliothèques Python qui pilotent chaque base depuis le code. |
| **python-dotenv** | Lit le fichier `.env` pour récupérer les mots de passe sans les écrire dans le code. |
| **venv** | Un environnement Python isolé : les bibliothèques du projet y vivent seules. |

## A3. Le contrat de données

Un contrat de données est la description exacte de ce que contiennent les tables : colonnes, types, clés, relations. Trois règles à retenir :
- **Granularité** : une ligne de `commandes` est une commande ; une ligne de `lignes_commande` est un produit dans une commande. Le panier = la somme de ses lignes.
- **Identifiants** : chaque entité a un identifiant texte stable (`CMD…`, `PRO…`). Un nom n'est jamais une clé (deux homonymes seraient fusionnés).
- **Prix** : le prix de catalogue est dans `produits`, le **prix payé** est dans `lignes_commande`. Le catalogue peut changer sans réécrire l'histoire. L'argent est un **entier en francs CFA**.

## A4. Le contrôle de pré-vol, concrètement

C'est une vérification avant le décollage : un script qui lit nos Parquet et contrôle trois choses.
1. Chaque clé primaire est **unique**.
2. Il n'y a **aucun orphelin** (chaque clé étrangère pointe vers un parent qui existe).
3. Le **paiement égale la somme des lignes** de sa commande : le pourcentage de commandes où c'est vrai est noté. S'il est inférieur à 100 %, ce n'est pas une erreur de notre part, c'est une découverte pour la finance.

Il vérifie aussi que `stock`, `commentaire` et `reference_transaction` n'existent pas encore : le Module 1 les crée lui-même.

## A5. La partition « volume »

Sur 10 000 lignes, PostgreSQL répond en quelques millisecondes avec ou sans index : les mesures ne prouvent rien. Il faut un jeu plus gros pour mesurer honnêtement, donc une deuxième partition de 200 000 lignes de commande.

Deux conséquences concrètes dans notre projet :
- les identifiants du générateur se répètent d'une partition à l'autre, donc **on ne les mélange jamais dans les mêmes tables** ;
- c'est pourquoi PostgreSQL contient **deux schémas séparés** : `principal` (petit jeu, pour comprendre) et `volume` (gros jeu, pour mesurer).
