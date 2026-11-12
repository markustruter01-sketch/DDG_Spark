import datetime as dt
import unittest
from pathlib import Path

from core.gateway import (
    Gateway, GatewayConfig, Message, MockAdapter, ModelAdapter, ModelReply,
    RouteRequest, Router, Sensitivity, SensitivityBlocked, SpendLedger, Tier,
)

RAW = {
    "tiers": {"reason": "opus", "reason_escalation": "fable", "work": "sonnet",
              "bulk": "haiku", "local_fallback": "local"},
    "escalation": {"min_harnesses": 3, "citation_failures": 2, "daily_budget_usd": 1.0},
    "models": {
        "fable": {"provider": "anthropic", "model_id": "f", "usd_per_mtok_in": 100.0, "usd_per_mtok_out": 100.0},
        "opus": {"provider": "anthropic", "model_id": "o", "usd_per_mtok_in": 10.0, "usd_per_mtok_out": 10.0},
        "sonnet": {"provider": "anthropic", "model_id": "s"},
        "haiku": {"provider": "anthropic", "model_id": "h"},
        "local": {"provider": "openai_compatible", "model_id": "l", "max_sensitivity": "RESTRICTED"},
    },
}


def router(raw=RAW):
    return Router(GatewayConfig.from_dict(raw), SpendLedger(today=lambda: dt.date(2026, 11, 13)))


class RoutingTests(unittest.TestCase):
    def test_tier_defaults(self):
        r = router()
        self.assertEqual(r.choose(RouteRequest(Tier.REASON)).model_key, "opus")
        self.assertEqual(r.choose(RouteRequest(Tier.WORK)).model_key, "sonnet")
        self.assertEqual(r.choose(RouteRequest(Tier.BULK)).model_key, "haiku")

    def test_each_escalation_rule_reaches_fable(self):
        r = router()
        for req in (
            RouteRequest(Tier.REASON, deep_think=True),
            RouteRequest(Tier.REASON, harness_count=3),
            RouteRequest(Tier.REASON, challenger_disagrees=True),
            RouteRequest(Tier.REASON, citation_failures=2),
        ):
            d = r.choose(req)
            self.assertEqual(d.model_key, "fable", req)
            self.assertTrue(d.escalated)

    def test_below_thresholds_stays_on_opus(self):
        d = router().choose(RouteRequest(Tier.REASON, harness_count=2, citation_failures=1))
        self.assertEqual(d.model_key, "opus")
        self.assertFalse(d.escalated)

    def test_only_reason_tier_escalates(self):
        self.assertEqual(router().choose(RouteRequest(Tier.WORK, deep_think=True)).model_key, "sonnet")

    def test_spent_budget_falls_back_and_says_so(self):
        r = router()
        r.ledger.record(r.config.models["fable"], 10_000, 0)  # $1.00, the whole budget
        d = r.choose(RouteRequest(Tier.REASON, deep_think=True))
        self.assertEqual(d.model_key, "opus")
        self.assertTrue(d.fell_back)
        self.assertIn("budget", d.reason)

    def test_restricted_data_goes_local(self):
        d = router().choose(RouteRequest(Tier.REASON, sensitivity=Sensitivity.RESTRICTED, deep_think=True))
        self.assertEqual(d.model_key, "local")
        self.assertFalse(d.escalated)

    def test_restricted_data_without_local_model_is_blocked(self):
        raw = {**RAW, "tiers": {k: v for k, v in RAW["tiers"].items() if k != "local_fallback"}}
        with self.assertRaises(SensitivityBlocked):
            router(raw).choose(RouteRequest(Tier.WORK, sensitivity=Sensitivity.RESTRICTED))

    def test_undefined_model_in_tiers_is_rejected(self):
        raw = {**RAW, "tiers": {**RAW["tiers"], "work": "missing"}}
        with self.assertRaises(ValueError):
            GatewayConfig.from_dict(raw)

    def test_shipped_config_loads(self):
        cfg = GatewayConfig.load(Path(__file__).parent.parent / "config" / "models.toml")
        self.assertEqual(cfg.models[cfg.tier_default[Tier.REASON]].model_id, "claude-opus-5-5")
        self.assertEqual(cfg.models[cfg.reason_escalation].model_id, "claude-fable-5-2")


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.adapters = {k: MockAdapter(k, local=(k == "local")) for k in RAW["models"]}
        self.gw = Gateway(router(), self.adapters, on_call=self.log.append)

    def test_mock_satisfies_the_contract(self):
        self.assertIsInstance(MockAdapter(), ModelAdapter)

    def test_run_routes_records_spend_and_logs_egress(self):
        self.adapters["opus"] = MockAdapter("opus", script=[ModelReply("hi", input_tokens=1000, output_tokens=1000)])
        self.gw.adapters = self.adapters
        out = self.gw.run(RouteRequest(Tier.REASON), [Message("user", "question")])
        self.assertEqual(out.reply.text, "hi")
        self.assertAlmostEqual(out.cost_usd, 0.02)
        self.assertAlmostEqual(self.gw.router.ledger.spent_today("opus"), 0.02)
        self.assertEqual(self.log[0]["sent"], ["question"])
        self.assertFalse(self.log[0]["local"])

    def test_swapping_a_model_is_only_a_config_change(self):
        raw = {**RAW, "tiers": {**RAW["tiers"], "work": "local"}}
        gw = Gateway(router(raw), self.adapters)
        self.assertEqual(gw.run(RouteRequest(Tier.WORK), [Message("user", "q")]).decision.model_key, "local")


if __name__ == "__main__":
    unittest.main()
