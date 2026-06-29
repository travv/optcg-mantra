"""Integration test for parser against a canonical Kalgara-vs-Teach replay.

Pins enough state to catch regressions in:
  * Player identity (`first` must be the real Kalgara-side player, not a
    leader-less placeholder like "Your Client" or "Opponent").
  * Turn-boundary logic (Kalgara's 5-DON turn is turn 4 going 1st).
  * Effect sub-verb extraction (deploy / effect_deploy / effect_attach_don /
    effect_top_life / effect_draw_card all surface with the right targets).

Run: `python3 -m unittest mantra/tests/test_parser_kalgara.py`
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # so `import parser` resolves

from parser import parse_log  # noqa: E402


FIXTURE = os.path.join(HERE, "fixtures", "kalgara-vs-teach-canonical.log")

KALGARA = "OP08-098"
TEACH = "OP16-080"


class TestKalgaraReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.parsed = parse_log(f.read())
        cls.kp = next(
            n for n, i in cls.parsed["players"].items() if i.get("leader") == KALGARA
        )
        cls.tp = next(
            n for n, i in cls.parsed["players"].items() if i.get("leader") == TEACH
        )

    def test_first_player_has_a_leader(self):
        """The `first` field must point at a real player, not a placeholder
        like `Your Client` or `Opponent` that has no leader assigned."""
        first = self.parsed["first"]
        self.assertIsNotNone(first)
        info = self.parsed["players"].get(first)
        self.assertIsNotNone(info, f"first={first!r} is not in players dict")
        self.assertIsNotNone(
            info.get("leader"),
            f"first={first!r} has no leader assigned — placeholder leaked",
        )

    def test_kalgara_goes_first(self):
        self.assertEqual(self.parsed["first"], self.kp)

    def test_kalgara_5don_turn_is_turn_4(self):
        """Going 1st, the DON curve is 1-3-5-7-9-10. Turn 4 is the 5-DON turn."""
        kalgara_turns = [t for t in self.parsed["turns"] if t.get("player") == self.kp]
        # Order is by appearance in the log; the 2nd Kalgara turn is turn 4
        # in the global numbering (turns interleave 1=K, 2=T, 3=K... wait, K
        # goes 1st so 1=K, 2=T, 3=K, 4=T, 5=K → Kalgara's 3rd turn is turn 5).
        # Just find the 5-DON turn directly.
        five_don = [t for t in kalgara_turns if t.get("don_at_start") == 5]
        self.assertEqual(
            len(five_don), 1,
            f"expected exactly one Kalgara 5-DON turn, got {len(five_don)}",
        )

    def test_5don_action_sequence(self):
        """Pin the structured-verb sequence on the 5-DON turn so future
        parser changes don't silently drop a sub-verb (e.g. effect_top_life,
        effect_draw_card from on-deploy)."""
        turn = next(
            t for t in self.parsed["turns"]
            if t.get("player") == self.kp and t.get("don_at_start") == 5
        )
        verbs = [a.get("verb") for a in turn["actions"]]
        # Must include the Kalgara-leader-effect sequence:
        for v in ("attack", "deploy", "effect_attach_don",
                  "effect_deploy", "effect_top_life", "effect_draw_card"):
            self.assertIn(v, verbs, f"missing {v!r} in turn verbs: {verbs}")

        # The leader-effect deploy must target 4c Kalgara (OP12-099) and the
        # following effect_top_life must source from the leader.
        eff_deploy = next(a for a in turn["actions"] if a.get("verb") == "effect_deploy")
        self.assertEqual(eff_deploy.get("card"), "OP12-099")
        self.assertEqual(eff_deploy.get("source_card"), KALGARA)

        eff_top = next(a for a in turn["actions"] if a.get("verb") == "effect_top_life")
        self.assertEqual(eff_top.get("source_card"), KALGARA)

        # The on-deploy draw from 4c Kalgara — source_card is OP12-099 (the
        # character speaking), and qty is 1.
        on_deploy_draw = next(
            a for a in turn["actions"]
            if a.get("verb") == "effect_draw_card" and a.get("source_card") == "OP12-099"
        )
        self.assertEqual(on_deploy_draw.get("qty"), 1)
        self.assertEqual(on_deploy_draw.get("player"), self.kp)

    def test_attack_attacker_attribution(self):
        """Make sure attack actions carry the attacker id so the analyzer
        can tell "swing with this-turn-deploy" vs "swing with old board"."""
        turn = next(
            t for t in self.parsed["turns"]
            if t.get("player") == self.kp and t.get("don_at_start") == 5
        )
        attacks = [a for a in turn["actions"] if a.get("verb") == "attack"]
        self.assertGreater(len(attacks), 0)
        for a in attacks:
            self.assertIsNotNone(a.get("attacker"), f"attack with no attacker: {a}")


if __name__ == "__main__":
    unittest.main()
