"""Transactional email via Resend's plain HTTP API. Uses `requests`
(already a dependency for the mesh-gen clients) rather than the `resend`
package, to avoid adding a new dependency for what's a single POST call.

Fails open, not closed: if RESEND_API_KEY is unset (local dev) or the API
call errors, this logs and returns False instead of raising. A user who
forgets their password should not also get a 500 -- the caller
(auth.forgot_password) already returns the same generic success response
regardless, so a delivery failure here is invisible to the caller by
design and only surfaces in logs.
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
# Must be on a domain verified in the Resend dashboard, or every send
# fails -- resend.com/domains. "onboarding@resend.dev" works unverified
# for local/dev testing but only delivers to the account owner's own
# inbox, not real users.
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "BrickForgerAI <onboarding@resend.dev>")

_RESEND_API_URL = "https://api.resend.com/emails"


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    if not RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY not set -- skipping password reset email. Reset URL for local testing: %s",
            reset_url,
        )
        return False

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1a1f36;">Reset your BrickForgerAI password</h2>
      <p style="color: #444; font-size: 15px; line-height: 1.5;">
        We received a request to reset your password. This link expires in 60 minutes
        and can only be used once.
      </p>
      <p style="margin: 28px 0;">
        <a href="{reset_url}"
           style="background: #e8813a; color: #fff; padding: 12px 22px; border-radius: 10px;
                  text-decoration: none; font-weight: 700; font-size: 15px;">
          Reset password
        </a>
      </p>
      <p style="color: #888; font-size: 13px; line-height: 1.5;">
        If you didn't request this, you can safely ignore this email -- your password
        won't change unless you click the link above and choose a new one.
      </p>
    </div>
    """.strip()

    try:
        response = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": RESEND_FROM_EMAIL,
                "to": [to_email],
                "subject": "Reset your BrickForgerAI password",
                "html": html,
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        logger.exception("Failed to send password reset email via Resend")
        return False
