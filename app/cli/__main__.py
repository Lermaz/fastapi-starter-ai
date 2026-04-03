from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import async_session
from app.models.user import User, UserRole


async def cmd_create_admin(*, email: str, password: str, force: bool) -> int:
    email_norm = email.lower()
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.email == email_norm))
        if user is not None:
            if not force:
                print(
                    f"Error: user with email {email_norm} already exists. Use --force to promote to admin.",
                    file=sys.stderr,
                )
                return 1
            user.role = UserRole.admin
            user.hashed_password = hash_password(password)
            await session.commit()
            print(f"Promoted existing user to admin: {email_norm}")
            return 0

        new_user = User(
            email=email_norm,
            hashed_password=hash_password(password),
            is_active=True,
            role=UserRole.admin,
        )
        session.add(new_user)
        await session.commit()
        print(f"Created admin user: {email_norm}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Operational CLI for the FastAPI app."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    admin_parser = sub.add_parser(
        "create-admin", help="Create a new admin user or promote an existing user with --force."
    )
    admin_parser.add_argument("--email", required=True, help="Admin email (login username).")
    admin_parser.add_argument("--password", required=True, help="Admin password.")
    admin_parser.add_argument(
        "--force",
        action="store_true",
        help="If the email exists, promote that user to admin and reset password.",
    )

    args = parser.parse_args()
    if args.command == "create-admin":
        exit_code = asyncio.run(
            cmd_create_admin(email=args.email, password=args.password, force=args.force)
        )
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
