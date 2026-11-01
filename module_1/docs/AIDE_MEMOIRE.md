# Aide-mémoire Module 1 (à copier-coller dans le terminal)

```bash
# 1. Toujours se placer dans module_1 (l'alias ne marche que d'ici)
cd ~/Documents/"Orange Digital center"/Parcours/senmarket/module_1

# 2. Définir le raccourci dc (à retaper à chaque nouveau terminal)
alias dc='docker compose --env-file .env -f infra/docker-compose.yml'

# 3. Démarrer le démon Docker (si "Cannot connect to the Docker daemon")
sudo systemctl start docker

# ---- Démarrer et surveiller ----
dc up -d                 # démarre les trois bases
dc ps                    # état : attendre (healthy) sur les trois
dc logs -f postgres      # lire les journaux (Ctrl+C pour quitter), ou mongo, redis

# ---- Arrêter ----
dc stop redis            # arrête UN service (panne propre)
dc start redis           # le relance
dc kill redis            # arrêt brutal (simule un crash)
dc stop                  # arrête les trois, GARDE les données
dc start                 # relance les trois arrêtés
dc down                  # supprime les conteneurs, GARDE les données
dc down -v               # DANGER : supprime aussi les données (volumes)

# ---- Ouvrir un client dans chaque base ----
dc exec postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
dc exec mongo sh -c 'mongosh -u $MONGO_INITDB_ROOT_USERNAME -p $MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase admin'
dc exec redis sh -c 'redis-cli -a $REDIS_PASSWORD'

# ---- Tests ----
python -m pytest -v
```

## Les ports, expliqués simplement

Une base de données est un programme qui attend qu'on lui parle. Pour que plusieurs
programmes cohabitent sur la même machine, chacun écoute sur un **port** : un numéro de
porte. L'adresse dit *quelle machine*, le port dit *quel programme* sur cette machine.

| Port | Base | Qui l'utilise dans SenMarket |
|---|---|---|
| 5432 | PostgreSQL | commandes, paiements, stock |
| 27017 | MongoDB | catalogue produit, avis |
| 6379 | Redis | panier, sessions, cache |
| 9042 | Cassandra (option) | événements de navigation |
| 7474 et 7687 | Neo4j (option) | graphe de recommandation |

### Lire une ligne du compose

`'127.0.0.1:5432:5432'` se lit de gauche à droite :

| Morceau | Sens |
|---|---|
| `127.0.0.1` | Seule ta machine peut se connecter (personne d'autre sur le Wi-Fi) |
| `5432` (1er) | Le port côté **ta machine**, celui que ton code utilise |
| `5432` (2e) | Le port côté **conteneur**, celui où la base écoute vraiment |

Sans le `127.0.0.1:` au début, le port serait ouvert à tout le réseau.

### Vérifier qui écoute

```bash
ss -tln | grep -E '5432|27017|6379'
```

À gauche, tu dois lire `127.0.0.1:5432` (et non `0.0.0.0:5432`).

### Un port est déjà utilisé

Une autre base installée sur ta machine occupe déjà le numéro. Change **seulement le
premier nombre** dans le compose (ex. `'127.0.0.1:5433:5432'`), puis mets à jour le port
dans ton `.env` (POSTGRES_PORT=5433). Ne touche jamais au second nombre.
