"""Tests de l'enrichissement : stock, puis références de transaction."""
import hashlib

import pandas as pd
import pytest

from senmarket_bases.enrichissement import (
    ErreurEnrichissement,
    generer_references,
    generer_stock,
    lancer,
)

DATE = "2026-01-15"


# Les 34 autres produits réels (hors Électronique), avec leur catégorie
AUTRES_PRODUITS = (
    [(n, "Alimentation") for n in [
        "Riz brisé", "Huile végétale", "Sucre", "Lait en poudre", "Farine",
        "Pâtes alimentaires", "Concentré de tomate", "Oignon", "Pomme de terre", "Arachide",
        "Mil", "Maïs", "Fonio", "Poisson séché", "Poulet", "Viande", "Œufs", "Pain"]]
    + [(n, "Boissons") for n in ["Thé", "Café", "Eau minérale", "Jus de fruits"]]
    + [(n, "Hygiène") for n in ["Savon", "Lessive"]]
    + [(n, "Vêtements") for n in ["T-shirt", "Chaussures", "Sac"]]
    + [(n, "Fournitures") for n in ["Cahier", "Stylo", "Cartable"]]
    + [(n, "Maison") for n in ["Drap", "Serviette", "Lampe", "Ventilateur"]]
)


def _faux_produits() -> pd.DataFrame:
    """Les 40 produits réels : 6 d'Électronique (dont le Téléphone) d'abord, puis les autres."""
    noms = ["Téléphone", "Écouteurs", "Chargeur", "Clavier", "Souris", "Casque audio"]
    noms += [nom for nom, _ in AUTRES_PRODUITS]
    return pd.DataFrame({
        "produit_id": [f"PRO{i:04d}" for i in range(1, 41)],
        "nom_produit": noms,
        "categorie": ["Électronique"] * 6 + [cat for _, cat in AUTRES_PRODUITS],
        "prix_catalogue_xof": 1000,
        "actif": True,
    })


def _faux_paiements() -> pd.DataFrame:
    """200 paiements, méthodes en alternance (libellés exacts du module 0)."""
    cycle = ["Wave", "Orange Money", "Carte bancaire", "Espèces", "Wave"]
    return pd.DataFrame({
        "paiement_id": [f"PAI{i:04d}" for i in range(1, 201)],
        "commande_id": [f"CMD{i:04d}" for i in range(1, 201)],
        "methode_paiement": [cycle[i % 5] for i in range(200)],
        "statut_paiement": ["reussi"] * 200,
        "montant_xof": 5000,
    })


@pytest.fixture
def processed(tmp_path):
    """Fausse partition du module 0, écrite dans un dossier temporaire."""
    dossier = tmp_path / "processed" / f"date={DATE}"
    dossier.mkdir(parents=True)
    _faux_produits().to_parquet(dossier / "produits.parquet")
    _faux_paiements().to_parquet(dossier / "paiements.parquet")
    _faux_avis().to_parquet(dossier / "avis.parquet")
    return tmp_path / "processed"


def _empreinte(chemin) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


# --- stock.csv : invariants ------------------------------------------------------

def test_un_stock_par_produit():
    stock = generer_stock(_faux_produits(), DATE)
    assert sorted(stock["produit_id"]) == sorted(_faux_produits()["produit_id"])


def test_aucun_stock_negatif_et_entier():
    stock = generer_stock(_faux_produits(), DATE)
    assert (stock["stock"] >= 0).all()
    assert pd.api.types.is_integer_dtype(stock["stock"])


def test_au_moins_trois_produits_flash_dont_le_telephone():
    stock = generer_stock(_faux_produits(), DATE)
    flash = stock[stock["stock"].between(1, 5)]
    assert len(flash) >= 3
    assert "PRO0001" in set(flash["produit_id"])   # PRO0001 est le Téléphone ici


def test_les_produits_flash_sont_en_electronique():
    produits = _faux_produits()
    stock = generer_stock(produits, DATE)
    flash_ids = set(stock[stock["stock"].between(1, 5)]["produit_id"])
    categories = set(produits[produits["produit_id"].isin(flash_ids)]["categorie"])
    assert categories == {"Électronique"}


