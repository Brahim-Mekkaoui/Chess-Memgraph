"""
app.py  –  Application Flask principale
========================================
Point d'entrée de l'application web de gestion d'ouvertures d'échecs.

Routes UI :
  GET  /                    → page principale (échiquier interactif)
  GET  /openings            → liste complète des ouvertures
  GET  /opening/<id>        → détail d'une ouverture
  GET  /graph               → visualisation du graphe (vis.js)

Routes API REST (retournent du JSON) :
  GET  /api/openings                → toutes les ouvertures
  GET  /api/opening/<id>            → détail par ID
  POST /api/opening                 → créer une ouverture
  PUT  /api/opening/<id>            → modifier une ouverture
  DELETE /api/opening/<id>          → supprimer une ouverture
  GET  /api/detect?fen=<fen>        → détecter par position FEN
  GET  /api/similar/<id>?depth=<n>  → ouvertures similaires
  GET  /api/search?q=<query>        → recherche textuelle
  GET  /api/moves?moves=<moves>     → rechercher par séquence de coups
  GET  /api/graph-data              → données pour vis.js
  GET  /api/stats                   → statistiques du graphe
  GET  /api/status                  → statut de la connexion Memgraph
"""

import logging
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    abort,
)

from config import Config
from models import MemgraphClient
from utils.fen_utils import fen_is_valid

# ─────────────────────────────────────────────────────────────────────────────
#  Initialisation Flask
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config["DEBUG"] = Config.DEBUG

# Instance globale du client Memgraph
db = MemgraphClient()


# ─────────────────────────────────────────────────────────────────────────────
#  Décorateur : vérifie la connexion Memgraph avant chaque requête API
# ─────────────────────────────────────────────────────────────────────────────

def require_db(f):
    """
    Décorateur qui retourne une erreur 503 si Memgraph est injoignable.
    Appliqué sur les routes API critiques.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not db.is_connected():
            return jsonify({
                "error": "Memgraph est inaccessible. "
                         f"Vérifiez qu'il tourne sur {Config.bolt_uri()}. "
                         "Commande Docker : docker run -p 7687:7687 memgraph/memgraph"
            }), 503
        return f(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
#  Context processor : injecte des variables globales dans tous les templates
# ─────────────────────────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    return {
        "app_name":    Config.APP_NAME,
        "app_version": Config.VERSION,
        "db_status":   db.is_connected(),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Routes UI (pages HTML)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """
    Page principale : échiquier interactif + détection d'ouverture en temps réel.
    """
    stats = {}
    popular_openings = []
    if db.is_connected():
        try:
            stats = db.get_stats()
            popular_openings = db.get_all_openings(limit=8)
        except Exception as exc:
            logger.warning("Impossible de récupérer les stats : %s", exc)
    return render_template("index.html", stats=stats, popular_openings=popular_openings)


@app.route("/openings")
def openings_list():
    """Liste paginée de toutes les ouvertures avec recherche."""
    search_query = request.args.get("q", "").strip()
    openings = []
    error = None

    if not db.is_connected():
        error = (
            "Memgraph est inaccessible. "
            "Lancez : docker run -p 7687:7687 memgraph/memgraph"
        )
    else:
        try:
            if search_query:
                openings = db.search_openings(search_query)
            else:
                openings = db.get_all_openings()
        except Exception as exc:
            error = str(exc)
            logger.error("Erreur get_all_openings : %s", exc)

    return render_template(
        "openings_list.html",
        openings=openings,
        search_query=search_query,
        error=error,
        stats=db.get_stats() if db.is_connected() else {},
    )


@app.route("/opening/<node_id>")
def opening_detail(node_id: str):
    """Page de détail d'une ouverture + ouvertures similaires."""
    if not db.is_connected():
        flash("Memgraph est inaccessible.", "danger")
        return redirect(url_for("index"))

    opening = db.get_opening_by_id(node_id)
    if not opening:
        abort(404)

    similar = []
    try:
        depth = int(request.args.get("depth", 1))
        similar = db.get_similar_openings(node_id, depth=depth)
    except Exception as exc:
        logger.warning("Erreur get_similar : %s", exc)

    return render_template(
        "opening_detail.html",
        opening=opening,
        similar=similar,
    )


@app.route("/graph")
def graph_view():
    """
    Visualisation interactive du graphe avec vis.js.
    Affiche les nœuds Opening et les arêtes SIMILAR_TO.
    """
    return render_template("graph_view.html")


# ─────────────────────────────────────────────────────────────────────────────
#  API REST – Lecture
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """Vérifie la connexion à Memgraph."""
    connected = db.is_connected()
    return jsonify({
        "connected": connected,
        "bolt_uri":  Config.bolt_uri(),
        "message":   "Memgraph opérationnel" if connected else "Memgraph inaccessible",
    }), 200 if connected else 503


@app.route("/api/stats")
@require_db
def api_stats():
    """Statistiques du graphe."""
    try:
        stats = db.get_stats()
        return jsonify(stats)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/openings")
