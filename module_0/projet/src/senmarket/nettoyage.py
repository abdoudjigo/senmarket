"""Cleaning, validation and quarantine of the SenMarket tables.

Each table is split into accepted rows and rejected rows. Every rejected row
keeps its reasons in the ``raison_rejet`` column so that no information is
silently lost. Tables are processed in dependency order, so foreign keys are
validated against the *accepted* rows of the parent tables.

Run it with:
    python -m src.senmarket.nettoyage --run-date 2026-10-28
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from .chemins import dossier_partition

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema configuration
# ---------------------------------------------------------------------------

# Processing order matters: parents must be cleaned before their children.
TABLES = (
    "clients",
    "vendeurs",
    "produits",
    "commandes",
    "lignes_commande",
    "paiements",
    "avis",
    "navigation",
)

CLES_PRIMAIRES = {
    "clients": "client_id",
    "vendeurs": "vendeur_id",
    "produits": "produit_id",
    "commandes": "commande_id",
    "lignes_commande": "ligne_commande_id",
    "paiements": "paiement_id",
    "avis": "avis_id",
    "navigation": "evenement_id",
}

COLONNES_REQUISES = {
    "clients": ("client_id", "nom_client", "email", "telephone", "ville", "region", "date_inscription"),
    "vendeurs": ("vendeur_id", "nom_vendeur", "ville", "region"),
    "produits": ("produit_id", "nom_produit", "categorie", "vendeur_id", "prix_catalogue_xof", "actif"),
    "commandes": ("commande_id", "client_id", "date_commande", "statut"),
    "lignes_commande": ("ligne_commande_id", "commande_id", "produit_id", "quantite", "prix_unitaire_xof", "montant_xof"),
    "paiements": ("paiement_id", "commande_id", "methode_paiement", "statut_paiement", "montant_xof", "date_paiement"),
    "avis": ("avis_id", "client_id", "produit_id", "commande_id", "note", "date_avis"),
    "navigation": ("evenement_id", "session_id", "client_id", "produit_id", "type_evenement", "date_evenement"),
}

COLONNES_DATE = {
    "clients": ("date_inscription",),
    "commandes": ("date_commande",),
    "paiements": ("date_paiement",),
    "avis": ("date_avis",),
    "navigation": ("date_evenement",),
}

COLONNES_NUMERIQUES = {
    "produits": ("prix_catalogue_xof",),
    "lignes_commande": ("quantite", "prix_unitaire_xof", "montant_xof"),
    "paiements": ("montant_xof",),
    "avis": ("note",),
}

# Columns that may be empty without rejecting the row.
CHAMPS_OPTIONNELS = {
    # A missing city/region is replaced by "Inconnue" instead of dropping the client.
    # email et telephone sont facultatifs : vides, ils ne rejettent pas la ligne.
    "clients": frozenset({"ville", "region", "email", "telephone"}),
    # Navigation events can be anonymous or not linked to a product.
    "navigation": frozenset({"client_id", "produit_id"}),
}

# child table -> {foreign key column: parent table}
RELATIONS = {
    "produits": {"vendeur_id": "vendeurs"},
    "commandes": {"client_id": "clients"},
    "lignes_commande": {"commande_id": "commandes", "produit_id": "produits"},
    "paiements": {"commande_id": "commandes"},
    "avis": {"client_id": "clients", "produit_id": "produits", "commande_id": "commandes"},
    "navigation": {"client_id": "clients", "produit_id": "produits"},
}

PRIX_MAX_XOF = 1_000_000
COLONNE_MOTIF_REJET = "raison_rejet"
VALEUR_INCONNUE = "Inconnue"


# ---------------------------------------------------------------------------
# Reading and validating inputs
# ---------------------------------------------------------------------------

def verifier_table_connue(nom_table: str) -> None:
    """Refuse a table that is not configured in the pipeline."""
    if nom_table not in COLONNES_REQUISES:
        raise ValueError(f"Table SenMarket inconnue : {nom_table!r}")


def verifier_schema(nom_table: str, df: pd.DataFrame) -> None:
    """Check that all expected columns exist and the reserved column is absent."""
    verifier_table_connue(nom_table)
    manquantes = sorted(set(COLONNES_REQUISES[nom_table]) - set(df.columns))
    if manquantes:
        raise ValueError(
            f"Schéma invalide pour {nom_table}. Colonnes manquantes : {manquantes}"
        )
    if COLONNE_MOTIF_REJET in df.columns:
        raise ValueError(
            f"La colonne réservée {COLONNE_MOTIF_REJET!r} ne doit pas être "
            "présente dans les données brutes."
        )


def verifier_partition_brute(dossier_brut: Path) -> None:
    """Fail early, with an actionable message, if the raw partition is unusable.

    This runs BEFORE any output folder is created, so a missing input never
    leaves empty output folders behind.
    """
    dossier_brut = Path(dossier_brut)
    if not dossier_brut.is_dir():
        parent = dossier_brut.parent
        disponibles = (
            sorted(p.name.removeprefix("date=") for p in parent.glob("date=*") if p.is_dir())
            if parent.is_dir()
            else []
        )
        raise FileNotFoundError(
            f"Partition brute introuvable : {dossier_brut}. "
            f"Partitions disponibles : {', '.join(disponibles) or 'aucune'}. "
            "Pour la créer : python -m src.senmarket.generateur --run-date AAAA-MM-JJ"
        )

    manquants = [t for t in TABLES if not (dossier_brut / f"{t}.csv").is_file()]
    if manquants:
        raise FileNotFoundError(
            f"Partition brute incomplète : {dossier_brut}. "
            f"Fichiers manquants : {[t + '.csv' for t in manquants]}"
        )


def lire_table_brute(dossier_brut: Path, nom_table: str) -> pd.DataFrame:
    """Read a raw CSV with every column as text (no silent type guessing)."""
    verifier_table_connue(nom_table)
    chemin = Path(dossier_brut) / f"{nom_table}.csv"
    if not chemin.is_file():
        raise FileNotFoundError(f"Fichier requis introuvable : {chemin}")
    return pd.read_csv(chemin, dtype=str)


def preparer_types(nom_table: str, df: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric and date columns; invalid values become NaN/NaT.

    The invalid values are NOT dropped here: they are detected afterwards and
    rejected with an explicit reason.
    """
    verifier_table_connue(nom_table)
    resultat = df.copy()

    for colonne in COLONNES_NUMERIQUES.get(nom_table, ()):
        if colonne in resultat.columns:
            resultat[colonne] = pd.to_numeric(resultat[colonne], errors="coerce")

    for colonne in COLONNES_DATE.get(nom_table, ()):
        if colonne in resultat.columns:
            resultat[colonne] = pd.to_datetime(resultat[colonne], errors="coerce")

    return resultat


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _masque_valeurs_vides(valeurs: pd.Series) -> pd.Series:
    """Flag nulls, empty strings and whitespace-only strings."""
    masque = valeurs.isna()
    if pd.api.types.is_string_dtype(valeurs.dtype) or pd.api.types.is_object_dtype(valeurs.dtype):
        texte = valeurs.astype("string").str.strip()
        masque = masque | texte.eq("").fillna(False)
    return masque.fillna(False)


