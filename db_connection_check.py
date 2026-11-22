"""Validate .env.local and test the MySQL connection without printing secrets."""

from __future__ import annotations

from admissions_common import (
    ensure_utf8_stdio,
    get_database_config,
)


def main() -> None:
    ensure_utf8_stdio()
    config = get_database_config(prompt=False)
    print("ENV_FILE_EXISTS", True)
    print("MYSQL_HOST", config.host)
    print("MYSQL_PORT", config.port)
    print("MYSQL_USER", config.user)
    print("MYSQL_DATABASE", config.database)
    print("MYSQL_PASSWORD_CONFIGURED", bool(config.password))
    if not config.password:
        raise RuntimeError(".env.local 中未解析到 MYSQL_PASSWORD")

    import mysql.connector

    connection = mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        connection_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT VERSION(), CURRENT_USER(), DATABASE()"
            )
            version, current_user, database = cursor.fetchone()
            print("MYSQL_OK", True)
            print("MYSQL_VERSION", version)
            print("CURRENT_USER", current_user)
            print("CURRENT_DATABASE", database)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
