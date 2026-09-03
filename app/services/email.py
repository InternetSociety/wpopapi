import asyncio
import smtplib
from email.message import EmailMessage

from app.config import settings


class PasswordResetMailer:
    async def send(self, recipient: str, code: str) -> None:
        if not settings.SMTP_ENABLED:
            raise smtplib.SMTPException("SMTP is disabled")
        await asyncio.to_thread(self._send_sync, recipient, code)

    @staticmethod
    def _send_sync(recipient: str, code: str) -> None:
        message = EmailMessage()
        message["From"] = settings.SMTP_SENDER
        message["To"] = recipient
        message["Subject"] = "Password reset code"
        message.set_content(
            "Use the following code to reset your password:\n\n"
            f"{code}\n\n"
            "Open /reset-password and paste this code."
        )
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.send_message(message)
