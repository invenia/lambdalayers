import psycopg2
import psycopg2.extensions


def lambda_handler(event, context):
    return {
        "libpq": psycopg2.extensions.libpq_version(),
        "psycopg2": psycopg2.__path__,
    }
