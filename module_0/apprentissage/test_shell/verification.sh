#!/bin/bash

# Définir le fichier à vérifier
FICHIER="test_shell/data/ventes.csv"

# Vérifier que le fichier existe
if [ -f "$FICHIER" ]; then
    echo "Fichier trouvé : $FICHIER"
    echo "Nombre de lignes :"
    wc -l < "$FICHIER"
else
    echo "Erreur : fichier introuvable"
    exit 1
fi
