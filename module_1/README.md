# SenMarket — Module 1 : choisir ses bases de données

**But :** décider où vit chaque donnée de SenMarket, et le prouver.
**Les trois bases :** PostgreSQL (argent, stock) · MongoDB (catalogue, avis) · Redis (panier, cache).
Lis `docs/DECISIONS.md` en premier : c'est le résultat du module.

## Les 5 commandes (depuis `module_1/`, après le pipeline du module 0)

```bash
cp .env.example .env            # puis remplis les 3 mots de passe
pip install -r requirements.txt

# 1. Allumer les bases
docker compose --env-file .env -f infra/docker-compose.yml up -d

# 2. Charger SenMarket dans PostgreSQL (principal = petite partition, volume = grosse)
python scripts/1_charger.py --run-date 2026-10-29 --schema principal
python scripts/1_charger.py --run-date 2026-11-02 --schema volume

# 3. Prouver : double vente, plantage, index, MongoDB, Redis
python scripts/2_double_vente.py --produit PRO0025
python scripts/3_index.py --schema volume
python scripts/4_mongo_redis.py --run-date 2026-10-29
```

## Ce que chaque script prouve

| Script | Question | Preuve |
|---|---|---|
| `1_charger.py` | Les données sont-elles toutes là, sans doublon si on relance ? | Comptes et somme identiques au Parquet |
| `2_double_vente.py` | Que se passe-t-il quand deux clients veulent le dernier article ? | Naïve : doubles ventes. Transaction + mise à jour atomique : 0 |
| `3_index.py` | Un index sert-il vraiment ? | `Seq Scan` → `Index Scan`, plus un cas où l'index ne sert pas |
| `4_mongo_redis.py` | Pourquoi Mongo et Redis ? | Fiches de formes différentes, note refusée, panier qui expire, cache |

## Fichiers

```
infra/docker-compose.yml   les 3 bases
sql/01_schema.sql          les tables et leurs règles (PostgreSQL)
scripts/bases.py           connexions (mots de passe lus dans .env)
scripts/1_…4_….py          les 4 étapes
docs/DECISIONS.md          la fiche de décision
```
