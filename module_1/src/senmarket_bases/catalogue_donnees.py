"""Attributs du catalogue SenMarket, produit par produit (données écrites à la main).

Règles :
- une unité par attribut : poids toujours en kg (poids_kg), volumes en litres (volume_l) ;
- les attributs numériques sont de vrais nombres, jamais du texte ;
- tous les produits n'ont pas les mêmes attributs : c'est l'intérêt d'un catalogue souple ;
- aucun prix, aucun stock ici : ils changent et vivent dans PostgreSQL (une seule vérité).
"""

ATTRIBUTS_PAR_PRODUIT = {
    # --- Alimentation (18) : poids ou volume ou nombre d'unités, et un conditionnement ---
    "Riz brisé": {"poids_kg": 5.0, "conditionnement": "sac"},
    "Huile végétale": {"volume_l": 5.0, "conditionnement": "bidon"},
    "Sucre": {"poids_kg": 1.0, "conditionnement": "sachet"},
    "Lait en poudre": {"poids_kg": 0.9, "conditionnement": "boîte"},
    "Farine": {"poids_kg": 1.0, "conditionnement": "sachet"},
    "Pâtes alimentaires": {"poids_kg": 0.5, "conditionnement": "paquet"},
    "Concentré de tomate": {"poids_kg": 0.4, "conditionnement": "boîte"},
    "Oignon": {"poids_kg": 1.0, "conditionnement": "filet"},
    "Pomme de terre": {"poids_kg": 1.0, "conditionnement": "filet"},
    "Arachide": {"poids_kg": 1.0, "conditionnement": "sachet"},
    "Mil": {"poids_kg": 1.0, "conditionnement": "sachet"},
    "Maïs": {"poids_kg": 1.0, "conditionnement": "sachet"},
    "Fonio": {"poids_kg": 1.0, "conditionnement": "sachet"},
    "Poisson séché": {"poids_kg": 0.5, "conditionnement": "sachet"},
    "Poulet": {"poids_kg": 1.5, "conditionnement": "pièce"},
    "Viande": {"poids_kg": 1.0, "conditionnement": "barquette"},
    "Œufs": {"nombre_unites": 30, "conditionnement": "plateau"},
    "Pain": {"poids_kg": 0.25, "conditionnement": "baguette"},
    # --- Boissons (4) ---
    "Thé": {"poids_kg": 0.25},
    "Café": {"poids_kg": 0.25},
    "Eau minérale": {"volume_l": 1.5},
    "Jus de fruits": {"volume_l": 1.0},
    # --- Hygiène (2) ---
    "Savon": {"poids_kg": 0.2},
    "Lessive": {"poids_kg": 1.0},
    # --- Électronique (6) : seul le téléphone a des specs imbriquées ---
    "Téléphone": {
        "specs": {"ram_go": 4, "stockage_go": 64, "ecran_pouces": 6.5},
        "couleurs": ["noir", "bleu"],
        "garantie_mois": 12,
    },
    "Écouteurs": {"connectique": "Bluetooth", "garantie_mois": 6},
    "Chargeur": {"connectique": "USB-C", "puissance_w": 20, "garantie_mois": 6},
    "Clavier": {"connectique": "USB-A", "disposition": "AZERTY", "garantie_mois": 12},
    "Souris": {"connectique": "USB-A", "garantie_mois": 12},
    "Casque audio": {"connectique": "Bluetooth", "autonomie_h": 30, "garantie_mois": 12},
    # --- Vêtements (3) : des listes ---
    "T-shirt": {"tailles": ["S", "M", "L", "XL"], "couleurs": ["blanc", "noir", "bleu"],
                "matiere": "coton"},
    "Chaussures": {"pointures": [38, 39, 40, 41, 42, 43, 44], "couleurs": ["noir", "marron"],
                   "matiere": "cuir"},
    "Sac": {"couleurs": ["noir", "marron", "beige"], "matiere": "simili-cuir"},
    # --- Fournitures (3) ---
    "Cahier": {"nombre_pages": 96, "format": "A5"},
    "Stylo": {"couleur_encre": "bleu"},
    "Cartable": {"capacite_l": 20, "couleurs": ["bleu", "rouge", "noir"]},
    # --- Maison (4) ---
    "Drap": {"matiere": "coton", "taille": "2 places"},
    "Serviette": {"matiere": "coton", "dimensions_cm": {"longueur": 140, "largeur": 70}},
    "Lampe": {"puissance_w": 9, "garantie_mois": 6},
    "Ventilateur": {"puissance_w": 45, "garantie_mois": 12},
}
