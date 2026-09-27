"""magicpin AI Challenge candidate bot."""

from dotenv import load_dotenv

# Load .env into the real process environment BEFORE anything else is imported.
# pydantic-settings' `env_file=".env"` (used by app.config.Settings) only
# populates the fields declared on that model - it does NOT export arbitrary
# keys to os.environ. composer.py reads GEMINI_API_KEY/LLM_MODEL/LLM_PROVIDER
# straight from os.environ, so without this call those variables are never
# actually visible to the running process, even though they're sitting right
# there in .env.
load_dotenv()

from app.main import create_app  # noqa: E402

__all__ = ["create_app"]
