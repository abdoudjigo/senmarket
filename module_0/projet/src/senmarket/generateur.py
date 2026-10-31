"""
Générateur des données synthétiques de SenMarket.

Granularité :
- Une ligne de commandes représente une commande.
- Une ligne de lignes_commande représente un produit dans une commande.
- Le paramètre --rows correspond au nombre de lignes de commande à générer.

Les données sont synthétiques. Elles servent à tester les traitements
de Data Engineering et ne représentent pas des transactions réelles.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker


# ---------------------------------------------------------------------------
# Configuration générale
# ---------------------------------------------------------------------------

RACINE_PROJET = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger(__name__)

# Graine de base (configurable par l'environnement). La graine réelle d'une
# exécution en dérive avec la date : voir graine_du_jour().
GRAINE_BASE = int(os.environ.get("SENMARKET_SEED", "42"))

FAKE = Faker("fr_FR")
FAKE.seed_instance(GRAINE_BASE)  # regraine par date dans generer_donnees

# Les villes et régions sont un référentiel synthétique de localisation.
# Plusieurs villes appartiennent à la région de Dakar.
VILLES_REGIONS = {
    "Dakar": "Dakar",
    "Pikine": "Dakar",
    "Guédiawaye": "Dakar",
    "Rufisque": "Dakar",
    "Thiès": "Thiès",
    "Mbour": "Thiès",
    "Saint-Louis": "Saint-Louis",
    "Richard-Toll": "Saint-Louis",
    "Louga": "Louga",
    "Diourbel": "Diourbel",
    "Touba": "Diourbel",
    "Kaolack": "Kaolack",
    "Fatick": "Fatick",
    "Ziguinchor": "Ziguinchor",
    "Kolda": "Kolda",
    "Tambacounda": "Tambacounda",
    "Kédougou": "Kédougou",
    "Matam": "Matam",
    "Sédhiou": "Sédhiou",
    "Kaffrine": "Kaffrine",
}

# Dakar est volontairement plus fréquent que les autres villes.
VILLES = list(VILLES_REGIONS)
POIDS_VILLES = np.array([
    0.25, 0.08, 0.05, 0.04,
    0.10, 0.07,
    0.06, 0.02,
    0.03,
    0.04, 0.05,
    0.05, 0.02,
    0.03, 0.02, 0.02,
    0.01, 0.02, 0.01, 0.03,
], dtype=float)
POIDS_VILLES /= POIDS_VILLES.sum()

# Catalogue de référence : chaque produit appartient à sa catégorie dès la
# source, avec un prix de catalogue fixe en XOF (entier). Il est donc
# impossible d'obtenir « Sucre » dans « Vêtements ».
# L'ordre compte : les premiers produits sont les plus populaires.
CATALOGUE = {
    "Alimentation": [
        ("Riz brisé", 12_500), ("Huile végétale", 6_000), ("Sucre", 1_000),
        ("Lait en poudre", 3_500), ("Farine", 800), ("Pâtes alimentaires", 600),
        ("Concentré de tomate", 500), ("Oignon", 700), ("Pomme de terre", 600),
        ("Arachide", 1_500), ("Mil", 900), ("Maïs", 800), ("Fonio", 1_800),
        ("Poisson séché", 2_500), ("Poulet", 4_500), ("Viande", 5_500),
        ("Œufs", 2_200), ("Pain", 500),
    ],
    "Boissons": [
        ("Thé", 1_200), ("Café", 2_000), ("Eau minérale", 500),
        ("Jus de fruits", 1_000),
    ],
    "Hygiène": [
        ("Savon", 700), ("Lessive", 2_500),
    ],
    "Électronique": [
        ("Téléphone", 85_000), ("Écouteurs", 8_000), ("Chargeur", 5_000),
        ("Clavier", 12_000), ("Souris", 6_000), ("Casque audio", 15_000),
    ],
    "Vêtements": [
        ("T-shirt", 5_000), ("Chaussures", 25_000), ("Sac", 15_000),
    ],
    "Fournitures": [
        ("Cahier", 500), ("Stylo", 500), ("Cartable", 12_000),
    ],
    "Maison": [
        ("Drap", 10_000), ("Serviette", 4_000), ("Lampe", 7_000),
        ("Ventilateur", 28_000),
    ],
}

CATEGORIES_PRODUITS = list(CATALOGUE)

# Coordonnées synthétiques des clients (téléphones au format sénégalais).
DOMAINES_EMAIL = ["gmail.com", "yahoo.fr", "hotmail.com", "orange.sn"]
POIDS_DOMAINES = np.array([0.55, 0.15, 0.10, 0.20])
PREFIXES_TELEPHONE = ["70", "75", "76", "77", "78"]
POIDS_PREFIXES = np.array([0.05, 0.10, 0.15, 0.40, 0.30])

METHODES_PAIEMENT = [
    "Wave", "Orange Money", "Carte bancaire", "Espèces"
]

STATUTS_PAIEMENT = ["réussi", "en_attente", "échoué"]

# Écarts métier voulus (ce ne sont pas des défauts à mettre en quarantaine).
TAUX_COMMANDES_SANS_PAIEMENT = 0.02
TAUX_PAIEMENTS_AVEC_ECART = 0.01

TYPES_NAVIGATION = [
    "page_vue", "recherche", "vue_produit",
    "ajout_panier", "debut_paiement",
]

DEFAUTS_DISPONIBLES = [
    "ville_manquante",
    "quantite_negative",
    "doublon_ligne",
    "date_future",
    "montant_texte",
    "outlier",
    "encodage_latin1",
    "colonne_manquante",
]


# ---------------------------------------------------------------------------
# Fonctions de génération
# ---------------------------------------------------------------------------

def generer_dates(
    nombre: int,
    run_date: date,
    rng: np.random.Generator,
    jours_historique: int = 365,
) -> np.ndarray:
    """
    Générer des dates réparties sur les 12 mois précédant run_date.

    Les dates sont exprimées au format ISO YYYY-MM-DD pour simplifier
    leur lecture et leur ingestion par les outils de données.
    """
    debut = run_date - timedelta(days=jours_historique - 1)
    decalages = rng.integers(0, jours_historique, size=nombre)

    dates = [
        (debut + timedelta(days=int(decalage))).isoformat()
        for decalage in decalages
    ]
    return np.array(dates, dtype=object)


def _texte_pour_email(nom: str) -> str:
    """Rendre un nom utilisable dans une adresse e-mail (sans accents ni espaces)."""
    sans_accents = (
        unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", ".", sans_accents.lower()).strip(".")


def generer_clients(
    nombre: int,
    rng: np.random.Generator,
    run_date: date,
) -> pd.DataFrame:
    """
    Générer les clients avec un identifiant métier stable.

    L'e-mail est construit à partir du nom et du numéro du client, ce qui
    garantit son unicité. Le téléphone suit le format +221 7x xxx xx xx.
    """
    villes = rng.choice(VILLES, size=nombre, p=POIDS_VILLES)
    noms = [FAKE.name() for _ in range(nombre)]

    domaines = rng.choice(DOMAINES_EMAIL, size=nombre, p=POIDS_DOMAINES)
    emails = [
        f"{_texte_pour_email(nom)}{numero}@{domaine}"
        for numero, (nom, domaine) in enumerate(zip(noms, domaines), start=1)
    ]

    prefixes = rng.choice(PREFIXES_TELEPHONE, size=nombre, p=POIDS_PREFIXES)
    blocs = rng.integers(0, [1000, 100, 100], size=(nombre, 3))
    telephones = [
        f"+221 {prefixe} {a:03d} {b:02d} {c:02d}"
        for prefixe, (a, b, c) in zip(prefixes, blocs)
    ]

    return pd.DataFrame({
        "client_id": [f"CLI{i:07d}" for i in range(1, nombre + 1)],
        "nom_client": noms,
        "email": emails,
        "telephone": telephones,
        "ville": villes,
        "region": [VILLES_REGIONS[ville] for ville in villes],
        "date_inscription": generer_dates(
            nombre, run_date, rng, jours_historique=730
        ),
    })


def generer_vendeurs(
    nombre: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Générer le référentiel des vendeurs."""
    villes = rng.choice(VILLES, size=nombre, p=POIDS_VILLES)

    return pd.DataFrame({
        "vendeur_id": [f"VEN{i:05d}" for i in range(1, nombre + 1)],
        "nom_vendeur": [f"Vendeur {FAKE.company()}" for _ in range(nombre)],
        "ville": villes,
        "region": [VILLES_REGIONS[ville] for ville in villes],
    })


