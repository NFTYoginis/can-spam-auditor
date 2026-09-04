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
}


def main():
    for filename, msg in FIXTURES.items():
        path = FIXTURES_DIR / filename
        path.write_bytes(bytes(msg))
        print(f"wrote {path.relative_to(FIXTURES_DIR.parent)}")


if __name__ == "__main__":
    main()
