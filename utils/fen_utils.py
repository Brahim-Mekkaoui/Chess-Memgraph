"""
utils/fen_utils.py
Utilitaires pour manipuler les chaînes FEN (Forsyth-Edwards Notation).

La FEN décrit l'état complet d'une position d'échecs :
  <pièces> <trait> <roques> <en-passant> <demi-coups> <numéro-coup>
  Exemple : rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1
"""


# Valeur des pièces pour comparer deux positions (approximation rapide)
PIECE_VALUES = {
    "p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0,
    "P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0,
}


def fen_is_valid(fen: str) -> bool:
    """
    Vérifie qu'une chaîne FEN a la bonne structure (6 parties séparées
    par des espaces) et que la partie pièces contient exactement 8 rangs.
    Ne valide pas la légalité complète de la position (trop coûteux sans
    python-chess).
    """
    if not fen or not isinstance(fen, str):
        return False

    parts = fen.strip().split()
    if len(parts) != 6:
        return False

    ranks = parts[0].split("/")
    if len(ranks) != 8:
        return False

    # Chaque rang doit avoir exactement 8 cases
    for rank in ranks:
        count = 0
        for ch in rank:
            if ch.isdigit():
                count += int(ch)
            elif ch.isalpha():
                count += 1
            else:
                return False
        if count != 8:
            return False

    return True


def normalize_fen(fen: str) -> str:
    """
    Normalise une FEN :
      - Supprime les espaces superflus
      - Remet le compteur de demi-coups et le numéro de coup à 0 / 1
        afin de faciliter la comparaison de positions indépendamment
        de l'historique des coups.
    """
    if not fen_is_valid(fen):
        return fen.strip()

    parts = fen.strip().split()
    # On conserve pièces, trait, roques, en-passant mais on normalise les compteurs
    return f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} 0 1"


def fen_to_board_dict(fen: str) -> dict:
    """
    Convertit la partie « pièces » d'une FEN en dictionnaire
    { "e1": "K", "d1": "Q", … } (coordonnées algébriques → symbole de pièce).
    Utile pour affichage ou calcul côté serveur.
    """
    if not fen_is_valid(fen):
        return {}

    board = {}
    pieces_part = fen.split()[0]
    ranks = pieces_part.split("/")

    # Les rangs FEN vont de la rangée 8 (index 0) à la rangée 1 (index 7)
    for rank_idx, rank_str in enumerate(ranks):
        rank_number = 8 - rank_idx  # 8, 7, … 1
        file_idx = 0
        for ch in rank_str:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                file_letter = chr(ord("a") + file_idx)
                square = f"{file_letter}{rank_number}"
                board[square] = ch
                file_idx += 1

    return board


def extract_side_to_move(fen: str) -> str:
    """Retourne 'white' ou 'black' selon le trait dans la FEN."""
    if not fen_is_valid(fen):
        return "unknown"
    return "white" if fen.split()[1] == "w" else "black"


def count_pieces(fen: str) -> dict:
    """
    Compte les pièces restantes sur l'échiquier.
    Retourne un dictionnaire { "P": 8, "p": 8, "N": 2, … }.
    """
    if not fen_is_valid(fen):
        return {}

    counts: dict = {}
    for ch in fen.split()[0]:
        if ch.isalpha():
            counts[ch] = counts.get(ch, 0) + 1

    return counts


def moves_string_to_raw(moves: str) -> str:
    """
    Convertit une chaîne de coups annotée (ex. '1. e4 e5 2. Nf3 Nc6')
    en une chaîne brute sans numéros (ex. 'e4 e5 Nf3 Nc6').
    Utilisée pour la comparaison de séquences entre ouvertures.
    """
    tokens = moves.replace(".", " ").split()
    # Filtrer les jetons purement numériques (numéros de coups)
    raw_tokens = [t for t in tokens if not t.isdigit()]
    return " ".join(raw_tokens)


def first_n_moves_raw(moves_raw: str, n: int = 2) -> str:
    """
    Retourne les n premiers coups (demi-coups / plies) d'une séquence brute.
    Ex. : first_n_moves_raw("e4 e5 Nf3 Nc6", 2) → "e4 e5"
    """
    tokens = moves_raw.split()
    return " ".join(tokens[:n])


def openings_share_first_moves(raw1: str, raw2: str, n: int = 2) -> bool:
    """
    Vérifie si deux séquences brutes partagent les n premiers demi-coups.
    """
    return first_n_moves_raw(raw1, n) == first_n_moves_raw(raw2, n)
