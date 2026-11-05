"""Chargement d'une partition (Parquet du module 0 + fichiers enrichis) dans PostgreSQL.

Usage : python -m senmarket_bases.charger_postgres --run-date AAAA-MM-JJ --schema NOM

Quatre garanties :
- rapide     : COPY (chargement en masse), pas d'INSERT ligne par ligne ;
- idempotent : on vide les huit tables puis on recharge, dans UNE transaction ;
- atomique   : un échec en cours de route annule tout (la base reste comme avant) ;
- vérifié    : comptes et sommes sont contrôlés AVANT le commit.
"""
import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

from senmarket_bases.connexions import ErreurConnexion, connexion_postgres
from senmarket_bases.enrichissement import DOSSIER_PROCESSED, DOSSIER_SORTIE

journal = logging.getLogger("chargement")

# Ordre des dépendances : un parent est toujours chargé avant ses enfants
ORDRE = ["vendeurs", "clients", "produits", "commandes", "lignes_commande",
         "paiements", "avis", "navigation"]

# Colonnes chargées, dans l'ordre du COPY (cree_le et modifie_le sont remplies par la base)
COLONNES = {
    "vendeurs": ["vendeur_id", "nom_vendeur", "ville", "region"],
    "clients": ["client_id", "nom_client", "email", "telephone", "ville", "region",
                "date_inscription"],
    "produits": ["produit_id", "nom_produit", "categorie", "vendeur_id",
                 "prix_catalogue_xof", "actif", "stock"],
    "commandes": ["commande_id", "client_id", "date_commande", "statut"],
    "lignes_commande": ["ligne_commande_id", "commande_id", "produit_id", "quantite",
                        "prix_unitaire_xof", "montant_xof"],
    "paiements": ["paiement_id", "commande_id", "methode_paiement", "statut_paiement",
                  "montant_xof", "date_paiement", "reference_transaction"],
    "avis": ["avis_id", "client_id", "produit_id", "commande_id", "note", "date_avis",
             "commentaire"],
    "navigation": ["evenement_id", "session_id", "client_id", "produit_id",
                   "type_evenement", "date_evenement"],
}

# Colonnes DATE : le Parquet les stocke en datetime (toujours à minuit, vérifié) ;
# on les écrit en AAAA-MM-JJ pour que la base reçoive exactement une date
COLONNES_DATE = {
    "clients": ["date_inscription"],
    "commandes": ["date_commande"],
    "paiements": ["date_paiement"],
    "avis": ["date_avis"],
}

TAILLE_LOT = 50_000   # lignes envoyées à COPY par morceau


class ErreurChargement(Exception):
    """Erreur courte et lisible : fichier absent, schéma absent, écart de vérification."""


# ---------------------------------------------------------------------------
# 1. Préparer en mémoire (aucun accès à la base)
# ---------------------------------------------------------------------------
def _lire_csv_enrichi(dossier: Path, nom: str, run_date: str) -> pd.DataFrame:
    fichier = dossier / nom
    if not fichier.exists():
        raise ErreurChargement(
            f"Fichier enrichi manquant : {nom}. "
            f"Lance d'abord : python -m senmarket_bases.enrichissement --run-date {run_date}"
        )
    return pd.read_csv(fichier, dtype=str)   # tout en texte : les identifiants restent intacts


def _rattacher(df: pd.DataFrame, extra: pd.DataFrame, cle: str, colonne: str,
               nom_fichier: str) -> pd.DataFrame:
    """Ajoute la colonne d'un fichier enrichi, en s'arrêtant si une clé n'a pas de correspondance."""
    if extra[cle].duplicated().any():
        raise ErreurChargement(f"{nom_fichier} contient des {cle} en double.")
    manquants = sorted(set(df[cle]) - set(extra[cle]))
    if manquants:
        raise ErreurChargement(
            f"{nom_fichier} ne couvre pas {len(manquants)} {cle} (exemples : {manquants[:3]})."
        )
    return df.merge(extra[[cle, colonne]], on=cle, how="left", validate="one_to_one")


