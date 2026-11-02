"""Tests du schéma PostgreSQL : chaque contrainte refuse ce qu'elle doit refuser.

Ils exigent que PostgreSQL tourne (dc up -d). Tout se passe dans un schéma jetable
(essai_tests), supprimé à la fin : principal et volume ne sont jamais touchés.
"""
import pytest

from senmarket_bases.connexions import connexion_postgres
from senmarket_bases.preuves_contraintes import (
    REFUS,
    creer_schema,
    executer_comportements,
    preparer_donnees,
    supprimer_schema,
)

SCHEMA = "essai_tests"


@pytest.fixture(scope="module")
def conn():
    """Une connexion sur un schéma jetable, supprimé à la fin des tests."""
    connexion = connexion_postgres()
    connexion.autocommit = True
    creer_schema(connexion, SCHEMA)
    preparer_donnees(connexion)
    yield connexion
    supprimer_schema(connexion, SCHEMA)
    connexion.close()


@pytest.mark.parametrize(
    "sql, attendu", [(sql, attendu) for _, _, sql, attendu in REFUS],
    ids=[f"{categorie}: {description}" for categorie, description, _, _ in REFUS],
)
def test_la_contrainte_refuse(conn, sql, attendu):
    with pytest.raises(attendu):
        conn.execute(sql)


def test_comportements_attendus(conn):
    """Les ON DELETE, les NULL multiples sous UNIQUE et le déclencheur se comportent comme prévu."""
    ecarts = [description for description, _, ok in executer_comportements(conn) if not ok]
    assert ecarts == []


def test_impossible_de_supprimer_les_vrais_schemas(conn):
    """Garde-fou : jamais de suppression de principal ni de volume."""
    for nom in ("principal", "volume"):
        with pytest.raises(ValueError):
            supprimer_schema(conn, nom)
