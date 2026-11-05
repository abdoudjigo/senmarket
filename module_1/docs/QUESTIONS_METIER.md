# Questions métier : une par base

Données : partition principale (4 084 commandes). Script : scripts/questions_metier.py

## PostgreSQL : où gagne-t-on notre argent ?
**Question :** quel est le chiffre d'affaires par région ?
**Réponse :** Dakar fait environ 40 % du total (65,1 M sur 163,0 M XOF), Dakar et Thiès ensemble près de 60 %. Kédougou est la plus faible (0,4 M).
**Pourquoi PostgreSQL :** il faut relier trois tables (lignes, commandes, clients), et le total doit être exact.
**Preuve :** la somme des 14 régions égale le total des lignes de commande (invariant vérifié).
**À retenir :** on ne somme jamais un montant après une jointure sans vérifier le total avant et après.

## PostgreSQL : quelles commandes n'ont aucun paiement réussi ?
**Réponse :**  543 commandes sur 4084 (13.3%)
**Pourquoi PostgreSQL :** une anti-jointure (NOT EXISTS) cherche ce qui manque, ce qu'un fichier ne peut pas faire.
**Piège rencontré :** le premier essai donnait 100 %, ce qui est impossible. Le statut s'écrit réussi avec un accent : il faut lire les valeurs réelles d'une colonne avant de filtrer dessus.
**À retenir :** un résultat qui paraît trop extrême est un bug jusqu'à preuve du contraire.

## Redis : quels sont les produits les plus consultés ?
**Réponse :** PRO0019 (120 vues), PRO0033 (119), PRO0013 (116), PRO0018 (113), PRO0002 (111).
**Pourquoi Redis :** un Sorted Set tient un classement à jour à chaque vue, très vite, avec un incrément atomique (ZINCRBY). Il expire seul au bout de 7 jours.
**Preuve :** le classement est identique à celui calculé par DuckDB sur les mêmes événements, égalités comprises.
**À retenir :** Redis départage les égalités à l'envers (ordre alphabétique inversé). Il faut le savoir pour comparer deux classements.

## MongoDB : que disent les clients du produit le plus commenté ?
**Réponse :** PRO0003, 60 avis, répartis presque également entre les notes 1 à 5 (12, 13, 11, 12, 12).
**Pourquoi MongoDB :** les avis sont nombreux et s'accumulent dans leur propre collection, sans réécrire la fiche produit. Le validateur refuse les notes hors de 1 à 5.
**À retenir :** une répartition aussi plate n'est pas réaliste : les données sont synthétiques, les notes ont été tirées au hasard.

## DuckDB : comment évolue le chiffre d'affaires mois par mois ?
**Réponse :** une forte croissance, de 0,15 M en novembre 2024 à 29,0 M en octobre 2026.
**Pourquoi DuckDB :** il lit directement les fichiers Parquet, sans serveur et sans toucher à la base de production. C'est l'outil de l'analyste.
**À retenir :** il sert à explorer et à analyser, pas à enregistrer des commandes (un seul écrivain à la fois).
