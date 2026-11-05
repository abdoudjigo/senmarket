"""Tests des connexions aux trois bases.

Ils exigent que PostgreSQL, MongoDB et Redis tournent (dc up -d, puis dc ps en healthy).
"""
import pytest

from senmarket_bases.connexions import (
    ErreurConnexion,
    client_mongo,
    client_redis,
    connexion_postgres,
)

# Mot de passe volontairement faux, reconnaissable pour vérifier qu'il ne fuit pas
FAUX_MOT_DE_PASSE = "mot-de-passe-bidon-xyz"


# --- Cas qui doivent réussir : une base qui répond -------------------------------

def test_postgres_repond():
    conn = connexion_postgres()
    try:
        assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        conn.close()


def test_mongo_repond():
    client = client_mongo()
    try:
        assert client.admin.command("ping")["ok"] == 1
    finally:
        client.close()


def test_redis_repond():
    client = client_redis()
    try:
        assert client.ping() is True
    finally:
        client.close()


# --- Cas d'erreur : mauvais mot de passe -----------------------------------------
# monkeypatch change la variable pour ce seul test, puis la remet toute seule.

def test_postgres_mauvais_mot_de_passe(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", FAUX_MOT_DE_PASSE)
    with pytest.raises(ErreurConnexion, match="PostgreSQL"):
        connexion_postgres()


def test_mongo_mauvais_mot_de_passe(monkeypatch):
    monkeypatch.setenv("MONGO_PASSWORD", FAUX_MOT_DE_PASSE)
    with pytest.raises(ErreurConnexion, match="MongoDB"):
        client_mongo()


def test_redis_mauvais_mot_de_passe(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", FAUX_MOT_DE_PASSE)
    with pytest.raises(ErreurConnexion, match="Redis"):
        client_redis()


# --- Cas d'erreur : réglage manquant ---------------------------------------------

def test_variable_absente_nomme_la_variable(monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ErreurConnexion, match="POSTGRES_PASSWORD"):
        connexion_postgres()


# --- Sécurité : un message d'erreur finit dans des journaux ----------------------

def test_le_mot_de_passe_ne_fuit_pas_dans_le_message(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", FAUX_MOT_DE_PASSE)
    with pytest.raises(ErreurConnexion) as erreur:
        connexion_postgres()
    assert FAUX_MOT_DE_PASSE not in str(erreur.value)
