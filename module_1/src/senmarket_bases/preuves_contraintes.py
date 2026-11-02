"""Preuves que les contraintes du schéma refusent bien ce qu'elles doivent refuser.

Tout se passe dans un schéma jetable (nom en essai_...), jamais dans principal ni volume.
Le même code sert au script scripts/prouver_contraintes.py (qui écrit docs/CONTRAINTES.md)
et aux tests pytest : une seule source de vérité.
"""
from pathlib import Path

import psycopg
from psycopg import errors

RACINE = Path(__file__).resolve().parents[2]
FICHIER_SCHEMA = RACINE / "sql" / "01_schema.sql"


def _verifier(conn: psycopg.Connection, nom: str) -> None:
    """Garde-fou : seuls les schémas jetables essai_... peuvent être créés ou supprimés."""
    if not nom.startswith("essai_"):
        raise ValueError(f"Schéma jetable attendu (nom en essai_...), reçu : {nom}")
    if not conn.autocommit:
        raise ValueError("La connexion doit être en autocommit : chaque essai est indépendant.")


def creer_schema(conn: psycopg.Connection, nom: str) -> None:
    """Crée un schéma jetable avec exactement le fichier sql/01_schema.sql."""
    _verifier(conn, nom)
    conn.execute(f'DROP SCHEMA IF EXISTS "{nom}" CASCADE')
    # Le fichier utilise la variable psql :"schema" : on la remplace par le nom jetable
    sql = FICHIER_SCHEMA.read_text(encoding="utf-8").replace(':"schema"', f'"{nom}"')
    conn.execute(sql)
    conn.execute(f'SET search_path TO "{nom}"')


def supprimer_schema(conn: psycopg.Connection, nom: str) -> None:
    """Supprime le schéma jetable."""
    _verifier(conn, nom)
    conn.execute(f'DROP SCHEMA IF EXISTS "{nom}" CASCADE')


# Données de départ, valides : un vendeur, un client, un produit, une commande,
# une ligne et un paiement Wave.
DONNEES_DE_BASE = [
    "INSERT INTO vendeurs (vendeur_id, nom_vendeur, ville, region) "
    "VALUES ('VEN1', 'Vendeur Un', 'Dakar', 'Dakar')",
    "INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) "
    "VALUES ('CLI1', 'Awa Diop', 'Dakar', 'Dakar', '2026-01-01')",
    "INSERT INTO produits (produit_id, nom_produit, categorie, vendeur_id, "
    "prix_catalogue_xof, actif, stock) "
    "VALUES ('PRO1', 'Téléphone', 'Électronique', 'VEN1', 85000, true, 10)",
    "INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
    "VALUES ('CMD1', 'CLI1', '2026-02-01', 'livrée')",
    "INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, "
    "prix_unitaire_xof, montant_xof) VALUES ('LIG1', 'CMD1', 'PRO1', 2, 85000, 170000)",
    "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
    "montant_xof, date_paiement, reference_transaction) "
    "VALUES ('PAI1', 'CMD1', 'Wave', 'réussi', 170000, '2026-02-01', 'WAV-100000001')",
]


def preparer_donnees(conn: psycopg.Connection) -> None:
    """Insère les données de départ (valides) dans le schéma jetable."""
    for sql in DONNEES_DE_BASE:
        conn.execute(sql)


