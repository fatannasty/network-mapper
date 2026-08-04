import os
import sys

# Use an in-memory database for ALL tests so dev data is never touched.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Create all tables on the shared in-memory engine before any test runs.
from database import init_db  # noqa: E402

init_db()
