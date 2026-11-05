# Architecture de SenMarket (Module 1)

## Le schéma

    Fichiers Parquet (Module 0)            Client / application
              |                                     |
              | chargement                          |
              v                                     v
    +---------------------+   commande    +--------------------+
    |     PostgreSQL      |<--------------|       Redis        |
    |  commandes, stock,  |   (cache-     |  panier, session,  |
    |  paiements, clients |    aside)     |  cache, classement |
    +---------------------+               +--------------------+
              ^
              | même identifiant : produit_id
              v
    +---------------------+      +----------------------------+
    |       MongoDB       |      | DuckDB : lit les Parquet   |
    |  fiches produit,    |      | directement, sans serveur, |
    |  avis               |      | pour analyser              |
    +---------------------+      +----------------------------+

## Une base = un métier

- **PostgreSQL** : la vérité sur l'argent. Une commande et son paiement réussissent ensemble ou pas du tout (transaction), et la base refuse les données absurdes (stock négatif, paiement sans commande).
- **MongoDB** : les fiches produit, qui n'ont pas toutes les mêmes champs, et les avis, qui s'accumulent.
- **Redis** : ce qui doit aller très vite et peut être perdu sans drame (panier, cache). Il redémarre vide : il n'est jamais la seule copie d'une donnée.
- **DuckDB** : l'analyste lit les fichiers sans serveur et sans toucher à la production.

## Ce qui les relie

`produit_id` est le même partout : c'est le lien entre la fiche (MongoDB), la ligne de commande (PostgreSQL) et le classement (Redis).

## Le parcours d'une commande

1. Le client remplit son panier : Redis.
2. Il valide : PostgreSQL décrémente le stock et enregistre commande et paiement dans une seule transaction.
3. Plus tard, il laisse un avis : MongoDB.
4. L'analyste calcule le chiffre d'affaires du mois : DuckDB sur les Parquet.
