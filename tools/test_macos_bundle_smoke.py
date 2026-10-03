import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("bundle_smoke", Path(__file__).with_name("macos-bundle-smoke.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class RejudgeValidationTests(unittest.TestCase):
    def response(self):
        return {
            "protocolVersion": 3, "engine": {"osuSourceRevision": "pinned"},
            "replay": {"frameCount": 4687},
            "judgements": [
                {"objectIndex": 0, "judgedAt": 1000, "objectEndTime": 1000, "hitError": 0},
                {"objectIndex": 1, "judgedAt": 35008, "objectEndTime": 35008, "hitError": 0},
                {"objectIndex": 1, "judgedAt": 35000, "objectEndTime": 35000, "hitError": 0},
            ],
            "rejudged": {k: {"total": 0} for k in
                         ("performance", "fullComboPerformance", "perfectPerformance")},
        }

    def test_clamped_spinner_time_preserves_callback_order(self):
        data = self.response()
        smoke.verify_rejudge(data, "pinned", 2)
        self.assertEqual([e["judgedAt"] for e in data["judgements"]], [1000, 35008, 35000])

    def test_missing_beatmap_object_is_rejected(self):
        with self.assertRaises(AssertionError):
            smoke.verify_rejudge(self.response(), "pinned", 3)

    def test_wrong_source_revision_is_rejected(self):
        with self.assertRaises(AssertionError):
            smoke.verify_rejudge(self.response(), "different", 2)

    def test_inconsistent_judgement_time_is_rejected(self):
        data = self.response()
        data["judgements"][0]["hitError"] = 50
        with self.assertRaises(AssertionError):
            smoke.verify_rejudge(data, "pinned", 2)

    def test_nonfinite_performance_is_rejected(self):
        data = self.response()
        data["rejudged"]["performance"]["total"] = float("nan")
        with self.assertRaises(AssertionError):
            smoke.verify_rejudge(data, "pinned", 2)


if __name__ == "__main__":
    unittest.main()
