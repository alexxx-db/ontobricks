"""Create the app's Unity Catalog tables and seed them, as the job's run-as identity.

Argument: the app's schema, as catalog.schema. Run by `databricks bundle run migrate`,
alongside the Lakebase migrations. Every statement is idempotent, so a rerun changes
nothing. The rows are reference data and hold no PHI.

Names go through IDENTIFIER and values through named parameters, never string
formatting, per the SQL controls in docs/guides/slices-and-ports.md.
"""

import sys

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

args = {
    "schema": sys.argv[1],
    "table": "examples",
    "id1": 1,
    "label1": "first",
    "id2": 2,
    "label2": "second",
    "id3": 3,
    "label3": "third",
}
spark.sql(
    "CREATE TABLE IF NOT EXISTS IDENTIFIER(:schema '.' :table) "
    "(id INT NOT NULL, label STRING NOT NULL)",
    args=args,
)
spark.sql(
    """
    MERGE INTO IDENTIFIER(:schema '.' :table) AS t
    USING (
      SELECT * FROM VALUES
        (:id1, :label1),
        (:id2, :label2),
        (:id3, :label3)
      AS s(id, label)
    ) AS s
    ON t.id = s.id
    WHEN NOT MATCHED THEN INSERT *
    """,
    args=args,
)
row_count = spark.sql(
    "SELECT COUNT(*) AS n FROM IDENTIFIER(:schema '.' :table)",
    args=args,
).collect()[0]["n"]
print(f"{row_count} rows")
