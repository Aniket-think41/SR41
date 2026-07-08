"""
Transactional email via AWS SES SMTP for org invitations.

Best-effort by design: if SES is disabled or misconfigured, invitations are
still created in the DB and the admin gets a server log warning. The DB record
is the source of truth — email delivery is a notification layer.
"""

import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _credentials_block_html(*, login_url: str, username: str, temp_password: str) -> str:
    """Credentials card shown only for invitees whose account we just created."""
    return f"""
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin:0 0 24px;">
                <tr>
                  <td style="padding:16px 18px;background:#f6f4ff;border:1px solid #e4ddff;border-radius:8px;">
                    <p style="margin:0 0 10px;color:#1a1a1a;font-size:14px;font-weight:600;">Your sign-in details</p>
                    <p style="margin:0 0 4px;color:#555;font-size:14px;">Email / username: <strong style="color:#1a1a1a;">{username}</strong></p>
                    <p style="margin:0 0 12px;color:#555;font-size:14px;">Temporary password: <strong style="color:#735ae5;font-family:monospace;">{temp_password}</strong></p>
                    <p style="margin:0;color:#999;font-size:12px;line-height:1.4;">
                      Sign in at <a href="{login_url}" style="color:#735ae5;text-decoration:none;">{login_url}</a> with these details.
                      You&#39;ll be asked to set a new password right away.
                    </p>
                  </td>
                </tr>
              </table>"""