def test_il_y_a_des_ruptures():
    stock = generer_stock(_faux_produits(), DATE)
    assert (stock["stock"] == 0).sum() == 5


def test_meme_date_meme_stock():
    pd.testing.assert_frame_equal(
        generer_stock(_faux_produits(), DATE), generer_stock(_faux_produits(), DATE)
    )


def test_une_autre_date_donne_un_autre_stock():
    a = generer_stock(_faux_produits(), "2026-01-15")
    b = generer_stock(_faux_produits(), "2026-01-16")
    assert not a["stock"].equals(b["stock"])


# --- paiements_references.csv : invariants ---------------------------------------

def test_une_reference_par_paiement():
    refs = generer_references(_faux_paiements(), DATE)
    assert sorted(refs["paiement_id"]) == sorted(_faux_paiements()["paiement_id"])


def test_references_electroniques_uniques_et_non_vides():
    refs = generer_references(_faux_paiements(), DATE)
    electroniques = refs["reference_transaction"].dropna()
    assert len(electroniques) == 160                      # 200 - 40 paiements en espèces
    assert electroniques.is_unique
    assert (electroniques.str.len() > 0).all()


def test_especes_sans_reference():
    paiements = _faux_paiements()
    refs = generer_references(paiements, DATE).merge(paiements, on="paiement_id")
    especes = refs[refs["methode_paiement"] == "Espèces"]
    assert len(especes) == 40
    assert especes["reference_transaction"].isna().all()


def test_prefixe_selon_la_methode():
    paiements = _faux_paiements()
    refs = generer_references(paiements, DATE).merge(paiements, on="paiement_id")
    for methode, prefixe in {"Wave": "WAV-", "Orange Money": "OM-", "Carte bancaire": "CB-"}.items():
        sous_ensemble = refs[refs["methode_paiement"] == methode]["reference_transaction"]
        assert sous_ensemble.str.startswith(prefixe).all(), methode


def test_references_independantes_de_l_ordre_des_lignes():
    paiements = _faux_paiements()
    melange = paiements.sample(frac=1, random_state=0)
    pd.testing.assert_frame_equal(
        generer_references(paiements, DATE), generer_references(melange, DATE)
    )


def test_une_autre_date_donne_d_autres_references():
    a = generer_references(_faux_paiements(), "2026-01-15")
    b = generer_references(_faux_paiements(), "2026-01-16")
    assert not a["reference_transaction"].equals(b["reference_transaction"])


def test_methode_inconnue_est_signalee():
    paiements = _faux_paiements()
    paiements.loc[0, "methode_paiement"] = "Bitcoin"
    with pytest.raises(ErreurEnrichissement, match="Bitcoin"):
        generer_references(paiements, DATE)


# --- Reproductibilité des fichiers -----------------------------------------------

def test_deux_executions_donnent_le_meme_sha256(processed, tmp_path):
    sortie_1 = lancer(DATE, processed, tmp_path / "sortie_1")
    sortie_2 = lancer(DATE, processed, tmp_path / "sortie_2")
    for nom in ("stock.csv", "paiements_references.csv"):
        assert _empreinte(sortie_1 / nom) == _empreinte(sortie_2 / nom), nom


# --- Cas d'erreur ----------------------------------------------------------------

def test_partition_inexistante_liste_les_partitions_disponibles(processed, tmp_path):
    with pytest.raises(ErreurEnrichissement, match=f"date={DATE}"):
        lancer("2099-01-01", processed, tmp_path / "sortie")


def test_aucun_dossier_cree_si_erreur(processed, tmp_path):
    sortie = tmp_path / "sortie"
    with pytest.raises(ErreurEnrichissement):
        lancer("2099-01-01", processed, sortie)
    assert not sortie.exists()


def test_date_invalide(processed, tmp_path):
    with pytest.raises(ErreurEnrichissement, match="Date invalide"):
        lancer("pas-une-date", processed, tmp_path / "sortie")


# === avis_commentaires.csv =======================================================
import re  # noqa: E402

from senmarket_bases.enrichissement import generer_commentaires  # noqa: E402