def _normaliser_references(valeurs: Iterable[object]) -> set[str]:
    """Turn accepted identifiers into a set of stripped strings for FK checks."""
    return {str(v).strip() for v in valeurs if pd.notna(v) and str(v).strip()}


def _normaliser_localisation(resultat: pd.DataFrame) -> None:
    """Replace missing city/region by an explicit value (in place)."""
    for colonne in ("ville", "region"):
        valeurs = resultat[colonne].astype("string").str.strip()
        resultat[colonne] = valeurs.mask(valeurs.isna() | valeurs.eq(""), VALEUR_INCONNUE)


def _typer_mesures_entieres(nom_table: str, acceptes: pd.DataFrame) -> None:
    """Cast integral measures (XOF amounts, quantities, ratings) to int64, in place.

    to_numeric yields float64 as soon as one NaN was present before rejection;
    clean integer types matter for Parquet, PostgreSQL and Spark later on.
    """
    for colonne in COLONNES_NUMERIQUES.get(nom_table, ()):
        serie = acceptes[colonne]
        if len(serie) and (serie % 1 == 0).all():
            acceptes[colonne] = serie.astype("int64")


# ---------------------------------------------------------------------------
# Cleaning one table
# ---------------------------------------------------------------------------

def nettoyer_table(
    nom_table: str,
    df: pd.DataFrame,
    run_date: date,
    cles_valides: dict[str, set[str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(acceptes, rejetes)``; each rejected row carries its reasons.

    A row can have several reasons, separated by ``;``. All occurrences of a
    duplicated primary key are rejected, because there is no safe way to pick
    which one to keep.

    ``cles_valides`` maps a parent table name to the set of its accepted keys.
    """
    verifier_schema(nom_table, df)

    # Fresh index: guarantees a stable row <-> reasons mapping even if the
    # incoming DataFrame has a duplicated index.
    resultat = preparer_types(nom_table, df.reset_index(drop=True))
    index_lignes = resultat.index
    raisons: dict[int, list[str]] = {index: [] for index in index_lignes}

    def rejeter(masque: pd.Series, raison: str) -> None:
        """Append ``raison`` to every row flagged by ``masque``."""
        masque = masque.reindex(index_lignes).fillna(False).astype(bool)
        for index in index_lignes[masque.to_numpy()]:
            raisons[index].append(raison)

    optionnels = CHAMPS_OPTIONNELS.get(nom_table, frozenset())

    # 1. Mandatory fields.
    for colonne in COLONNES_REQUISES[nom_table]:
        if colonne not in optionnels:
            rejeter(_masque_valeurs_vides(resultat[colonne]), f"champ_obligatoire_absent:{colonne}")

    # 2. Primary key: missing and duplicated are two distinct anomalies.
    cle = CLES_PRIMAIRES[nom_table]
    rejeter(_masque_valeurs_vides(resultat[cle]), f"cle_primaire_absente:{cle}")
    valeurs_cle = resultat[cle].astype("string").str.strip()
    masque_doublons = valeurs_cle.notna() & valeurs_cle.ne("") & valeurs_cle.duplicated(keep=False)
    rejeter(masque_doublons, f"cle_primaire_dupliquee:{cle}")

    # 3. Invalid dates and dates later than the run date.
    borne = pd.Timestamp(run_date)
    for colonne in COLONNES_DATE.get(nom_table, ()):
        rejeter(resultat[colonne].isna(), f"date_invalide:{colonne}")
        rejeter(resultat[colonne].notna() & (resultat[colonne] > borne), f"date_future:{colonne}")

    # 4. Business rules specific to each table.
    if nom_table == "produits":
        prix = resultat["prix_catalogue_xof"]
        rejeter(prix.isna() | prix.le(0), "prix_catalogue_non_positif_ou_invalide")
        rejeter(prix.gt(PRIX_MAX_XOF), "prix_catalogue_outlier")

    elif nom_table == "lignes_commande":
        quantite = resultat["quantite"]
        prix = resultat["prix_unitaire_xof"]
        montant = resultat["montant_xof"]
        rejeter(quantite.isna() | quantite.le(0), "quantite_invalide")
        rejeter(prix.isna() | prix.le(0), "prix_unitaire_invalide")
        rejeter(prix.gt(PRIX_MAX_XOF), "prix_unitaire_outlier")
        rejeter(montant.isna(), "montant_non_numerique")
        # The amount must equal quantity x unit price.
        montant_calcule = quantite * prix
        incoherent = montant.notna() & montant_calcule.notna() & montant.ne(montant_calcule)
        rejeter(incoherent, "montant_incoherent")

    elif nom_table == "paiements":
        montant = resultat["montant_xof"]
        rejeter(montant.isna() | montant.lt(0), "montant_paiement_invalide")

    elif nom_table == "avis":
        note = resultat["note"]
        rejeter(note.isna() | ~note.between(1, 5), "note_hors_intervalle")

    # 5. A missing location must not delete a customer.
    if nom_table == "clients":
        _normaliser_localisation(resultat)

    # 6. Foreign keys: only keys accepted in the parent table are valid.
    for colonne, table_parent in RELATIONS.get(nom_table, {}).items():
        references = _normaliser_references(cles_valides.get(table_parent, set()))
        valeurs = resultat[colonne].astype("string").str.strip()
        vide = _masque_valeurs_vides(resultat[colonne])
        if colonne in optionnels:
            # Optional FK: only a PRESENT value that is unknown is an error.
            invalides = ~vide & ~valeurs.isin(references)
        else:
            invalides = vide | ~valeurs.isin(references)
        rejeter(invalides, f"cle_etrangere_invalide:{colonne}")

    # 7. Split accepted / rejected and keep the reasons for traceability.
    resultat[COLONNE_MOTIF_REJET] = [";".join(raisons[index]) for index in index_lignes]
    masque_rejet = resultat[COLONNE_MOTIF_REJET].ne("")
    colonnes_sortie = list(df.columns)
    rejetes = resultat.loc[masque_rejet, colonnes_sortie + [COLONNE_MOTIF_REJET]].copy()
    acceptes = resultat.loc[~masque_rejet, colonnes_sortie].copy()

    _typer_mesures_entieres(nom_table, acceptes)

    # Dates are exported as ISO strings, in both accepted and rejected files.
    for colonne in COLONNES_DATE.get(nom_table, ()):
        for sortie in (acceptes, rejetes):
            sortie[colonne] = pd.to_datetime(sortie[colonne], errors="coerce").dt.strftime("%Y-%m-%d")

    LOGGER.info(
        "%s | entrée=%d | acceptées=%d | rejetées=%d",
        nom_table, len(df), len(acceptes), len(rejetes),
    )
    return acceptes.reset_index(drop=True), rejetes.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cleaning a whole partition
# ---------------------------------------------------------------------------

def _ecrire_parquet(df: pd.DataFrame, chemin: Path, nom_table: str) -> None:
    """Write Parquet with real datetime columns (CSV keeps ISO strings)."""
    sortie = df.copy()
    for colonne in COLONNES_DATE.get(nom_table, ()):
        sortie[colonne] = pd.to_datetime(sortie[colonne], errors="coerce")
    sortie.to_parquet(chemin, index=False)


def _compter_motifs(nom_table: str, rejetes: pd.DataFrame) -> list[dict[str, object]]:
    """Count rejected rows per reason (a row with 2 reasons counts in both)."""
    if rejetes.empty:
        return []
    compteurs = rejetes[COLONNE_MOTIF_REJET].str.split(";").explode().value_counts()
    return [
        {"table": nom_table, "motif": motif, "nombre": int(nombre)}
        for motif, nombre in compteurs.items()
    ]


def nettoyer_partition(
    run_date: date,
    dossier_brut: Path | None = None,
    racine_donnees: Path | None = None,
) -> dict[str, dict[str, int]]:
    """Clean every table of one dated partition and write all deliverables.

    Outputs (under ``<data>/processed|rejected/date=<run_date>/``):
      - ``<table>.csv`` and ``<table>.parquet``   accepted rows
      - ``<table>_rejetes.csv``                   quarantined rows + reasons
      - ``bilan_nettoyage.csv``                   counts per table
      - ``motifs_rejet.csv``                      counts per rejection reason

    Everything is computed in memory first and written afterwards, so a
    failure while reading or validating never leaves half-written outputs.
    """
    if dossier_brut is None:
        dossier_brut = dossier_partition("raw", run_date, racine_donnees)
    dossier_brut = Path(dossier_brut)
    dossier_propre = dossier_partition("processed", run_date, racine_donnees)
    dossier_rejets = dossier_partition("rejected", run_date, racine_donnees)

    # Phase 0: check inputs BEFORE creating anything.
    verifier_partition_brute(dossier_brut)

    # Phase 1: clean all tables in dependency order (in memory).
    cles_valides: dict[str, set[str]] = {}
    resultats: dict[str, tuple[int, pd.DataFrame, pd.DataFrame]] = {}
    for nom_table in TABLES:
        brut = lire_table_brute(dossier_brut, nom_table)
        propre, rejete = nettoyer_table(nom_table, brut, run_date, cles_valides)
        cles_valides[nom_table] = _normaliser_references(propre[CLES_PRIMAIRES[nom_table]])
        resultats[nom_table] = (len(brut), propre, rejete)

    # Phase 2: write everything.
    dossier_propre.mkdir(parents=True, exist_ok=True)
    dossier_rejets.mkdir(parents=True, exist_ok=True)

    bilan: dict[str, dict[str, int]] = {}
    motifs: list[dict[str, object]] = []
    for nom_table, (nb_brut, propre, rejete) in resultats.items():
        propre.to_csv(dossier_propre / f"{nom_table}.csv", index=False)
        _ecrire_parquet(propre, dossier_propre / f"{nom_table}.parquet", nom_table)
        # Always write the rejects file, even when empty, so a stale file from
        # a previous run can never survive a clean re-run.
        rejete.to_csv(dossier_rejets / f"{nom_table}_rejetes.csv", index=False)

        bilan[nom_table] = {
            "lignes_brutes": nb_brut,
            "lignes_acceptees": len(propre),
            "lignes_rejetees": len(rejete),
        }
        motifs.extend(_compter_motifs(nom_table, rejete))

    pd.DataFrame.from_dict(bilan, orient="index").to_csv(
        dossier_rejets / "bilan_nettoyage.csv", index_label="table"
    )
    pd.DataFrame(motifs, columns=["table", "motif", "nombre"]).to_csv(
        dossier_rejets / "motifs_rejet.csv", index=False
    )

    LOGGER.info("Données propres : %s", dossier_propre)
    LOGGER.info("Quarantaine : %s", dossier_rejets)
    return bilan


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point: clean one dated partition."""
    parser = argparse.ArgumentParser(description="Nettoyer les tables SenMarket.")
    parser.add_argument(
        "--run-date",
        type=date.fromisoformat,
        required=True,
        help="Date de la partition au format AAAA-MM-JJ.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        bilan = nettoyer_partition(args.run_date)
    except FileNotFoundError as erreur:
        raise SystemExit(f"ERREUR : {erreur}")

    print("\n=== BILAN DU NETTOYAGE ===")
    print(pd.DataFrame.from_dict(bilan, orient="index").to_string())


if __name__ == "__main__":
    main()