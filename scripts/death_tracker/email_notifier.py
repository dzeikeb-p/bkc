"""Email notification via Gmail SMTP."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional


class EmailNotifier:
    """
    Sends email notifications via Gmail SMTP.

    Requires a Gmail App Password (not your regular Gmail password).
    To create an App Password:
    1. Enable 2-Factor Authentication on your Google Account
    2. Go to Google Account > Security > 2-Step Verification > App passwords
    3. Create a new app password for "Mail"
    """

    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 465  # SSL

    def __init__(
        self,
        gmail_user: str,
        gmail_app_password: str,
        recipient: Optional[str] = None,
    ):
        """
        Initialize the email notifier.

        Args:
            gmail_user: Gmail address for sending
            gmail_app_password: Gmail App Password (NOT regular password)
            recipient: Email address to receive notifications (defaults to gmail_user)
        """
        self.gmail_user = gmail_user
        self.gmail_password = gmail_app_password
        self.recipient = recipient or gmail_user

    def send_draft_notification(
        self,
        drafts: List[Dict],
        spreadsheet_url: str,
    ) -> bool:
        """
        Send email notification about new draft entries.

        Args:
            drafts: List of draft incident dictionaries
            spreadsheet_url: URL to the Google Sheet for review

        Returns:
            True if email sent successfully, False otherwise
        """
        if not drafts:
            return True  # Nothing to send

        subject = f"BKC Alert: {len(drafts)} New Brightline Incident Draft(s)"

        # Build HTML body
        html_body = self._build_html_body(drafts, spreadsheet_url)
        plain_body = self._build_plain_body(drafts, spreadsheet_url)

        return self._send_email(subject, html_body, plain_body)

    def send_source_update_notification(
        self,
        updates: List[Dict],
        spreadsheet_url: str,
    ) -> bool:
        """
        Send notification about source URL updates to existing records.

        Args:
            updates: List of update dictionaries with 'date', 'location', 'new_source'
            spreadsheet_url: URL to the Google Sheet

        Returns:
            True if email sent successfully, False otherwise
        """
        if not updates:
            return True

        subject = f"BKC: {len(updates)} Existing Record(s) Updated with New Sources"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2 style="color: #333;">Source URLs Added to Existing Records</h2>
        <p>The following existing incidents have been updated with new source URLs:</p>
        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background-color: #f2f2f2;">
            <th>Date</th>
            <th>Location</th>
            <th>New Source</th>
        </tr>
        """

        for update in updates:
            html_body += f"""
            <tr>
                <td>{update.get('date', 'Unknown')}</td>
                <td>{update.get('location', 'Unknown')}</td>
                <td><a href="{update.get('new_source', '#')}">Link</a></td>
            </tr>
            """

        html_body += f"""
        </table>
        <p style="margin-top: 20px;">
            <a href="{spreadsheet_url}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                Open Google Sheet
            </a>
        </p>
        </body>
        </html>
        """

        plain_body = f"Source URLs added to {len(updates)} existing record(s). View sheet: {spreadsheet_url}"

        return self._send_email(subject, html_body, plain_body)

    def _build_html_body(self, drafts: List[Dict], spreadsheet_url: str) -> str:
        """Build HTML email body for draft notifications."""
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2 style="color: #c0392b;">New Brightline Incident Draft(s) Detected</h2>
        <p>The following potential incidents have been added to the Google Sheet as <strong>drafts</strong>.</p>
        <p>Please review and change the Status column to "<strong>Approved</strong>" or "<strong>Rejected</strong>".</p>

        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; margin-top: 15px;">
        <tr style="background-color: #f2f2f2;">
            <th>Date</th>
            <th>Location</th>
            <th>Victim</th>
            <th>Mode</th>
            <th>Source</th>
        </tr>
        """

        for draft in drafts:
            source_url = draft.get("source", "")
            source_link = f'<a href="{source_url}">Article</a>' if source_url else "N/A"

            html += f"""
            <tr>
                <td>{draft.get('date', 'Unknown')}</td>
                <td>{draft.get('location_city', 'Unknown')}</td>
                <td>{draft.get('name', 'Unknown')}</td>
                <td>{draft.get('mode', 'Unknown')}</td>
                <td>{source_link}</td>
            </tr>
            """

        html += f"""
        </table>

        <p style="margin-top: 25px;">
            <a href="{spreadsheet_url}" style="background-color: #c0392b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Review Drafts in Google Sheet
            </a>
        </p>

        <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
        <p style="color: #666; font-size: 12px;">
            This is an automated notification from the Brightline Kill Count tracker.<br>
            Drafts require manual review before appearing in the public count.
        </p>
        </body>
        </html>
        """

        return html

    def _build_plain_body(self, drafts: List[Dict], spreadsheet_url: str) -> str:
        """Build plain text email body for draft notifications."""
        lines = [
            "New Brightline Incident Draft(s) Detected",
            "=" * 40,
            "",
            f"{len(drafts)} potential incident(s) have been added as drafts.",
            "Please review and approve or reject in the Google Sheet.",
            "",
        ]

        for i, draft in enumerate(drafts, 1):
            lines.append(f"{i}. Date: {draft.get('date', 'Unknown')}")
            lines.append(f"   Location: {draft.get('location_city', 'Unknown')}")
            lines.append(f"   Victim: {draft.get('name', 'Unknown')}")
            lines.append(f"   Source: {draft.get('source', 'N/A')}")
            lines.append("")

        lines.append(f"Review sheet: {spreadsheet_url}")

        return "\n".join(lines)

    def _send_email(
        self, subject: str, html_body: str, plain_body: str
    ) -> bool:
        """
        Send an email via Gmail SMTP.

        Args:
            subject: Email subject
            html_body: HTML content
            plain_body: Plain text fallback

        Returns:
            True if successful, False otherwise
        """
        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.gmail_user
            message["To"] = self.recipient

            # Attach plain text and HTML versions
            part1 = MIMEText(plain_body, "plain")
            part2 = MIMEText(html_body, "html")
            message.attach(part1)
            message.attach(part2)

            # Send via SSL
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self.SMTP_SERVER, self.SMTP_PORT, context=context
            ) as server:
                server.login(self.gmail_user, self.gmail_password)
                server.sendmail(
                    self.gmail_user, self.recipient, message.as_string()
                )

            print(f"Email notification sent to {self.recipient}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            print(f"Gmail authentication failed: {e}")
            print("Make sure you're using a Gmail App Password, not your regular password.")
            return False
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
