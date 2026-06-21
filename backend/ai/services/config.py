import os
import sys


def validate_config():
    """Validate required environment variables. Call at module import."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(
            "ERROR: OPENAI_API_KEY environment variable is not set or empty. "
            "The AI service cannot start without it.",
            file=sys.stderr,
        )
        sys.exit(1)
