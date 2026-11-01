# Mesures et preuves du Module 1

## Ma machine
```
Linux 7.0.0-38-generic
Coeurs : 12
               total       utilisé      libre     partagé tamp/cache   disponible
Mem:            14Gi        12Gi       175Mi       1,1Gi       3,3Gi       2,0Gi
NAME    ROTA
loop0      0
loop1      0
```
(ROTA 0 = SSD, ROTA 1 = disque dur)

## Chapitre 0 : état des services
```
NAME                         IMAGE         COMMAND                  SERVICE    CREATED         STATUS                   PORTS
senmarket-bases-mongo-1      mongo:7       "docker-entrypoint.s…"   mongo      2 minutes ago   Up 2 minutes (healthy)   127.0.0.1:27017->27017/tcp
senmarket-bases-postgres-1   postgres:16   "docker-entrypoint.s…"   postgres   2 minutes ago   Up 2 minutes (healthy)   127.0.0.1:5432->5432/tcp
senmarket-bases-redis-1      redis:7       "docker-entrypoint.s…"   redis      2 minutes ago   Up 2 minutes (healthy)   127.0.0.1:6379->6379/tcp
```

## Chapitre 0 : requêtes de vie
```
PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
{ ok: 1 }
PONG
```

## Chapitre 0 : tests
```
configfile: pyproject.toml
testpaths: tests
plugins: Faker-40.43.0, platformdirs-4.13.5
collecting ... collected 8 items

tests/test_connexions.py::test_postgres_repond PASSED                    [ 12%]
tests/test_connexions.py::test_mongo_repond PASSED                       [ 25%]
tests/test_connexions.py::test_redis_repond PASSED                       [ 37%]
tests/test_connexions.py::test_postgres_mauvais_mot_de_passe PASSED      [ 50%]
tests/test_connexions.py::test_mongo_mauvais_mot_de_passe PASSED         [ 62%]
tests/test_connexions.py::test_redis_mauvais_mot_de_passe PASSED         [ 75%]
tests/test_connexions.py::test_variable_absente_nomme_la_variable PASSED [ 87%]
tests/test_connexions.py::test_le_mot_de_passe_ne_fuit_pas_dans_le_message PASSED [100%]

============================== 8 passed in 3.28s ===============================
```

## Chapitre 0 : qui écoute sur quels ports
```
LISTEN 0      4096       127.0.0.1:5432       0.0.0.0:*   
LISTEN 0      4096       127.0.0.1:6379       0.0.0.0:*   
LISTEN 0      4096       127.0.0.1:27017      0.0.0.0:*   
```

## Chapitre 0 : questions

**1. Pourquoi publier les ports sur 127.0.0.1 ?**
`ss` montre que les trois bases écoutent sur `127.0.0.1` et non sur `0.0.0.0`, et un test
de connexion sur mon adresse Wi-Fi (192.168.1.78) trouve les trois ports fermés. Seule ma
machine peut donc leur parler, pas les autres appareils du réseau. Mon code Python tourne
sur ma machine, donc il n'a besoin de rien de plus.

**2. Que deviennent les données après down puis up, et après down -v ?**
PostgreSQL et MongoDB gardent leurs données après `down` puis `up`, parce qu'elles vivent
dans des volumes que `down` conserve, mais les perdent après `down -v`, qui supprime les
volumes. Redis perd tout dans les deux cas : le compose désactive sa sauvegarde
(`--save ''` et `--appendonly no`), donc il ne garde ses données qu'en mémoire.
