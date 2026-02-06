"""
Initialize or reset the ABC Music Manager database (schema + default seeds).
Run from project root: python -m src.abc_music_manager.cli_init_db
"""

from .db.schema import get_db_path, init_database


def main() -> None:
    path = get_db_path()
    print(f"Database path: {path}")
    conn = init_database(path)
    conn.close()
    print("Schema created and defaults seeded.")


if __name__ == "__main__":
    main()
