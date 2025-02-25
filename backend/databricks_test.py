from databricks import sql
import os

with sql.connect(server_hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME"),
                 http_path       = os.getenv("DATABRICKS_HTTP_PATH"),
                 access_token    = os.getenv("DATABRICKS_TOKEN")) as connection:

  with connection.cursor() as cursor:
    cursor.execute("SELECT * FROM samples.nyctaxi.trips LIMIT 2")
    result = cursor.fetchall()

    for row in result:
      print(row)


from pyspark.sql.types import StructType, StructField, IntegerType, ArrayType, StringType

schema = StructType([
    StructField("id", IntegerType(), nullable=False),
    StructField("approved_skills", ArrayType(StringType())),
    StructField("approved_competencies", ArrayType(StringType()))
])
