#!/usr/bin/env python3
"""
Generates every fixture in fixtures/ from ONE base clean email by mutating
exactly one thing per bad fixture — so a fixture can't drift out of sync
with what audit.py actually reads (research-claude's suggestion, 2026-09-04
cross-session thread on this build). Fixtures are checked into the repo as
plain .eml files a reader can open directly; re-running this script should
reproduce them byte-for-byte.

Run: python3 fixtures/generate_fixtures.py
"""
from email.message import EmailMessage
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent

BASE_BODY = """Hi there,

Here's what's new at Sunrise Yoga Studio this October: three new class \
times added to our weekly schedule, plus a new outdoor sunrise flow series \
starting October 5th.

This is a promotional email from Sunrise Yoga Studio.

Sunrise Yoga Studio
123 Main Street, Suite 4
Austin, TX 78701

You can unsubscribe at any time by clicking here: \
https://sunriseyoga.example/unsubscribe
"""


def base_message(**overrides) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = overrides.get("from_", "Sunrise Yoga Studio <hello@sunriseyoga.example>")
    msg["Reply-To"] = overrides.get("reply_to", "hello@sunriseyoga.example")
    msg["To"] = "subscriber@example.com"
    msg["Subject"] = overrides.get("subject", "New class schedule for October")
    msg.set_content(overrides.get("body", BASE_BODY))
    return msg


def messy_html_only_message() -> EmailMessage:
    """No text/plain part at all, table-layout address, HTML entities,
    and opt-out phrased as 'no longer receive these emails' instead of the
    word 'unsubscribe' — three real-world ESP-output patterns in one
    fixture, none of them present in the clean plain-text base. Everything
    here should still fully PASS: this proves the parser handles real
    marketing-email shape, not just clean synthetic text."""
    msg = EmailMessage()
    msg["From"] = "Sunrise Yoga Studio <hello@sunriseyoga.example>"
    msg["Reply-To"] = "hello@sunriseyoga.example"
    msg["To"] = "subscriber@example.com"
    msg["Subject"] = "New class schedule for October"
    msg.set_content(
        "<html><body>"
        "<p>New classes this October at Sunrise Yoga Studio.</p>"
        "<p>This is a promotional email from Sunrise Yoga Studio.</p>"
        "<table><tr><td>Sunrise&nbsp;Yoga&nbsp;Studio</td></tr>"
        "<tr><td>123&nbsp;Main&nbsp;Street,&nbsp;Suite&nbsp;4</td></tr>"
        "<tr><td>Austin,&nbsp;TX&nbsp;78701</td></tr></table>"
        "<p>Don&#39;t want these emails? "
        "<a href=\"https://sunriseyoga.example/u\">Click here</a> "
        "to no longer receive these emails.</p>"
        "</body></html>",
        subtype="html",
    )
    return msg


def messy_view_in_browser_message() -> EmailMessage:
    """multipart/alternative where the text/plain part is a near-empty
    'view in browser' stub (extremely common real ESP output — Mailchimp/
    Klaviyo/Kajabi all do this) and the real content lives only in the
    HTML part. A naive 'always prefer text/plain' parser reads only the
    stub and false-FAILs every check on a genuinely compliant email."""
    msg = EmailMessage()
    msg["From"] = "Sunrise Yoga Studio <hello@sunriseyoga.example>"
    msg["Reply-To"] = "hello@sunriseyoga.example"
    msg["To"] = "subscriber@example.com"
    msg["Subject"] = "New class schedule for October"
    msg.set_content(
        "View this email in your browser: https://sunriseyoga.example/view\n"
    )
    msg.add_alternative(
        "<html><body>"
        "<p>New classes this October at Sunrise Yoga Studio.</p>"
        "<p>This is a promotional email from Sunrise Yoga Studio.</p>"
        "<p>Sunrise Yoga Studio<br>123 Main Street, Suite 4<br>"
        "Austin, TX 78701</p>"
        "<p>You can unsubscribe at any time: "
        "<a href=\"https://sunriseyoga.example/u\">click here</a></p>"
        "</body></html>",
        subtype="html",
    )
    return msg


