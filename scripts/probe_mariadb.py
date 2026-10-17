"""Read-only probe of an explicitly selected MariaDB; never prints grant/auth material."""

import argparse
import asyncio
import json
from pathlib import Path

import asyncmy

from inspector.config import read_secret


async def probe(args: argparse.Namespace) -> dict:
    connection = await asyncmy.connect(
        host=args.host,
        port=args.port,
        db=args.database,
        user=args.username,
        password=read_secret(args.password_file).encode("utf-8"),
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=5,
        local_infile=False,
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT VERSION(), DATABASE(), @@character_set_database, @@collation_database"
            )
            version, database, charset, collation = await cursor.fetchone()
            await cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                (args.database,),
            )
            table_count = (await cursor.fetchone())[0]
            await cursor.execute("SHOW GRANTS")
            grants = await cursor.fetchall()
            privileges = []
            for row in grants:
                grant = row[0]
                if grant.startswith("GRANT ") and " ON " in grant:
                    permission, remainder = grant[6:].split(" ON ", 1)
                    scope = remainder.split(" TO ", 1)[0]
                    privileges.append(
                        {
                            "privileges": permission,
                            "scope": scope,
                            "grant_option": " WITH GRANT OPTION" in grant,
                        }
                    )
            await cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            tls = await cursor.fetchone()
        return {
            "connected": True,
            "version": version,
            "database": database,
            "database_charset": charset,
            "database_collation": collation,
            "table_count": table_count,
            "grants_without_account_or_auth_material": privileges,
            "database_tls_active": bool(tls and tls[1]),
            "scope": "Read-only probe; no schema or account was changed.",
        }
    finally:
        await connection.ensure_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=["127.0.0.1", "::1"])
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--database", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-file", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        report = asyncio.run(probe(args))
    except Exception as error:
        # Driver exception strings may contain server/account or authentication data.
        report = {
            "connected": False,
            "error_type": type(error).__name__,
            "error_number": error.args[0]
            if error.args and isinstance(error.args[0], int)
            else None,
            "scope": "Read-only connection probe failed; no schema changed.",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["connected"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