@require_db
def api_get_all_openings():
    """
    GET /api/openings  → liste toutes les ouvertures.
    Paramètres optionnels : ?limit=<n>
    """
    try:
        limit = int(request.args.get("limit", 500))
        openings = db.get_all_openings(limit=limit)
        return jsonify({"openings": openings, "count": len(openings)})
    except Exception as exc:
        logger.error("api_get_all_openings : %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/opening/<node_id>")
@require_db
def api_get_opening(node_id: str):
    """GET /api/opening/<id>  → détail d'une ouverture."""
    try:
        opening = db.get_opening_by_id(node_id)
        if not opening:
            return jsonify({"error": "Ouverture introuvable"}), 404
        return jsonify(opening)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/detect")
@require_db
def api_detect():
    """
    GET /api/detect?fen=<fen>
    Détecte l'ouverture correspondant à une position FEN.
    """
    fen = request.args.get("fen", "").strip()
    if not fen:
        return jsonify({"error": "Paramètre 'fen' manquant"}), 400

    try:
        opening = db.detect_opening_by_fen(fen)
        if opening:
            return jsonify({"found": True, "opening": opening})
        return jsonify({"found": False, "message": "Aucune ouverture reconnue pour cette position"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/similar/<node_id>")
@require_db
def api_similar(node_id: str):
    """
    GET /api/similar/<id>?depth=<n>
    Retourne les ouvertures similaires (profondeur 1 ou 2).
    """
    try:
        depth = min(int(request.args.get("depth", 1)), 2)
        similar = db.get_similar_openings(node_id, depth=depth)
        return jsonify({"similar": similar, "count": len(similar)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/search")
@require_db
def api_search():
    """
    GET /api/search?q=<query>
    Recherche textuelle dans nom, variante et code ECO.
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Paramètre 'q' manquant"}), 400
    try:
        results = db.search_openings(q)
        return jsonify({"results": results, "count": len(results), "query": q})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/moves")
@require_db
def api_by_moves():
    """
    GET /api/moves?moves=<séquence>
    Cherche des ouvertures par séquence de coups.
    Exemple : /api/moves?moves=e4+c5
    """
    moves = request.args.get("moves", "").strip()
    if not moves:
        return jsonify({"error": "Paramètre 'moves' manquant"}), 400
    try:
        results = db.get_opening_by_move_sequence(moves)
        return jsonify({"results": results, "count": len(results)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/graph-data")
@require_db
def api_graph_data():
    """
    GET /api/graph-data
    Retourne les nœuds et arêtes pour vis.js.
    """
    try:
        limit = int(request.args.get("limit", Config.GRAPH_MAX_NODES))
        data = db.get_graph_data(limit=limit)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  API REST – Écriture
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/opening", methods=["POST"])
@require_db
def api_create_opening():
    """
    POST /api/opening
    Corps JSON :
    {
        "name":     "Défense Sicilienne",
        "eco_code": "B20",
        "moves":    "1. e4 c5",
        "variant":  "Partie ouverte",
        "fen":      "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Corps JSON invalide ou manquant"}), 400

    required = ["name", "eco_code", "moves"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Champs manquants : {', '.join(missing)}"}), 400

    if data.get("fen") and not fen_is_valid(data["fen"]):
        return jsonify({"error": "FEN invalide"}), 400

    try:
        new_opening = db.create_opening(data)
        if not new_opening:
            return jsonify({"error": "Échec de la création"}), 500
        return jsonify({
            "message":  "Ouverture créée avec succès",
            "opening":  new_opening,
        }), 201
    except Exception as exc:
        logger.error("api_create_opening : %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/opening/<node_id>", methods=["PUT"])
@require_db
def api_update_opening(node_id: str):
    """
    PUT /api/opening/<id>
    Met à jour une ouverture existante. Corps JSON identique à la création.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Corps JSON invalide"}), 400

    if data.get("fen") and not fen_is_valid(data["fen"]):
        return jsonify({"error": "FEN invalide"}), 400

    try:
        updated = db.update_opening(node_id, data)
        if not updated:
            return jsonify({"error": "Ouverture introuvable"}), 404
        return jsonify({"message": "Ouverture mise à jour", "opening": updated})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/opening/<node_id>", methods=["DELETE"])
@require_db
def api_delete_opening(node_id: str):
    """
    DELETE /api/opening/<id>
    Supprime une ouverture et toutes ses relations (DETACH DELETE).
    """
    try:
        deleted = db.delete_opening(node_id)
        if not deleted:
            return jsonify({"error": "Ouverture introuvable"}), 404
        return jsonify({"message": "Ouverture supprimée avec succès"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  Gestion des erreurs
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Ressource introuvable"}), 404
    return render_template("index.html", error="Page introuvable (404)"), 404


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Erreur interne du serveur"}), 500
    return render_template("index.html", error="Erreur interne (500)"), 500


# ─────────────────────────────────────────────────────────────────────────────
#  Point d'entrée
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("🚀 Démarrage de '%s' v%s", Config.APP_NAME, Config.VERSION)
    logger.info("📊 Base de données graphe : %s", Config.bolt_uri())

    if not db.is_connected():
        logger.warning(
            "⚠️  Memgraph inaccessible sur %s. "
            "Lance : docker run -p 7687:7687 memgraph/memgraph",
            Config.bolt_uri(),
        )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=Config.DEBUG,
    )
