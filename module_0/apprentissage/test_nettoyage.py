
import pandas as pd
from nettoyage import nettoyer_commandes


def test_supprime_doublons():
    df = pd.DataFrame({
        "commande_id": [1, 1],
        "ville": ["Dakar", "Dakar"],
        "quantite": [2, 2],
        "prix_unitaire": [1000, 1000],
        "montant": [2000, 2000]
    })
    resultat = nettoyer_commandes(df)
    assert len(resultat) == 1


def test_supprime_quantites_negatives():
    df = pd.DataFrame({
        "commande_id": [1, 2],
        "ville": ["Dakar", "Thies"],
        "quantite": [2, -1],
        "prix_unitaire": [1000, 1000],
        "montant": [2000, -1000]
    })
    resultat = nettoyer_commandes(df)
    assert (resultat["quantite"] > 0).all()


def test_recalcule_montant():
    df = pd.DataFrame({
        "commande_id": [1],
        "ville": ["Dakar"],
        "quantite": [3],
        "prix_unitaire": [1000],
        "montant": [999]
    })
    resultat = nettoyer_commandes(df)
    assert resultat.iloc[0]["montant"] == 3000
