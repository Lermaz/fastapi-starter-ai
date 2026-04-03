from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def send_email(*, settings: Settings, to_addr: str, subject: str, body_text: str) -> None:
    if settings.email_backend == "console":
        logger.info(
            "Email (console backend) to=%s subject=%s\n%s",
            to_addr,
            subject,
            body_text,
        )
        return

    if not settings.smtp_host.strip():
        raise RuntimeError("SMTP host is not configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body_text)

    await aiosmtplib.send(
        message,
        sender=settings.smtp_from,
        recipients=[to_addr],
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
