# Chapitre 6 : le conseil d'architecture (ticket SM-200)

> **Awa** : « Dis-moi simplement : où met-on quoi, pourquoi, et qu'est-ce qui se passe si un serveur tombe ? »

## Le schéma

    Fichiers Parquet (Module 0)            Application / client
              |                                     |
              | chargement                          |
              v                                     v
    +---------------------+   cache-aside  +--------------------+
    |     PostgreSQL      |<---------------|       Redis        |
    |  commandes, stock,  |                |  panier, session,  |
    |  paiements, clients |                |  cache, classement |
    +---------------------+                +--------------------+
              ^
              | même identifiant : produit_id
              v
    +---------------------+      +----------------------------+
    |       MongoDB       |      | DuckDB : lit les Parquet,  |
    |  fiches produit,    |      | sans serveur, en lecture   |
    |  avis               |      +----------------------------+
    +---------------------+

## Où vit chaque donnée

| Donnée | Base | Pourquoi | Si la base tombe |
|---|---|---|---|
| Clients, commandes, paiements | PostgreSQL | Argent : contraintes et transactions (ch2a) | Plus aucune vente |
| Stock | PostgreSQL | Mise à jour conditionnelle + verrou de ligne : une seule vente du dernier article (ch2a) | Idem |
| Fiche produit | MongoDB | Formes d'attributs différentes selon la catégorie (ch3) | Catalogue indisponible, les ventes en cours continuent |
| Avis | MongoDB | Nombreux, croissants, dans leur propre collection | Plus d'affichage des avis, rien de critique |
| Panier, session | Redis | Rapide, expire tout seul (ch4) | Paniers perdus, le client les refait |
| Top produits | Redis (cache) | Évite d'interroger PostgreSQL à chaque affichage | Plus lent, mais tout fonctionne |
| Analyses | DuckDB sur Parquet | Exploration sans serveur ni accès à la production (ch5) | Aucun impact client |

## Les preuves (elles sont dans les notebooks)
- **Contraintes** : clé étrangère, CHECK, NOT NULL et UNIQUE ont refusé une donnée absurde (ch2a).
- **Concurrence** : le second acheteur attend, puis son `UPDATE` ne touche aucune ligne (ch2a).
- **Index** : balayage complet remplacé par un index, avec temps médians (ch2a).
- **Cache** : 1er appel via PostgreSQL, suivants via Redis (ch4).
- **Validateur MongoDB** : une note de 9 est refusée (ch3).
- **Même résultat** dans PostgreSQL et DuckDB, par empreinte (ch5).

## Cohérence ou disponibilité pendant une coupure réseau
- **Stock** : cohérence. Mieux vaut refuser une commande que vendre deux fois le dernier article.
- **Panier** : disponibilité. Une copie un peu en retard est sans gravité.
- **Avis** : disponibilité. Un avis qui arrive plus tard n'est pas un problème.

## Pourquoi ne pas tout mettre dans PostgreSQL ?
On pourrait : il a `JSONB` et peut servir de cache. Ajouter une base, c'est une panne de plus à superviser et à sauvegarder. On garde MongoDB pour la forme variable des fiches et le validateur, Redis pour la vitesse des paniers, DuckDB pour explorer sans toucher à la production. Sur 200 000 lignes, DuckDB n'est pas forcément plus rapide : les mesures de `ch5` font foi.

## Ma réponse initiale sur le stock
Le stock vit dans PostgreSQL parce qu'il touche à l'argent. Je n'ai pas changé d'avis : Redis redémarre vide (ch4) et ne doit jamais être la seule copie d'une donnée.
