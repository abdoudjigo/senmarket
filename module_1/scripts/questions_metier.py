"""Une question métier par base. Lancer : python scripts/questions_metier.py"""
import duckdb

from senmarket_bases.connexions import RACINE, client_mongo, client_redis, connexion_postgres

S = "principal"  # schéma PostgreSQL de la partition principale
PARTITION = RACINE / "data" / "processed" / "date=2026-10-29"  # mêmes données que "principal"

# ---- PostgreSQL Q1 : chiffre d'affaires par région (chaîne de jointures) ----
print("== PostgreSQL Q1 : chiffre d'affaires par région ==")
with connexion_postgres() as conn:
    lignes = conn.execute(f"""
        SELECT c.region, SUM(l.montant_xof) AS ca
        FROM {S}.lignes_commande l
        JOIN {S}.commandes o ON o.commande_id = l.commande_id
        JOIN {S}.clients c ON c.client_id = o.client_id
        GROUP BY c.region ORDER BY ca DESC""").fetchall()
    total = conn.execute(f"SELECT SUM(montant_xof) FROM {S}.lignes_commande").fetchone()[0]
    for region, ca in lignes:
        print(f"  {region:<15}{int(ca):>14}")
    print("  invariant (somme des régions == total) :", sum(ca for _, ca in lignes) == total)

    # ---- PostgreSQL Q2 : commandes sans paiement réussi (anti-jointure) ----
    print("\n== PostgreSQL Q2 : commandes sans paiement réussi ==")
    # On regarde d'abord les valeurs réelles du statut, au lieu de les supposer
    statuts = conn.execute(
        f"SELECT statut_paiement, COUNT(*) FROM {S}.paiements GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print("  valeurs de statut_paiement :", statuts)
    n, nb_total = conn.execute(f"""
        SELECT COUNT(*) FILTER (WHERE NOT EXISTS (
                 SELECT 1 FROM {S}.paiements p
                 WHERE p.commande_id = o.commande_id AND p.statut_paiement = 'réussi')),
               COUNT(*)
        FROM {S}.commandes o""").fetchone()
    print(f"  {n} commandes sur {nb_total} ({n / nb_total:.1%})")

# ---- Redis : produits les plus consultés (Sorted Set), comparés à DuckDB ----
print("\n== Redis : top 5 des produits les plus consultés ==")
nav = f"read_parquet('{PARTITION}/navigation.parquet')"
filtre = "type_evenement = 'vue_produit' AND produit_id IS NOT NULL"
vues = duckdb.sql(f"SELECT produit_id FROM {nav} WHERE {filtre}").fetchall()
ref_top = duckdb.sql(f"""SELECT produit_id, COUNT(*) FROM {nav} WHERE {filtre}
                         GROUP BY produit_id ORDER BY 2 DESC, 1 LIMIT 5""").fetchall()

r = client_redis()
cle = "popularite:principal"
r.delete(cle)
pipe = r.pipeline()
for (pid,) in vues:
    pipe.zincrby(cle, 1, pid)  # incrément atomique, une vue à la fois
pipe.expire(cle, 7 * 24 * 3600)  # le classement disparaît seul au bout de 7 jours
pipe.execute()
# Redis départage les égalités à l'envers : on retrie comme la requête de référence
tous = sorted(r.zrange(cle, 0, -1, withscores=True), key=lambda x: (-x[1], x[0]))[:5]
redis_top = [(p, int(s)) for p, s in tous]
print("  Redis    :", redis_top)
print("  Référence:", [(p, int(c)) for p, c in ref_top])
print("  identiques :", redis_top == [(p, int(c)) for p, c in ref_top])

# ---- MongoDB : répartition des notes du produit le plus commenté ----
print("\n== MongoDB : répartition des notes du produit le plus commenté ==")
db = client_mongo()["senmarket"]
plus = next(db.avis.aggregate([
    {"$group": {"_id": "$produit_id", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}, {"$limit": 1}]))
print(f"  produit {plus['_id']} ({plus['n']} avis)")
for ligne in db.avis.aggregate([
        {"$match": {"produit_id": plus["_id"]}},
        {"$group": {"_id": "$note", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]):
    print(f"  note {ligne['_id']} : {ligne['n']} avis")

# ---- DuckDB : chiffre d'affaires par mois, lu directement dans les Parquet ----
print("\n== DuckDB : chiffre d'affaires par mois (lecture des fichiers Parquet) ==")
for mois, ca in duckdb.sql(f"""
        SELECT strftime(CAST(o.date_commande AS DATE), '%Y-%m') AS mois, SUM(l.montant_xof) AS ca
        FROM read_parquet('{PARTITION}/lignes_commande.parquet') l
        JOIN read_parquet('{PARTITION}/commandes.parquet') o USING (commande_id)
        GROUP BY mois ORDER BY mois""").fetchall():
    print(f"  {mois}  {int(ca):>14}")
