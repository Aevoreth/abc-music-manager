"""Verify schema and seed (run from project root: python scripts/verify_schema.py)."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.abc_music_manager.db.schema import create_schema, seed_defaults
import sqlite3

conn = sqlite3.connect(":memory:")
create_schema(conn)
seed_defaults(conn)
cur = conn.execute("SELECT id, name FROM Status ORDER BY sort_order")
print("Status rows:", cur.fetchall())
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print("Tables:", [r[0] for r in cur.fetchall()])
conn.close()
print("Schema OK.")
