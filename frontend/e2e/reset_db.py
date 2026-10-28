"""Drop, recreate and migrate the end-to-end database (run with the backend's uv env).

Usage: uv run python ../frontend/e2e/reset_db.py <database-url>
"""

import sys

from sqlalchemy import create_engine, make_url, text

from trafiqon.persistence.db import migrate

url = make_url(sys.argv[1])
admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
with admin.connect() as conn:
    conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    conn.execute(text(f'CREATE DATABASE "{url.database}"'))
admin.dispose()
migrate(sys.argv[1])
print("e2e database migrated from clean")