# (type de contrainte, ce qu'on essaie, requête, erreur que PostgreSQL doit lever)
REFUS = [
    ("NOT NULL", "Un client sans nom",
     "INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) "
     "VALUES ('CLI9', NULL, 'Dakar', 'Dakar', '2026-01-01')",
     errors.NotNullViolation),
    ("Clé primaire", "Deux clients avec le même identifiant",
     "INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) "
     "VALUES ('CLI1', 'Doublon', 'Dakar', 'Dakar', '2026-01-01')",
     errors.UniqueViolation),
    ("Clé étrangère", "Une commande pour un client qui n'existe pas",
     "INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
     "VALUES ('CMD9', 'CLI_INCONNU', '2026-02-01', 'livrée')",
     errors.ForeignKeyViolation),
    ("Clé étrangère", "Un paiement pour une commande qui n'existe pas (le cauchemar de Fatou)",
     "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
     "montant_xof, date_paiement, reference_transaction) "
     "VALUES ('PAI9', 'CMD_INCONNUE', 'Wave', 'réussi', 1000, '2026-02-02', 'WAV-100000002')",
     errors.ForeignKeyViolation),
    ("CHECK", "Une ligne de commande de quantité 0",
     "INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, "
     "prix_unitaire_xof, montant_xof) VALUES ('LIG9', 'CMD1', 'PRO1', 0, 1000, 0)",
     errors.CheckViolation),
    ("CHECK", "Un montant de ligne qui ne vaut pas quantité x prix",
     "INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, "
     "prix_unitaire_xof, montant_xof) VALUES ('LIG9', 'CMD1', 'PRO1', 2, 1000, 1500)",
     errors.CheckViolation),
    ("CHECK", "Un stock négatif",
     "UPDATE produits SET stock = -1 WHERE produit_id = 'PRO1'",
     errors.CheckViolation),
    ("CHECK", "Une note de 6",
     "INSERT INTO avis (avis_id, client_id, produit_id, commande_id, note, date_avis, "
     "commentaire) VALUES ('AVI9', 'CLI1', 'PRO1', 'CMD1', 6, '2026-02-02', 'Test')",
     errors.CheckViolation),
    ("CHECK", "Un statut de commande sans accent (livree au lieu de livrée)",
     "INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
     "VALUES ('CMD9', 'CLI1', '2026-02-01', 'livree')",
     errors.CheckViolation),
    ("CHECK", "Un paiement en espèces avec une référence de transaction",
     "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
     "montant_xof, date_paiement, reference_transaction) "
     "VALUES ('PAI9', 'CMD1', 'Espèces', 'réussi', 1000, '2026-02-02', 'ESP-1')",
     errors.CheckViolation),
    ("CHECK", "Un paiement Wave sans référence de transaction",
     "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
     "montant_xof, date_paiement, reference_transaction) "
     "VALUES ('PAI9', 'CMD1', 'Wave', 'réussi', 1000, '2026-02-02', NULL)",
     errors.CheckViolation),
    ("CHECK", "Une référence de transaction vide (texte vide, pas NULL)",
     "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
     "montant_xof, date_paiement, reference_transaction) "
     "VALUES ('PAI9', 'CMD1', 'Wave', 'réussi', 1000, '2026-02-02', '')",
     errors.CheckViolation),
    ("UNIQUE", "Deux paiements avec la même référence de transaction",
     "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
     "montant_xof, date_paiement, reference_transaction) "
     "VALUES ('PAI9', 'CMD1', 'Wave', 'réussi', 1000, '2026-02-02', 'WAV-100000001')",
     errors.UniqueViolation),
]


def executer_refus(conn: psycopg.Connection) -> list[dict]:
    """Tente chaque insertion interdite et note ce que PostgreSQL répond."""
    resultats = []
    for categorie, description, sql, attendu in REFUS:
        fiche = {"categorie": categorie, "description": description, "sql": sql,
                 "attendu": attendu.__name__, "obtenu": "aucune erreur", "sqlstate": "-",
                 "contrainte": "-", "message": "-", "ok": False}
        try:
            conn.execute(sql)
        except psycopg.Error as erreur:
            diag = erreur.diag
            if diag.constraint_name:
                contrainte = diag.constraint_name
            elif diag.column_name:
                contrainte = f"colonne {diag.column_name}"
            else:
                contrainte = "-"
            fiche.update(
                obtenu=type(erreur).__name__,
                sqlstate=erreur.sqlstate or "-",
                contrainte=contrainte,
                message=diag.message_primary or str(erreur),
                ok=isinstance(erreur, attendu),
            )
        resultats.append(fiche)
    return resultats


def _valeur(conn: psycopg.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]


