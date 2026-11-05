"""Mesure EXPLAIN ANALYZE des 3 requêtes du 2.5, avant ou après index.

Usage : python scripts/mesure_index.py --etape avant|apres [--repet-sm125 3]
Écrit docs/mesures_index_<etape>.md (plan texte de la passe à froid + médianes).
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

from senmarket_bases.connexions import connexion_postgres

SCHEMA = "volume"
INDEX = {
    "idx_paiements_commande": "CREATE INDEX IF NOT EXISTS idx_paiements_commande ON paiements(commande_id)",
    "idx_commandes_client": "CREATE INDEX IF NOT EXISTS idx_commandes_client ON commandes(client_id)",
    "idx_navigation_client_date": "CREATE INDEX IF NOT EXISTS idx_navigation_client_date ON navigation(client_id, date_evenement)",
}

# Requête 1 : SM-125 « Liste 1 », copiée telle quelle de sql/10_questions.sql
SQL_SM125 = """
SELECT
    COUNT(*) AS commandes_sans_paiement_reussi,
    COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM paiements q WHERE q.commande_id = c.commande_id)) AS dont_aucun_paiement,
    COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM paiements q WHERE q.commande_id = c.commande_id)) AS dont_paiement_non_reussi
FROM commandes c
WHERE NOT EXISTS (
    SELECT 1 FROM paiements p
    WHERE p.commande_id = c.commande_id AND p.statut_paiement = 'réussi'
)
"""
SQL_ACHATS = "SELECT * FROM commandes WHERE client_id = %s"
SQL_NAV = ("SELECT * FROM navigation WHERE client_id = %s "
           "AND date_evenement >= %s::date AND date_evenement < %s::date + 1")


def plan_json(cur, sql, params):
    """Exécute EXPLAIN (ANALYZE, BUFFERS) et renvoie le plan racine."""
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
    brut = cur.fetchone()[0]
    if isinstance(brut, str):
        brut = json.loads(brut)
    return brut[0]


def noeuds(plan):
    """Liste les nœuds du plan (type + table ou index), sous-plans inclus."""
    nom = plan["Node Type"]
    cible = plan.get("Index Name") or plan.get("Relation Name")
    sortie = [f"{nom}({cible})" if cible else nom]
    for enfant in plan.get("Plans", []):
        sortie += noeuds(enfant)
    return sortie


def plan_texte(cur, sql, params):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
    return "\n".join(ligne[0] for ligne in cur.fetchall())


def mesurer(cur, label, sql, params, repet):
    """Passe à froid (plan texte gardé, temps ignoré) puis `repet` mesures."""
    cur.execute("ANALYZE")
    texte = plan_texte(cur, sql, params)
    temps, dernier = [], None
    for _ in range(repet):
        dernier = plan_json(cur, sql, params)
        temps.append(dernier["Execution Time"])
    p = dernier["Plan"]
    tampons = p.get("Shared Hit Blocks", 0) + p.get("Shared Read Blocks", 0)
    res = {
        "label": label, "mediane_ms": statistics.median(temps), "mesures": len(temps),
        "estimees": p["Plan Rows"], "reelles": p["Actual Rows"], "tampons": tampons,
        "noeuds": " > ".join(noeuds(p)), "texte": texte,
    }
    print(f"{label:<26} médiane={res['mediane_ms']:10.2f} ms ({len(temps)} mesures) "
          f"estimées={res['estimees']} réelles={res['reelles']}")
    print(f"   plan : {res['noeuds']}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etape", choices=["avant", "apres"], required=True)
    ap.add_argument("--repet-sm125", type=int, default=3,
                    help="mesures pour SM-125 (lente avant index)")
    args = ap.parse_args()

    with connexion_postgres() as conn:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"SET search_path TO {SCHEMA}")

        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname=%s", (SCHEMA,))
        presents = {r[0] for r in cur.fetchall()}
        if args.etape == "avant" and presents & set(INDEX):
            sys.exit(f"Index déjà présents {presents & set(INDEX)} : la mesure « avant » serait fausse.")
        if args.etape == "apres":
            for nom, ddl in INDEX.items():
                cur.execute(ddl)

        # Cibles choisies par requête (jamais en dur)
        cur.execute("SELECT client_id FROM commandes GROUP BY 1 ORDER BY COUNT(*) DESC, 1 LIMIT 1")
        client = cur.fetchone()[0]
        cur.execute("""SELECT client_id, date_evenement::date FROM navigation
                       WHERE client_id IS NOT NULL GROUP BY 1,2 ORDER BY COUNT(*) DESC, 1, 2 LIMIT 1""")
        nav_client, nav_jour = cur.fetchone()
        print(f"Cibles : client={client} | navigation client={nav_client} jour={nav_jour}\n")

        cas = [
            ("Q1 SM-125 Liste 1", SQL_SM125, None, args.repet_sm125),
            ("Q2 achats d'un client", SQL_ACHATS, (client,), 5),
            ("Q3 navigation client/jour", SQL_NAV, (nav_client, nav_jour, nav_jour), 5),
        ]
        resultats = [mesurer(cur, *c[:3], c[3]) for c in cas]

        # Contrôle : le nombre de lignes rendues par Q2 et Q3 doit être identique avant/après
        cur.execute(SQL_ACHATS, (client,)); n2 = len(cur.fetchall())
        cur.execute(SQL_NAV, (nav_client, nav_jour, nav_jour)); n3 = len(cur.fetchall())
        print(f"\nContrôle lignes rendues : Q2={n2} Q3={n3} (doivent être identiques avant/après)")

        tailles = {}
        if args.etape == "apres":
            for nom in INDEX:
                cur.execute("SELECT pg_size_pretty(pg_relation_size(%s::regclass))", (nom,))
                tailles[nom] = cur.fetchone()[0]
            print("Taille des index :", tailles)

    sortie = Path("docs") / f"mesures_index_{args.etape}.md"
    with sortie.open("w", encoding="utf-8") as f:
        f.write(f"# Mesures 2.5, étape « {args.etape} » (schéma {SCHEMA})\n\n")
        f.write(f"Cibles : client `{client}`, navigation `{nav_client}` le `{nav_jour}`. "
                f"Lignes rendues : Q2={n2}, Q3={n3}.\n\n")
        f.write("| Requête | Médiane (ms) | Mesures | Lignes estimées | Lignes réelles | Tampons | Nœuds |\n|---|---|---|---|---|---|---|\n")
        for r in resultats:
            f.write(f"| {r['label']} | {r['mediane_ms']:.2f} | {r['mesures']} | {r['estimees']} | "
                    f"{r['reelles']} | {r['tampons']} | {r['noeuds']} |\n")
        if tailles:
            f.write("\nTaille des index : " + ", ".join(f"{k} = {v}" for k, v in tailles.items()) + "\n")
        for r in resultats:
            f.write(f"\n## Plan (passe à froid) : {r['label']}\n\n```\n{r['texte']}\n```\n")
    print(f"\nÉcrit : {sortie}")


if __name__ == "__main__":
    main()
