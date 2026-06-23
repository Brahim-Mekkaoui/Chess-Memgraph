"""
models.py  –  Couche d'accès aux données Memgraph
=================================================
Ce fichier expose la classe MemgraphClient qui encapsule toutes les
interactions avec la base de données graphe via le driver officiel
neo4j (protocole Bolt, compatible Memgraph v2.x).

Pourquoi une base de données graphe pour les ouvertures d'échecs ?
──────────────────────────────────────────────────────────────────
• Les ouvertures forment naturellement un GRAPHE : chaque ouverture
  est un nœud (Opening), et les relations SIMILAR_TO relient des
  ouvertures qui partagent un début commun ou appartiennent à la même
  famille ECO.
• Parcourir les ouvertures similaires à k sauts est trivial en Cypher
  (MATCH path) alors qu'une jointure SQL récursive serait complexe.
• L'ajout de nouvelles relations (TRANSPOSE_OF, LEADS_TO, …) ne
  nécessite aucune modification de schéma.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError

from config import Config
from utils.fen_utils import normalize_fen, moves_string_to_raw

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers de sérialisation
# ─────────────────────────────────────────────────────────────────────────────

def _node_to_dict(node) -> dict:
    """
    Convertit un nœud neo4j/Memgraph en dictionnaire Python standard.
    Memgraph utilise node.id (entier) - pas node.element_id (Neo4j 5.x).
    On stocke l'ID en str pour les URLs Flask.
    """
    data = dict(node)
    try:
        data["id"] = str(node.id)        # Memgraph : entier
    except AttributeError:
        data["id"] = str(node.element_id) # Neo4j 5.x fallback
    return data


# ─────────────────────────────────────────────────────────────────────────────
#  Client principal
# ─────────────────────────────────────────────────────────────────────────────

class MemgraphClient:
    """
    Interface haut niveau vers la base de données Memgraph.

    Usage recommandé (Flask app factory) :
        client = MemgraphClient()
        app.config["db"] = client
    """

    def __init__(self) -> None:
        self._driver: Driver | None = None
        self._connect()

    # ── Connexion ────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        """Établit la connexion Bolt vers Memgraph."""
        try:
            auth = (Config.MEMGRAPH_USERNAME, Config.MEMGRAPH_PASSWORD)
            # Si pas d'authentification configurée sur Memgraph, on passe None
            if not Config.MEMGRAPH_USERNAME:
                auth = None

            self._driver = GraphDatabase.driver(
                Config.bolt_uri(),
                auth=auth,
            )
            # Vérifie que la connexion fonctionne réellement
            self._driver.verify_connectivity()
            logger.info("✅ Connecté à Memgraph sur %s", Config.bolt_uri())
        except (ServiceUnavailable, AuthError) as exc:
            logger.error("❌ Impossible de se connecter à Memgraph : %s", exc)
            self._driver = None

    def is_connected(self) -> bool:
        """Retourne True si le driver est actif et joignable."""
        if self._driver is None:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Ferme proprement la connexion au driver."""
        if self._driver:
            self._driver.close()
            self._driver = None

    @contextmanager
    def _session(self) -> Generator:
        """Context manager : ouvre une session et la ferme après usage."""
        if self._driver is None:
            raise RuntimeError(
                "Le driver Memgraph n'est pas initialisé. "
                "Vérifiez que Memgraph tourne sur "
                f"{Config.bolt_uri()}"
            )
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    # ── Lecture ──────────────────────────────────────────────────────────────

    def get_all_openings(self, limit: int = 500) -> list[dict]:
        """
        Retourne toutes les ouvertures triées par code ECO.
        Cypher : MATCH (o:Opening) RETURN o ORDER BY o.eco_code LIMIT $limit
        """
        query = """
        MATCH (o:Opening)
        RETURN o
        ORDER BY o.eco_code
        LIMIT $limit
        """
        with self._session() as s:
            result = s.run(query, limit=limit)
            return [_node_to_dict(record["o"]) for record in result]

    def get_opening_by_id(self, node_id: str) -> dict | None:
        """
        Cherche une ouverture par son element_id Memgraph.
        Memgraph accepte la fonction id() en Cypher.
        """
        query = """
        MATCH (o:Opening)
        WHERE id(o) = $node_id
        RETURN o
        LIMIT 1
        """
        with self._session() as s:
            result = s.run(query, node_id=int(node_id))
            record = result.single()
            return _node_to_dict(record["o"]) if record else None

    def detect_opening_by_fen(self, fen: str) -> dict | None:
        """
        Détecte l'ouverture correspondant à une position FEN donnée.
        On normalise d'abord la FEN (ignore l'historique de coups).
        """
        norm = normalize_fen(fen)
        # Essai exact sur la FEN normalisée
        query = """
        MATCH (o:Opening)
        WHERE o.fen = $fen OR o.fen_normalized = $fen
        RETURN o
        LIMIT 1
        """
        with self._session() as s:
            result = s.run(query, fen=norm)
            record = result.single()
            if record:
                return _node_to_dict(record["o"])

        # Fallback : cherche aussi sur la FEN brute
        query2 = """
        MATCH (o:Opening)
        WHERE o.fen = $fen
        RETURN o
        LIMIT 1
        """
        with self._session() as s:
            result = s.run(query2, fen=fen)
            record = result.single()
            return _node_to_dict(record["o"]) if record else None

    def get_opening_by_move_sequence(self, moves: str) -> list[dict]:
        """
        Cherche des ouvertures par séquence de coups (partielle ou complète).
        moves peut être : '1. e4 c5' ou 'e4 c5' (format brut).
        On compare via moves_raw pour être insensible aux numéros de coups.
        """
        raw = moves_string_to_raw(moves).lower()
        query = """
        MATCH (o:Opening)
        WHERE toLower(o.moves_raw) STARTS WITH $raw
           OR toLower(o.moves_raw) = $raw
        RETURN o
        ORDER BY size(o.moves_raw)
        LIMIT 20
        """
        with self._session() as s:
            result = s.run(query, raw=raw)
            return [_node_to_dict(record["o"]) for record in result]

    def get_similar_openings(self, node_id: str, depth: int = 1) -> list[dict]:
        """
        Retourne les ouvertures reliées par SIMILAR_TO à une profondeur
        donnée (default 1 = voisins directs).
        La relation est non-dirigée pour la recherche de similarité.
        """
        query = """
        MATCH (o:Opening)-[:SIMILAR_TO*1..$depth]-(similar:Opening)
        WHERE id(o) = $node_id
          AND id(similar) <> $node_id
        RETURN DISTINCT similar
        LIMIT 30
        """
        with self._session() as s:
            result = s.run(query, node_id=int(node_id), depth=depth)
            return [_node_to_dict(record["similar"]) for record in result]

    def search_openings(self, query_str: str) -> list[dict]:
        """Recherche textuelle sur nom, variante et code ECO."""
        q = query_str.lower().strip()
        query = """
        MATCH (o:Opening)
        WHERE toLower(o.name)     CONTAINS $q
           OR toLower(o.variant)  CONTAINS $q
           OR toLower(o.eco_code) CONTAINS $q
        RETURN o
        ORDER BY o.eco_code
        LIMIT 50
        """
        with self._session() as s:
            result = s.run(query, q=q)
            return [_node_to_dict(record["o"]) for record in result]

    def get_graph_data(self, limit: int = 150) -> dict:
        """
        Retourne les nœuds et arêtes pour la visualisation vis.js.
        Format : { "nodes": [...], "edges": [...] }
        """
        # Récupère les nœuds
        node_query = """
        MATCH (o:Opening)
        RETURN o
        LIMIT $limit
        """
        # Récupère les relations
        edge_query = """
        MATCH (o1:Opening)-[r:SIMILAR_TO]->(o2:Opening)
        RETURN id(o1) AS from, id(o2) AS to, id(r) AS rid
        LIMIT $limit
        """
        with self._session() as s:
            nodes_result = s.run(node_query, limit=limit)
            nodes = [_node_to_dict(record["o"]) for record in nodes_result]

        with self._session() as s:
            edges_result = s.run(edge_query, limit=limit * 3)
            edges = [
                {
                    "from": record["from"],
                    "to":   record["to"],
                    "id":   record["rid"],
                }
                for record in edges_result
            ]

        return {"nodes": nodes, "edges": edges}

    def get_stats(self) -> dict:
        """Retourne des statistiques globales sur le graphe."""
        query = """
        MATCH (o:Opening)
        WITH count(o) AS total_openings
        MATCH ()-[r:SIMILAR_TO]->()
        WITH total_openings, count(r) AS total_relations
        RETURN total_openings, total_relations
        """
        with self._session() as s:
            record = s.run(query).single()
            if record:
                return {
                    "total_openings":  record["total_openings"],
                    "total_relations": record["total_relations"],
                }
        return {"total_openings": 0, "total_relations": 0}

    # ── Création ─────────────────────────────────────────────────────────────

    def create_opening(self, data: dict) -> dict | None:
        """
        Crée un nouveau nœud Opening.
        Calcule automatiquement moves_raw et fen_normalized.
        Crée aussi les relations SIMILAR_TO avec les ouvertures existantes.

        Note Memgraph : on utilise CREATE car on vérifie l'unicité
        par eco_code avant d'appeler cette méthode.
        """
        from utils.fen_utils import normalize_fen, moves_string_to_raw

        moves_raw = moves_string_to_raw(data.get("moves", ""))
        fen_norm  = normalize_fen(data.get("fen", ""))

        query = """
        CREATE (o:Opening {
            name:           $name,
            eco_code:       $eco_code,
            moves:          $moves,
            moves_raw:      $moves_raw,
            variant:        $variant,
            fen:            $fen,
            fen_normalized: $fen_normalized
        })
        RETURN o
        """
        params = {
            "name":         data.get("name", ""),
            "eco_code":     data.get("eco_code", ""),
            "moves":        data.get("moves", ""),
            "moves_raw":    moves_raw,
            "variant":      data.get("variant", ""),
            "fen":          data.get("fen", ""),
            "fen_normalized": fen_norm,
        }

        with self._session() as s:
            result = s.run(query, **params)
            record = result.single()
            if not record:
                return None
            new_opening = _node_to_dict(record["o"])

        # Création automatique des relations SIMILAR_TO
        self._create_similar_relations_for(new_opening["id"], moves_raw, data.get("eco_code", ""))
        return new_opening

    def _create_similar_relations_for(
        self, node_id: str, moves_raw: str, eco_code: str
    ) -> int:
        """
        Crée des relations SIMILAR_TO entre le nœud nouvellement créé
        et les ouvertures existantes qui partagent :
          - la même première lettre de code ECO
          - ET les 2 premiers demi-coups
        Retourne le nombre de relations créées.
        """
        if not moves_raw or not eco_code:
            return 0

        tokens = moves_raw.split()
        if len(tokens) < 2:
            return 0

        first_move  = tokens[0]
        second_move = tokens[1]
        eco_letter  = eco_code[0].upper()

        query = """
        MATCH (new:Opening), (existing:Opening)
        WHERE id(new) = $node_id
          AND id(existing) <> $node_id
          AND LEFT(existing.eco_code, 1) = $eco_letter
          AND size(split(existing.moves_raw, ' ')) >= 2
          AND split(existing.moves_raw, ' ')[0] = $first_move
          AND split(existing.moves_raw, ' ')[1] = $second_move
        CREATE (new)-[:SIMILAR_TO]->(existing)
        CREATE (existing)-[:SIMILAR_TO]->(new)
        RETURN count(*) AS created
        """
        # Note : on évite MERGE pour rester cohérent avec la contrainte Memgraph
        # et on accepte de potentielles duplications (gérées à l'import)
        with self._session() as s:
            result = s.run(
                query,
                node_id=int(node_id),
                eco_letter=eco_letter,
                first_move=first_move,
                second_move=second_move,
            )
            record = result.single()
            return record["created"] if record else 0

    # ── Mise à jour ──────────────────────────────────────────────────────────

    def update_opening(self, node_id: str, data: dict) -> dict | None:
        """
        Met à jour les propriétés d'une ouverture existante.
        Recalcule moves_raw et fen_normalized si les champs source changent.
        """
        from utils.fen_utils import normalize_fen, moves_string_to_raw

        moves_raw = moves_string_to_raw(data.get("moves", ""))
        fen_norm  = normalize_fen(data.get("fen", ""))

        query = """
        MATCH (o:Opening)
        WHERE id(o) = $node_id
        SET o.name           = $name,
            o.eco_code       = $eco_code,
            o.moves          = $moves,
            o.moves_raw      = $moves_raw,
            o.variant        = $variant,
            o.fen            = $fen,
            o.fen_normalized = $fen_normalized
        RETURN o
        """
        params = {
            "node_id":        node_id,
            "name":           data.get("name", ""),
            "eco_code":       data.get("eco_code", ""),
            "moves":          data.get("moves", ""),
            "moves_raw":      moves_raw,
            "variant":        data.get("variant", ""),
            "fen":            data.get("fen", ""),
            "fen_normalized": fen_norm,
        }

        with self._session() as s:
            result = s.run(query, **params)
            record = result.single()
            return _node_to_dict(record["o"]) if record else None

    # ── Suppression ──────────────────────────────────────────────────────────

    def delete_opening(self, node_id: str) -> bool:
        """
        Supprime un nœud Opening et toutes ses relations (DETACH DELETE).
        Retourne True si un nœud a été supprimé, False sinon.
        """
        query = """
        MATCH (o:Opening)
        WHERE id(o) = $node_id
        DETACH DELETE o
        RETURN count(o) AS deleted
        """
        with self._session() as s:
            result = s.run(query, node_id=int(node_id))
            record = result.single()
            return bool(record and record["deleted"] > 0)

    # ── Utilitaires base de données ───────────────────────────────────────────

    def create_indexes(self) -> None:
        """
        Crée les index Memgraph pour accélérer les requêtes fréquentes.
        Compatible Memgraph v2.14+ (syntaxe standard Cypher).
        """
        indexes = [
            "CREATE INDEX ON :Opening(eco_code);",
            "CREATE INDEX ON :Opening(fen);",
            "CREATE INDEX ON :Opening(fen_normalized);",
            "CREATE INDEX ON :Opening(name);",
        ]
        with self._session() as s:
            for idx in indexes:
                try:
                    s.run(idx)
                    logger.info("Index créé : %s", idx)
                except Exception as exc:
                    # L'index existe peut-être déjà
                    logger.debug("Index ignoré (%s) : %s", idx, exc)

    def clear_all(self) -> int:
        """
        Supprime tous les nœuds et relations (réinitialisation complète).
        Retourne le nombre de nœuds supprimés.
        ATTENTION : irréversible.
        """
        query = "MATCH (n) DETACH DELETE n RETURN count(n) AS deleted"
        with self._session() as s:
            result = s.run(query)
            record = result.single()
            return record["deleted"] if record else 0

    def run_raw(self, cypher: str, **params) -> list[dict]:
        """
        Exécute une requête Cypher brute (usage avancé / débogage).
        Retourne une liste de dictionnaires.
        """
        with self._session() as s:
            result = s.run(cypher, **params)
            return [dict(record) for record in result]