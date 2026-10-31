import unittest

from src.scoring_engine import score_competitors, score_website


class ScoringTests(unittest.TestCase):
    def test_perfect_available_signals_score_one_hundred(self):
        result = score_website({"Title": "Salon", "Meta Description": "Hair care",
                                "H1 Count": 1, "Heading Count": 3,
                                "Word Count": 150, "Contact Signal": True})
        self.assertEqual(result["Website Score"], 100)
        self.assertEqual(result["Score Coverage"], "6/6 signals")

    def test_missing_signals_are_excluded(self):
        result = score_website({"Title": "Salon", "H1 Count": 2})
        self.assertEqual(result["Website Score"], 50)
        self.assertEqual(result["Score Coverage"], "2/6 signals")

    def test_no_measurable_signals_has_no_score(self):
        self.assertIsNone(score_website({})["Website Score"])

    def test_batch_scoring_does_not_mutate_input(self):
        source = [{"Business": "A", "Title": "A"}]
        scored = score_competitors(source)
        self.assertNotIn("Website Score", source[0])
        self.assertEqual(scored[0]["Website Score"], 100)


if __name__ == "__main__":
    unittest.main()
