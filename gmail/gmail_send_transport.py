"""SMTP submission transport for Gmail using XOAUTH2 authentication."""

import asyncio
import base64
import smtplib


async def send_via_smtp(
    sender: str,
    envelope_recipients: list[str],
    raw_bytes: bytes,
    user_email: str,
    access_token: str,
) -> str:
    """Submit *raw_bytes* (a complete RFC 822 message) via smtp.gmail.com:587.

    Authentication uses the XOAUTH2 mechanism.  SMTP/auth errors propagate to
    the caller unchanged — no swallowing, no fallback.

    Returns the decoded AUTH response string from the server.
    """

    def _send() -> str:
        auth_string = f"user={user_email}\x01auth=Bearer {access_token}\x01\x01"
        b64 = base64.b64encode(auth_string.encode("ascii")).decode("ascii")

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            code, response = smtp.docmd("AUTH", "XOAUTH2 " + b64)
            if code != 235:
                raise smtplib.SMTPAuthenticationError(code, response)
            smtp.sendmail(sender, envelope_recipients, raw_bytes)
            return response.decode() if isinstance(response, bytes) else str(response)

    return await asyncio.to_thread(_send)
