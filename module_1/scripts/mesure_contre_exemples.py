"""Contre-exemples d'index (où l'index ne sert pas) et ordre d'un index composite."""
from mesure_index import mesurer
from senmarket_bases.connexions import connexion_postgres

TEMP = ["idx_tmp_statut", "idx_tmp_nom", "idx_tmp_ville", "idx_tmp_nav_date",
        "idx_tmp_cmd_a", "idx_tmp_cmd_b"]

with connexion_postgres() as conn:
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET search_path TO volume")
    for i in TEMP:
        cur.execute(f"DROP INDEX IF EXISTS {i}")

    print("=== Contre-exemple 1 : colonne à peu de valeurs (statut) ===")
    cur.execute("SELECT statut, COUNT(*) FROM commandes GROUP BY 1 ORDER BY 2 DESC")
    print("répartition :", cur.fetchall())
    cur.execute("SELECT statut FROM commandes GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1")
    statut = cur.fetchone()[0]
    cur.execute("CREATE INDEX idx_tmp_statut ON commandes(statut)")
    mesurer(cur, "statut frequent", "SELECT * FROM commandes WHERE statut = %s", (statut,), 5)

    print("\n=== Contre-exemple 2 : fonction sur la colonne indexée (lower) ===")
    cur.execute("SELECT nom_client FROM clients ORDER BY client_id LIMIT 1")
    nom = cur.fetchone()[0]
    cur.execute("CREATE INDEX idx_tmp_nom ON clients(nom_client)")
    mesurer(cur, "nom_client = (index OK)", "SELECT * FROM clients WHERE nom_client = %s", (nom,), 5)
    mesurer(cur, "lower(nom_client) =", "SELECT * FROM clients WHERE lower(nom_client) = %s", (nom.lower(),), 5)

    print("\n=== Contre-exemple 3 : LIKE avec joker au début ===")
    cur.execute("SELECT ville FROM clients GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1")
    ville = cur.fetchone()[0]
    cur.execute("CREATE INDEX idx_tmp_ville ON clients(ville text_pattern_ops)")
    mesurer(cur, "LIKE 'debut%' (index)", "SELECT * FROM clients WHERE ville LIKE %s", (ville[:3] + "%",), 5)
    mesurer(cur, "LIKE '%fin' (joker)", "SELECT * FROM clients WHERE ville LIKE %s", ("%" + ville[-3:],), 5)

    print("\n=== Contre-exemple 4 : conversion de date sur la colonne ===")
    cur.execute("SELECT date_evenement::date FROM navigation GROUP BY 1 ORDER BY COUNT(*) DESC, 1 LIMIT 1")
    jour = cur.fetchone()[0]
    cur.execute("CREATE INDEX idx_tmp_nav_date ON navigation(date_evenement)")
    mesurer(cur, "plage (index OK)",
            "SELECT * FROM navigation WHERE date_evenement >= %s::date AND date_evenement < %s::date + 1",
            (jour, jour), 5)
    mesurer(cur, "date_evenement::date =", "SELECT * FROM navigation WHERE date_evenement::date = %s", (jour,), 5)

    print("\n=== Index composite : les deux ordres ===")
    cur.execute("SELECT client_id FROM commandes GROUP BY 1 ORDER BY COUNT(*) DESC, 1 LIMIT 1")
    client = cur.fetchone()[0]
    cur.execute("SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY date_commande) FROM commandes")
    seuil = cur.fetchone()[0]
    sql = "SELECT * FROM commandes WHERE client_id = %s AND date_commande >= %s"
    cur.execute("DROP INDEX IF EXISTS idx_commandes_client")  # isoler le test
    for nom_idx, cols in [("idx_tmp_cmd_a", "client_id, date_commande"),
                          ("idx_tmp_cmd_b", "date_commande, client_id")]:
        cur.execute(f"CREATE INDEX {nom_idx} ON commandes({cols})")
        mesurer(cur, f"composite ({cols})", sql, (client, seuil), 5)
        cur.execute(f"DROP INDEX {nom_idx}")
    cur.execute("CREATE INDEX idx_commandes_client ON commandes(client_id)")  # restaurer

    for i in TEMP:
        cur.execute(f"DROP INDEX IF EXISTS {i}")
    print("\nIndex temporaires supprimés.")
