"""Mesure : COPY contre INSERT ligne par ligne, sur 20 000 lignes (chapitre 2.2).

Trois variantes sont chronométrées sur la même table jetable (essai_mesure_copy) :
  1. INSERT en autocommit      : une requête ET un commit par ligne ;
  2. INSERT, une transaction   : une requête par ligne, un seul commit ;
  3. COPY                      : le code réel du chargeur (un seul flux).

Chaque variante : 1 passage à blanc (ignoré), puis 5 mesures, on garde la médiane.
Usage : python scripts/mesurer_copy_vs_insert.py
"""
import statistics
import sys
import time

import pandas as pd

from senmarket_bases.charger_postgres import _copier
from senmarket_bases.connexions import connexion_postgres
from senmarket_bases.enrichissement import DOSSIER_PROCESSED

SCHEMA = "essai_mesure_copy"      # le préfixe essai_ marque un schéma jetable
TABLE = "lignes_test"
PARTITION = "2026-11-02"          # la partition « volume » : assez de lignes
NB_LIGNES = 20_000
NB_MESURES = 5

COLONNES = ["ligne_commande_id", "commande_id", "produit_id", "quantite",
            "prix_unitaire_xof", "montant_xof"]
REQUETE_INSERT = (f'INSERT INTO "{SCHEMA}"."{TABLE}" ({", ".join(COLONNES)}) '
                  "VALUES (%s, %s, %s, %s, %s, %s)")


def preparer_table(conn) -> None:
    """Recrée une table vide, de même forme que lignes_commande mais sans clés étrangères."""
    conn.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
    conn.execute(f'CREATE SCHEMA "{SCHEMA}"')
    conn.execute(f"""
        CREATE TABLE "{SCHEMA}"."{TABLE}" (
            ligne_commande_id  TEXT PRIMARY KEY,
            commande_id        TEXT NOT NULL,
            produit_id         TEXT NOT NULL,
            quantite           INTEGER NOT NULL,
            prix_unitaire_xof  BIGINT NOT NULL,
            montant_xof        BIGINT NOT NULL
        )""")


def vider(conn) -> None:
    conn.execute(f'TRUNCATE TABLE "{SCHEMA}"."{TABLE}"')      # hors chronomètre


def verifier(conn) -> None:
    """Une mesure n'a de sens que si les 20 000 lignes sont bien arrivées."""
    n = conn.execute(f'SELECT count(*) FROM "{SCHEMA}"."{TABLE}"').fetchone()[0]
    if n != NB_LIGNES:
        raise SystemExit(f"ERREUR : {n} lignes en base au lieu de {NB_LIGNES}")


def insert_autocommit(conn, df, lignes) -> None:
    for ligne in lignes:                     # chaque execute = une requête + un commit
        conn.execute(REQUETE_INSERT, ligne)


def insert_une_transaction(conn, df, lignes) -> None:
    with conn.transaction():                 # un seul commit à la fin
        for ligne in lignes:
            conn.execute(REQUETE_INSERT, ligne)


def copy_en_masse(conn, df, lignes) -> None:
    _copier(conn, SCHEMA, TABLE, df)         # le vrai code du chargeur


VARIANTES = [
    ("INSERT, autocommit (1 commit par ligne)", insert_autocommit),
    ("INSERT, une seule transaction", insert_une_transaction),
    ("COPY (code du chargeur)", copy_en_masse),
]


def main() -> int:
    fichier = DOSSIER_PROCESSED / f"date={PARTITION}" / "lignes_commande.parquet"
    if not fichier.exists():
        print(f"ERREUR : {fichier} introuvable (partition {PARTITION} du module 0).", file=sys.stderr)
        return 1
    df = pd.read_parquet(fichier, columns=COLONNES).head(NB_LIGNES).reset_index(drop=True)
    if len(df) < NB_LIGNES:
        print(f"ERREUR : seulement {len(df)} lignes dans la partition.", file=sys.stderr)
        return 1
    lignes = df.to_numpy(dtype=object).tolist()      # entiers Python natifs pour psycopg

    conn = connexion_postgres()
    conn.autocommit = True
    resultats = []
    try:
        preparer_table(conn)
        for nom, fonction in VARIANTES:
            temps = []
            for essai in range(NB_MESURES + 1):      # l'essai 0 est le passage à blanc
                vider(conn)
                debut = time.perf_counter()
                fonction(conn, df, lignes)
                duree = time.perf_counter() - debut
                verifier(conn)
                if essai > 0:
                    temps.append(duree)
            resultats.append((nom, statistics.median(temps), min(temps), max(temps)))
            print(f"{nom:<42} médiane {resultats[-1][1]:7.2f} s", flush=True)
    finally:
        conn.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        conn.close()

    copie = resultats[-1][1]
    print("\n--- À coller dans docs/MESURES.md ---")
    print(f"## Chapitre 2.2 : COPY contre INSERT ({NB_LIGNES} lignes de lignes_commande, "
          f"médiane de {NB_MESURES} mesures, passage à blanc ignoré)\n")
    print("| Méthode | Médiane | Min | Max | Fois plus lent que COPY |")
    print("|---|---|---|---|---|")
    for nom, med, mini, maxi in resultats:
        print(f"| {nom} | {med:.2f} s | {mini:.2f} s | {maxi:.2f} s | x{med / copie:.1f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())