"""Connexions aux trois bases + chemin des données. Aucun mot de passe dans le code : tout vient de .env."""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent          # le dossier module_1/
load_dotenv(RACINE / ".env")


def _var(nom):
    valeur = os.getenv(nom)
    if not valeur:
        raise SystemExit(f"Variable {nom} absente : copie .env.example en .env et remplis-le.")
    return valeur


def pg(schema=None):
    """Connexion PostgreSQL. `schema` = quel jeu de tables utiliser (principal, volume...)."""
    import psycopg
    options = f"-c search_path={schema}" if schema else None
    try:
        return psycopg.connect(
            host="localhost", port=5432, user=_var("POSTGRES_USER"),
            password=_var("POSTGRES_PASSWORD"), dbname=os.getenv("POSTGRES_DB", "senmarket"),
            options=options, connect_timeout=5)
    except psycopg.OperationalError as e:
        raise SystemExit(f"PostgreSQL injoignable ({str(e).splitlines()[0]}). "
                         "Lance les bases : docker compose --env-file .env -f infra/docker-compose.yml up -d")


def mongo():
    import pymongo
    uri = (f"mongodb://{quote_plus(_var('MONGO_USER'))}:{quote_plus(_var('MONGO_PASSWORD'))}"
           "@localhost:27017/?authSource=admin")
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except Exception as e:
        raise SystemExit(f"MongoDB injoignable ({type(e).__name__}). Les bases sont-elles lancées ? Le .env est-il bon ?")
    return client


def redis_():
    import redis
    r = redis.Redis(host="localhost", port=6379, password=_var("REDIS_PASSWORD"),
                    decode_responses=True, socket_connect_timeout=3)
    try:
        r.ping()
    except Exception as e:
        raise SystemExit(f"Redis injoignable ({type(e).__name__}). Les bases sont-elles lancées ? Le .env est-il bon ?")
    return r


def dossier_partition(run_date):
    """Dossier des Parquet nettoyés du module 0 pour une date."""
    base = Path(os.getenv("SENMARKET_DONNEES",
                          RACINE.parent / "module_0" / "projet" / "data" / "processed"))
    dossier = base / f"date={run_date}"
    if not dossier.exists():
        dispo = sorted(p.name for p in base.glob("date=*")) if base.exists() else []
        raise SystemExit(f"Partition {run_date} introuvable dans {base}. Disponibles : {dispo or 'aucune'}. "
                         "Lance d'abord le pipeline du module 0.")
    return dossier