FIXTURES = {
    "clean.eml": base_message(),

    "bad-header-mismatch.eml": base_message(
        reply_to="support@a-totally-different-domain.example",
    ),

    "bad-subject-contradicts-body.eml": base_message(
        subject="Re: Your Order Confirmation",
        body=(
            "Flash Sale: 30% off all classes this week! Buy now and save "
            "before it's gone.\n\n"
            "This is a promotional email from Sunrise Yoga Studio.\n\n"
            "Sunrise Yoga Studio\n"
            "123 Main Street, Suite 4\n"
            "Austin, TX 78701\n\n"
            "You can unsubscribe at any time by clicking here: "
            "https://sunriseyoga.example/unsubscribe\n"
        ),
    ),

    "bad-no-ad-disclosure.eml": base_message(
        body=(
            "Hi there,\n\n"
            "Here's what's new at Sunrise Yoga Studio this October: three "
            "new class times added to our weekly schedule, plus a new "
            "outdoor sunrise flow series starting October 5th.\n\n"
            "Sunrise Yoga Studio\n"
            "123 Main Street, Suite 4\n"
            "Austin, TX 78701\n\n"
            "You can unsubscribe at any time by clicking here: "
            "https://sunriseyoga.example/unsubscribe\n"
        ),
    ),

    "bad-no-postal-address.eml": base_message(
        body=(
            "Hi there,\n\n"
            "Here's what's new at Sunrise Yoga Studio this October: three "
            "new class times added to our weekly schedule, plus a new "
            "outdoor sunrise flow series starting October 5th.\n\n"
            "This is a promotional email from Sunrise Yoga Studio.\n\n"
            "You can unsubscribe at any time by clicking here: "
            "https://sunriseyoga.example/unsubscribe\n"
        ),
    ),

    "bad-no-optout.eml": base_message(
        body=(
            "Hi there,\n\n"
            "Here's what's new at Sunrise Yoga Studio this October: three "
            "new class times added to our weekly schedule, plus a new "
            "outdoor sunrise flow series starting October 5th.\n\n"
            "This is a promotional email from Sunrise Yoga Studio.\n\n"
            "Sunrise Yoga Studio\n"
            "123 Main Street, Suite 4\n"
            "Austin, TX 78701\n"
        ),
    ),

    "bad-fee-gated-optout.eml": base_message(
        body=(
            "Hi there,\n\n"
            "Here's what's new at Sunrise Yoga Studio this October: three "
            "new class times added to our weekly schedule, plus a new "
            "outdoor sunrise flow series starting October 5th.\n\n"
            "This is a promotional email from Sunrise Yoga Studio.\n\n"
            "Sunrise Yoga Studio\n"
            "123 Main Street, Suite 4\n"
            "Austin, TX 78701\n\n"
            "To unsubscribe, please pay a $5 processing fee at "
            "https://sunriseyoga.example/unsubscribe\n"
        ),
    ),

    "bad-multistep-optout.eml": base_message(
        body=(
            "Hi there,\n\n"
            "Here's what's new at Sunrise Yoga Studio this October: three "
            "new class times added to our weekly schedule, plus a new "
            "outdoor sunrise flow series starting October 5th.\n\n"
            "This is a promotional email from Sunrise Yoga Studio.\n\n"
            "Sunrise Yoga Studio\n"
            "123 Main Street, Suite 4\n"
            "Austin, TX 78701\n\n"
            "To unsubscribe, please call us at (555) 123-4567 or mail a "
            "letter to our office.\n"
        ),
    ),

    # Messy-but-compliant fixtures — same content as the base, shaped like
    # real-world ESP output rather than clean synthetic plain text. All of
    # these must fully PASS; see fixtures/manifest.md § Parser robustness.
    "clean-html-only-entities.eml": messy_html_only_message(),
    "clean-view-in-browser-stub.eml": messy_view_in_browser_message(),
}


def main():
    for filename, msg in FIXTURES.items():
        path = FIXTURES_DIR / filename
        path.write_bytes(bytes(msg))
        print(f"wrote {path.relative_to(FIXTURES_DIR.parent)}")


if __name__ == "__main__":
    main()
