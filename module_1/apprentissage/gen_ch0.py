from _nb import build

C = []
C.append(("md", '''
# Chapitre 0 : allumer l'atelier (ticket SM-100)

> **Awa (fondatrice)** : « Je veux une base qui tienne, pas un énième fichier. On commence quand ? »

## À comprendre
Une base de données est un **serveur** : un programme qui attend des connexions, avec une adresse (hôte + port), un utilisateur et un mot de passe. Le mot de passe vit dans `.env`, jamais dans le code, jamais dans Git.

Ici, trois bases tournent chacune dans une « boîte » Docker : PostgreSQL, MongoDB, Redis. Ce chapitre prouve que l'atelier est allumé et répond aux deux questions du module.
'''))
C.append(("code", '''
import os, subprocess
from senmarket_bases.connexions import (ErreurConnexion, client_mongo, client_redis, connexion_postgres)

# docker compose command, run from the apprentissage/ folder
DC = ["docker", "compose", "--env-file", "../.env", "-f", "../infra/docker-compose.yml"]

def dc(*args):
    return subprocess.run([*DC, *args], capture_output=True, text=True).stdout
'''))
C.append(("md", "## 1. Les trois bases sont-elles démarrées et en bonne santé ?\nOn cherche `healthy` pour chacune : c'est le `healthcheck` du compose qui l'affirme."))
C.append(("code", 'print(dc("ps", "--format", "table {{.Service}}\\t{{.Status}}\\t{{.Ports}}"))'))
C.append(("md", "## 2. Une requête de vie dans chaque base\nOn ne dit pas « ça marche » : on pose une question à chaque serveur."))
C.append(("code", '''
with connexion_postgres() as conn:
    print("PostgreSQL :", conn.execute("SELECT version()").fetchone()[0][:40], "...")
print("MongoDB    : ping ->", client_mongo().admin.command("ping"))
print("Redis      : PING ->", client_redis().ping())
'''))
C.append(("md", "## 3. Une erreur claire quand le mot de passe est faux\nUn bon code ne crache pas vingt lignes de trace : il dit **quel service** et **quelle cause probable**."))
C.append(("code", '''
bon = os.environ["POSTGRES_PASSWORD"]
os.environ["POSTGRES_PASSWORD"] = "mauvais-mot-de-passe"
try:
    connexion_postgres()
except ErreurConnexion as e:
    print("Erreur attrapée proprement :\\n ", e)
finally:
    os.environ["POSTGRES_PASSWORD"] = bon  # always restore
'''))
C.append(("md", "## Question 1 : pourquoi le compose publie-t-il les ports sur `127.0.0.1` et pas sur toutes les interfaces ?\nPreuve : sur quelles adresses la machine écoute-t-elle réellement ?"))
C.append(("code", 'print(subprocess.run("ss -ltn | grep -E \':(5432|27017|6379)\\\\b\'", shell=True, capture_output=True, text=True).stdout)'))
C.append(("md", '''
**Réponse.** `127.0.0.1` désigne **cette machine seulement** : la colonne d'adresse ci-dessus montre `127.0.0.1:5432`, pas `0.0.0.0:5432`. Publier sur toutes les interfaces (`0.0.0.0`) ouvrirait les bases à tout le réseau local (le wifi du centre, par exemple), avec des mots de passe de développement.
**Justificatif :** la sortie `ss` ci-dessus. Rien d'autre que ton poste ne peut s'y connecter.
'''))
C.append(("md", '''
## Question 2 : que deviennent tes données avec `down` puis `up` ? Et avec `down -v` ?
**Danger :** `down -v` efface les données. On ne le lance **pas** sur tes vraies bases. On fait l'expérience sur un **PostgreSQL jetable** (autre projet Docker, autre port 5499, autre volume) : « vérifier au lieu de supposer », sans rien risquer.
'''))
C.append(("code", '''
import pathlib, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "docker-compose.yml").write_text("""name: sm_test
services:
  pg:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: test
    ports:
      - '127.0.0.1:5499:5432'
    volumes:
      - test_data:/var/lib/postgresql/data
volumes:
  test_data:
""")

def t(*args, check=True):
    return subprocess.run(["docker", "compose", "-f", str(tmp / "docker-compose.yml"), *args],
                          capture_output=True, text=True, check=check)

def psql(sql):
    return t("exec", "-T", "pg", "psql", "-U", "postgres", "-tA", "-c", sql).stdout.strip()

def attendre():
    # -h 127.0.0.1 checks the final server (the init phase only listens on the socket)
    for _ in range(60):
        if t("exec", "-T", "pg", "pg_isready", "-h", "127.0.0.1", "-U", "postgres", check=False).returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("PostgreSQL jetable non prêt")

try:
    t("up", "-d"); attendre()
    psql("CREATE TABLE test(x int)"); psql("INSERT INTO test VALUES (1),(2),(3)")
    print("Après création                 :", psql("SELECT count(*) FROM test"), "lignes")

    t("down"); t("up", "-d"); attendre()
    apres_down = psql("SELECT count(*) FROM test")
    print("Après  down puis up            :", apres_down, "lignes")

    t("down", "-v"); t("up", "-d"); attendre()
    apres_v = psql("SELECT to_regclass('public.test')")
    print("Après  down -v puis up         :", "table disparue" if not apres_v else "table présente")

    assert apres_down == "3" and not apres_v
    print("\\nVERDICT : down garde les données, down -v les efface.")
finally:
    t("down", "-v", check=False)  # always clean the throwaway project
'''))
C.append(("md", '''
**Réponse.** `down` arrête et supprime les **conteneurs**, mais les données vivent dans un **volume** qui reste : après `up`, la table est toujours là. `down -v` supprime aussi les volumes : tout est perdu.
**Justificatif :** les trois lignes de la cellule ci-dessus (3 lignes, 3 lignes, table disparue), obtenues sur le PostgreSQL jetable.

## Ce qu'on retient
- Les bases sont des serveurs, publiés uniquement sur ta machine.
- Les mots de passe vivent dans `.env`, et une erreur doit être lisible.
- `down` garde, `down -v` détruit : on ne lance jamais `-v` « pour nettoyer ».
'''))

build("ch0_atelier.ipynb", C)
print("ch0_atelier.ipynb créé")
