import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


@unittest.skipUnless(os.getenv("ARGUS_TEST_DATABASE_URL"), "Set ARGUS_TEST_DATABASE_URL for database bootstrap checks")
class BootstrapTest(unittest.TestCase):
    def test_fresh_database_supports_repeated_startup(self):
        root = Path(__file__).resolve().parents[3]
        params = conninfo_to_dict(os.environ["ARGUS_TEST_DATABASE_URL"])
        name = "argus_bootstrap_" + uuid.uuid4().hex
        with psycopg.connect(make_conninfo(**params), autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            try:
                target = urlunsplit(urlsplit(os.environ["ARGUS_TEST_DATABASE_URL"])._replace(path="/" + name))
                code = "from app.database import migrate; from app.ingestion import initialize; migrate(); initialize()"
                env = {**os.environ, "DATABASE_URL": target, "PYTHONPATH": str(root / "backend" / "python")}
                for _ in range(2):
                    result = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr)
                with psycopg.connect(target) as conn:
                    self.assertEqual(conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 4)
                    self.assertEqual(conn.execute("SELECT count(*) FROM ingestion_publications").fetchone()[0], 0)
                    self.assertIsNotNone(conn.execute("SELECT to_regclass('ingestion_publications_active_sources')").fetchone()[0])
                    self.assertIsNotNone(conn.execute("SELECT to_regclass('retrieval_query_embeddings')").fetchone()[0])
                    self.assertIsNotNone(conn.execute("SELECT to_regclass('checkpoints')").fetchone()[0])
            finally:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


if __name__ == "__main__":
    unittest.main()
