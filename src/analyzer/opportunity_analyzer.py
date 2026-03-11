from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite business opportunity analyst working exclusively for a solo entrepreneur based in Turkey who is looking for business opportunities across ALL industries and sectors. Your job is to scan real-time signals from the GLOBAL ecosystem — Hacker News, Product Hunt, Reddit, GitHub, Google Trends, and Indie Hackers — and surface high-value, actionable business opportunities in ANY industry: e-commerce, food & beverage, health & wellness, education, finance, real estate, logistics, agriculture, entertainment, fashion, travel, manufacturing, and more.

CRITICAL: You MUST write ALL your output in TURKISH. Every field (title, explanation, why_it_works, market_opportunity, monetization, success_factors) must be in Turkish. Research globally, write in Turkish.

Your analysis framework:

1. SIGNAL INTERPRETATION
   - Identify problems people are complaining about, gaps in existing products or services, emerging trends, and underserved markets across ANY sector
   - Look for patterns across multiple signals (cross-source validation = higher confidence)
   - Pay special attention to "Show HN", trending discussions, Reddit posts with high engagement and frustration/need language, and rapidly growing communities around a topic
   - Consider both online (digital products, platforms, marketplaces) and offline (physical products, local services, hybrid models) business opportunities

2. OPPORTUNITY CRITERIA (score each)
   - Market Demand: Is there clear evidence people need/want this? (1-5)
   - Competition Level: Is the space uncrowded enough for a solo founder? (1-5, higher = less competition)
   - Monetization Clarity: Is it obvious how to generate revenue? (1-5)
   - Execution Feasibility: Can a solo founder launch a v1 or MVP within 1-3 months with reasonable resources? (1-5)
   - Turkey/Global Applicability: Can this serve the Turkish market and/or scale globally? (1-5)

