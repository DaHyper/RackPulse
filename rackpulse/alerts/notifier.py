from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from rackpulse.config import SmtpConfig, WebhookConfig

logger = logging.getLogger(__name__)


@dataclass
class AlertMessage:
    subject: str
    body: str
    severity: str = "info"


class EmailSender:
    def __init__(self, smtp: SmtpConfig) -> None:
        self.smtp = smtp

    @property
    def configured(self) -> bool:
        return bool(self.smtp.host and self.smtp.recipients)

    def send(self, subject: str, body: str) -> None:
        if not self.configured:
            return

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.smtp.from_address or self.smtp.username
        message["To"] = ", ".join(self.smtp.recipients)
        message.set_content(body)

        if self.smtp.security == "ssl":
            with smtplib.SMTP_SSL(self.smtp.host, self.smtp.port) as client:
                self._authenticate(client)
                client.send_message(message)
        else:
            with smtplib.SMTP(self.smtp.host, self.smtp.port) as client:
                if self.smtp.security == "tls":
                    client.starttls(context=ssl.create_default_context())
                self._authenticate(client)
                client.send_message(message)

    def _authenticate(self, client: smtplib.SMTP) -> None:
        if self.smtp.username:
            client.login(self.smtp.username, self.smtp.password)

    def send_test(self) -> None:
        self.send(
            subject="[RackPulse] Test alert",
            body="This is a test email from RackPulse. SMTP settings are working.",
        )


def _build_webhook_payload(webhook: WebhookConfig, alert: AlertMessage) -> dict[str, Any]:
    text = (
        f"*{alert.subject}*\n{alert.body}"
        if webhook.format == "slack"
        else f"**{alert.subject}**\n{alert.body}"
    )

    if webhook.format == "slack":
        return {"text": text}
    if webhook.format == "discord":
        return {"content": text[:2000]}
    return {
        "source": "rackpulse",
        "severity": alert.severity,
        "title": alert.subject,
        "message": alert.body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


class WebhookSender:
    def __init__(self, webhooks: list[WebhookConfig]) -> None:
        self.webhooks = [w for w in webhooks if w.enabled and w.url]

    @property
    def configured(self) -> bool:
        return bool(self.webhooks)

    def send(self, alert: AlertMessage) -> None:
        for webhook in self.webhooks:
            self._post(webhook, alert)

    def send_test(self) -> None:
        self.send(
            AlertMessage(
                subject="[RackPulse] Test alert",
                body="This is a test webhook from RackPulse.",
                severity="info",
            )
        )

    def _post(self, webhook: WebhookConfig, alert: AlertMessage) -> None:
        payload = _build_webhook_payload(webhook, alert)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            webhook.url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "RackPulse/2.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 400:
                    logger.warning(
                        "Webhook %s returned HTTP %s",
                        webhook.name or webhook.url,
                        response.status,
                    )
        except urllib.error.URLError as exc:
            logger.warning("Webhook %s failed: %s", webhook.name or webhook.url, exc)


class AlertNotifier:
    def __init__(self, smtp: SmtpConfig, webhooks: list[WebhookConfig]) -> None:
        self.email = EmailSender(smtp)
        self.webhooks = WebhookSender(webhooks)

    @property
    def configured(self) -> bool:
        return self.email.configured or self.webhooks.configured

    def send(self, subject: str, body: str, severity: str = "info") -> None:
        alert = AlertMessage(subject=subject, body=body, severity=severity)

        if self.email.configured:
            try:
                self.email.send(subject, body)
            except Exception:
                logger.exception("Email alert failed")

        if self.webhooks.configured:
            try:
                self.webhooks.send(alert)
            except Exception:
                logger.exception("Webhook alert failed")

    def send_test_email(self) -> None:
        self.email.send_test()

    def send_test_webhooks(self) -> None:
        self.webhooks.send_test()
