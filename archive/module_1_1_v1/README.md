

# SenMarket — Module 1 : choisir ses bases de données

## Objectif

Décider où vit chaque donnée de SenMarket et justifier les choix par des expériences reproductibles.

**Les trois bases retenues :**

- **PostgreSQL** — clients, vendeurs, commandes, paiements et stock.
- **MongoDB** — fiches produits aux caractéristiques variables et avis.
- **Redis** — paniers, sessions et cache temporaire.

La fiche de décision présente les choix métier. L’étude technique détaille les expériences et leurs résultats.

## Documentation

| Document | Contenu |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Choix des bases, justifications et comportement en cas de panne |
| [`docs/TECHNICAL_STUDY.md`](docs/TECHNICAL_STUDY.md) | Architecture, protocole des tests, résultats, interprétations et limites |

## Démarrage rapide

Les commandes suivantes sont à exécuter depuis `module_1/`, après le pipeline du Module 0.

### 1. Préparer l’environnement

```bash
cp .env.example .env
```

Renseigner les trois mots de passe dans `.env`, puis installer les dépendances :

```bash
pip install -r requirements.txt
```

> Ne jamais publier le fichier `.env` : il contient des secrets.

### 2. Démarrer les bases de données

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d
```

### 3. Charger les données SenMarket dans PostgreSQL

Le schéma `principal` utilise le jeu de données réduit ; `volume` utilise le jeu plus important.

```bash
python scripts/1_charger.py --run-date 2026-10-29 --schema principal
python scripts/1_charger.py --run-date 2026-11-02 --schema volume
```

### 4. Exécuter les expériences

```bash
# Concurrence : deux clients tentent d'acheter le dernier exemplaire
python scripts/2_double_vente.py --produit PRO0025

# Index : comparer les plans et les temps d'exécution
python scripts/3_index.py --schema volume

# MongoDB : documents et validation des avis
# Redis : expiration du panier et cache
python scripts/4_mongo_redis.py --run-date 2026-10-29
```

## Ce que les expériences vérifient

| Script | Question | Preuve recherchée |
|---|---|---|
| `1_charger.py` | Les données sont-elles chargées sans doublons lors d’une relance ? | Comptes et somme des montants comparés au Parquet |
| `2_double_vente.py` | Que se passe-t-il lorsque deux clients veulent le dernier article ? | Comparaison entre une approche naïve et une approche sûre |
| `3_index.py` | Un index améliore-t-il réellement une recherche ? | Plans d’exécution et temps mesurés, avec un contre-exemple |
| `4_mongo_redis.py` | Quels besoins justifient MongoDB et Redis ? | Documents flexibles, validation des avis, expiration du panier et cache |

## Résultats principaux

Les expériences réalisées ont montré que :

- Les comptes chargés dans PostgreSQL correspondent aux comptes du Parquet, et les sommes des montants sont identiques.
- Le scénario naïf produit des doubles ventes dans les essais de concurrence ; la version sûre n’en produit aucune.
- La version sûre évite les commandes sans paiement et les débits de stock sans paiement dans le scénario de plantage testé.
- L’index réduit le temps médian de la recherche testée d’environ **21,60 ms à 6,91 ms**, soit un gain mesuré d’environ **×3,1**.
- MongoDB représente des fiches produits dont les attributs varient selon la catégorie et refuse une note d’avis invalide.
- Redis expire automatiquement le panier de test et répond plus rapidement que PostgreSQL lors du second appel au cache dans l’expérience réalisée.

Les protocoles, chiffres détaillés et limites sont présentés dans [`docs/TECHNICAL_STUDY.md`](docs/TECHNICAL_STUDY.md).

## Structure du projet

```text
infra/docker-compose.yml   Configuration des trois bases
sql/01_schema.sql          Tables et contraintes PostgreSQL
scripts/bases.py            Connexions aux bases, secrets lus depuis .env
scripts/1_charger.py        Chargement des données
scripts/2_double_vente.py   Expériences de concurrence et de plantage
scripts/3_index.py          Expérience sur les index
scripts/4_mongo_redis.py    Expériences MongoDB et Redis
docs/DECISIONS.md           Fiche de décision
docs/TECHNICAL_STUDY.md     Étude technique et résultats
```

