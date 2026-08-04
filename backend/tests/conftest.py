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

# Seed one user per RBAC role so login flows work in tests.
import repositories  # noqa: E402
from database import SessionLocal  # noqa: E402

with SessionLocal() as db:
    for name, role in (("admin", "admin"), ("operator", "operator"), ("viewer", "viewer")):
        try:
            repositories.create_user(db, name, name, role)
        except ValueError:
            pass

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from security import create_token  # noqa: E402


def token_for(role: str) -> str:
    """Sign a valid token for the given role (no DB lookup required)."""
    return create_token(1, role, role)


def make_client(role: str = "admin") -> TestClient:
    """A TestClient whose requests carry a bearer token for the given role."""
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token_for(role)}"})
    return client


def public_client() -> TestClient:
    """A TestClient with no Authorization header."""
    return TestClient(app)
