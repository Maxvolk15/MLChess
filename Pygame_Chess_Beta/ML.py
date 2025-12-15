from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple, List, Dict, Set

import chess
import chess.engine


BoardMove = Tuple[Tuple[int, int], Tuple[int, int]]  # ((x1,y1),(x2,y2))


@dataclass(frozen=True)
class DirectionRules:
    """
    Ограничения по направлениям в терминах вектора (dx, dy) в твоих координатах.
    dy>0 — "вверх" (для белых вперёд), dy<0 — "вниз" (для чёрных вперёд).
    Если allow_knight=True — коней НЕ режем по направлению (часто так удобнее).
    """
    allowed_vectors: Set[Tuple[int, int]]
    allow_knight: bool = True

    def is_allowed(self, piece_name: str, from_pos: Tuple[int, int], to_pos: Tuple[int, int]) -> bool:
        if self.allow_knight and piece_name == "Knight":
            return True
        dx = to_pos[0] - from_pos[0]
        dy = to_pos[1] - from_pos[1]

        # Нормализуем вектор для “дальних” фигур (ладья/слон/ферзь)
        # Например (0,5) -> (0,1), (3,-3) -> (1,-1)
        ndx, ndy = _normalize_direction(dx, dy)
        return (ndx, ndy) in self.allowed_vectors


def _normalize_direction(dx: int, dy: int) -> Tuple[int, int]:
    if dx == 0 and dy == 0:
        return (0, 0)
    # направления по прямой/диагонали:
    if dx == 0:
        return (0, 1 if dy > 0 else -1)
    if dy == 0:
        return (1 if dx > 0 else -1, 0)
    # диагональ (для слонов/ферзей):
    if abs(dx) == abs(dy):
        return (1 if dx > 0 else -1, 1 if dy > 0 else -1)
    # “нестандартный” (например, ход коня) — оставим как есть
    return (dx, dy)


class EngineAI:
    """
    Обёртка над UCI-движком (Stockfish или Lc0).
    Мы НЕ генерим ходы через python-chess, потому что у тебя свои правила/логика.
    Мы берём легальные ходы из твоего движка -> фильтруем -> просим UCI выбрать лучший.
    """
    def __init__(self, engine_path: str, movetime_ms: int = 150, threads: int = 1, hash_mb: int = 128):
        self.engine_path = engine_path
        self.movetime_ms = movetime_ms
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        # базовые опции (движок может игнорировать неподдерживаемые)
        try:
            self.engine.configure({"Threads": threads, "Hash": hash_mb})
        except Exception:
            pass

    def close(self):
        try:
            self.engine.quit()
        except Exception:
            pass

    def choose_move(self, chess_board, legal_moves: Dict[Tuple[int, int], List[Tuple[int, int]]],
                    rules: Optional[DirectionRules] = None) -> Optional[BoardMove]:
        """
        chess_board: твой ChessBoard
        legal_moves: как у тебя в Game.get_all_poss_moves(): {from_pos: [to_pos,...]}
        rules: DirectionRules
        """
        fen = chess_board.to_fen()
        b = chess.Board(fen)

        # Список допустимых ходов в UCI-формате
        root_moves: List[chess.Move] = []

        for from_pos, tos in legal_moves.items():
            piece = chess_board.get_piece_at(from_pos)
            if piece is None:
                continue
            for to_pos in tos:
                if rules and not rules.is_allowed(piece.name, from_pos, to_pos):
                    continue
                uci = self._to_uci(from_pos, to_pos)
                mv = chess.Move.from_uci(uci)
                # Очень важно: ход должен быть легален и по FEN-представлению,
                # иначе движок не сможет его анализировать.
                if mv in b.legal_moves:
                    root_moves.append(mv)

        if not root_moves:
            return None

        limit = chess.engine.Limit(time=self.movetime_ms / 1000.0)

        # Ключевой трюк: ограничиваем выбор движка только root_moves
        result = self.engine.play(b, limit, root_moves=root_moves)
        best = result.move
        if best is None:
            return None

        return self._from_uci(best.uci())

    @staticmethod
    def _to_uci(from_pos: Tuple[int, int], to_pos: Tuple[int, int]) -> str:
        # твои координаты: x=0..7 => a..h, y=0..7 => rank 1..8
        def sq(p):
            file_char = "abcdefgh"[p[0]]
            rank_char = str(p[1] + 1)
            return file_char + rank_char
        return sq(from_pos) + sq(to_pos)

    @staticmethod
    def _from_uci(uci: str) -> BoardMove:
        # uci вида "e2e4"
        f1 = "abcdefgh".index(uci[0])
        r1 = int(uci[1]) - 1
        f2 = "abcdefgh".index(uci[2])
        r2 = int(uci[3]) - 1
        return (f1, r1), (f2, r2)