def _formater(nom: str, df: pd.DataFrame) -> pd.DataFrame:
    """Garde les colonnes à charger, dans le bon ordre, avec les dates au bon format."""
    manquantes = [c for c in COLONNES[nom] if c not in df.columns]
    if manquantes:
        raise ErreurChargement(f"{nom} : colonne(s) manquante(s) {manquantes}.")
    df = df[COLONNES[nom]].copy()
    for colonne in COLONNES_DATE.get(nom, []):
        df[colonne] = pd.to_datetime(df[colonne]).dt.strftime("%Y-%m-%d")
    return df


def preparer(run_date: str, dossier_processed: Path, dossier_enrichi: Path) -> dict[str, pd.DataFrame]:
    """Lit et prépare les huit tables. Renvoie des tableaux prêts pour COPY."""
    try:
        date.fromisoformat(run_date)
    except ValueError:
        raise ErreurChargement(f"Date invalide : '{run_date}'. Format attendu : AAAA-MM-JJ.") from None

    partition = dossier_processed / f"date={run_date}"
    if not partition.exists():
        dispo = ", ".join(sorted(p.name for p in dossier_processed.glob("date=*"))) or "aucune"
        raise ErreurChargement(
            f"Partition introuvable : date={run_date}. Partitions disponibles : {dispo}"
        )
    brut = {}
    for nom in ORDRE:
        fichier = partition / f"{nom}.parquet"
        if not fichier.exists():
            raise ErreurChargement(f"Fichier manquant : {fichier}")
        brut[nom] = pd.read_parquet(fichier)

    enrichi = dossier_enrichi / f"date={run_date}"
    brut["produits"] = _rattacher(
        brut["produits"], _lire_csv_enrichi(enrichi, "stock.csv", run_date),
        "produit_id", "stock", "stock.csv")
    brut["produits"]["stock"] = brut["produits"]["stock"].astype("int64")
    brut["avis"] = _rattacher(
        brut["avis"], _lire_csv_enrichi(enrichi, "avis_commentaires.csv", run_date),
        "avis_id", "commentaire", "avis_commentaires.csv")
    brut["paiements"] = _rattacher(
        brut["paiements"], _lire_csv_enrichi(enrichi, "paiements_references.csv", run_date),
        "paiement_id", "reference_transaction", "paiements_references.csv")

    return {nom: _formater(nom, brut[nom]) for nom in ORDRE}


# ---------------------------------------------------------------------------
# 2. Charger dans PostgreSQL
# ---------------------------------------------------------------------------
def _table(schema: str, nom: str) -> sql.Composable:
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(nom))


def _copier(conn: psycopg.Connection, schema: str, nom: str, df: pd.DataFrame) -> None:
    """Envoie une table en un seul flux COPY (un champ vide non guillemeté devient NULL)."""
    colonnes = sql.SQL(", ").join(sql.Identifier(c) for c in df.columns)
    requete = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, NULL '')").format(
        _table(schema, nom), colonnes)
    with conn.cursor() as curseur:
        with curseur.copy(requete) as copie:
            for debut in range(0, len(df), TAILLE_LOT):
                lot = df.iloc[debut:debut + TAILLE_LOT]
                copie.write(lot.to_csv(index=False, header=False, lineterminator="\n"))


def _somme(conn: psycopg.Connection, schema: str, nom: str) -> int:
    requete = sql.SQL("SELECT coalesce(sum(montant_xof), 0) FROM {}").format(_table(schema, nom))
    return int(conn.execute(requete).fetchone()[0])


