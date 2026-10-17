"""
zoho_zia.py — Zoho QuickML LLM Serving & Catalyst Adapter for SapthaEvent
========================================================================
Integrates SapthaEvent Portal directly with your dedicated Zoho QuickML LLM Serving API:
- Endpoint: https://api.catalyst.zoho.in/quickml/v1/project/51960000000013050/vlm/chat
- CATALYST-ORG: 60076411708
- Models: VL-Qwen3.6-35B-A3B / GLM-4.7-Flash
"""

import os
import json
import logging
try:
    import requests
except Exception:
    requests = None
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Zoho QuickML Endpoint Configuration
QUICKML_ENDPOINT = os.environ.get(
    'ZOHO_QUICKML_ENDPOINT',
    'https://api.catalyst.zoho.in/quickml/v1/project/51960000000013050/vlm/chat'
)
CATALYST_ORG_ID = os.environ.get('ZOHO_CATALYST_ORG', '60076411708')
ZOHO_AUTH_TOKEN = os.environ.get('ZOHO_AUTH_TOKEN', os.environ.get('CATALYST_AUTH_TOKEN', ''))
DEFAULT_MODEL = os.environ.get('ZOHO_QUICKML_MODEL', 'VL-Qwen3.6-35B-A3B')


def _get_headers() -> Dict[str, str]:
    org_id = os.environ.get('ZOHO_CATALYST_ORG') or CATALYST_ORG_ID
    headers = {
        'Content-Type': 'application/json',
        'CATALYST-ORG': org_id,
    }
    token = os.environ.get('ZOHO_AUTH_TOKEN') or os.environ.get('CATALYST_AUTH_TOKEN') or ZOHO_AUTH_TOKEN
    if token:
        if token.startswith('Bearer ') or token.startswith('Zoho-oauthtoken '):
            headers['Authorization'] = token
        else:
            headers['Authorization'] = f'Bearer {token}'
    return headers


def call_quickml_llm(
    prompt: str,
    system_prompt: str = "Be concise and factual.",
    images: Optional[List[str]] = None,
    temperature: float = 0.7,
    max_tokens: int = 500
) -> Optional[str]:
    """
    Calls the Zoho QuickML LLM Serving API (VL-Qwen3.6-35B-A3B or GLM-4.7-Flash).
    """
    payload = {
        "prompt": prompt,
        "model": DEFAULT_MODEL,
        "system_prompt": system_prompt,
        "top_k": 50,
        "top_p": 0.9,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if images:
        payload["images"] = images

    try:
        headers = _get_headers()
        res = requests.post(QUICKML_ENDPOINT, json=payload, headers=headers, timeout=12)
        if res.status_code == 200:
            data = res.json()
            # Extract output text from QuickML standard JSON response
            if isinstance(data, dict):
                return (
                    data.get('response') or
                    data.get('output') or
                    data.get('message') or
                    data.get('choices', [{}])[0].get('message', {}).get('content') or
                    json.dumps(data)
                )
            return str(data)
        else:
            logger.warning("Zoho QuickML API responded with status %s: %s", res.status_code, res.text)
    except Exception as exc:
        logger.error("Zoho QuickML LLM call failed: %s", exc)

    return None


def ask_zia_chatbot(message: str, context: str = "") -> str:
    """
    Sends user query directly to Zoho QuickML LLM (Qwen 3.6 35B / GLM 4.7 Flash).
    """
    system_prompt = (
        "You are Sparky, the official AI event assistant for Sapthagiri NPS University Event Portal. "
        "Use the provided event context to answer student queries concisely and enthusiastically."
    )
    prompt = f"CONTEXT:\n{context}\n\nUSER QUESTION: {message}"

    llm_output = call_quickml_llm(prompt=prompt, system_prompt=system_prompt, max_tokens=300)
    if llm_output:
        return llm_output

    # Not configured or no answer: say nothing, so the caller tries the next
    # provider or tells the student plainly. The canned "[Zoho QuickML AI]"
    # replies pasted the prompt (with the student's details) into the chat (UPG-65).
    return ''


def match_teams_zia(judges: List[Dict[str, Any]], teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Uses Zoho QuickML LLM Serving to match judges to hackathon teams based on domain expertise.
    """
    prompt = (
        f"Match these judges to teams based on domain expertise:\n"
        f"Judges: {json.dumps(judges)}\n"
        f"Teams: {json.dumps(teams)}\n"
        "Return structured JSON matches."
    )
    system_prompt = "You are a hackathon judge allocator. Return factual judge-to-team assignments."

    llm_output = call_quickml_llm(prompt=prompt, system_prompt=system_prompt, max_tokens=600)
    if llm_output:
        try:
            parsed = json.loads(llm_output)
            if isinstance(parsed, dict) and 'matches' in parsed:
                return parsed
        except Exception:
            pass

    # No model answered. The old fallback assigned teams round-robin and called
    # it a 96%-confident QuickML match; raising lets the caller use Gemini (UPG-65).
    raise RuntimeError("Zoho QuickML is not configured or gave no usable answer")


def search_catalyst_data(search_word: str, table_name: str = "events", column_name: str = "title") -> List[Any]:
    """
    Executes full-text search across Zoho Catalyst Data Store tables
    using the official zcatalyst_sdk Search API.
    """
    try:
        import zcatalyst_sdk
        app = zcatalyst_sdk.initialize()
        config = {
            "search": search_word,
            "search_table_columns": {
                table_name: [column_name]
            }
        }
        search_service = app.search()
        result = search_service.execute_search_query(config)
        return result
    except Exception as exc:
        logger.warning("Zoho Catalyst SDK Search API skipped: %s", exc)
        return []

