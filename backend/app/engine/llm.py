from typing import Dict, Any, Optional
from backend.app.config import settings

def explain_finding_advisory(
    reason_code: str,
    plain_reason: str,
    field: str,
    value: str,
    source_lane: str
) -> Dict[str, str]:
    """
    Generates plain-language regulatory advisory explanation.
    Uses Ollama or Gemini if available, else deterministic template fallback.
    Returns: {"text": str, "producer": "ollama" | "gemini" | "template"}
    """
    template_text = (
        f"Observation [{reason_code}] in {source_lane.upper()} channel: "
        f"Claimed '{field}' with value '{value}' deviates from regulatory baseline. "
        f"{plain_reason}"
    )

    # 1. Try local Ollama if configured
    if settings.LLM_PROVIDER == "ollama" and settings.OLLAMA_URL:
        try:
            import httpx
            prompt = (
                f"You are a regulatory scrutiny AI assistant. Rephrase the following compliance observation "
                f"into one concise, professional sentence for an AICTE scrutiny officer:\n"
                f"{template_text}"
            )
            resp = httpx.post(
                f"{settings.OLLAMA_URL.rstrip('/')}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 60}
                },
                timeout=1.5
            )
            if resp.status_code == 200:
                data = resp.json()
                rephrased = data.get("response", "").strip()
                if rephrased:
                    return {"text": rephrased, "producer": "ollama"}
        except Exception:
            pass

    # 2. Try Gemini if GEMINI_API_KEY present
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(
                f"Summarize this compliance observation concisely:\n{template_text}"
            )
            if response and response.text:
                return {"text": response.text.strip(), "producer": "gemini"}
        except Exception:
            pass

    # 3. Deterministic template fallback
    return {"text": template_text, "producer": "template"}