def _verifier(conn: psycopg.Connection, schema: str, donnees: dict[str, pd.DataFrame]):
    """Compare la base au Parquet. Lève une erreur au moindre écart (donc annule la transaction)."""
    bilan, ecarts = [], []
    for nom in ORDRE:
        charge = conn.execute(
            sql.SQL("SELECT count(*) FROM {}").format(_table(schema, nom))).fetchone()[0]
        attendu = len(donnees[nom])
        bilan.append((nom, attendu, charge))
        if attendu != charge:
            ecarts.append(f"{nom} : {attendu} lignes attendues, {charge} chargées")
    for nom in ("lignes_commande", "paiements"):
        attendu, charge = int(donnees[nom]["montant_xof"].sum()), _somme(conn, schema, nom)
        if attendu != charge:
            ecarts.append(f"somme de {nom}.montant_xof : {attendu} attendue, {charge} chargée")
    if ecarts:
        raise ErreurChargement("Vérification échouée, chargement annulé : " + " ; ".join(ecarts))
    return bilan


def charger(run_date: str, schema: str, dossier_processed: Path = DOSSIER_PROCESSED,
            dossier_enrichi: Path = DOSSIER_SORTIE, conn: psycopg.Connection | None = None) -> dict:
    """Charge une partition dans un schéma. Renvoie le bilan et la durée."""
    # 1) Tout préparer en mémoire : une erreur de fichier n'ouvre même pas de connexion
    donnees = preparer(run_date, dossier_processed, dossier_enrichi)

    possede = conn is None
    if possede:
        conn = connexion_postgres()
    try:
        conn.autocommit = True   # la transaction est posée explicitement ci-dessous
        existe = conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (schema,)).fetchone()
        if not existe:
            autres = [r[0] for r in conn.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT LIKE 'pg\\_%' AND schema_name <> 'information_schema' "
                "ORDER BY 1")]
            raise ErreurChargement(
                f"Schéma introuvable : {schema}. Schémas existants : {', '.join(autres)}. "
                f"Pour le créer : psql -v schema={schema} < sql/01_schema.sql")

        debut = time.perf_counter()
        try:
            with conn.transaction():          # tout ou rien
                conn.execute("SET LOCAL TIME ZONE 'UTC'")
                tables = sql.SQL(", ").join(_table(schema, nom) for nom in ORDRE)
                conn.execute(sql.SQL("TRUNCATE TABLE {}").format(tables))   # vider
                for nom in ORDRE:             # recharger, parents avant enfants
                    _copier(conn, schema, nom, donnees[nom])
                bilan = _verifier(conn, schema, donnees)   # avant le commit
        except psycopg.Error as erreur:
            raise ErreurChargement(
                f"PostgreSQL a refusé le chargement (SQLSTATE {erreur.sqlstate}) : "
                f"{erreur.diag.message_primary or erreur}. Rien n'a été modifié.") from None
        return {"bilan": bilan, "duree": time.perf_counter() - debut}
    finally:
        if possede:
            conn.close()


def empreintes(conn: psycopg.Connection, schema: str) -> dict[str, str]:
    """Empreinte md5 du contenu de chaque table, hors colonnes d'audit (preuve d'idempotence)."""
    resultat = {}
    for nom in ORDRE:
        colonnes = sql.SQL(", ").join(sql.Identifier(c) for c in COLONNES[nom])
        requete = sql.SQL(
            "SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "
            "FROM (SELECT {} FROM {}) t").format(colonnes, _table(schema, nom))
        resultat[nom] = conn.execute(requete).fetchone()[0]
    return resultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Charge une partition dans PostgreSQL.")
    parser.add_argument("--run-date", required=True, help="date de la partition, AAAA-MM-JJ")
    parser.add_argument("--schema", required=True, help="schéma PostgreSQL cible (principal, volume...)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        resultat = charger(args.run_date, args.schema)
    except (ErreurChargement, ErreurConnexion) as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1
    for nom, attendu, charge in resultat["bilan"]:
        journal.info("%-16s Parquet : %7d | PostgreSQL : %7d", nom, attendu, charge)
    journal.info("Terminé en %.1f s : %s <- date=%s", resultat["duree"], args.schema, args.run_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
