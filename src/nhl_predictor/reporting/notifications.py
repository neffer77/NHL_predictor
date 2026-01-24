"""Alert and Notification System.

Sends notifications for daily picks, goalie changes,
and late-breaking updates.
"""

import json
import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from ..config import get_config
from .report_generator import DailyReport, ReportGenerator

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Configuration for notifications."""

    # Email settings
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: list[str] = None

    # Webhook settings
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_type: str = "slack"  # "slack", "discord", "generic"

    # Timing
    daily_picks_time: str = "14:00"  # 2 PM

    def __post_init__(self):
        if self.email_to is None:
            self.email_to = []


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    def send(
        self,
        subject: str,
        message: str,
        html: Optional[str] = None,
    ) -> bool:
        """
        Send a notification.

        Args:
            subject: Notification subject/title.
            message: Plain text message.
            html: Optional HTML message.

        Returns:
            True if sent successfully.
        """
        pass


class EmailChannel(NotificationChannel):
    """Email notification channel."""

    def __init__(self, config: NotificationConfig):
        """Initialize email channel."""
        self.config = config

    def send(
        self,
        subject: str,
        message: str,
        html: Optional[str] = None,
    ) -> bool:
        """Send email notification."""
        if not self.config.email_enabled:
            logger.debug("Email notifications disabled")
            return False

        if not self.config.email_to:
            logger.warning("No email recipients configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.email_from
            msg["To"] = ", ".join(self.config.email_to)

            # Plain text part
            msg.attach(MIMEText(message, "plain"))

            # HTML part (if provided)
            if html:
                msg.attach(MIMEText(html, "html"))

            # Send via SMTP
            with smtplib.SMTP(
                self.config.smtp_host,
                self.config.smtp_port,
            ) as server:
                server.starttls()
                server.login(
                    self.config.smtp_user,
                    self.config.smtp_password,
                )
                server.sendmail(
                    self.config.email_from,
                    self.config.email_to,
                    msg.as_string(),
                )

            logger.info(f"Email sent to {self.config.email_to}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class WebhookChannel(NotificationChannel):
    """Webhook notification channel (Slack, Discord, etc)."""

    def __init__(self, config: NotificationConfig):
        """Initialize webhook channel."""
        self.config = config

    def send(
        self,
        subject: str,
        message: str,
        html: Optional[str] = None,
    ) -> bool:
        """Send webhook notification."""
        if not self.config.webhook_enabled:
            logger.debug("Webhook notifications disabled")
            return False

        if not self.config.webhook_url:
            logger.warning("No webhook URL configured")
            return False

        try:
            payload = self._format_payload(subject, message)

            req = Request(
                self.config.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            with urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("Webhook notification sent")
                    return True
                else:
                    logger.warning(f"Webhook returned {response.status}")
                    return False

        except URLError as e:
            logger.error(f"Failed to send webhook: {e}")
            return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False

    def _format_payload(self, subject: str, message: str) -> dict:
        """Format payload based on webhook type."""
        if self.config.webhook_type == "slack":
            return self._format_slack(subject, message)
        elif self.config.webhook_type == "discord":
            return self._format_discord(subject, message)
        else:
            return {"subject": subject, "message": message}

    def _format_slack(self, subject: str, message: str) -> dict:
        """Format Slack webhook payload."""
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": subject,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message,
                    },
                },
            ],
        }

    def _format_discord(self, subject: str, message: str) -> dict:
        """Format Discord webhook payload."""
        return {
            "embeds": [
                {
                    "title": subject,
                    "description": message,
                    "color": 5814783,  # Blue
                },
            ],
        }


class NotificationManager:
    """Manages all notification channels."""

    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize notification manager."""
        if config is None:
            config = self._load_config()

        self.config = config
        self.channels: list[NotificationChannel] = []

        # Initialize enabled channels
        if config.email_enabled:
            self.channels.append(EmailChannel(config))

        if config.webhook_enabled:
            self.channels.append(WebhookChannel(config))

        self.report_generator = ReportGenerator()

    def _load_config(self) -> NotificationConfig:
        """Load notification config from app config."""
        try:
            app_config = get_config()
            return NotificationConfig(
                email_enabled=getattr(app_config, "email_enabled", False),
                smtp_host=getattr(app_config, "smtp_host", ""),
                smtp_port=getattr(app_config, "smtp_port", 587),
                smtp_user=getattr(app_config, "smtp_user", ""),
                smtp_password=getattr(app_config, "smtp_password", ""),
                email_from=getattr(app_config, "email_from", ""),
                email_to=getattr(app_config, "email_to", []),
                webhook_enabled=getattr(app_config, "webhook_enabled", False),
                webhook_url=getattr(app_config, "webhook_url", ""),
                webhook_type=getattr(app_config, "webhook_type", "slack"),
            )
        except Exception:
            return NotificationConfig()

    def send_daily_picks(self, report: DailyReport) -> dict:
        """
        Send daily picks notification.

        Args:
            report: DailyReport to send.

        Returns:
            Dict with send status for each channel.
        """
        email_content = self.report_generator.format_email(report)

        # Format for webhook (simplified)
        webhook_message = self._format_picks_for_webhook(report)

        results = {}
        for channel in self.channels:
            channel_name = type(channel).__name__
            try:
                if isinstance(channel, EmailChannel):
                    success = channel.send(
                        email_content["subject"],
                        email_content["body"],
                        email_content["html"],
                    )
                else:
                    success = channel.send(
                        f"NHL Picks - {report.date}",
                        webhook_message,
                    )
                results[channel_name] = success
            except Exception as e:
                logger.error(f"Error sending via {channel_name}: {e}")
                results[channel_name] = False

        return results

    def _format_picks_for_webhook(self, report: DailyReport) -> str:
        """Format picks for webhook message."""
        lines = [
            f"**{report.summary['confidence_level']}**",
            "",
        ]

        for pick in report.picks:
            emoji = {"LOCK": "🔒", "STRONG": "💪", "STANDARD": "✓", "LEAN": "→"}.get(
                pick.tier, ""
            )
            lines.append(
                f"{emoji} **#{pick.rank} {pick.pick}** vs {pick.matchup.split('@')[0].strip()}"
            )
            lines.append(
                f"   Confidence: {pick.confidence} | Edge: {pick.edge}"
            )

        lines.extend([
            "",
            f"_Model: {report.model_health['accuracy_7d']} (7d)_",
        ])

        return "\n".join(lines)

    def send_goalie_alert(
        self,
        team: str,
        old_goalie: Optional[str],
        new_goalie: str,
        game_id: int,
        matchup: str,
    ) -> dict:
        """
        Send goalie change alert.

        Args:
            team: Team code.
            old_goalie: Previous goalie (None if new confirmation).
            new_goalie: New/confirmed goalie.
            game_id: Game ID.
            matchup: Game matchup string.

        Returns:
            Send status for each channel.
        """
        if old_goalie:
            subject = f"⚠️ Goalie Change: {team}"
            message = (
                f"Goalie change for {team} in {matchup}:\n"
                f"  Previous: {old_goalie}\n"
                f"  Now: {new_goalie}\n\n"
                f"Review your pick if this affects your selection."
            )
        else:
            subject = f"✅ Goalie Confirmed: {team}"
            message = (
                f"Starting goalie confirmed for {team}:\n"
                f"  {new_goalie}\n"
                f"  Game: {matchup}"
            )

        results = {}
        for channel in self.channels:
            channel_name = type(channel).__name__
            try:
                success = channel.send(subject, message)
                results[channel_name] = success
            except Exception as e:
                logger.error(f"Error sending alert via {channel_name}: {e}")
                results[channel_name] = False

        return results

    def send_injury_alert(
        self,
        team: str,
        player: str,
        status: str,
        game_id: int,
        matchup: str,
        affects_pick: bool = False,
    ) -> dict:
        """
        Send injury alert.

        Args:
            team: Team code.
            player: Player name.
            status: Injury status.
            game_id: Game ID.
            matchup: Game matchup.
            affects_pick: Whether this affects an active pick.

        Returns:
            Send status for each channel.
        """
        emoji = "🚨" if affects_pick else "⚠️"
        subject = f"{emoji} Injury Update: {player} ({team})"

        message = (
            f"Injury update for {team}:\n"
            f"  Player: {player}\n"
            f"  Status: {status}\n"
            f"  Game: {matchup}\n"
        )

        if affects_pick:
            message += "\n⚠️ This affects one of today's picks!"

        results = {}
        for channel in self.channels:
            channel_name = type(channel).__name__
            try:
                success = channel.send(subject, message)
                results[channel_name] = success
            except Exception as e:
                logger.error(f"Error sending alert via {channel_name}: {e}")
                results[channel_name] = False

        return results

    def send_custom_alert(
        self,
        subject: str,
        message: str,
        priority: str = "normal",
    ) -> dict:
        """
        Send custom alert.

        Args:
            subject: Alert subject.
            message: Alert message.
            priority: Priority level (low, normal, high).

        Returns:
            Send status for each channel.
        """
        if priority == "high":
            subject = f"🚨 {subject}"
        elif priority == "low":
            subject = f"ℹ️ {subject}"

        results = {}
        for channel in self.channels:
            channel_name = type(channel).__name__
            try:
                success = channel.send(subject, message)
                results[channel_name] = success
            except Exception as e:
                logger.error(f"Error sending alert via {channel_name}: {e}")
                results[channel_name] = False

        return results

    def test_notifications(self) -> dict:
        """
        Test all notification channels.

        Returns:
            Test status for each channel.
        """
        subject = "NHL Predictor - Test Notification"
        message = (
            f"This is a test notification from NHL Predictor.\n"
            f"Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"If you received this, notifications are working!"
        )

        results = {}
        for channel in self.channels:
            channel_name = type(channel).__name__
            try:
                success = channel.send(subject, message)
                results[channel_name] = success
                logger.info(f"Test notification via {channel_name}: {'OK' if success else 'FAILED'}")
            except Exception as e:
                logger.error(f"Test failed for {channel_name}: {e}")
                results[channel_name] = False

        return results