def generer_produits(
    nombre_vendeurs: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Générer le catalogue à partir du référentiel CATALOGUE.

    Le nom, la catégorie et le prix catalogue viennent du même endroit :
    ils sont cohérents par construction. Seul le vendeur est tiré au hasard.
    Le prix effectivement payé sera stocké séparément dans les lignes de
    commande.
    """
    articles = [
        (categorie, nom, prix)
        for categorie, produits in CATALOGUE.items()
        for nom, prix in produits
    ]
    nombre = len(articles)

    # Certains produits sont plus populaires que d'autres (ordre du catalogue).
    poids = np.exp(-np.linspace(0, 2.0, nombre))
    poids /= poids.sum()

    return pd.DataFrame({
        "produit_id": [f"PRO{i:04d}" for i in range(1, nombre + 1)],
        "nom_produit": [nom for _, nom, _ in articles],
        "categorie": [categorie for categorie, _, _ in articles],
        "vendeur_id": [
            f"VEN{i:05d}"
            for i in rng.integers(1, nombre_vendeurs + 1, size=nombre)
        ],
        "prix_catalogue_xof": np.array(
            [prix for _, _, prix in articles], dtype="int64"
        ),
        "actif": True,
        "poids_simulation": poids,
    })


def graine_du_jour(run_date: date, graine_base: int = GRAINE_BASE) -> list[int]:
    """
    Dériver la graine de la date d'exécution.

    Même date et mêmes paramètres : mêmes données (reproductible).
    Dates différentes : jeux de données indépendants.
    Exemple : 2026-10-29 -> [42, 20261029].
    """
    return [graine_base, int(run_date.strftime("%Y%m%d"))]


def _dates_apres(
    debuts: np.ndarray,
    run_date: date,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Tirer, pour chaque élément, une date comprise entre `debuts` et run_date.

    Sert à ne jamais dater un événement avant celui dont il dépend
    (une commande après l'inscription, un avis après la commande).
    Les dates sont renvoyées au format ISO YYYY-MM-DD.
    """
    fin = np.datetime64(run_date, "D")
    ecarts = np.maximum((fin - debuts).astype("int64"), 0)
    decalages = (rng.random(len(debuts)) * (ecarts + 1)).astype("int64")
    dates = debuts + decalages.astype("timedelta64[D]")
    return np.datetime_as_string(dates, unit="D").astype(object)


def generer_donnees(
    rows: int = 10_000,
    run_date: date | None = None,
    defauts: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Générer les huit tables liées de SenMarket.

    Args:
        rows: Nombre de lignes de commande à générer.
        run_date: Date d'exécution, utilisée pour les partitions et les dates.
        defauts: Liste des défauts à injecter dans les données brutes.

    Returns:
        Dictionnaire dont les clés sont les noms des tables et les valeurs
        les DataFrames correspondants.
    """
    if rows < 1:
        raise ValueError("Le paramètre rows doit être supérieur à zéro.")

    run_date = run_date or date.today()
    defauts = defauts or []
    inconnus = set(defauts) - set(DEFAUTS_DISPONIBLES)
    if inconnus:
        raise ValueError(f"Défauts inconnus : {sorted(inconnus)}")

    # La graine dérive de la date : reproductible pour une même date,
    # indépendante d'une date à l'autre. Faker est regrainé au même moment.
    graine = graine_du_jour(run_date)
    rng = np.random.default_rng(graine)
    FAKE.seed_instance(graine[0] * 100_000_000 + graine[1])

    # La taille des référentiels dépend du volume demandé.
    nombre_clients = min(max(rows // 3, 100), 50_000)
    nombre_vendeurs = 20
    nombre_commandes_max = max(1, int(np.ceil(rows / 2.2)))

    clients = generer_clients(nombre_clients, rng, run_date)
    vendeurs = generer_vendeurs(nombre_vendeurs, rng)
    produits = generer_produits(nombre_vendeurs, rng)

    # Chaque ligne reçoit un identifiant de commande. Plusieurs lignes
    # peuvent donc appartenir à une même commande.
    numeros_commandes = rng.integers(
        1, nombre_commandes_max + 1, size=rows
    )
    numeros_commandes_uniques = np.unique(numeros_commandes)

    client_ids = clients["client_id"].to_numpy()
    produits_ids = produits["produit_id"].to_numpy()
    poids_produits = produits["poids_simulation"].to_numpy()
    prix_catalogue = produits.set_index("produit_id")["prix_catalogue_xof"]

    # Chaque commande possède un client et une date. La date est tirée entre
    # l'inscription du client et run_date : on ne commande pas avant de
    # s'être inscrit.
    nombre_commandes = len(numeros_commandes_uniques)
    clients_commandes = rng.choice(client_ids, size=nombre_commandes)
    inscriptions = (
        pd.to_datetime(clients.set_index("client_id")["date_inscription"].loc[clients_commandes])
        .to_numpy()
        .astype("datetime64[D]")
    )
    dates_commandes = _dates_apres(inscriptions, run_date, rng)

    commandes = pd.DataFrame({
        "commande_id": [
            f"CMD{numero:08d}" for numero in numeros_commandes_uniques
        ],
        "client_id": clients_commandes,
        "date_commande": dates_commandes,
        "statut": rng.choice(
            ["livrée", "expédiée", "en_preparation", "annulée"],
            size=len(numeros_commandes_uniques),
            p=[0.72, 0.12, 0.10, 0.06],
        ),
    })

    # Associer chaque ligne à sa commande.
    correspondance_commandes = {
        numero: f"CMD{numero:08d}"
        for numero in numeros_commandes_uniques
    }
    commande_ids_lignes = [
        correspondance_commandes[numero]
        for numero in numeros_commandes
    ]

    produits_choisis = rng.choice(
        produits_ids, size=rows, p=poids_produits
    )
    quantites = rng.integers(1, 6, size=rows)

    # Le prix payé peut différer légèrement du prix catalogue.
    prix_de_base = prix_catalogue.loc[produits_choisis].to_numpy()
    facteurs_prix = rng.uniform(0.90, 1.10, size=rows)
    prix_payes = np.maximum(
        1, np.rint(prix_de_base * facteurs_prix)
    ).astype("int64")

    lignes_commande = pd.DataFrame({
        "ligne_commande_id": [
            f"LC{i:09d}" for i in range(1, rows + 1)
        ],
        "commande_id": commande_ids_lignes,
        "produit_id": produits_choisis,
        "quantite": quantites.astype("int64"),
        "prix_unitaire_xof": prix_payes,
        "montant_xof": (quantites * prix_payes).astype("int64"),
    })

    # Un paiement initial par commande. Les paiements ne sont pas tous
    # réussis, ce qui permet d'étudier les statuts et les taux de paiement.
    totaux_commandes = (
        lignes_commande.groupby("commande_id")["montant_xof"].sum()
    )
    paiements_complets = pd.DataFrame({
        "commande_id": commandes["commande_id"].to_numpy(),
        "methode_paiement": rng.choice(
            METHODES_PAIEMENT,
            size=len(commandes),
            p=[0.40, 0.35, 0.15, 0.10],
        ),
        "statut_paiement": rng.choice(
            STATUTS_PAIEMENT,
            size=len(commandes),
            p=[0.88, 0.05, 0.07],
        ),
        "montant_xof": (
            commandes["commande_id"]
            .map(totaux_commandes)
            .astype("int64")
        ),
        "date_paiement": commandes["date_commande"].to_numpy(),
    })

    # Écart métier n°1 : environ 2 % des commandes n'ont aucun paiement.
    a_un_paiement = (
        rng.random(len(paiements_complets)) >= TAUX_COMMANDES_SANS_PAIEMENT
    )
    paiements = paiements_complets.loc[a_un_paiement].reset_index(drop=True)

    # Écart métier n°2 : environ 1 % des paiements ont un montant différent
    # de la somme des lignes (frais ou remise de 2 % à 10 %).
    avec_ecart = rng.random(len(paiements)) < TAUX_PAIEMENTS_AVEC_ECART
    facteurs = np.where(
        rng.random(len(paiements)) < 0.5,
        rng.uniform(0.90, 0.98, size=len(paiements)),
        rng.uniform(1.02, 1.10, size=len(paiements)),
    )
    montants_avec_ecart = np.rint(
        paiements["montant_xof"].to_numpy() * facteurs
    ).astype("int64")
    paiements["montant_xof"] = np.where(
        avec_ecart, montants_avec_ecart, paiements["montant_xof"].to_numpy()
    )
    paiements.insert(
        0,
        "paiement_id",
        [f"PAI{i:08d}" for i in range(1, len(paiements) + 1)],
    )

    # Avis uniquement sur des commandes livrées, datés après la commande.
    livrees = set(commandes.loc[commandes["statut"] == "livrée", "commande_id"])
    lignes_livrees = lignes_commande[lignes_commande["commande_id"].isin(livrees)]
    commande_client = commandes.set_index("commande_id")["client_id"]
    commande_date = commandes.set_index("commande_id")["date_commande"]

    nombre_avis = min(max(1, int(rows * 0.10)), len(lignes_livrees))
    indices_avis = rng.integers(
        0, max(len(lignes_livrees), 1), size=nombre_avis
    )
    lignes_avis = lignes_livrees.iloc[indices_avis].reset_index(drop=True)
    debuts_avis = (
        pd.to_datetime(lignes_avis["commande_id"].map(commande_date))
        .to_numpy()
        .astype("datetime64[D]")
    )

    avis = pd.DataFrame({
        "avis_id": [
            f"AVI{i:08d}" for i in range(1, nombre_avis + 1)
        ],
        "client_id": lignes_avis["commande_id"].map(commande_client),
        "produit_id": lignes_avis["produit_id"].to_numpy(),
        "commande_id": lignes_avis["commande_id"].to_numpy(),
        "note": rng.integers(1, 6, size=nombre_avis),
        "date_avis": _dates_apres(debuts_avis, run_date, rng),
    }).drop_duplicates(subset=["avis_id"])

    # Les événements de navigation comprennent des visiteurs anonymes.
    nombre_evenements = min(rows * 2, 1_000_000)
    # Utiliser dtype=object pour préserver les véritables valeurs None.
    # Elles deviendront des cellules vides dans les CSV et des NULL en base.
    clients_potentiels = np.concatenate([
        client_ids.astype(object),
        np.full(max(1, nombre_clients // 4), None, dtype=object),
    ])
    produits_potentiels = np.concatenate([
        produits_ids.astype(object),
        np.full(3, None, dtype=object),
    ])

    evenements_clients = rng.choice(
        clients_potentiels,
        size=nombre_evenements,
    )
    evenements_produits = rng.choice(
        produits_potentiels,
        size=nombre_evenements,
    )

    navigation = pd.DataFrame({
        "evenement_id": [
            f"EVT{i:09d}" for i in range(1, nombre_evenements + 1)
        ],
        "session_id": [
            f"SES{int(numero):09d}"
            for numero in rng.integers(
                1, max(2, nombre_evenements // 3), size=nombre_evenements
            )
        ],
        "client_id": evenements_clients,
        "produit_id": evenements_produits,
        "type_evenement": rng.choice(
            TYPES_NAVIGATION,
            size=nombre_evenements,
            p=[0.50, 0.15, 0.20, 0.10, 0.05],
        ),
        "date_evenement": generer_dates(
            nombre_evenements, run_date, rng
        ),
    })

    tables = {
        "clients": clients,
        "vendeurs": vendeurs,
        "produits": produits.drop(columns=["poids_simulation"]),
        "commandes": commandes,
        "lignes_commande": lignes_commande,
        "paiements": paiements,
        "avis": avis,
        "navigation": navigation,
    }

    # Injection optionnelle de défauts pour les exercices de qualité.
    # Les fichiers ainsi produits sont volontairement imparfaits.
    injecter_defauts(tables, defauts, run_date)

    return tables


def injecter_defauts(
    tables: dict[str, pd.DataFrame],
    defauts: list[str],
    run_date: date,
) -> None:
    """
    Injecter des anomalies contrôlées dans les tables brutes.

    Les défauts sont désactivés par défaut. Les tables doivent ensuite
    passer par une étape de nettoyage et de quarantaine.
    """
    lignes = tables["lignes_commande"]
    commandes = tables["commandes"]
    clients = tables["clients"]

    if "ville_manquante" in defauts and not clients.empty:
        clients.loc[clients.index[0], "ville"] = None

    if "quantite_negative" in defauts and not lignes.empty:
        lignes.loc[lignes.index[0], "quantite"] = -3

    if "doublon_ligne" in defauts and not lignes.empty:
        tables["lignes_commande"] = pd.concat(
            [lignes, lignes.iloc[[0]]],
            ignore_index=True,
        )

    if "date_future" in defauts and not commandes.empty:
        commandes.loc[commandes.index[0], "date_commande"] = (
            run_date + timedelta(days=30)
        ).isoformat()

    if "montant_texte" in defauts and not lignes.empty:
        # Colonne convertie en texte pour pouvoir y injecter une valeur non numérique
        lignes["montant_xof"] = lignes["montant_xof"].astype(object)
        lignes.loc[lignes.index[0], "montant_xof"] = "inconnu"

    if "outlier" in defauts and not lignes.empty:
        lignes.loc[lignes.index[0], "prix_unitaire_xof"] = 999_999_999
        lignes.loc[lignes.index[0], "montant_xof"] = 999_999_999

    if "colonne_manquante" in defauts:
        tables["clients"] = clients.drop(columns=["region"])

    # Le défaut d'encodage est appliqué au moment de l'écriture des fichiers.
    # Il n'est donc pas modifié dans les DataFrames ici.


def sauvegarder_donnees(
    tables: dict[str, pd.DataFrame],
    run_date: date,
    defauts: list[str] | None = None,
) -> Path:
    """
    Écrire chaque table CSV dans une partition d'exécution.

    Exemple :
        data/raw/date=2026-10-28/clients.csv

    Returns:
        Le chemin du répertoire de partition créé.
    """
    defauts = defauts or []
    dossier = (
        RACINE_PROJET / "data" / "raw" / f"date={run_date.isoformat()}"
    )
    dossier.mkdir(parents=True, exist_ok=True)

    for nom_table, df in tables.items():
        chemin = dossier / f"{nom_table}.csv"

        # Permet de simuler un problème d'encodage lors des exercices.
        encodage = (
            "latin-1"
            if "encodage_latin1" in defauts and nom_table == "clients"
            else "utf-8"
        )

        df.to_csv(chemin, index=False, encoding=encodage)
        LOGGER.info(
            "Table %s écrite : %s lignes (%s)",
            nom_table,
            len(df),
            chemin,
        )

    return dossier


def construire_arguments() -> argparse.Namespace:
    """Définir les options de ligne de commande du générateur."""
    parser = argparse.ArgumentParser(
        description="Générer les données synthétiques de SenMarket."
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=10_000,
        help="Nombre de lignes de commande à générer (défaut : 10000).",
    )
    parser.add_argument(
        "--run-date",
        type=date.fromisoformat,
        default=date.today(),
        help="Date de partition au format YYYY-MM-DD.",
    )
    parser.add_argument(
        "--defauts",
        nargs="*",
        choices=DEFAUTS_DISPONIBLES,
        default=[],
        help="Liste facultative de défauts à injecter dans les données brutes.",
    )
    return parser.parse_args()


def main() -> None:
    """Point d'entrée CLI du générateur."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    args = construire_arguments()

    LOGGER.info(
        "Génération démarrée : rows=%s, run_date=%s, défauts=%s",
        args.rows,
        args.run_date,
        args.defauts,
    )

    tables = generer_donnees(
        rows=args.rows,
        run_date=args.run_date,
        defauts=args.defauts,
    )
    dossier = sauvegarder_donnees(
        tables=tables,
        run_date=args.run_date,
        defauts=args.defauts,
    )

    LOGGER.info("Génération terminée. Fichiers disponibles dans %s", dossier)
    for nom_table, df in tables.items():
        LOGGER.info("%s : %s lignes", nom_table, len(df))


if __name__ == "__main__":
    main()
