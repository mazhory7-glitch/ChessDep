import unittest
import chess

class ChessRulesTests(unittest.TestCase):
    def test_standard_initial_position_has_twenty_legal_moves(self):
        self.assertEqual(len(list(chess.Board().legal_moves)),20)

    def test_castling_en_passant_and_promotion_are_supported_by_rules_engine(self):
        castle=chess.Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1')
        self.assertIn('e1g1',[m.uci() for m in castle.legal_moves])
        ep=chess.Board('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1')
        self.assertIn('e5d6',[m.uci() for m in ep.legal_moves])
        promo=chess.Board('4k3/P7/8/8/8/8/8/4K3 w - - 0 1')
        self.assertIn('a7a8q',[m.uci() for m in promo.legal_moves])

    def test_mate_and_stalemate_are_distinct(self):
        mate=chess.Board('7k/6Q1/5K2/8/8/8/8/8 b - - 0 1')
        stale=chess.Board('7k/5Q2/5K2/8/8/8/8/8 b - - 0 1')
        self.assertTrue(mate.is_checkmate());self.assertTrue(stale.is_stalemate())

if __name__=='__main__':unittest.main()
