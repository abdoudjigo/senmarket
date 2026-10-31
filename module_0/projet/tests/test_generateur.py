"""Tests du générateur : catalogue cohérent et coordonnées des clients."""

import re
from datetime import date

import pytest

from src.senmarket import generateur as gen


@pytest.fixture(scope="module")
def tables():
    """Jeu sans défaut, assez petit pour rester rapide."""
    return gen.generer_donnees(rows=2_000, run_date=date(2026, 10, 29))


def produits_incoherents(produits):
    """Renvoyer les produits dont le nom n'appartient pas à leur catégorie."""
    mauvais = []
    for _, produit in produits.iterrows():
        autorises = [nom for nom, _ in gen.CATALOGUE.get(produit["categorie"], [])]
        if produit["nom_produit"] not in autorises:
            mauvais.append(produit["nom_produit"])
    return mauvais


def test_produit_dans_la_bonne_categorie(tables):
    assert produits_incoherents(tables["produits"]) == []


def test_le_garde_fou_detecte_une_incoherence(tables):
    """Un garde-fou qu'on n'a jamais vu refuser n'est pas testé."""
    produits = tables["produits"].copy()
    produits.loc[produits["nom_produit"] == "Sucre", "categorie"] = "Vêtements"
    assert produits_incoherents(produits) == ["Sucre"]


def test_un_nom_de_produit_n_existe_que_dans_une_categorie():
    noms = [nom for produits in gen.CATALOGUE.values() for nom, _ in produits]
    assert len(noms) == len(set(noms))


def test_catalogue_complet_et_prix_entiers(tables):
    produits = tables["produits"]
    assert len(produits) == 40
    assert produits["prix_catalogue_xof"].between(500, 100_000).all()
    assert str(produits["prix_catalogue_xof"].dtype).startswith("int")


def test_colonnes_clients(tables):
    assert list(tables["clients"].columns) == [
        "client_id", "nom_client", "email", "telephone",
        "ville", "region", "date_inscription",
    ]


def test_emails_valides_et_uniques(tables):
    emails = tables["clients"]["email"]
    modele = re.compile(r"^[a-z0-9.]+@[a-z0-9.\-]+\.[a-z]{2,}$")
    assert emails.map(lambda e: bool(modele.match(e))).all()
    assert emails.is_unique


def test_telephones_au_format_senegalais(tables):
    modele = re.compile(r"^\+221 7[05678] \d{3} \d{2} \d{2}$")
    assert tables["clients"]["telephone"].map(lambda t: bool(modele.match(t))).all()


def test_erreur_rows_invalide():
    with pytest.raises(ValueError, match="supérieur à zéro"):
        gen.generer_donnees(rows=0)


@pytest.fixture(scope="module")
def tables_volume():
    """Jeu plus gros, pour vérifier des taux à quelques points près."""
    return gen.generer_donnees(rows=20_000, run_date=date(2026, 10, 29))


def test_environ_2_pour_cent_des_commandes_sans_paiement(tables_volume):
    commandes = tables_volume["commandes"]
    payees = set(tables_volume["paiements"]["commande_id"])
    part = (~commandes["commande_id"].isin(payees)).mean()
    assert 0.01 <= part <= 0.03


def test_au_plus_un_paiement_par_commande(tables_volume):
    assert tables_volume["paiements"]["commande_id"].is_unique


def test_environ_1_pour_cent_des_paiements_avec_ecart(tables_volume):
    totaux = tables_volume["lignes_commande"].groupby("commande_id")["montant_xof"].sum()
    paiements = tables_volume["paiements"]
    ecart = paiements["montant_xof"] != paiements["commande_id"].map(totaux)
    assert 0.003 <= ecart.mean() <= 0.02


def test_commande_jamais_avant_l_inscription(tables_volume):
    commandes = tables_volume["commandes"].merge(
        tables_volume["clients"][["client_id", "date_inscription"]], on="client_id"
    )
    assert len(commandes) == len(tables_volume["commandes"])
    assert (commandes["date_commande"] >= commandes["date_inscription"]).all()
    assert (commandes["date_commande"] <= "2026-10-29").all()


def test_avis_sur_commande_livree_apres_la_commande(tables_volume):
    avis = tables_volume["avis"].merge(
        tables_volume["commandes"][["commande_id", "statut", "date_commande"]],
        on="commande_id",
    )
    assert len(avis) == len(tables_volume["avis"])
    assert (avis["statut"] == "livrée").all()
    assert (avis["date_avis"] >= avis["date_commande"]).all()
    assert (avis["date_avis"] <= "2026-10-29").all()


def test_avis_porte_sur_un_produit_de_la_commande(tables_volume):
    lignes = tables_volume["lignes_commande"]
    paires = set(zip(lignes["commande_id"], lignes["produit_id"]))
    avis = tables_volume["avis"]
    assert all(
        (c, p) in paires for c, p in zip(avis["commande_id"], avis["produit_id"])
    )


from pandas.testing import assert_frame_equal


def test_graine_du_jour():
    assert gen.graine_du_jour(date(2026, 10, 29), graine_base=42) == [42, 20261029]


def test_meme_date_memes_donnees():
    """Reproductibilité : deux générations pour la même date sont identiques."""
    a = gen.generer_donnees(rows=500, run_date=date(2026, 10, 29))
    b = gen.generer_donnees(rows=500, run_date=date(2026, 10, 29))
    for nom in ("clients", "commandes", "lignes_commande"):
        assert_frame_equal(a[nom], b[nom])


def test_dates_differentes_jeux_independants():
    """Deux dates donnent des clients différents (ce n'était pas le cas avant)."""
    a = gen.generer_donnees(rows=500, run_date=date(2026, 10, 29))
    b = gen.generer_donnees(rows=500, run_date=date(2026, 11, 2))
    noms_a = a["clients"]["nom_client"].head(50).tolist()
    noms_b = b["clients"]["nom_client"].head(50).tolist()
    assert noms_a != noms_b
