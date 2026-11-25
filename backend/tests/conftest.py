import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

# Load .env first so the dummy defaults below really only fill gaps (integration tests need real values).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Unit tests never call Supabase. Dummy values only apply when .env doesn't define them.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
# Tests never start the background job worker; they drive it with Worker.run_once().
os.environ["WORKER_ENABLED"] = "false"
