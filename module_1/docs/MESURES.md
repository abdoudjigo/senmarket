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

## Chapitre 1 : réponse initiale (avant le chapitre 2)

Où doit vivre le stock ? Dans PostgreSQL.
Pourquoi : (à compléter avec mes mots avant le chapitre 6)

## Chapitre 2.2 : chargement dans PostgreSQL
- principal (partition 2026-10-29) : 9 995 lignes de commande, chargé en 1,1 s
- volume (partition 2026-11-02) : 199 997 lignes de commande, chargé en 20,1 s
- idempotence : les empreintes md5 des 8 tables sont identiques avant et après un second chargement
- 358 paiements en espèces chargés avec une référence NULL (et non une chaîne vide)

## Chapitre 2.2 : COPY contre INSERT (20 000 lignes de lignes_commande, médiane de 5 mesures, passage à blanc ignoré)

| Méthode | Médiane | Min | Max | Fois plus lent que COPY |
|---|---|---|---|---|
| INSERT, autocommit (1 commit par ligne) | 34.70 s | 31.99 s | 35.66 s | x256.6 |
| INSERT, une seule transaction | 2.10 s | 1.94 s | 2.32 s | x15.5 |
| COPY (code du chargeur) | 0.14 s | 0.13 s | 0.14 s | x1.0 |

Lecture : 34,7 s → 2,1 s en groupant les 20 000 commits en un seul (≈ 1,6 ms par commit, le temps d'attendre
le disque) ; 2,1 s → 0,14 s en envoyant les lignes en un seul flux au lieu d'une requête chacune.
Limites : table sans clés étrangères, PostgreSQL sur la même machine (aucune latence réseau).

## Chapitre 2.2 : « vider puis recharger » ou « insérer avec gestion de conflit » ?

**Pendant que l'application lit :** « vider puis recharger » est le moins confortable, car le `TRUNCATE`
prend un verrou exclusif : dans mon expérience à deux terminaux, un simple `SELECT` est resté bloqué puis annulé
(`canceling statement due to lock timeout`), alors qu'avec un `DELETE` le lecteur a répondu aussitôt avec les
anciennes données (999 avis) grâce au MVCC. Mon chargeur verrouille les huit tables pendant tout le chargement,
soit 1,1 s sur `principal` et 20,1 s sur `volume`, ce qui reste acceptable la nuit, alors que « insérer avec gestion de
conflit » ne bloque personne (il ne verrouille que les lignes qu'il modifie), mais il laisse en place une ligne
disparue de la source et demande donc un nettoyage à part. En contrepartie, « vider puis recharger » est dans une seule
transaction : les lecteurs voient soit l'ancien état complet, soit le nouvel état complet, jamais un état à moitié chargé.

**À 100 millions de lignes (×500) :** « vider puis recharger » deviendrait le moins bon, car si la durée suit à
peu près linéairement, mes 20,1 s deviendraient environ 10 000 s (≈ 2 h 45) de verrou exclusif, pendant lesquelles
l'application serait figée. L'insertion avec conflit reste utilisable, parce qu'elle ne bloque pas les lecteurs, mais
elle coûte cher par ligne : une recherche dans l'index, une nouvelle version de ligne à chaque mise à jour, et
beaucoup d'anciennes versions que PostgreSQL doit nettoyer ensuite (VACUUM). À cette échelle, on ne rechargerait de
toute façon plus tout : on chargerait seulement ce qui a changé (chargement incrémental, module 3).

_Limite : extrapolation linéaire, indicative ; mes mesures viennent d'un PostgreSQL local sur ma machine._

## Chapitre 2.3 : SM-120, CA par région (partition principale)
- 14 régions ; Dakar 65 064 469 XOF (39,9 %), Thiès 31 499 993 (19,3 %), Kédougou la plus faible (0,3 %).
- Invariant 1 : somme des régions = CA total = 163 011 763 XOF (écart 0).
- Invariant 2 : 9 995 lignes avant et après les jointures (rien multiplié, rien perdu).
- Limite : 1 client « Inconnue » est rattaché à la région Dakar (héritage du module 0), donc Dakar est légèrement surestimée.
