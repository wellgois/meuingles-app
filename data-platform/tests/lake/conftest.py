import pytest


@pytest.fixture(scope="session")
def spark():
    from delta import configure_spark_with_delta_pip
    from pyspark.sql import SparkSession

    builder = (SparkSession.builder.master("local[2]").appName("lake-tests")
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
               .config("spark.sql.shuffle.partitions", "2")
               .config("spark.ui.enabled", "false")
               .config("spark.driver.memory", "1g")
               .config("spark.sql.session.timeZone", "UTC"))
    session = configure_spark_with_delta_pip(builder).getOrCreate()
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
