"""Connexions aux trois bases de SenMarket (PostgreSQL, MongoDB, Redis).

Tous les réglages viennent du fichier .env : aucun identifiant n'est écrit dans le code.
"""
import os
from pathlib import Path

import psycopg
import pymongo
import redis
from dotenv import load_dotenv
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

# Le .env est à la racine de module_1 :
# connexions.py -> senmarket_bases -> src -> module_1
RACINE = Path(__file__).resolve().parents[2]

# Chargé une seule fois, à l'import. Une variable déjà définie dans le shell
# n'est PAS écrasée par le .env.
load_dotenv(RACINE / ".env")


class ErreurConnexion(Exception):
    """Erreur courte et lisible levée quand une base est inutilisable."""


def _lire(nom: str, defaut: str | None = None) -> str:
    """Lit une variable d'environnement ; échoue clairement si elle est absente ou vide."""
    valeur = os.environ.get(nom, defaut)
    if not valeur:
        raise ErreurConnexion(
            f"Variable {nom} absente ou vide : renseigne-la dans {RACINE / '.env'}"
        )
    return valeur


def connexion_postgres() -> psycopg.Connection:
    """Renvoie une connexion PostgreSQL ouverte (à fermer par l'appelant)."""
    hote = _lire("POSTGRES_HOST", "127.0.0.1")
    port = int(_lire("POSTGRES_PORT", "5432"))
    try:
        return psycopg.connect(
            host=hote,
            port=port,
            user=_lire("POSTGRES_USER"),
            password=_lire("POSTGRES_PASSWORD"),
            dbname=_lire("POSTGRES_DB"),
            connect_timeout=5,
        )
    except psycopg.OperationalError:
        # "from None" masque la longue chaîne technique : le message suffit
        raise ErreurConnexion(
            f"PostgreSQL ({hote}:{port}) : connexion impossible. "
            "Causes probables : conteneur arrêté (dc ps), ou POSTGRES_USER / "
            "POSTGRES_PASSWORD différents de ceux de la première création du volume."
        ) from None


def client_mongo() -> pymongo.MongoClient:
    """Renvoie un client MongoDB qui a réellement répondu à un ping."""
    hote = _lire("MONGO_HOST", "127.0.0.1")
    port = int(_lire("MONGO_PORT", "27017"))
    client = pymongo.MongoClient(
        host=hote,
        port=port,
        username=_lire("MONGO_USER"),
        password=_lire("MONGO_PASSWORD"),
        authSource="admin",
        serverSelectionTimeoutMS=3000,
    )
    try:
        # pymongo se connecte paresseusement : sans ce ping, un mauvais
        # mot de passe passerait inaperçu
        client.admin.command("ping")
    except PyMongoError:
        client.close()
        raise ErreurConnexion(
            f"MongoDB ({hote}:{port}) : connexion impossible. "
            "Causes probables : conteneur arrêté (dc ps), ou MONGO_USER / "
            "MONGO_PASSWORD incorrects."
        ) from None
    return client


def client_redis() -> redis.Redis:
    """Renvoie un client Redis qui a réellement répondu à un PING."""
    hote = _lire("REDIS_HOST", "127.0.0.1")
    port = int(_lire("REDIS_PORT", "6379"))
    client = redis.Redis(
        host=hote,
        port=port,
        password=_lire("REDIS_PASSWORD"),
        socket_connect_timeout=3,
        decode_responses=True,
    )
    try:
        # redis-py est aussi paresseux : le PING force l'authentification
        client.ping()
    except RedisError:
        client.close()
        raise ErreurConnexion(
            f"Redis ({hote}:{port}) : connexion impossible. "
            "Causes probables : conteneur arrêté (dc ps), ou REDIS_PASSWORD incorrect."
        ) from None
    return client
