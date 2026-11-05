"""Query the volume partition directly from Parquet with DuckDB, then compare to PostgreSQL."""
import time

import duckdb

from senmarket_bases.connexions import RACINE, connexion_postgres

FICHIER = RACINE / "data" / "processed" / "date=2026-11-02" / "lignes_commande.parquet"
SQL = "SELECT produit_id, SUM(montant_xof) AS ca FROM {src} GROUP BY produit_id ORDER BY ca DESC, produit_id LIMIT 5"

debut = time.perf_counter()
duck = duckdb.sql(SQL.format(src=f"read_parquet('{FICHIER}')")).fetchall()
t_duck = time.perf_counter() - debut

debut = time.perf_counter()
with connexion_postgres() as conn:
    pg = conn.execute(SQL.format(src="volume.lignes_commande")).fetchall()
t_pg = time.perf_counter() - debut

print("DuckDB  :", duck, f"{t_duck * 1000:.1f} ms")
print("Postgres:", pg, f"{t_pg * 1000:.1f} ms")
print("Same result:", [(p, int(c)) for p, c in duck] == [(p, int(c)) for p, c in pg])