def _invite_html(
    *,
    org_name: str,
    inviter_name: str,
    role: str,
    accept_url: str,
    credentials_block: str = "",
) -> str:
    """Full branded HTML email for an org invitation."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
    <tr>
      <td align="center" style="padding:40px 20px;">
        <table width="480" cellpadding="0" cellspacing="0" role="presentation" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">

          <!-- Header: SkillShare brand bar -->
          <tr>
            <td style="padding:28px 32px;text-align:center;background:linear-gradient(135deg,#735ae5,#9070f0);">
              <table cellpadding="0" cellspacing="0" role="presentation" align="center">
                <tr>
                  <td style="vertical-align:middle;">
                    <svg width="28" height="28" viewBox="0 0 32 32" style="display:block;margin:0 auto 6px;">
                      <rect x="1" y="1" width="30" height="30" rx="9" fill="#fff" opacity="0.95"/>
                      <rect x="7" y="7" width="18" height="18" rx="6" fill="none" stroke="#735ae5" stroke-width="1.7" opacity="0.8"/>
                      <rect x="11.5" y="11.5" width="9" height="9" rx="3" fill="none" stroke="#735ae5" stroke-width="1.7"/>
                      <rect x="14" y="14" width="4" height="4" rx="1.2" fill="#d1ff00"/>
                    </svg>
                  </td>
                  <td style="vertical-align:middle;padding-left:10px;">
                    <span style="color:#fff;font-size:20px;font-weight:700;letter-spacing:-0.02em;">Skill<span style="color:#d1ff00;">Share</span></span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 4px;font-size:20px;color:#1a1a1a;font-weight:600;">You&#39;ve been invited</h2>
              <p style="margin:0 0 24px;color:#555;font-size:15px;line-height:1.5;">
                <strong style="color:#1a1a1a;">{inviter_name}</strong> invited you to join
                <strong style="color:#735ae5;">{org_name}</strong> as
                <strong style="color:#1a1a1a;">{role}</strong>.
              </p>
{credentials_block}
              <table cellpadding="0" cellspacing="0" role="presentation">
                <tr>
                  <td style="border-radius:8px;background:#735ae5;" bgcolor="#735ae5">
                    <a href="{accept_url}" target="_blank"
                       style="display:inline-block;padding:12px 32px;background:#735ae5;color:#fff;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600;">
                      Accept invitation &rarr;
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:24px 0 0;color:#999;font-size:13px;line-height:1.4;">
                This invitation expires in 7 days.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;border-top:1px solid #eee;">
              <p style="margin:0;color:#aaa;font-size:12px;line-height:1.4;">
                Sent by <strong>SkillShare</strong> &mdash; the skill &amp; MCP registry by
                <a href="https://think41.com" style="color:#735ae5;text-decoration:none;">Think41</a>.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _invite_text(
    *, org_name: str, inviter_name: str, role: str, accept_url: str, credentials_text: str = ""
) -> str:
    """Plain-text fallback for the invite email."""
    return (
        f"You've been invited to join {org_name}\n"
        f"\n"
        f"{inviter_name} invited you to join {org_name} as {role}.\n"
        f"{credentials_text}"
        f"\n"
        f"Accept the invitation: {accept_url}\n"
        f"\n"
        f"This invitation expires in 7 days.\n"
        f"\n"
        f"— SkillShare by Think41"
    )


def send_scope_add_email(
    *,
    to_email: str,
    org_name: str,
    scope_label: str,
    scope_name: str,
    inviter_name: str,
    role: str,
    username: str | None = None,
    temp_password: str | None = None,
) -> bool:
    """Notify someone they were added directly to a pod/project (no accept step —
    they're already a member). When username/temp_password are given the account
    was just provisioned, so the email also carries sign-in credentials and the
    login link. Best-effort, like send_invite_email."""
    from .config import get_settings

    settings = get_settings()
    if not settings.ses_enabled or not settings.ses_sender:
        logger.info("SES is disabled — skipping scope-add email to %s", to_email)
        return False

    frontend = settings.frontend_url.rstrip("/")
    login_url = f"{frontend}/login"
    dash_url = f"{frontend}/dashboard"
    subject = f"You've been added to {scope_name} on SkillShare"

    credentials_block = ""
    credentials_text = ""
    if username and temp_password:
        credentials_block = _credentials_block_html(
            login_url=login_url, username=to_email, temp_password=temp_password
        )
        credentials_text = (
            f"\nYour sign-in details:\n"
            f"  Email / username: {to_email}\n"
            f"  Temporary password: {temp_password}\n"
            f"Sign in at {login_url} — you'll be asked to set a new password right away.\n"
        )

    intro_html = (
        f"<strong style=\"color:#1a1a1a;\">{inviter_name}</strong> added you to the "
        f"{scope_label} <strong style=\"color:#735ae5;\">{scope_name}</strong> in "
        f"<strong style=\"color:#1a1a1a;\">{org_name}</strong> as "
        f"<strong style=\"color:#1a1a1a;\">{role}</strong>."
    )
    html = _invite_html(
        org_name=org_name, inviter_name=inviter_name, role=role,
        accept_url=dash_url, credentials_block=credentials_block,
    ).replace("You&#39;ve been invited", f"You've been added to {scope_name}") \
     .replace("Accept invitation &rarr;", "Open SkillShare &rarr;")
    # Swap the invite sentence for the direct-add sentence.
    html = re.sub(
        r"<p style=\"margin:0 0 24px;color:#555;font-size:15px;line-height:1\.5;\">.*?</p>",
        f"<p style=\"margin:0 0 24px;color:#555;font-size:15px;line-height:1.5;\">{intro_html}</p>",
        html, count=1, flags=re.DOTALL,
    )
    text = (
        f"You've been added to {scope_name}\n\n"
        f"{inviter_name} added you to the {scope_label} {scope_name} in {org_name} as {role}.\n"
        f"{credentials_text}\n"
        f"Open SkillShare: {dash_url}\n\n"
        f"— SkillShare by Think41"
    )
    return _send(subject=subject, to_email=to_email, html=html, text=text)


def _otp_html(*, code: str, display_name: str, ttl_minutes: int, heading: str, intro: str) -> str:
    """Branded HTML for a one-time verification code (signup or password reset)."""
    spaced = " ".join(code)  # visually separated digits
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
    <tr>
      <td align="center" style="padding:40px 20px;">
        <table width="480" cellpadding="0" cellspacing="0" role="presentation" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">
          <tr>
            <td style="padding:28px 32px;text-align:center;background:linear-gradient(135deg,#735ae5,#9070f0);">
              <span style="color:#fff;font-size:20px;font-weight:700;letter-spacing:-0.02em;">Skill<span style="color:#d1ff00;">Share</span></span>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 4px;font-size:20px;color:#1a1a1a;font-weight:600;">{heading}</h2>
              <p style="margin:0 0 24px;color:#555;font-size:15px;line-height:1.5;">
                Hi {display_name or "there"}, {intro}
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin:0 0 24px;">
                <tr>
                  <td align="center" style="padding:18px;background:#f6f4ff;border:1px solid #e4ddff;border-radius:8px;">
                    <span style="font-size:32px;font-weight:700;letter-spacing:8px;color:#735ae5;font-family:monospace;">{spaced}</span>
                  </td>
                </tr>
              </table>
              <p style="margin:0;color:#999;font-size:13px;line-height:1.5;">
                This code expires in {ttl_minutes} minutes. If you didn&#39;t request it, you can safely ignore this email.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px;border-top:1px solid #eee;">
              <p style="margin:0;color:#aaa;font-size:12px;line-height:1.4;">
                Sent by <strong>SkillShare</strong> &mdash; the skill &amp; MCP registry by
                <a href="https://think41.com" style="color:#735ae5;text-decoration:none;">Think41</a>.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_otp_email(
    *, to_email: str, code: str, display_name: str, ttl_minutes: int, purpose: str = "signup"
) -> bool:
    """Email a one-time code. `purpose` is "signup" or "password_reset" and only
    swaps the copy. Best-effort — returns False (and the caller falls back to
    surfacing the code) when SES isn't configured."""
    from .config import get_settings

    settings = get_settings()
    if not settings.ses_enabled or not settings.ses_sender:
        logger.info("SES is disabled — not emailing OTP to %s (falling back to API response)", to_email)
        return False
    if purpose == "password_reset":
        heading, intro = "Reset your password", "enter this code on SkillShare to reset your password:"
        subject = "Your SkillShare password-reset code"
    else:
        heading, intro = "Confirm your email", "enter this code to finish creating your SkillShare account:"
        subject = "Your SkillShare verification code"
    html = _otp_html(code=code, display_name=display_name, ttl_minutes=ttl_minutes, heading=heading, intro=intro)
    text = (
        f"{heading}\n\n"
        f"Your SkillShare code is: {code}\n"
        f"It expires in {ttl_minutes} minutes.\n\n"
        f"If you didn't request this, you can ignore this email.\n\n"
        f"— SkillShare by Think41"
    )
    return _send(subject=subject, to_email=to_email, html=html, text=text)


def _send(*, subject: str, to_email: str, html: str, text: str) -> bool:
    """Shared SMTP send used by the invite + scope-add emails."""
    from .config import get_settings

    settings = get_settings()
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Think41 <{settings.ses_sender}>"
        msg["To"] = to_email
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.ses_smtp_host, settings.ses_smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.ses_smtp_username, settings.ses_smtp_password)
            server.send_message(msg)
        logger.info("Email sent to %s (%s)", to_email, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s (%s)", to_email, subject)
        return False


def send_invite_email(
    *,
    to_email: str,
    org_name: str,
    org_slug: str,
    inviter_name: str,
    role: str,
    invite_token: str,
    username: str | None = None,
    temp_password: str | None = None,
) -> bool:
    """Send an org invitation email via AWS SES SMTP. Best-effort: logs errors
    and returns False on failure so the caller never blocks a response on email.

    When ``username`` and ``temp_password`` are given (the invitee had no account
    yet, so we provisioned one), the email also carries their sign-in details."""
    from .config import get_settings

    settings = get_settings()
    if not settings.ses_enabled or not settings.ses_sender:
        logger.info("SES is disabled — skipping invite email to %s (set SES_ENABLED=true and SES_SENDER)", to_email)
        return False

    frontend = settings.frontend_url.rstrip("/")
    accept_url = f"{frontend}/join/{org_slug}/{invite_token}"
    login_url = f"{frontend}/login"
    subject = f"You've been invited to join {org_name} on SkillShare"

    credentials_block = ""
    credentials_text = ""
    if username and temp_password:
        credentials_block = _credentials_block_html(
            login_url=login_url, username=to_email, temp_password=temp_password
        )
        credentials_text = (
            f"\n"
            f"Your sign-in details:\n"
            f"  Email / username: {to_email}\n"
            f"  Temporary password: {temp_password}\n"
            f"Sign in at {login_url} — you'll be asked to set a new password right away.\n"
        )

    html = _invite_html(
        org_name=org_name, inviter_name=inviter_name, role=role,
        accept_url=accept_url, credentials_block=credentials_block,
    )
    text = _invite_text(
        org_name=org_name, inviter_name=inviter_name, role=role,
        accept_url=accept_url, credentials_text=credentials_text,
    )

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Think41 <{settings.ses_sender}>"
        msg["To"] = to_email
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.ses_smtp_host, settings.ses_smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.ses_smtp_username, settings.ses_smtp_password)
            server.send_message(msg)

        logger.info("Invite email sent to %s for org %s", to_email, org_slug)
        return True
    except Exception:
        logger.exception("Failed to send invite email to %s for org %s", to_email, org_slug)
        return False