def executer_comportements(conn: psycopg.Connection) -> list[tuple[str, str, bool]]:
    """Observe ce que la base accepte et ce que font les ON DELETE.

    Renvoie une liste de (ce qu'on vérifie, ce qu'on a observé, résultat attendu ?).
    """
    obs: list[tuple[str, str, bool]] = []

    def noter(description: str, observation: str, ok: bool) -> None:
        obs.append((description, observation, bool(ok)))

    # 1. Un client peut exister sans commande
    conn.execute("INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) "
                 "VALUES ('CLI2', 'Moussa Ba', 'Thiès', 'Thiès', '2026-01-05')")
    n = _valeur(conn, "SELECT count(*) FROM commandes WHERE client_id = 'CLI2'")
    noter("Un client sans aucune commande est accepté",
          f"CLI2 créé, nombre de ses commandes : {n}", n == 0)

    # 2. Une commande peut exister sans ligne (question 1 du document)
    conn.execute("INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
                 "VALUES ('CMD3', 'CLI1', '2026-02-03', 'en_preparation')")
    n = _valeur(conn, "SELECT count(*) FROM lignes_commande WHERE commande_id = 'CMD3'")
    noter("Une commande sans aucune ligne est acceptée : la base ne l'empêche pas, "
          "c'est la transaction du chapitre 2.4 qui garantit commande + lignes + paiement",
          f"CMD3 créée, nombre de ses lignes : {n}", n == 0)

    # 3. Plusieurs paiements en espèces, tous sans référence (question 2 du chapitre 1)
    for pid in ("PAI2", "PAI3"):
        conn.execute("INSERT INTO paiements (paiement_id, commande_id, methode_paiement, "
                     "statut_paiement, montant_xof, date_paiement, reference_transaction) "
                     f"VALUES ('{pid}', 'CMD1', 'Espèces', 'réussi', 1000, '2026-02-02', NULL)")
    n = _valeur(conn, "SELECT count(*) FROM paiements WHERE reference_transaction IS NULL")
    noter("Plusieurs paiements en espèces sans référence sont acceptés malgré UNIQUE : "
          "PostgreSQL ne considère pas deux NULL comme égaux",
          f"{n} paiements avec une référence NULL", n == 2)

    # 4. RESTRICT : on ne supprime pas un client qui a des commandes
    try:
        conn.execute("DELETE FROM clients WHERE client_id = 'CLI1'")
        refuse, nom = False, "-"
    except errors.ForeignKeyViolation as erreur:
        refuse, nom = True, erreur.diag.constraint_name
    existe = _valeur(conn, "SELECT count(*) FROM clients WHERE client_id = 'CLI1'")
    noter("Supprimer un client qui a des commandes est refusé (RESTRICT)",
          f"suppression refusée par {nom}, le client existe toujours ({existe})",
          refuse and existe == 1)

    # 5. Chaîne : une commande avec paiement ne peut pas être supprimée,
    #    et ses lignes ne disparaissent pas à moitié (la suppression est atomique)
    try:
        conn.execute("DELETE FROM commandes WHERE commande_id = 'CMD1'")
        refuse, nom = False, "-"
    except errors.ForeignKeyViolation as erreur:
        refuse, nom = True, erreur.diag.constraint_name
    lignes = _valeur(conn, "SELECT count(*) FROM lignes_commande WHERE commande_id = 'CMD1'")
    noter("Supprimer une commande qui a un paiement est refusé (RESTRICT sur le paiement), "
          "et ses lignes restent intactes malgré le CASCADE (tout ou rien)",
          f"suppression refusée par {nom}, lignes restantes : {lignes}",
          refuse and lignes == 1)

    # 6. CASCADE : une commande sans paiement disparaît avec ses lignes
    conn.execute("INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
                 "VALUES ('CMD2', 'CLI1', '2026-02-04', 'en_preparation')")
    conn.execute("INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, "
                 "quantite, prix_unitaire_xof, montant_xof) "
                 "VALUES ('LIG2', 'CMD2', 'PRO1', 1, 85000, 85000)")
    conn.execute("DELETE FROM commandes WHERE commande_id = 'CMD2'")
    n = _valeur(conn, "SELECT count(*) FROM lignes_commande WHERE ligne_commande_id = 'LIG2'")
    noter("Supprimer une commande sans paiement supprime aussi ses lignes (CASCADE)",
          f"CMD2 supprimée, lignes restantes : {n}", n == 0)

    # 7. SET NULL : l'événement de navigation reste, mais devient anonyme
    conn.execute("INSERT INTO navigation (evenement_id, session_id, client_id, produit_id, "
                 "type_evenement, date_evenement) "
                 "VALUES ('NAV1', 'SES1', 'CLI2', 'PRO1', 'vue_produit', '2026-02-01 10:00:00+00')")
    conn.execute("DELETE FROM clients WHERE client_id = 'CLI2'")
    ligne = conn.execute("SELECT client_id FROM navigation WHERE evenement_id = 'NAV1'").fetchone()
    noter("Supprimer un client met à NULL son client_id dans la navigation (SET NULL) : "
          "l'événement est conservé, devenu anonyme",
          f"événement conservé : {ligne is not None}, client_id vaut maintenant : "
          f"{None if ligne is None else ligne[0]}",
          ligne is not None and ligne[0] is None)

    # 8. Le déclencheur met modifie_le à jour
    conn.execute("UPDATE produits SET stock = 9 WHERE produit_id = 'PRO1'")
    plus_recent = _valeur(conn, "SELECT modifie_le > cree_le FROM produits WHERE produit_id = 'PRO1'")
    noter("Modifier une ligne met à jour modifie_le (déclencheur)",
          f"modifie_le est postérieur à cree_le : {plus_recent}", plus_recent)

    return obs