# Vocabulaire de contrôle, volontairement écrit ICI et plus large que celui du script :
# un test qui réutiliserait la liste du script ne pourrait jamais la contredire.
MOTS_POSITIFS = ["excellent", "parfait", "super", "génial", "fantastique", "recommande",
                 "ravi", "adore", "impeccable", "satisfait", "content"]
MOTS_NEGATIFS = ["déçu", "décevant", "catastrophe", "mauvais", "mauvaise", "abîmé",
                 "retard", "défaut", "défauts", "éviter", "arnaque", "nul"]


def _contient(texte: str, mots: list[str]) -> bool:
    """Vrai si l'un des mots apparaît comme mot entier (pas comme morceau d'un autre mot)."""
    return re.search(r"\b(" + "|".join(mots) + r")\b", texte, flags=re.IGNORECASE) is not None


def _faux_avis() -> pd.DataFrame:
    """100 avis, notes de 1 à 5 en alternance."""
    return pd.DataFrame({
        "avis_id": [f"AVI{i:04d}" for i in range(1, 101)],
        "client_id": "CLI0000001",
        "produit_id": "PRO0001",
        "commande_id": "CMD0000001",
        "note": [(i % 5) + 1 for i in range(100)],
    })


def _commentaires_avec_notes() -> pd.DataFrame:
    avis = _faux_avis()
    return generer_commentaires(avis, DATE).merge(avis[["avis_id", "note"]], on="avis_id")


def test_un_commentaire_par_avis():
    avis = _faux_avis()
    commentaires = generer_commentaires(avis, DATE)
    assert sorted(commentaires["avis_id"]) == sorted(avis["avis_id"])


def test_aucun_commentaire_vide():
    commentaires = generer_commentaires(_faux_avis(), DATE)
    assert commentaires["commentaire"].str.strip().str.len().gt(0).all()


def test_notes_basses_sans_vocabulaire_positif():
    basses = _commentaires_avec_notes().query("note <= 2")
    assert len(basses) > 0
    fautifs = [c for c in basses["commentaire"] if _contient(c, MOTS_POSITIFS)]
    assert fautifs == []


def test_notes_hautes_sans_vocabulaire_negatif():
    hautes = _commentaires_avec_notes().query("note >= 4")
    assert len(hautes) > 0
    fautifs = [c for c in hautes["commentaire"] if _contient(c, MOTS_NEGATIFS)]
    assert fautifs == []


def test_textes_differents_entre_notes_basses_et_hautes():
    donnees = _commentaires_avec_notes()
    basses = set(donnees.query("note <= 2")["commentaire"])
    hautes = set(donnees.query("note >= 4")["commentaire"])
    assert basses.isdisjoint(hautes)


def test_commentaires_varies():
    assert generer_commentaires(_faux_avis(), DATE)["commentaire"].nunique() >= 20


def test_memes_commentaires_pour_la_meme_date():
    pd.testing.assert_frame_equal(
        generer_commentaires(_faux_avis(), DATE), generer_commentaires(_faux_avis(), DATE)
    )


def test_commentaires_independants_de_l_ordre_des_lignes():
    avis = _faux_avis()
    melange = avis.sample(frac=1, random_state=0)
    pd.testing.assert_frame_equal(
        generer_commentaires(avis, DATE), generer_commentaires(melange, DATE)
    )


def test_note_hors_intervalle_est_signalee():
    avis = _faux_avis()
    avis.loc[0, "note"] = 9
    with pytest.raises(ErreurEnrichissement, match="9"):
        generer_commentaires(avis, DATE)


def test_sha256_des_commentaires(processed, tmp_path):
    sortie_1 = lancer(DATE, processed, tmp_path / "sortie_1")
    sortie_2 = lancer(DATE, processed, tmp_path / "sortie_2")
    assert _empreinte(sortie_1 / "avis_commentaires.csv") == _empreinte(
        sortie_2 / "avis_commentaires.csv"
    )


# === catalogue.jsonl =============================================================
import json  # noqa: E402

