"""ÉTAPE 3 : une requête lente, un index, et la preuve que ça change quelque chose.

    python scripts/1_charger.py --run-date 2026-11-02 --schema volume     (une seule fois)
    python scripts/3_index.py --schema volume

On mesure sur la grosse partition (200 000 lignes) : sur 10 000 lignes, PostgreSQL
répond vite avec ou sans index et la mesure ne prouve rien.
Chaque mesure = médiane de 5 exécutions (la première, à froid, est jetée).
"""
import argparse
import json
import statistics

from bases import pg

REQUETE = "SELECT count(*), sum(montant_xof) FROM lignes_commande WHERE {filtre}"


def scans(noeud):
    """Parcourt le plan et renvoie le type de balayage utilisé (Seq Scan, Index Scan...)."""
    trouves = [noeud["Node Type"]] if "Scan" in noeud["Node Type"] else []
    for fils in noeud.get("Plans", []):
        trouves += scans(fils)
    return trouves


def mesurer(conn, filtre, valeur):
    sql = "EXPLAIN (ANALYZE, FORMAT JSON) " + REQUETE.format(filtre=filtre)
    temps = []
    for i in range(6):
        plan = conn.execute(sql, (valeur,)).fetchone()[0][0]
        if i > 0:
            temps.append(plan["Execution Time"])
    return " + ".join(scans(plan["Plan"])), statistics.median(temps)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--schema", default="volume")
    a = p.parse_args()
    conn = pg(a.schema)
    conn.autocommit = True

    conn.execute("DROP INDEX IF EXISTS idx_lignes_produit")
    conn.execute("ANALYZE lignes_commande")
    produit, nb = conn.execute("SELECT produit_id, count(*) FROM lignes_commande "
                               "GROUP BY 1 ORDER BY 2 DESC LIMIT 1").fetchone()
    total = conn.execute("SELECT count(*) FROM lignes_commande").fetchone()[0]
    print(f"Table de {total} lignes. Question : « toutes les lignes du produit {produit} » ({nb} lignes).\n")

    print(f"{'situation':<46}{'plan':<40}{'temps médian':>13}")
    plan, t_avant = mesurer(conn, "produit_id = %s", produit)
    print(f"{'AVANT index':<46}{plan:<40}{t_avant:>10.2f} ms")

    conn.execute("CREATE INDEX idx_lignes_produit ON lignes_commande (produit_id)")
    conn.execute("ANALYZE lignes_commande")          # sans ANALYZE, PostgreSQL ne connaît pas le nouvel index
    plan, t_apres = mesurer(conn, "produit_id = %s", produit)
    print(f"{'APRÈS index sur produit_id':<46}{plan:<40}{t_apres:>10.2f} ms")

    # Contre-exemple : une fonction appliquée à la colonne rend l'index inutilisable.
    plan, t_fonction = mesurer(conn, "lower(produit_id) = lower(%s)", produit)
    print(f"{'index présent, mais WHERE lower(produit_id)':<46}{plan:<40}{t_fonction:>10.2f} ms")

    taille = conn.execute("SELECT pg_size_pretty(pg_relation_size('idx_lignes_produit'))").fetchone()[0]
    print(f"\nGain : x{t_avant / t_apres:.1f}. Taille de l'index : {taille}.")
    print("Contre-exemple : la fonction cache la colonne à l'index, PostgreSQL relit toute la table.")


if __name__ == "__main__":
    main()
