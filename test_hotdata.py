import os
import time

import pandas as pd

from src.hotdata_client import connect, create_task_db, destroy_db, run_sql

project_root = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(project_root, "data", "orders.csv")

df = pd.read_csv(csv_path)
print("Loaded", len(df), "rows from", csv_path)

con = connect()
print("Connected to Hotdata")

create_start = time.time()
db = create_task_db("test_db", df)
create_elapsed = time.time() - create_start
print("Created database test_db id=", db)
print("Create time seconds=", round(create_elapsed, 2))

sql = (
    'SELECT region, SUM(amount) AS total_amount '
    'FROM "default"."main"."orders" '
    "GROUP BY region "
    "ORDER BY total_amount DESC"
)

query_start = time.time()
result = run_sql(con, db, sql)
query_elapsed = time.time() - query_start
print("Total amount by region:")
print(result)
print("Query time seconds=", round(query_elapsed, 2))

destroy_start = time.time()
destroy_db(con, db)
destroy_elapsed = time.time() - destroy_start
print("Destroyed database")
print("Destroy time seconds=", round(destroy_elapsed, 2))
