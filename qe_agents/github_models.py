"""Thin wrapper around the OpenAI SDK pointed at GitHub Models.

GitHub Models exposes an OpenAI-compatible chat completions API, so we reuse
the official `openai` client and just override `base_url` + `api_key`. This
keeps agent code identical to what it would look like against real OpenAI --
swapping providers later is a one-line change in settings.py.
"""

from openai import OpenAI

from qe_agents import settings


def get_client() -> OpenAI:
    if not settings.GITHUB_TOKEN:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. Create a GitHub PAT with 'models: read' "
            "permission (or run `gh auth login` and `export "
            "GITHUB_TOKEN=$(gh auth token)`), then re-run."
        )
    return OpenAI(base_url=settings.GITHUB_MODELS_BASE_URL, api_key=settings.GITHUB_TOKEN)


def chat(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    """Single-turn chat completion helper used by every agent node."""
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""
