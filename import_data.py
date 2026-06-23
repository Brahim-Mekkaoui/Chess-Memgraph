"""
import_data.py
--------------
Script d'importation du dataset d'ouvertures d'échecs dans Memgraph.

Étapes :
  1. Connexion à Memgraph via le driver neo4j (Bolt)
  2. Suppression de toutes les données existantes (clear_all)
  3. Création des index pour les performances
  4. Création de chaque nœud Opening depuis openings_eco.json
  5. Création des relations SIMILAR_TO basées sur :
       - même première lettre du code ECO (même famille)
       - ET partage des 2 premiers coups de la séquence moves_raw
"""

import json
import os
import sys
import time

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# ---------------------------------------------------------------------------
# Configuration inline (reprend config.py sans l'importer, pour autonomie)
# ---------------------------------------------------------------------------
MEMGRAPH_HOST = os.getenv("MEMGRAPH_HOST", "localhost")
MEMGRAPH_PORT = int(os.getenv("MEMGRAPH_PORT", 7687))
BOLT_URI      = f"bolt://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}"
DATA_FILE     = os.path.join(os.path.dirname(__file__),"data","openings_eco.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def first_two_moves(moves_raw: str) -> list[str]:
    """
    Retourne les 2 premiers coups d'une séquence moves_raw.
    Ex : 'e4 e5 Nf3 Nc6' → ['e4', 'e5']
    """
    tokens = moves_raw.strip().split()
    return tokens[:2]


def are_similar(moves_a: str, moves_b: str, eco_a: str, eco_b: str) -> bool:
    """
    Deux ouvertures sont similaires si :
      - même 1ère lettre ECO (A, B, C, D ou E)
      - ET les 2 premiers coups sont identiques
    """
    if not moves_a or not moves_b:
        return False
    if eco_a[0].upper() != eco_b[0].upper():
        return False
    return first_two_moves(moves_a) == first_two_moves(moves_b)


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def connect(retries: int = 5, delay: float = 2.0):
    """
    Tente de se connecter à Memgraph avec plusieurs essais.
    Renvoie le driver neo4j ou lève une exception.
    """
    for attempt in range(1, retries + 1):
        try:
            # Memgraph n'utilise pas d'authentification par défaut
            driver = GraphDatabase.driver(
                BOLT_URI,
                auth=("", ""),
                connection_timeout=5
            )
            # Vérifier que la connexion fonctionne réellement
            with driver.session() as session:
                session.run("RETURN 1")
            print(f"✅  Connecté à Memgraph ({BOLT_URI})")
            return driver
        except (ServiceUnavailable, Exception) as exc:
            print(f"⚠️   Tentative {attempt}/{retries} échouée : {exc}")
            if attempt < retries:
                print(f"    Nouvel essai dans {delay}s…")
                time.sleep(delay)
    raise RuntimeError(
        f"Impossible de se connecter à Memgraph après {retries} tentatives.\n"
        "Vérifiez que le conteneur Docker tourne : "
        "docker run -it -p 7687:7687 -p 7444:7444 memgraph/memgraph"
    )


# ---------------------------------------------------------------------------
# Opérations Cypher
# ---------------------------------------------------------------------------

def clear_all(driver) -> None:
    """Supprime tous les nœuds et relations existants."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("🗑️   Base vidée.")


def create_indexes(driver) -> None:
    """
    Crée les index pour accélérer les recherches.
    Memgraph utilise : CREATE INDEX ON :Label(property)
    """
    indexes = [
        "CREATE INDEX ON :Opening(eco_code)",
        "CREATE INDEX ON :Opening(fen)",
        "CREATE INDEX ON :Opening(fen_normalized)",
        "CREATE INDEX ON :Opening(name)",
    ]
    with driver.session() as session:
        for cypher in indexes:
            try:
                session.run(cypher)
            except Exception as e:
                # L'index peut déjà exister — on l'ignore
                print(f"  ↳ Index ignoré ({e})")
    print("📑  Index créés.")


def normalize_fen(fen: str) -> str:
    """
    Normalise un FEN pour comparaison : remet les compteurs
    halfmove et fullmove à 0 et 1 respectivement.
    Ex : 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
         → 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1'
    """
    if not fen:
        return fen
    parts = fen.strip().split()
    if len(parts) == 6:
        parts[4] = "0"   # halfmove clock
        parts[5] = "1"   # fullmove number
    return " ".join(parts)


def create_openings(driver, openings: list[dict]) -> dict[str, str]:
    """
    Crée tous les nœuds Opening dans Memgraph.
    Retourne un mapping name → id Memgraph pour la création des relations.
    """
    id_map: dict[str, int] = {}  # eco_code → id Memgraph (entier)

    cypher = """
    CREATE (o:Opening {
        name          : $name,
        eco_code      : $eco_code,
        moves         : $moves,
        moves_raw     : $moves_raw,
        variant       : $variant,
        fen           : $fen,
        fen_normalized: $fen_normalized
    })
    RETURN id(o) AS eid
    """

    print(f"📦  Importation de {len(openings)} ouvertures…")

    with driver.session() as session:
        for i, op in enumerate(openings, 1):
            fen_raw  = op.get("fen", "")
            fen_norm = normalize_fen(fen_raw)

            result = session.run(cypher, {
                "name"          : op.get("name", ""),
                "eco_code"      : op.get("eco_code", ""),
                "moves"         : op.get("moves", ""),
                "moves_raw"     : op.get("moves_raw", ""),
                "variant"       : op.get("variant", ""),
                "fen"           : fen_raw,
                "fen_normalized": fen_norm,
            })
            record = result.single()
            if record:
                id_map[op.get("eco_code", f"__unknown_{i}")] = record["eid"]  # int

            if i % 20 == 0:
                print(f"    … {i}/{len(openings)} nœuds créés")

    print(f"✅  {len(openings)} nœuds Opening créés.")
    return id_map


def create_similar_relations(driver, openings: list[dict]) -> int:
    """
    Crée les relations SIMILAR_TO entre ouvertures similaires.
    On parcourt toutes les paires (i, j) avec i < j pour éviter les doublons.
    Retourne le nombre de relations créées.
    """
    cypher = """
    MATCH (a:Opening {eco_code: $eco_a}), (b:Opening {eco_code: $eco_b})
    CREATE (a)-[:SIMILAR_TO]->(b)
    """

    count = 0
    total_pairs = len(openings) * (len(openings) - 1) // 2
    print(f"🔗  Analyse de {total_pairs} paires pour relations SIMILAR_TO…")

    with driver.session() as session:
        for i in range(len(openings)):
            for j in range(i + 1, len(openings)):
                a = openings[i]
                b = openings[j]

                if are_similar(
                    a.get("moves_raw", ""),
                    b.get("moves_raw", ""),
                    a.get("eco_code", ""),
                    b.get("eco_code", "")
                ):
                    session.run(cypher, {
                        "eco_a": a["eco_code"],
                        "eco_b": b["eco_code"]
                    })
                    count += 1

    print(f"✅  {count} relations SIMILAR_TO créées.")
    return count


# ---------------------------------------------------------------------------
# Vérification finale
# ---------------------------------------------------------------------------

def print_summary(driver) -> None:
    """Affiche un résumé de l'état de la base après import."""
    with driver.session() as session:
        n_openings = session.run(
            "MATCH (o:Opening) RETURN count(o) AS n"
        ).single()["n"]

        n_relations = session.run(
            "MATCH ()-[r:SIMILAR_TO]->() RETURN count(r) AS n"
        ).single()["n"]

        print("\n" + "=" * 50)
        print("  📊  RÉSUMÉ DE L'IMPORT")
        print("=" * 50)
        print(f"  Nœuds Opening    : {n_openings}")
        print(f"  Relations SIMILAR: {n_relations}")
        print("=" * 50)

        # Exemples de requêtes Cypher intéressantes
        print("\n  💡  Requêtes Cypher d'exemple :")
        print()
        print("  # Toutes les ouvertures de la famille Sicilienne (B20–B99)")
        print("  MATCH (o:Opening) WHERE o.eco_code STARTS WITH 'B'")
        print("  RETURN o.name, o.eco_code ORDER BY o.eco_code;")
        print()
        print("  # Ouvertures similaires à une ouverture donnée")
        print("  MATCH (o:Opening {eco_code: 'B20'})-[:SIMILAR_TO]-(s:Opening)")
        print("  RETURN o.name AS source, s.name AS similaire;")
        print()
        print("  # Chemin entre deux ouvertures (puissance du graphe !)")
        print("  MATCH p = shortestPath(")
        print("    (a:Opening {eco_code: 'C00'})-[:SIMILAR_TO*]-(b:Opening {eco_code: 'C97'})")
        print("  )")
        print("  RETURN [n IN nodes(p) | n.name] AS chemin;")
        print()
        print("  # Ouvertures les plus connectées (hubs du graphe)")
        print("  MATCH (o:Opening)-[r:SIMILAR_TO]-()")
        print("  RETURN o.name, count(r) AS degre")
        print("  ORDER BY degre DESC LIMIT 10;")
        print()


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 50)
    print("  ♟️   IMPORT DES OUVERTURES D'ÉCHECS")
    print("=" * 50 + "\n")

    # 1. Charger le JSON
    if not os.path.exists(DATA_FILE):
        print(f"❌  Fichier introuvable : {DATA_FILE}")
        sys.exit(1)

    with open(DATA_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    # Support des deux formats : liste directe ou {"openings": [...]}
    if isinstance(raw, dict):
        openings: list[dict] = raw.get("openings", list(raw.values())[0] if raw else [])
    else:
        openings = raw

    print(f"📂  {len(openings)} ouvertures chargées depuis {DATA_FILE}")

    # 2. Connexion à Memgraph
    try:
        driver = connect()
    except RuntimeError as e:
        print(f"\n❌  {e}")
        sys.exit(1)

    try:
        # 3. Nettoyage + index
        clear_all(driver)
        create_indexes(driver)

        # 4. Nœuds
        create_openings(driver, openings)

        # 5. Relations
        create_similar_relations(driver, openings)

        # 6. Résumé
        print_summary(driver)

    except Exception as e:
        print(f"\n❌  Erreur pendant l'import : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        driver.close()

    print("\n🎉  Import terminé avec succès !")
    print("    Lancez maintenant : python app.py\n")


if __name__ == "__main__":
    main()