from _nb import build
C = []
C.append(("md", '''
# Chapitre 4 : Redis, la vitesse avec ses limites

> **Mame Diarra (développeuse)** : « Quand un client change d'onglet, son panier disparaît. Et la page des produits les plus consultés interroge la base à chaque affichage : au Black Friday, elle va s'effondrer. »

## À comprendre
Trois usages, trois structures : le **panier** (un petit objet par client : un *Hash*), la **session** (un jeton à durée de vie limitée : une *String* avec TTL), le **classement** des produits consultés (un *Sorted Set*), plus un **cache** devant PostgreSQL.
Redis est en mémoire : très rapide, mais il **redémarre vide**. Aucun de ces usages ne doit être la seule copie d'une donnée critique.
'''))
C.append(("code", '''
import subprocess, time, statistics
import duckdb
from senmarket_bases.connexions import RACINE, client_redis
from senmarket_bases import panier_redis as pr

r = client_redis()
CLI = "TEST_CLI"
'''))
C.append(("md", "## 1. Le panier : un Hash avec expiration\n`HINCRBY` ajoute une quantité de façon **atomique** : deux clients qui ajoutent en même temps ne perdent aucun comptage."))
C.append(("code", '''
r.delete(f"panier:{CLI}")
pr.ajouter(CLI, "PRO0001", 2); pr.ajouter(CLI, "PRO0001", 1); pr.ajouter(CLI, "PRO0007")
print("panier :", pr.lire(CLI), "| type :", r.type(f"panier:{CLI}"), "| expire dans", r.ttl(f"panier:{CLI}"), "s")
assert pr.lire(CLI) == {"PRO0001": "3", "PRO0007": "1"}
'''))
C.append(("md", "Un panier abandonné doit **disparaître seul** (sinon les clés s'accumulent jusqu'à saturer la mémoire). On le prouve avec un TTL de 2 secondes."))
C.append(("code", '''
r.set("test:abandon", "panier", ex=2)
print("tout de suite :", r.get("test:abandon"))
time.sleep(3)
print("3 s plus tard :", r.get("test:abandon"))
assert r.get("test:abandon") is None
'''))
C.append(("md", "## 2. Le cache devant PostgreSQL (cache-aside)\nOn regarde dans Redis ; si absent (*miss*), on interroge PostgreSQL et on range le résultat avec un TTL ; sinon (*hit*) on répond tout de suite."))
C.append(("code", '''
def duree():
    t = time.perf_counter()
    _, source = pr.top_produits()
    return (time.perf_counter() - t) * 1000, source

r.delete("cache:top:principal")
miss, src = duree()
hits = [duree()[0] for _ in range(5)]
print(f"1er appel ({src}) : {miss:.1f} ms")
print(f"5 appels suivants (cache) : médiane {statistics.median(hits):.1f} ms")
'''))
C.append(("md", "**À lire.** Le 1er appel paie la requête SQL, les suivants lisent la mémoire. Au Black Friday, des milliers d'affichages ne coûtent qu'une requête SQL par TTL."))
C.append(("md", "## 3. Le classement : un Sorted Set\n`ZINCRBY` ajoute 1 point à un produit à chaque vue. On compare au classement calculé par DuckDB sur les mêmes événements, égalités comprises."))
C.append(("code", '''
nav = f"read_parquet('{RACINE}/data/processed/date=2026-10-29/navigation.parquet')"
filtre = "type_evenement = 'vue_produit' AND produit_id IS NOT NULL"
vues = duckdb.sql(f"SELECT produit_id FROM {nav} WHERE {filtre}").fetchall()
ref = duckdb.sql(f"SELECT produit_id, COUNT(*) FROM {nav} WHERE {filtre} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5").fetchall()

cle = "test:popularite"
r.delete(cle)
pipe = r.pipeline()
for (pid,) in vues:
    pipe.zincrby(cle, 1, pid)
pipe.expire(cle, 7 * 24 * 3600)
pipe.execute()
# Redis breaks ties in reverse alphabetical order: re-sort exactly like the SQL query
redis_top = [(p, int(s)) for p, s in sorted(r.zrange(cle, 0, -1, withscores=True), key=lambda x: (-x[1], x[0]))[:5]]
print("Redis     :", redis_top)
print("Référence :", [(p, int(c)) for p, c in ref])
assert redis_top == [(p, int(c)) for p, c in ref]
print("OK : classements identiques")
r.delete(cle, f"panier:{CLI}")
'''))
C.append(("md", "## 4. Ce qui se passe quand Redis redémarre\n**Attention :** cette cellule redémarre vraiment Redis. Elle ne touche qu'à une clé de test, mais elle vide aussi le cache et les paniers de test."))
C.append(("code", '''
DC = ["docker", "compose", "--env-file", "../.env", "-f", "../infra/docker-compose.yml"]
r.set("test:survie", "oui")
print("avant le redémarrage :", r.get("test:survie"))
subprocess.run([*DC, "restart", "redis"], capture_output=True)
for _ in range(30):
    try:
        r = client_redis(); break
    except Exception:
        time.sleep(1)
print("après le redémarrage :", r.get("test:survie"))
print("config :", r.config_get("maxmemory-policy"), r.config_get("appendonly"), r.config_get("maxmemory"))
'''))
C.append(("md", '''
## Questions

**1. Si Redis redémarre pendant le Black Friday, que perd-on ?**
Tout (la clé de test a disparu) : le compose ne sauvegarde rien (`appendonly no`, pas de `save`). On perd les paniers et les caches. Les caches se reconstruisent tout seuls depuis PostgreSQL ; les paniers sont perdus, le client les refait. C'est acceptable **parce que Redis n'est pas la seule copie d'une donnée critique**.

**2. Pourquoi ne pas mettre le stock dans Redis, malgré sa vitesse ?**
Le stock touche à l'argent et ne doit jamais disparaître : un redémarrage le remettrait à zéro ou à une valeur périmée. Il vit dans PostgreSQL, qui garantit la cohérence.

**3. Quelle politique d'éviction pour des paniers ?**
La cellule précédente affiche `volatile-lru` : seules les clés **avec TTL** sont évincées quand la mémoire est pleine. `allkeys-lru` pourrait évincer n'importe quelle clé, paniers compris : dangereux. D'où l'importance de **mettre un TTL sur chaque panier**.

## Ce qu'on retient
- Redis = rapidité + expiration, jamais source de vérité.
- `INCR`/`HINCRBY`/`ZINCRBY` sont atomiques ; le TTL nettoie tout seul.
- Un cache se mesure : premier appel lent, suivants rapides.
'''))
build("ch4_redis.ipynb", C)