3. OPPORTUNITY CATEGORIES
   You MUST identify exactly 3-4 opportunities in these categories:

   - BEST: The single highest-potential opportunity. Should have strong demand signals, clear monetization, and be achievable for a solo founder within 60-90 days. This is the one to pursue.

   - MEDIUM: A solid opportunity requiring more resources or time. Might need 3-6 months or a small team. Good market potential but higher complexity.

   - SMALL: A quick win that can be launched in 2-4 weeks. Lower ceiling but fast to market. Could be a side project generating $500-5000/month equivalent.

   - AI_SYNTHESIZED (include if and only if you see a creative cross-signal opportunity that isn't obvious from any single signal): A novel idea that emerges from combining multiple weak signals into something stronger.

4. OUTPUT FORMAT
   Respond with ONLY valid JSON. No markdown, no explanation outside JSON. Use this exact structure:

{
  "opportunities": [
    {
      "category": "BEST",
      "title": "Concise product/business name/concept (max 80 chars)",
      "explanation": "2-3 sentence description of what this is and who it's for",
      "why_it_works": "2-3 sentences explaining WHY this specific opportunity exists NOW — what signals validate it, what problem is underserved",
      "market_opportunity": "Specific market size indication, target customer segment, pricing model potential (e.g., '200 TL/ay abonelik, 10.000 KOBİ hedefi = 24M TRY ARR tavanı')",
      "monetization": "Primary monetization strategy with specific pricing tier examples",
      "difficulty": 2,
      "success_factors": "3-5 critical factors that determine success or failure for this specific opportunity"
    }
  ]
}

IMPORTANT RULES:
- difficulty is an integer 1-5 (1=easiest, 5=hardest)
- Each opportunity must be genuinely distinct — no overlapping ideas
- Ground every opportunity in specific signals from the data provided — never invent signals
- Be ruthlessly specific about pricing and market size — avoid vague statements
- The BEST opportunity should be the one you would personally pursue if you were the entrepreneur
- For Turkey market: consider local payment methods (IBAN, credit card penetration ~60%), Turkish SMB digitization gap, EUR/USD pricing for global products, TRY pricing for local products and services
- Opportunities exist across all sectors: e-commerce, food, health, education, finance, real estate, logistics, agriculture, entertainment, fashion, travel, software, and more — do not limit yourself to tech
- ABSOLUTELY CRITICAL: ALL text in the JSON output MUST be written in TURKISH language. Title, explanation, why_it_works, market_opportunity, monetization, success_factors - ALL fields MUST be in Turkish. This is non-negotiable. Example title: "Yerel Üreticiler İçin Online Pazar Yeri" NOT "Online Marketplace for Local Producers"."""

_MODELS = [
    "google/gemma-3n-e4b-it:free",
    "openrouter/free",
]
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _build_signal_text(signals: list[dict], max_signals: int = 150) -> str:
    lines: list[str] = []
    for i, signal in enumerate(signals[:max_signals]):
        source = signal.get("source", "unknown")
        title = signal.get("title", "")
        content = signal.get("content", "") or ""
        url = signal.get("url", "") or ""
        metadata = signal.get("metadata", {}) or {}

        parts = [f"[{i+1}] SOURCE: {source.upper()}"]
        parts.append(f"TITLE: {title}")
        if url:
            parts.append(f"URL: {url}")

        if content:
            trimmed_content = content[:300].replace("\n", " ").strip()
            if trimmed_content:
                parts.append(f"CONTENT: {trimmed_content}")

        meta_highlights: list[str] = []
        for key in ("score", "points", "num_comments", "stars_today", "language", "subreddit", "geo"):
            val = metadata.get(key)
            if val is not None and val != "" and val != 0:
                meta_highlights.append(f"{key}={val}")

        if meta_highlights:
            parts.append(f"META: {', '.join(meta_highlights)}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


def _extract_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text


def _validate_opportunity(opp: dict[str, Any]) -> bool:
    required = {"category", "title", "explanation", "why_it_works", "market_opportunity", "monetization", "difficulty", "success_factors"}
    valid_categories = {"BEST", "MEDIUM", "SMALL", "AI_SYNTHESIZED"}
    has_required = required.issubset(opp.keys())
    has_valid_category = opp.get("category") in valid_categories
    return has_required and has_valid_category


class OpportunityAnalyzer:
    def __init__(self) -> None:
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not configured")

    def _call_model(self, model: str, messages: list[dict], client: httpx.Client) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        response = client.post(_OPENROUTER_URL, json=payload, headers=headers, timeout=180.0)
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        logger.info("Model %s returned content length: %s", model, len(content) if content else "None")
        if not content:
            logger.warning("Model %s returned no content. Full response: %s", model, str(data)[:500])
        return content or ""

    def analyze_signals(self, signals: list[dict]) -> list[dict]:
        if not signals:
            logger.warning("OpportunityAnalyzer: no signals provided")
            return []

        signal_text = _build_signal_text(signals, max_signals=20)
        user_message = f"""Analyze these {len(signals)} signals from today's tech ecosystem scan and identify 3-4 business opportunities:

--- BEGIN SIGNALS ---
{signal_text}
--- END SIGNALS ---

Based on these signals, identify the most promising business opportunities. Return ONLY the JSON response as specified."""

        combined_message = f"""{SYSTEM_PROMPT}

{user_message}"""
        messages = [
            {"role": "user", "content": combined_message},
        ]

        logger.info("OpportunityAnalyzer: sending %d signals to OpenRouter", len(signals))

        raw_text = ""
        with httpx.Client() as client:
            for model in _MODELS:
                try:
                    logger.info("Trying model: %s", model)
                    raw_text = self._call_model(model, messages, client)
                    if raw_text:
                        logger.info("Model %s succeeded", model)
                        break
                except httpx.HTTPStatusError as exc:
                    logger.warning("Model %s returned HTTP %d, trying next", model, exc.response.status_code)
                    continue
                except Exception as exc:
                    logger.warning("Model %s error: %s, trying next", model, exc)
                    continue
            if not raw_text:
                logger.error("All models failed")
                return []

        logger.info("OpenRouter raw response length: %d chars, first 300: %s", len(raw_text), raw_text[:300])

        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```\s*$", "", raw_text)

        try:
            json_str = _extract_json(raw_text)
            parsed = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse OpenRouter JSON response: %s\nRaw: %s", exc, raw_text[:1000])
            return []

        raw_opportunities = parsed.get("opportunities", [])
        if not isinstance(raw_opportunities, list):
            logger.error("Unexpected opportunities format: %s", type(raw_opportunities))
            return []

        valid_opportunities: list[dict] = []
        for opp in raw_opportunities:
            if not isinstance(opp, dict):
                continue
            if not _validate_opportunity(opp):
                logger.warning("Skipping invalid opportunity: %s", opp.get("title", "?"))
                continue

            difficulty = opp.get("difficulty", 3)
            try:
                difficulty = max(1, min(5, int(difficulty)))
            except (TypeError, ValueError):
                difficulty = 3

            normalized = {
                "title": str(opp.get("title", ""))[:500],
                "explanation": str(opp.get("explanation", "")),
                "why_it_works": str(opp.get("why_it_works", "")),
                "market_opportunity": str(opp.get("market_opportunity", "")),
                "monetization": str(opp.get("monetization", "")),
                "difficulty": difficulty,
                "success_factors": str(opp.get("success_factors", "")),
                "category": str(opp.get("category", "MEDIUM")),
            }
            valid_opportunities.append(normalized)

        logger.info("OpportunityAnalyzer: %d valid opportunities extracted", len(valid_opportunities))
        return valid_opportunities