class GoalieMonitor:
    """Monitors for goalie changes and sends alerts."""

    def __init__(self, notification_manager: NotificationManager):
        """Initialize goalie monitor."""
        self.notifications = notification_manager
        self._last_known_goalies: dict[str, str] = {}

    def check_and_alert(
        self,
        team: str,
        goalie: str,
        game_id: int,
        matchup: str,
    ) -> bool:
        """
        Check for goalie change and alert if needed.

        Args:
            team: Team code.
            goalie: Current goalie.
            game_id: Game ID.
            matchup: Matchup string.

        Returns:
            True if alert was sent.
        """
        key = f"{game_id}_{team}"
        old_goalie = self._last_known_goalies.get(key)

        if old_goalie and old_goalie != goalie:
            # Goalie changed!
            self.notifications.send_goalie_alert(
                team, old_goalie, goalie, game_id, matchup
            )
            self._last_known_goalies[key] = goalie
            return True

        if not old_goalie and goalie:
            # New confirmation
            self.notifications.send_goalie_alert(
                team, None, goalie, game_id, matchup
            )
            self._last_known_goalies[key] = goalie
            return True

        return False


def send_daily_picks_notification(report: DailyReport) -> dict:
    """Convenience function to send daily picks."""
    manager = NotificationManager()
    return manager.send_daily_picks(report)


def test_notifications() -> dict:
    """Convenience function to test notifications."""
    manager = NotificationManager()
    return manager.test_notifications()
