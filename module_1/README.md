# SenMarket, Module 1 : choisir ses bases de données

SenMarket est une marketplace sénégalaise fictive. Elle prépare son premier Black Friday (27 novembre) et ses données vivent encore dans des fichiers. Ce module décide **où vit chaque donnée** et le **prouve avec des mesures** faites sur nos propres données.

Quatre outils sont mis en place :

| Outil | Rôle dans SenMarket |
|---|---|
| **PostgreSQL** | Les données qui coûtent de l'argent si elles sont fausses : clients, commandes, paiements, stock |
| **MongoDB** | Le catalogue (fiches de forme variable) et les avis qui grossissent |
| **Redis** | Le panier, le cache et le classement : rapide, reconstructible, jamais la seule copie |
| **DuckDB** | Les analyses directement sur les fichiers Parquet, sans serveur et sans toucher à la production |

Cassandra et Neo4j sont déclarés dans le `docker-compose` comme options (profils), mais ne sont pas utilisés ici.

> Ce module s'appuie sur le [Module 0](../module_0/projet) (générateur, nettoyage, Parquet). Les fichiers du Module 0 sont accessibles ici par le lien symbolique `data/`, qui pointe vers `../module_0/projet/data`.

---

## 1. Démarrage rapide

### Prérequis
- Docker avec Docker Compose v2 (`docker compose version`)
- Python 3.11 ou plus, dans un environnement virtuel actif. Le parcours recommande Python 3.12 : en 3.14, l'installation de `psycopg[binary]` peut échouer faute de paquets précompilés.
- Les partitions du Module 0 **2026-10-29** (principale) et **2026-11-02** (volume, 200 000 lignes de commande) déjà nettoyées dans `data/processed/`

### Installation

```bash
cd module_1
cp .env.example .env        # puis ouvrir .env et choisir de vrais mots de passe
pip install -e .            # installe le package senmarket_bases
```

Le fichier `.env` est ignoré par Git : il ne doit **jamais** être commité. Seul `.env.example` (sans mot de passe) est versionné.

### Tout lancer

```bash
./demarrer.sh
```

