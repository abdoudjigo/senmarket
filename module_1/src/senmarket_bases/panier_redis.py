"""Redis usage: shopping cart (Hash + TTL) and cache-aside for the top products."""
import json
import time

from senmarket_bases.connexions import client_redis, connexion_postgres

TTL_PANIER = 3600  # one hour, renewed on every action
TTL_CACHE = 60


def ajouter(client_id: str, produit_id: str, quantite: int = 1) -> None:
    r, cle = client_redis(), f"panier:{client_id}"
    r.hincrby(cle, produit_id, quantite)  # atomic increment
    r.expire(cle, TTL_PANIER)


def lire(client_id: str) -> dict:
    return client_redis().hgetall(f"panier:{client_id}")


def retirer(client_id: str, produit_id: str) -> None:
    client_redis().hdel(f"panier:{client_id}", produit_id)


def top_produits(schema: str = "principal") -> tuple[list, str]:
    """Cache-aside: look in Redis first, else ask PostgreSQL and store with a TTL."""
    r = client_redis()
    cache = r.get(f"cache:top:{schema}")
    if cache:
        return json.loads(cache), "cache"
    with connexion_postgres() as conn:
        lignes = conn.execute(
            f"SELECT produit_id, SUM(quantite) FROM {schema}.lignes_commande "
            "GROUP BY produit_id ORDER BY 2 DESC, 1 LIMIT 10"
        ).fetchall()
    resultat = [[p, int(q)] for p, q in lignes]
    r.set(f"cache:top:{schema}", json.dumps(resultat), ex=TTL_CACHE)
    return resultat, "postgres"


if __name__ == "__main__":
    ajouter("CLI0000001", "PRO0001", 2)
    ajouter("CLI0000001", "PRO0001", 1)
    ajouter("CLI0000001", "PRO0007")
    print("cart:", lire("CLI0000001"), "| TTL:", client_redis().ttl("panier:CLI0000001"), "s")
    client_redis().delete("cache:top:principal")
    for essai in (1, 2):
        debut = time.perf_counter()
        _, source = top_produits()
        print(f"top products call {essai}: from {source} in {(time.perf_counter() - debut) * 1000:.1f} ms")
