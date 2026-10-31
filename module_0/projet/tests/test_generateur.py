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
