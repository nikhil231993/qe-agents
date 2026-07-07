"""Central configuration for the QE Agents pipeline.

Keeping model choice, sandbox limits, and SUT config here (rather than
scattered through agent code) so reviewers can see configuration separated
from logic, and so the models can be swapped without touching pipeline code.

All values are overridable via environment variables.
"""

import os

from dotenv import load_dotenv

# Load a local .env file if present (gitignored) so GITHUB_TOKEN can persist
# across separate shell invocations without re-exporting it every time.
load_dotenv()

# --- LLM configuration (GitHub Models: free, OpenAI-compatible) ---
# Auth: set GITHUB_TOKEN to a GitHub PAT with "models: read" permission,
# or run `gh auth login` and export `GITHUB_TOKEN=$(gh auth token)`.
GITHUB_MODELS_BASE_URL = os.environ.get(
    "GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"
)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Reasoning-heavy steps (risk ranking, ambiguity surfacing, root cause,
# clustering rationale) use the larger model; mechanical plan->code
# generation uses the smaller/faster one. Swap freely via env vars.
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "openai/gpt-4o")
GENERATOR_MODEL = os.environ.get("GENERATOR_MODEL", "openai/gpt-4o-mini")
TRIAGER_MODEL = os.environ.get("TRIAGER_MODEL", "openai/gpt-4o")

# --- System under test ---
SUT_BASE_URL = os.environ.get("SUT_BASE_URL", "https://restful-booker.herokuapp.com")
SUT_NAME = os.environ.get("SUT_NAME", "restful-booker")

# --- Executor sandbox limits ---
# v2 (simplified) safety posture: subprocess.run (no shell=True), isolated
# tempdir, hard timeout. No AST allow-list / container isolation in this
# pass -- see DESIGN.md "What's next" for the hardened version.
EXECUTOR_TIMEOUT_SECONDS = int(os.environ.get("EXECUTOR_TIMEOUT_SECONDS", "60"))

# --- Misc ---
ARTIFACTS_DIR = os.environ.get("ARTIFACTS_DIR", "artifacts")
GENERATED_TESTS_DIR = os.environ.get("GENERATED_TESTS_DIR", "tests_generated")
