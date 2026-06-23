"""
config.py - Configuration centralisée de l'application
Toutes les variables d'environnement et constantes sont définies ici.
"""

import os


class Config:
    # ──────────────────────────────────────────────
    #  Connexion Memgraph (via driver Bolt / neo4j)
    # ──────────────────────────────────────────────
    MEMGRAPH_HOST     = os.getenv("MEMGRAPH_HOST",     "localhost")
    MEMGRAPH_PORT     = int(os.getenv("MEMGRAPH_PORT", "7687"))
    MEMGRAPH_USERNAME = os.getenv("MEMGRAPH_USERNAME", "")
    MEMGRAPH_PASSWORD = os.getenv("MEMGRAPH_PASSWORD", "")

    # URI complète Bolt pour le driver neo4j
    @classmethod
    def bolt_uri(cls) -> str:
        return f"bolt://{cls.MEMGRAPH_HOST}:{cls.MEMGRAPH_PORT}"

    # ──────────────────────────────────────────────
    #  Flask
    # ──────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "chess-graph-nosql-secret-2024")
    DEBUG      = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    # ──────────────────────────────────────────────
    #  Application
    # ──────────────────────────────────────────────
    APP_NAME    = "Gestionnaire d'Ouvertures d'Échecs"
    VERSION     = "1.0.0"
    DESCRIPTION = (
        "Application de gestion d'ouvertures d'échecs "
        "propulsée par une base de données graphe Memgraph."
    )

    # Nombre max de nœuds renvoyés dans la vue graphe
    GRAPH_MAX_NODES = 200
