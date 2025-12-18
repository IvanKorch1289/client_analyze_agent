"""
Email service client for sending notifications and checking SMTP connectivity.

Provides email functionality with health checking for the system dashboard.
"""

import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from app.utility.logging_client import logger
from app.settings import settings


class EmailClient:
    """Client for email operations with health checking."""

    _instance: Optional["EmailClient"] = None

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host or settings.smtp_host or os.getenv("SMTP_HOST", "")
        self.smtp_port = (
            smtp_port or settings.smtp_port or int(os.getenv("SMTP_PORT", "587"))
        )
        self.smtp_user = smtp_user or settings.smtp_user or os.getenv("SMTP_USER", "")
        self.smtp_password = (
            smtp_password
            or settings.smtp_password
            or os.getenv("SMTP_PASSWORD", "")
        )
        self.use_tls = use_tls
        self.default_from = settings.smtp_from or os.getenv("SMTP_FROM", self.smtp_user)

    @classmethod
    def get_instance(cls) -> "EmailClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    def check_health(self, timeout: int = 10) -> Dict[str, Any]:
        """
        Check SMTP server connectivity.

        Args:
            timeout: Connection timeout in seconds.

        Returns:
            Dict with health check results.
        """
        if not self.smtp_host:
            return {
                "status": "not_configured",
                "configured": False,
                "message": "SMTP сервер не настроен",
            }

        try:
            with socket.create_connection(
                (self.smtp_host, self.smtp_port), timeout=timeout
            ) as sock:
                sock.close()

            return {
                "status": "ok",
                "configured": self.is_configured(),
                "host": self.smtp_host,
                "port": self.smtp_port,
                "message": "SMTP сервер доступен",
            }

        except socket.timeout:
            logger.warning(
                f"SMTP health check timeout: {self.smtp_host}:{self.smtp_port}",
                component="email",
            )
            return {
                "status": "timeout",
                "configured": self.is_configured(),
                "host": self.smtp_host,
                "port": self.smtp_port,
                "message": "Таймаут подключения к SMTP серверу",
            }

        except ConnectionRefusedError:
            logger.warning(
                f"SMTP connection refused: {self.smtp_host}:{self.smtp_port}",
                component="email",
            )
            return {
                "status": "refused",
                "configured": self.is_configured(),
                "host": self.smtp_host,
                "port": self.smtp_port,
                "message": "Соединение с SMTP сервером отклонено",
            }

        except Exception as e:
            logger.error(
                f"SMTP health check failed: {type(e).__name__}: {e}",
                component="email",
            )
            return {
                "status": "error",
                "configured": self.is_configured(),
                "host": self.smtp_host,
                "port": self.smtp_port,
                "message": str(e) or "Неизвестная ошибка",
            }

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
        from_addr: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body content.
            html: If True, body is treated as HTML.
            from_addr: Sender address (uses default if not provided).

        Returns:
            Dict with send result.
        """
        if not self.is_configured():
            return {"success": False, "error": "SMTP не настроен"}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_addr or self.default_from
            msg["To"] = to

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(
                f"Email sent to {to}: {subject[:50]}",
                component="email",
            )
            return {"success": True, "message": "Email отправлен"}

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed", component="email")
            return {"success": False, "error": "Ошибка аутентификации SMTP"}

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}", component="email")
            return {"success": False, "error": str(e)}

        except Exception as e:
            logger.error(f"Email send failed: {type(e).__name__}: {e}", component="email")
            return {"success": False, "error": str(e) or "Неизвестная ошибка"}

    def get_status(self) -> Dict[str, Any]:
        """Get email service status."""
        health = self.check_health()
        return {
            "configured": self.is_configured(),
            "smtp_host": self.smtp_host if self.smtp_host else None,
            "smtp_port": self.smtp_port,
            "health": health,
        }
