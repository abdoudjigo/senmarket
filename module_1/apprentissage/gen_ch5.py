from _nb import build
C = []
C.append(("md", '''
# Chapitre 5 : DuckDB, l'analyste sans serveur

> **Awa** : « Notre analyste veut explorer les données sans qu'on lui installe un serveur, et sans toucher à la base de production. »

## À comprendre
DuckDB est un moteur analytique **embarqué** : une bibliothèque, pas de serveur ni de mot de passe. Il lit les fichiers Parquet **tels quels** et ne lit que les colonnes dont il a besoin (stockage en colonnes). Il sert à **explorer et calculer en lecture** ; il ne remplace pas PostgreSQL pour enregistrer des commandes (un seul écrivain à la fois).
'''))
C.append(("code", '''
import hashlib, statistics, tempfile, time
import duckdb, pandas as pd
from senmarket_bases.connexions import RACINE, connexion_postgres

P = RACINE / "data" / "processed"
TABLES = ["clients", "commandes", "lignes_commande", "produits", "paiements"]

def duck(date):
    """A DuckDB connection with one view per table, named like the PostgreSQL tables."""
    con = duckdb.connect()
    for t in TABLES:
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{P}/date={date}/{t}.parquet')")
    return con

def pg(requete, schema):
    with connexion_postgres() as c:
        c.execute(f"SET search_path TO {schema}")
        cur = c.execute(requete)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])

def empreinte(df):
    """A short fingerprint of a result: identical results give identical fingerprints."""
    df = df.copy()
    for c in df.columns:  # PostgreSQL gives Decimal, DuckDB other number types: unify before hashing
        try:
            s = pd.to_numeric(df[c])
            df[c] = s.astype("int64") if (s % 1 == 0).all() else s.round(6)
        except (ValueError, TypeError):
            pass
    # row order is not part of the answer: PostgreSQL and DuckDB sort accents differently
    df = df.sort_values(list(df.columns)).reset_index(drop=True)
    return hashlib.md5(df.astype(str).to_csv(index=False).encode()).hexdigest()[:8]
'''))
C.append(("md", "## 1. Lire toutes les partitions d'un coup, avec la date en colonne\nUn motif générique `date=*` lit toutes les partitions ; `hive_partitioning` transforme le nom du dossier en colonne."))
C.append(("code", '''
print(duckdb.sql(f"""SELECT date, COUNT(*) AS nb_lignes
                     FROM read_parquet('{P}/date=*/lignes_commande.parquet', hive_partitioning = true)
                     GROUP BY date ORDER BY date""").df())
'''))
C.append(("md", "## 2. Trois requêtes, deux moteurs, un résultat identique\nLa **même requête SQL** est lancée dans PostgreSQL et dans DuckDB. On compare une **empreinte** du résultat, pas « à l'œil ». Les lignes sont retriées dans Python avant la comparaison, car les deux moteurs ne classent pas les accents de la même façon."))
C.append(("code", '''
REQUETES = {
 "CA par région (jointures + agrégation)": """
    SELECT cl.region, SUM(l.montant_xof) AS ca
    FROM lignes_commande l JOIN commandes c ON c.commande_id = l.commande_id
    JOIN clients cl ON cl.client_id = c.client_id
    GROUP BY cl.region ORDER BY ca DESC, cl.region""",
 "Top 3 produits par catégorie (fenêtre)": """
    WITH v AS (SELECT p.categorie, p.produit_id, SUM(l.quantite) AS qte
               FROM lignes_commande l JOIN produits p ON p.produit_id = l.produit_id GROUP BY 1, 2),
    r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY categorie ORDER BY qte DESC, produit_id) AS rang FROM v)
    SELECT categorie, rang, produit_id, qte FROM r WHERE rang <= 3 ORDER BY categorie, rang""",
 "Commandes sans paiement réussi (anti-jointure)": """
    SELECT COUNT(*) AS nb FROM commandes c
    WHERE NOT EXISTS (SELECT 1 FROM paiements p WHERE p.commande_id = c.commande_id AND p.statut_paiement = 'réussi')""",
}
con = duck("2026-10-29")
for nom, q in REQUETES.items():
    a, b = empreinte(pg(q, "principal")), empreinte(con.execute(q).df())
    print(f"{nom:<48} PostgreSQL {a} | DuckDB {b} | {'IDENTIQUE' if a == b else 'DIFFÉRENT'}")
    if a != b:
        x = {tuple(map(str, r)) for r in pg(q, "principal").values.tolist()}
        y = {tuple(map(str, r)) for r in con.execute(q).df().values.tolist()}
        raise AssertionError(f"{nom} | seulement PostgreSQL : {sorted(x - y)[:3]} | seulement DuckDB : {sorted(y - x)[:3]}")
'''))
C.append(("md", "## 3. La course, sur la partition volume (199 997 lignes)\nMédiane de 5 mesures (la 1re, à froid, est ignorée). PostgreSQL a l'index posé au chapitre 2a."))
C.append(("code", '''
con_v = duck("2026-11-02")
def mediane(f, n=5):
    f()  # warm-up run, ignored
    t = []
    for _ in range(n):
        d = time.perf_counter(); f(); t.append((time.perf_counter() - d) * 1000)
    return statistics.median(t)

lignes = []
for nom, q in list(REQUETES.items())[:2]:
    lignes.append((nom, mediane(lambda: pg(q, "volume")), mediane(lambda: con_v.execute(q).df())))
print(pd.DataFrame(lignes, columns=["requête", "PostgreSQL (ms)", "DuckDB (ms)"]).round(1))
'''))
C.append(("md", "**À lire.** Sur 200 000 lignes, l'écart peut être faible, voire en faveur de PostgreSQL : le volume est petit et la connexion PostgreSQL est déjà chaude. L'avantage de DuckDB (colonnes, calcul vectorisé, aucune transaction) grandit avec les millions de lignes. **On ne conclut que ce que les mesures montrent.**"))
C.append(("md", "## 4. Retrouver le Module 0 : réécrire une règle de nettoyage en SQL sur les CSV bruts\nLe nettoyage a rejeté les lignes de commande dont la quantité est invalide. DuckDB les retrouve directement dans le CSV brut."))
C.append(("code", '''
brut = f"{RACINE}/data/raw/date=2026-10-29"
n_sql = duckdb.sql(f"SELECT COUNT(*) FROM read_csv('{brut}/lignes_commande.csv', all_varchar = true) WHERE TRY_CAST(quantite AS INTEGER) <= 0").fetchall()[0][0]
rejets = pd.read_csv(RACINE / "data" / "rejected" / "date=2026-10-29" / "motifs_rejet.csv")
print("lignes à quantité <= 0 (DuckDB, CSV brut) :", n_sql)
print(rejets[rejets.astype(str).apply(lambda c: c.str.contains("quantite", na=False)).any(axis=1)])
'''))
C.append(("md", "**À lire.** Les deux nombres doivent coïncider. S'ils diffèrent, soit ma règle SQL est fausse, soit la règle du Module 0 est mal documentée : c'est justement l'intérêt de refaire le calcul par un autre chemin."))
C.append(("md", "## 5. Écrire un résultat en Parquet et vérifier les types"))
C.append(("code", '''
sortie = tempfile.mkdtemp() + "/ca_par_region.parquet"
con.execute(f"COPY (SELECT cl.region, SUM(l.montant_xof) AS ca FROM lignes_commande l JOIN commandes c ON c.commande_id = l.commande_id JOIN clients cl ON cl.client_id = c.client_id GROUP BY 1) TO '{sortie}' (FORMAT PARQUET)")
print(pd.read_parquet(sortie).dtypes)
'''))
C.append(("md", '''
## Questions

**1. Si l'analyste modifie un fichier Parquet à la main, qu'est-ce qui l'en empêche ?**
Rien dans DuckDB ni dans le fichier : un Parquet n'a ni contraintes ni droits. Ce qui devrait l'en empêcher : des **droits d'accès** sur le dossier (lecture seule pour l'analyste), et des copies versionnées. C'est une raison de plus de garder la vérité dans PostgreSQL.

**2. Quand DuckDB cesserait-il de suffire ?**
Quand les données ne tiennent plus sur une machine (milliers de millions de lignes), ou quand plusieurs personnes ou programmes doivent **écrire** en même temps : DuckDB n'accepte qu'un écrivain à la fois. On passe alors à Spark (Module 2) ou à un entrepôt cloud.

## Ce qu'on retient
- DuckDB lit les fichiers sans serveur : l'outil de l'exploration, pas celui des commandes.
- On prouve l'égalité de deux moteurs par une **empreinte**, pas à l'œil.
- Une mesure ne prouve que ce qu'elle mesure : ici, pas de victoire automatique de DuckDB.
'''))
build("ch5_duckdb.ipynb", C)