Le script est **rejouable sans risque**. Il fait, dans l'ordre :
1. démarre PostgreSQL, MongoDB et Redis avec Docker Compose, puis attend que les trois soient `healthy` (jusqu'à environ 2 minutes) ;
2. crée les schémas PostgreSQL `principal` et `volume` s'ils n'existent pas, avec [`sql/01_schema.sql`](sql/01_schema.sql) ;
3. charge la partition 2026-10-29 dans `principal` et la partition 2026-11-02 dans `volume` ;
4. charge le catalogue et les avis de la partition 2026-10-29 dans MongoDB.

Les fichiers enrichis lus par le chargeur doivent exister dans [`bases_enriched/`](bases_enriched). Ils y sont déjà pour les deux dates. Pour les régénérer :

```bash
python -m senmarket_bases.enrichissement --run-date 2026-10-29
python -m senmarket_bases.enrichissement --run-date 2026-11-02
```

### Vérifier

```bash
docker compose --env-file .env -f infra/docker-compose.yml ps   # trois services "healthy"
python -m pytest -q                                             # nécessite les bases démarrées
```

### Repartir de zéro

```bash
docker compose --env-file .env -f infra/docker-compose.yml down -v   # EFFACE toutes les données
./demarrer.sh                                                         # reconstruit tout
```

`down` seul arrête les conteneurs et **garde** les données. `down -v` supprime aussi les volumes : à n'utiliser que si on veut tout effacer.

---

## 2. Le plan du dépôt

```
module_1/
├── README.md                    ce fichier
├── demarrer.sh                  démarre les bases, crée les schémas, charge tout
├── pyproject.toml               définition du package et réglage de pytest
├── .env.example                 modèle de configuration (versionné)
├── .env                         mots de passe réels (jamais versionné)
├── infra/docker-compose.yml     les services de bases
├── sql/                         schéma et questions métier
├── src/senmarket_bases/         le code Python
├── tests/                       les tests pytest
├── bases_enriched/              données ajoutées par ce module (par date)
├── apprentissage/               parcours pédagogique : notes et notebooks
└── data -> ../module_0/projet/data    données du Module 0 (lien symbolique)
```

### Les fichiers racine

| Fichier | Rôle |
|---|---|
| [`demarrer.sh`](demarrer.sh) | Script unique de mise en route (voir section 1). Écrit avec `set -euo pipefail` : il s'arrête à la première erreur. |
| [`pyproject.toml`](pyproject.toml) | Déclare le package `senmarket-bases` (dossier `src/`) pour que `import senmarket_bases` marche partout. Configure aussi pytest (`testpaths = tests`, `pythonpath = src`). |
| [`.env.example`](.env.example) | Variables attendues : `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `MONGO_USER`, `MONGO_PASSWORD`, `REDIS_PASSWORD`, `NEO4J_PASSWORD`. |

### L'infrastructure : [`infra/docker-compose.yml`](infra/docker-compose.yml)

Trois services démarrent par défaut, chacun avec un `healthcheck` :

| Service | Image | Port (local uniquement) | Particularité |
|---|---|---|---|
| `postgres` | postgres:16 | 127.0.0.1:5432 | Volume `pg_data` |
| `mongo` | mongo:7 | 127.0.0.1:27017 | Volume `mongo_data` |
| `redis` | redis:7 | 127.0.0.1:6379 | **Sans persistance**, mémoire limitée à 256 Mo, politique `volatile-lru` : seules les clés qui ont un TTL peuvent être évincées |

Les ports sont publiés sur `127.0.0.1` : personne d'autre sur le réseau ne peut s'y connecter. Les services `cassandra` et `neo4j` ne démarrent qu'avec leur profil (`--profile cassandra`, `--profile neo4j`).

### Le SQL : [`sql/`](sql)

| Fichier | Rôle |
|---|---|
| [`01_schema.sql`](sql/01_schema.sql) | Crée les **huit tables** (clients, vendeurs, produits, commandes, lignes_commande, paiements, avis, navigation) avec clés primaires, clés étrangères, contraintes (`CHECK`, `UNIQUE`, `NOT NULL`) et colonnes d'audit. Le nom du schéma est un paramètre (`-v schema=principal`). Tout s'exécute dans **une transaction** : en cas d'erreur, rien n'est créé à moitié. Il refuse d'écraser un schéma existant. Les clés étrangères ne sont **pas indexées exprès**, pour que les mesures « avant/après index » partent d'un état honnête. |
| [`10_questions.sql`](sql/10_questions.sql) | Les huit questions métier d'Awa (SM-120 à SM-127), une requête par question, commentées : CA par région, top produits par catégorie, évolution mensuelle, panier moyen, délai avant la deuxième commande, commandes sans paiement réussi, concentration du CA, sessions avec panier sans paiement. Lu par le notebook `ch2b`. |

### Le code : [`src/senmarket_bases/`](src/senmarket_bases)

| Fichier | Ce qu'il fait |
|---|---|
| [`connexions.py`](src/senmarket_bases/connexions.py) | Fournit trois fonctions (`connexion_postgres`, `client_mongo`, `client_redis`) qui lisent le `.env`. Aucun identifiant n'est écrit dans le code. En cas de problème, elles lèvent `ErreurConnexion` avec un message clair (quel service, quelle cause probable). |
| [`enrichissement.py`](src/senmarket_bases/enrichissement.py) | Ajoute ce qui manquait aux données du Module 0 : **stock** par produit, **catalogue** JSON, **commentaires** d'avis et **références de transaction** Wave/Orange Money. Il est reproductible : la graine dérive de la date, donc deux exécutions donnent des fichiers identiques. |
| [`catalogue_donnees.py`](src/senmarket_bases/catalogue_donnees.py) | Les attributs de chaque produit, écrits à la main (poids en kg, volumes en litres, vrais nombres). Aucun prix ni stock : ils changent et vivent uniquement dans PostgreSQL, pour n'avoir qu'une seule vérité. |
| [`charger_postgres.py`](src/senmarket_bases/charger_postgres.py) | Charge une partition dans PostgreSQL avec quatre garanties : **rapide** (`COPY`), **idempotent** (vider les huit tables puis recharger), **atomique** (une seule transaction), **vérifié** (comptes et sommes contrôlés avant le `COMMIT`). Usage : `python -m senmarket_bases.charger_postgres --run-date AAAA-MM-JJ --schema NOM`. |
| [`charger_mongo.py`](src/senmarket_bases/charger_mongo.py) | Charge le catalogue (collection `produits`) et les avis (collection `avis`) dans MongoDB. Le `produit_id` reste identique à celui de PostgreSQL : c'est le lien entre les deux bases. Usage : `python -m senmarket_bases.charger_mongo 2026-10-29`. |
| [`commande.py`](src/senmarket_bases/commande.py) | Passer une commande. Contient la version **naïve** (volontairement fausse, pour prouver le bug de double vente) et trois versions **réparées** : mise à jour atomique conditionnelle, verrou `SELECT ... FOR UPDATE`, isolation `SERIALIZABLE` avec nouvelle tentative. Exceptions : `StockInsuffisant` (refus normal), `PlantageSimule`, `TropDeConflits`. |
| [`experience_concurrence.py`](src/senmarket_bases/experience_concurrence.py) | Lance deux acheteurs en parallèle sur le dernier article, répète l'essai de nombreuses fois, compte les doubles ventes et les commandes orphelines, et mesure le débit. Tout se passe dans un schéma jetable : `principal` et `volume` ne sont jamais touchés. |
| [`preuves_contraintes.py`](src/senmarket_bases/preuves_contraintes.py) | Prouve que chaque contrainte du schéma refuse bien ce qu'elle doit refuser (clé étrangère, `CHECK`, `UNIQUE`, `NOT NULL`). Il utilise un schéma jetable. Il est importé par les tests. |
| [`panier_redis.py`](src/senmarket_bases/panier_redis.py) | Redis : le panier (un Hash avec un TTL d'une heure, renouvelé à chaque action) et le cache-aside du « top produits » devant PostgreSQL (TTL de 60 s). |

### Les tests : [`tests/`](tests)

| Fichier | Ce qu'il vérifie |
|---|---|
| [`test_connexions.py`](tests/test_connexions.py) | Les trois bases répondent, et un mauvais mot de passe donne un message clair. |
| [`test_enrichissement.py`](tests/test_enrichissement.py) | Le stock n'est jamais négatif, un commentaire par avis, aucune référence de transaction dupliquée, fichiers identiques à chaque relance. |
| [`test_schema_postgres.py`](tests/test_schema_postgres.py) | Chaque contrainte refuse ce qu'elle doit refuser. |
| [`test_charger_postgres.py`](tests/test_charger_postgres.py) | Nombres de lignes et sommes égaux au Parquet, double exécution sans changement, échec sans donnée partielle. |
| [`test_commande.py`](tests/test_commande.py) | Concurrence (exactement une commande réussit sur un stock de 1) et atomicité (échec simulé : aucune écriture). |

Les tests de base de données exigent que les services soient démarrés. Ils travaillent dans des schémas jetables (`essai_...`) et ne touchent jamais `principal` ni `volume`.

### Les données ajoutées : [`bases_enriched/`](bases_enriched)

Un dossier par partition (`date=2026-10-29`, `date=2026-11-02`), avec quatre fichiers :

| Fichier | Contenu |
|---|---|
| `stock.csv` | `produit_id`, `stock` (entier ≥ 0, quelques ruptures, quelques produits « flash » à très faible stock) |
| `catalogue.jsonl` | Un document par produit, avec des attributs qui varient selon la catégorie |
| `avis_commentaires.csv` | Un texte par avis, cohérent avec la note |
| `paiements_references.csv` | Référence de transaction externe, unique par méthode, vide pour les espèces |

### Le parcours pédagogique : [`apprentissage/`](apprentissage)

À lire et exécuter dans cet ordre :

| Fichier | Contenu |
|---|---|
| [`A_prerequis.md`](apprentissage/A_prerequis.md) | Vérifier le sol : ce que le Module 0 a laissé, les outils nécessaires |
| [`B_comprendre.md`](apprentissage/B_comprendre.md) | Le cours résumé : pourquoi une base, les cinq familles, les idées clés de PostgreSQL, MongoDB, Redis et DuckDB |
| [`ch0_atelier.ipynb`](apprentissage/ch0_atelier.ipynb) | Allumer l'atelier : Docker, `.env`, connexions |
| [`ch1_enrichir.ipynb`](apprentissage/ch1_enrichir.ipynb) | Enrichir SenMarket : stock, catalogue, commentaires, références |
| [`ch2a_postgres_base.ipynb`](apprentissage/ch2a_postgres_base.ipynb) | PostgreSQL : schéma, chargement, transactions et index |
| [`ch2b_sql_analytique.ipynb`](apprentissage/ch2b_sql_analytique.ipynb) | SQL analytique : les huit questions SM-120 à SM-127 |
| [`ch3_mongodb.ipynb`](apprentissage/ch3_mongodb.ipynb) | MongoDB : catalogue, avis, validateur |
| [`ch4_redis.ipynb`](apprentissage/ch4_redis.ipynb) | Redis : panier, cache, expiration |
| [`ch5_duckdb.ipynb`](apprentissage/ch5_duckdb.ipynb) | DuckDB : analyser les Parquet sans serveur |
| [`ch6_decision.md`](apprentissage/ch6_decision.md) | Le conseil d'architecture : où met-on quoi, et pourquoi |

---

## 3. Où vit chaque donnée (la décision)

| Donnée | Base | Pourquoi | Si la base tombe |
|---|---|---|---|
| Clients, commandes, lignes, paiements | PostgreSQL | Cohérence stricte, transactions, contraintes | On ne peut plus commander |
| **Stock** | PostgreSQL | Une erreur coûte de l'argent (double vente) ; Redis redémarre vide | On ne peut plus commander |
| Fiche produit, caractéristiques | MongoDB | Forme variable selon le produit (téléphone, tissu, sac de riz) | Fiches indisponibles, commandes toujours possibles |
| Avis | MongoDB | Nombreux et croissants, rattachés à un produit | Avis indisponibles |
| Panier, cache, classement | Redis | Très rapide ; reconstructible ; avec TTL | L'application continue, plus lentement, via PostgreSQL |
| Analyses sur fichiers | DuckDB | Lecture colonnaire des Parquet, sans serveur ni mot de passe | Aucun impact sur la vente |

**Règle de départ :** chaque base ajoutée est une panne de plus à superviser, à sauvegarder et à expliquer. On n'en ajoute une que si PostgreSQL ne ferait pas assez bien, avec une mesure à l'appui.

---

## 4. Les choix de conception à savoir défendre

- **Argent en entier (`BIGINT`)** : le franc CFA n'a pas de centimes, et les décimaux flottants accumulent des erreurs d'arrondi.
- **`ON DELETE`** : `RESTRICT` pour client→commandes, produit→lignes, commande→paiements, vendeur→produits et avis (on ne supprime pas l'historique par accident) ; `CASCADE` pour commande→lignes (une ligne n'existe pas sans sa commande) ; `SET NULL` pour navigation→client et produit (un événement anonyme reste utile).
- **Deux schémas PostgreSQL** : `principal` (petite partition, pour comprendre) et `volume` (200 000 lignes de commande, pour que les mesures d'index aient un sens).
- **Chargement idempotent en « vider puis recharger » dans une transaction** : relancé deux fois, le chargeur laisse la base identique, et un échec ne laisse rien de partiel.
- **`COPY` plutôt qu'`INSERT` ligne par ligne** : sur 20 000 lignes, mesuré sur notre machine à 34,7 s en autocommit, 2,1 s en une transaction et 0,14 s avec `COPY`.
- **Double vente** : lire le stock puis le réécrire en deux temps est une condition de course. La version naïve a produit 194 doubles ventes sur 200 essais. Les trois remèdes (mise à jour conditionnelle atomique, `FOR UPDATE`, `SERIALIZABLE` avec nouvelle tentative) sont à 0. Un `CHECK (stock >= 0)` seul empêche le pire, mais pas la double vente.
- **Transaction et isolation sont deux problèmes distincts** : la transaction garantit « commande + paiement, tout ou rien » ; l'isolation évite que deux acheteurs voient le même stock.
- **Index** : sur la partition volume (199 997 lignes), une requête passe de 32,2 ms à 1,9 ms. La mesure s'appuie sur `EXPLAIN (ANALYZE, BUFFERS)`, jamais sur un simple « c'est plus rapide ».
- **Stock et prix hors de MongoDB** : un attribut qui change ailleurs donnerait deux vérités.
- **Redis sans persistance, avec TTL** : il ne détient jamais la seule copie d'une donnée qu'on ne sait pas reconstruire. `volatile-lru` n'évince que les clés avec TTL.
- **Libellés réels des Parquet** (statuts avec accents, cinq types d'événements de navigation) : ils priment sur ceux du document du module.
- **Mots de passe** : uniquement dans `.env`, jamais dans le code ni dans Git.

---

## 5. Commandes utiles

```bash
# Raccourci pour la session
alias dc='docker compose --env-file .env -f infra/docker-compose.yml'

dc ps                          # état et santé des services
dc logs -f postgres            # lire les journaux
dc stop redis                  # simuler une panne propre
dc kill redis                  # simuler un arrêt brutal
dc start redis

# Ouvrir un client dans chaque conteneur
dc exec postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
dc exec mongo sh -c 'mongosh -u $MONGO_INITDB_ROOT_USERNAME -p $MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase admin'
dc exec redis sh -c 'redis-cli -a $REDIS_PASSWORD'

# Lancer les questions métier sur la partition principale
dc exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1' < sql/10_questions.sql
```

Pour exécuter les questions sur la partition volume, remplacer `principal` par `volume` dans `SET search_path` en tête de [`10_questions.sql`](sql/10_questions.sql).

---

## 6. Dépannage

| Problème | Cause probable et solution |
|---|---|
| **Port déjà utilisé** (5432, 27017, 6379) | Un service local occupe le port. Changer le premier nombre du port dans le compose (côté machine), puis mettre à jour la connexion. |
| **PostgreSQL refuse le mot de passe après modification de `.env`** | Le mot de passe n'est lu qu'à la première initialisation du volume. Le changer dans la base (`ALTER USER`) ou repartir de zéro avec `down -v` (les données sont perdues). |
| **`authentication failed` dans MongoDB** | Il manque `authSource=admin` dans l'URI, ou `--authenticationDatabase admin` dans `mongosh`. |
| **`permission denied` avec Docker** | L'utilisateur n'est pas dans le groupe `docker` (Linux), ou Docker Desktop n'est pas démarré. |
| **L'installation de `psycopg` échoue** | Python trop récent (3.14). Créer un venv en Python 3.12. |
| **Un service reste `starting` ou `unhealthy`** | Lire `dc logs NOM_DU_SERVICE` : le plus souvent, une variable manque dans `.env`. |
| **Les mesures changent à chaque exécution** | Normal : répéter au moins 5 fois, ignorer la première (à froid) et garder la médiane. |
| **Le chargeur dit que des fichiers enrichis manquent** | Lancer `python -m senmarket_bases.enrichissement --run-date AAAA-MM-JJ` pour la date concernée. |

---

## 7. Pour passer au Module 2

Avant de démarrer Spark, il faut que, depuis un dépôt cloné :
- `./demarrer.sh` fonctionne depuis zéro (`down -v` puis relance) ;
- les deux schémas `principal` et `volume` contiennent les huit tables ;
- le chargeur relancé deux fois laisse la base identique ;
- `python -m pytest -q` est entièrement vert ;
- `git status` est propre et `.env` n'apparaît pas.