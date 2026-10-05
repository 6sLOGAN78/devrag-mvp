"""Create the system_settings table (stores schema.version and later system-level settings)."""
from api.db.migrations.runner import ensure_system_settings

VERSION = "0001"


def upgrade(db) -> None:
    ensure_system_settings(db)
