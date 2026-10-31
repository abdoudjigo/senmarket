"""Tests unitaires des règles de nettoyage SenMarket."""

from datetime import date

import pandas as pd
import pytest

from src.senmarket.nettoyage import nettoyer_table


DATE_EXECUTION = date(2026, 10, 28)

CLES_VALIDES = {
    "clients": {"CL001"},
    "vendeurs": {"VEN001"},
    "produits": {"PR001"},
    "commandes": {"CMD001", "CMD002"},
}


def creer_lignes_commande() -> pd.DataFrame:
    """Créer des lignes de commande valides pour les tests."""
    return pd.DataFrame({
        "ligne_commande_id": ["LC001", "LC002"],
        "commande_id": ["CMD001", "CMD002"],
        "produit_id": ["PR001", "PR001"],
        "quantite": [2, 3],
        "prix_unitaire_xof": [1000, 500],
        "montant_xof": [2000, 1500],
    })


def test_rejette_toutes_les_occurrences_d_une_cle_dupliquee():
    """Toutes les lignes portant une clé primaire dupliquée sont rejetées."""
    df = creer_lignes_commande()
    df.loc[1, "ligne_commande_id"] = "LC001"

    acceptes, rejetes = nettoyer_table(
        "lignes_commande", df, DATE_EXECUTION, CLES_VALIDES
    )

    assert len(acceptes) == 0
    assert len(rejetes) == 2
    assert rejetes["raison_rejet"].str.contains(
        "cle_primaire_dupliquee:ligne_commande_id"
    ).all()


def test_rejette_une_quantite_negative():
    """Une quantité négative ne doit pas être acceptée."""
    df = creer_lignes_commande()
    df.loc[0, "quantite"] = -1
    df.loc[0, "montant_xof"] = -1000

    acceptes, rejetes = nettoyer_table(
        "lignes_commande", df, DATE_EXECUTION, CLES_VALIDES
    )

    assert len(acceptes) == 1
    assert len(rejetes) == 1
    assert "quantite_invalide" in rejetes.iloc[0]["raison_rejet"]


def test_rejette_un_montant_incoherent():
    """Le montant doit correspondre à la quantité multipliée par le prix."""
    df = pd.DataFrame({
        "ligne_commande_id": ["LC003"],
        "commande_id": ["CMD001"],
        "produit_id": ["PR001"],
        "quantite": [3],
        "prix_unitaire_xof": [1000],
        "montant_xof": [999],
    })

    acceptes, rejetes = nettoyer_table(
        "lignes_commande", df, DATE_EXECUTION, CLES_VALIDES
    )

    assert acceptes.empty
    assert len(rejetes) == 1
    assert "montant_incoherent" in rejetes.iloc[0]["raison_rejet"]


def test_accepte_une_ligne_valide():
    """Une ligne valide avec des clés étrangères existantes est conservée."""
    df = pd.DataFrame({
        "ligne_commande_id": ["LC004"],
        "commande_id": ["CMD001"],
        "produit_id": ["PR001"],
        "quantite": [4],
        "prix_unitaire_xof": [250],
        "montant_xof": [1000],
    })

    acceptes, rejetes = nettoyer_table(
        "lignes_commande", df, DATE_EXECUTION, CLES_VALIDES
    )

    assert len(acceptes) == 1
    assert rejetes.empty
    assert acceptes.iloc[0]["montant_xof"] == 1000


def test_rejette_une_cle_etrangere_inconnue():
    """Une ligne liée à une commande absente est rejetée."""
    df = pd.DataFrame({
        "ligne_commande_id": ["LC005"],
        "commande_id": ["CMD_INCONNUE"],
        "produit_id": ["PR001"],
        "quantite": [1],
        "prix_unitaire_xof": [500],
        "montant_xof": [500],
    })

    acceptes, rejetes = nettoyer_table(
        "lignes_commande", df, DATE_EXECUTION, CLES_VALIDES
    )

    assert acceptes.empty
    assert len(rejetes) == 1
    assert "cle_etrangere_invalide:commande_id" in (
        rejetes.iloc[0]["raison_rejet"]
    )


def test_refuse_une_colonne_requise_absente():
    """Une erreur de schéma doit interrompre le nettoyage."""
    df = creer_lignes_commande().drop(columns=["quantite"])

    with pytest.raises(ValueError):
        nettoyer_table(
            "lignes_commande", df, DATE_EXECUTION, CLES_VALIDES
        )


def creer_clients() -> pd.DataFrame:
    """Créer un client valide pour les tests."""
    return pd.DataFrame({
        "client_id": ["CLI0000001"],
        "nom_client": ["Aïssatou Diop"],
        "email": ["aissatou.diop1@gmail.com"],
        "telephone": ["+221 77 123 45 67"],
        "ville": ["Dakar"],
        "region": ["Dakar"],
        "date_inscription": ["2026-03-10"],
    })


@pytest.mark.parametrize("colonne", ["email", "telephone"])
@pytest.mark.parametrize("vide", [None, ""])
def test_client_sans_email_ou_telephone_est_accepte(colonne, vide):
    """Email et téléphone sont facultatifs : vides, ils ne rejettent pas le client."""
    df = creer_clients()
    df.loc[0, colonne] = vide

    acceptes, rejetes = nettoyer_table("clients", df, DATE_EXECUTION, CLES_VALIDES)

    assert len(acceptes) == 1
    assert len(rejetes) == 0
    valeur = acceptes[colonne].iloc[0]
    # La cellule reste vide : elle n'est pas remplacée par « Inconnue ».
    assert pd.isna(valeur) or valeur == ""


def test_client_sans_ville_recoit_inconnue():
    """Une ville manquante ne supprime pas le client : elle devient « Inconnue »."""
    df = creer_clients()
    df.loc[0, "ville"] = None

    acceptes, rejetes = nettoyer_table("clients", df, DATE_EXECUTION, CLES_VALIDES)

    assert len(rejetes) == 0
    assert acceptes["ville"].iloc[0] == "Inconnue"


def test_client_sans_nom_est_rejete():
    """Le nom reste obligatoire : un client sans nom est mis en quarantaine."""
    df = creer_clients()
    df.loc[0, "nom_client"] = None

    acceptes, rejetes = nettoyer_table("clients", df, DATE_EXECUTION, CLES_VALIDES)

    assert len(acceptes) == 0
    assert len(rejetes) == 1
    assert "champ_obligatoire_absent:nom_client" in rejetes["raison_rejet"].iloc[0]
