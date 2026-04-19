from __future__ import annotations

import unittest

from src.render_payload import (
    build_fallback_draft,
    build_prompt,
    build_render_payload,
    detect_language,
    format_plain_reply,
    infer_confidence,
    infer_data_quality,
    infer_stance,
    validate_model_draft,
)


class RenderPayloadRegressionTests(unittest.TestCase):
    def test_detect_language_prefers_explicit_override_and_per_message_auto_detect(self) -> None:
        self.assertEqual(detect_language("BTC next 2h?", "zh"), "zh")
        self.assertEqual(detect_language("BTC next 2h?"), "en")
        self.assertEqual(detect_language("BTC 接下来 2h?"), "zh")
        self.assertEqual(detect_language("BTC next 2h? 接下来呢"), "zh")
        self.assertEqual(detect_language("!?123"), "zh")

    def test_null_ml_validation_does_not_crash(self) -> None:
        context = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "latest_candle": {
                "open": "69000",
                "high": "69200",
                "low": "68900",
                "close": "69150",
            },
            "indicator_row": None,
            "momentum": {"up_count": 3, "down_count": 1, "flat_count": 0, "total": 4},
            "active_signal": {
                "direction": "bearish",
                "rule_key": "RSI_OVERBOUGHT",
                "price": 69172.2,
                "score": 1.7411,
                "detail": "RSI14 >= 70.0",
                "ml_validation": None,
            },
            "ui_context": {"requested_mode": "standard", "language": "zh"},
        }

        data_quality = infer_data_quality(context, "zh")
        stance = infer_stance(context, "分析一下 BTCUSDT 1m 的走势")
        confidence = infer_confidence(context, stance, data_quality, "zh")
        draft = build_fallback_draft(
            context=context,
            mode="standard",
            language="zh",
            stance=stance,
            confidence=confidence,
        )
        payload = build_render_payload(
            draft=draft,
            context=context,
            mode="standard",
            language="zh",
            stance=stance,
            confidence=confidence,
            data_quality=data_quality,
        )

        self.assertEqual(stance, "bearish")
        self.assertIsNotNone(payload.summary)
        self.assertGreater(len(payload.watchpoints or []), 0)

    def test_english_fallback_payload_and_plain_reply_stay_in_english(self) -> None:
        context = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "latest_candle": {
                "open": "68420",
                "high": "69200",
                "low": "67800",
                "close": "68850",
            },
            "indicator_row": {"rsi": 63.2},
            "momentum": {"up_count": 12, "down_count": 4, "flat_count": 2, "total": 18},
            "active_signal": {
                "direction": "bullish",
                "rule_key": "BREAKOUT_CONTINUATION",
                "price": 68400,
                "score": 0.82,
                "detail": "Breakout is holding above the prior range high.",
                "ml_validation": {"decision": "passed", "probability": 0.82, "threshold": 0.7},
            },
            "ui_context": {"requested_mode": "standard"},
        }

        data_quality = infer_data_quality(context, "en")
        stance = infer_stance(context, "What's the BTC setup over the next 2 hours?")
        confidence = infer_confidence(context, stance, data_quality, "en")
        draft = build_fallback_draft(
            context=context,
            mode="standard",
            language="en",
            stance=stance,
            confidence=confidence,
        )
        payload = build_render_payload(
            draft=draft,
            context=context,
            mode="standard",
            language="en",
            stance=stance,
            confidence=confidence,
            data_quality=data_quality,
        )
        reply = format_plain_reply(payload)

        self.assertEqual(payload.language, "en")
        self.assertEqual(confidence.reason, "ML validation and live context are aligned.")
        self.assertIn("What matters", reply)
        self.assertIn("If this is wrong", reply)
        self.assertNotIn("重点看", reply)

    def test_build_prompt_uses_english_instructions_even_for_chinese_output(self) -> None:
        context = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "latest_candle": {
                "open": "68420",
                "high": "69200",
                "low": "67800",
                "close": "68850",
            },
            "indicator_row": {"rsi": 63.2},
            "momentum": {"up_count": 12, "down_count": 4, "flat_count": 2, "total": 18},
            "active_signal": {
                "direction": "bullish",
                "rule_key": "BREAKOUT_CONTINUATION",
                "price": 68400,
                "score": 0.82,
                "detail": "Breakout is holding above the prior range high.",
                "ml_validation": {"decision": "passed", "probability": 0.82, "threshold": 0.7},
            },
            "ui_context": {"requested_mode": "standard", "language": "zh"},
        }

        data_quality = infer_data_quality(context, "zh")
        confidence = infer_confidence(context, "bullish", data_quality, "zh")
        prompt = build_prompt(
            context=context,
            message="分析一下 BTCUSDT 未来 2 小时的方向。",
            mode="standard",
            language="zh",
            stance="bullish",
            confidence=confidence,
            data_quality=data_quality,
        )

        self.assertIn("Write every user-facing field in natural, professional Simplified Chinese.", prompt)
        self.assertIn("Do not write headings or label prefixes inside any field.", prompt)
        self.assertNotIn("默认使用自然、专业、像交易员说话的中文。", prompt)

    def test_deep_fallback_payload_keeps_expandable_detail(self) -> None:
        context = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "latest_candle": {
                "open": "69000",
                "high": "69200",
                "low": "68900",
                "close": "69150",
            },
            "indicator_row": {"rsi": 71.4},
            "momentum": {"up_count": 3, "down_count": 1, "flat_count": 0, "total": 4},
            "active_signal": {
                "direction": "bearish",
                "rule_key": "RSI_OVERBOUGHT",
                "price": 69172.2,
                "score": 0.68,
                "detail": "RSI14 >= 70.0 and price is stalling into local resistance.",
                "ml_validation": None,
            },
            "ui_context": {"requested_mode": "deep", "language": "zh"},
        }

        data_quality = infer_data_quality(context, "zh")
        stance = infer_stance(context, "分析一下 BTCUSDT 1m 的走势")
        confidence = infer_confidence(context, stance, data_quality, "zh")
        draft = build_fallback_draft(
            context=context,
            mode="deep",
            language="zh",
            stance=stance,
            confidence=confidence,
        )
        payload = build_render_payload(
            draft=draft,
            context=context,
            mode="deep",
            language="zh",
            stance=stance,
            confidence=confidence,
            data_quality=data_quality,
        )

        self.assertIsNotNone(payload.expandable_detail)
        assert payload.expandable_detail is not None
        self.assertIn("RSI14 >= 70.0", payload.expandable_detail.thesis or "")
        self.assertEqual(payload.expandable_detail.evidence, [payload.expandable_detail.thesis])
        self.assertGreater(len(payload.expandable_detail.scenario_map or []), 0)

    def test_validate_model_draft_accepts_deep_expandable_detail(self) -> None:
        draft = validate_model_draft(
            """
            {
              "title": "BTCUSDT 1h",
              "summary": "现在偏多，但要等确认。",
              "market_context": "量能还在配合。",
              "action_posture": "等回踩确认再跟。",
              "risk_flags": ["跌回触发位下方，这段就弱化。"],
              "watchpoints": ["先看触发位能不能守住。"],
              "expandable_detail": {
                "thesis": "延续结构还没坏。",
                "evidence": ["价格还在触发位上方。"],
                "scenario_map": ["守住触发位再看延续。"],
                "ml_context": "ML 验证方向一致。"
              }
            }
            """,
            "deep",
        )

        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertIsNotNone(draft.expandable_detail)
        assert draft.expandable_detail is not None
        self.assertEqual(draft.expandable_detail.ml_context, "ML 验证方向一致。")
        self.assertEqual(draft.expandable_detail.evidence, ["价格还在触发位上方。"])


if __name__ == "__main__":
    unittest.main()