from senmarket_bases.catalogue_donnees import ATTRIBUTS_PAR_PRODUIT  # noqa: E402
from senmarket_bases.enrichissement import generer_catalogue  # noqa: E402


def test_un_document_par_produit_avec_les_memes_identifiants():
    produits = _faux_produits()
    catalogue = generer_catalogue(produits)
    assert sorted(d["produit_id"] for d in catalogue) == sorted(produits["produit_id"])


def test_structure_des_documents():
    for doc in generer_catalogue(_faux_produits()):
        assert set(doc) == {"produit_id", "nom", "categorie", "attributs"}
        assert isinstance(doc["attributs"], dict)


def test_pas_de_prix_ni_de_stock_dans_le_catalogue():
    # Ces valeurs changent et vivent dans PostgreSQL : une seule vérité
    interdits = {"prix", "prix_xof", "prix_catalogue_xof", "stock"}
    for doc in generer_catalogue(_faux_produits()):
        assert interdits.isdisjoint(doc)
        assert interdits.isdisjoint(doc["attributs"])


def test_au_moins_trois_jeux_d_attributs_differents():
    jeux = {frozenset(d["attributs"]) for d in generer_catalogue(_faux_produits())}
    assert len(jeux) >= 3


def test_un_attribut_imbrique_et_une_liste():
    valeurs = [v for d in generer_catalogue(_faux_produits()) for v in d["attributs"].values()]
    assert any(isinstance(v, dict) for v in valeurs)
    assert any(isinstance(v, list) for v in valeurs)


def test_attributs_numeriques_sont_de_vrais_nombres():
    # Sinon l'épreuve du chapitre 3 (« 8 Go » à la place de 8) ne prouverait rien
    numeriques = {"poids_kg", "volume_l", "garantie_mois", "puissance_w", "autonomie_h",
                  "nombre_unites", "nombre_pages", "capacite_l"}
    for doc in generer_catalogue(_faux_produits()):
        for cle, valeur in doc["attributs"].items():
            if cle in numeriques:
                assert isinstance(valeur, (int, float)) and not isinstance(valeur, bool), (
                    doc["nom"], cle)
        for cle, valeur in doc["attributs"].get("specs", {}).items():
            assert isinstance(valeur, (int, float)), (doc["nom"], cle)


def test_tous_les_produits_n_ont_pas_les_memes_attributs():
    # Des produits sans garantie : de quoi tester $exists au chapitre 3
    catalogue = generer_catalogue(_faux_produits())
    avec = [d for d in catalogue if "garantie_mois" in d["attributs"]]
    assert 0 < len(avec) < len(catalogue)


def test_pas_de_champ_origine_en_alimentation():
    for doc in generer_catalogue(_faux_produits()):
        if doc["categorie"] == "Alimentation":
            assert "origine" not in doc["attributs"]


def test_les_donnees_couvrent_exactement_les_40_produits():
    assert set(_faux_produits()["nom_produit"]) == set(ATTRIBUTS_PAR_PRODUIT)


def test_produit_sans_attributs_est_signale():
    produits = _faux_produits()
    produits.loc[0, "nom_produit"] = "Produit inconnu"
    with pytest.raises(ErreurEnrichissement, match="Produit inconnu"):
        generer_catalogue(produits)


def test_fichier_jsonl_une_ligne_par_produit_accents_lisibles(processed, tmp_path):
    sortie = lancer(DATE, processed, tmp_path / "sortie")
    texte = (sortie / "catalogue.jsonl").read_text(encoding="utf-8")
    documents = [json.loads(ligne) for ligne in texte.splitlines()]
    assert len(documents) == 40
    assert documents[0]["produit_id"] == "PRO0001"
    assert "Téléphone" in texte        # accents écrits tels quels
    assert "\\u00" not in texte        # et non échappés (\u00e9)


def test_sha256_du_catalogue(processed, tmp_path):
    sortie_1 = lancer(DATE, processed, tmp_path / "sortie_1")
    sortie_2 = lancer(DATE, processed, tmp_path / "sortie_2")
    assert _empreinte(sortie_1 / "catalogue.jsonl") == _empreinte(sortie_2 / "catalogue.jsonl")
