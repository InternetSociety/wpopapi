import argparse
import asyncio
import sys

from app.database import AsyncSessionLocal
from app.repositories.users import UserRepository
from app.services.exceptions import DomainError
from app.services.users import UserService


async def create_admin(email: str, password: str) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        await UserService(UserRepository(session)).create_initial_admin(email, password)
    print(f"Administrator {email.lower()} created.")


async def remove_user(email: str) -> None:
    async with AsyncSessionLocal() as session, session.begin():
        await UserService(UserRepository(session)).remove_user_by_email(email)
    print(f"User {email.lower()} removed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage application administrators.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Create the first administrator.")
    create.add_argument("email")
    create.add_argument("password")
    remove = subparsers.add_parser("remove", help="Remove a user.")
    remove.add_argument("email")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.command == "create":
        await create_admin(args.email, args.password)
    else:
        await remove_user(args.email)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except DomainError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
