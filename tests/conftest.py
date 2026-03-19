from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RENDER_BACKEND_URL = "https://unlxck-gpt-webhook.onrender.com"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
