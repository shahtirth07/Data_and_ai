import os
import time

import ibis
from dotenv import load_dotenv

_con = None


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_connection():
    env_path = os.path.join(_project_root(), ".env")
    load_dotenv(env_path)

    api_key = os.getenv("HOTDATA_API_KEY")
    workspace_id = os.getenv("HOTDATA_WORKSPACE_ID")

    con = ibis.hotdata.connect(
        api_url="https://api.hotdata.dev",
        token=api_key,
        workspace_id=workspace_id,
    )
    return con


def connect():
    global _con
    con = make_connection()
    _con = con
    return con


def create_task_db(name, df, con=None):
    client = _con
    if con is not None:
        client = con

    database_id = client.create_database(name, tables=["orders"])
    client.create_table(
        "orders",
        df,
        database=(database_id, "main"),
        overwrite=True,
    )
    # Uploads are async — wait briefly before querying.
    time.sleep(2)
    return database_id


def run_sql(con, db, sql):
    con._database_id = db
    con._database_connection_id = None
    result = con.sql(sql).execute()
    return result


def destroy_db(con, db):
    if hasattr(con, "drop_database"):
        con.drop_database(db, force=True)
        return

    # TODO: hotdata-ibis had no delete method when this was written.
    print("destroy_db: no drop_database method available; skipped delete for", db)
