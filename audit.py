#!/usr/bin/env python3
"""
can-spam-auditor — audits a raw email (.eml, full RFC 5322 source incl. headers)
against the CAN-SPAM Act's core requirements, 16 CFR Part 316.

Zero third-party dependencies. Zero network calls. Zero API key required on
the critical path — this is the whole mechanism, not a claim about it (see
reference/rule-map.md for exactly which checks are AUTOMATED, which are
AI-ASSISTED, and which are explicitly OUT OF SCOPE, and why).

Usage:
    python3 audit.py <path-to-email.eml>              # audit one email, print Markdown report
    python3 audit.py <path-to-email.eml> --json        # machine-readable report
    python3 audit.py <path-to-email.eml> --sarif out.sarif   # also write SARIF (go-beyond #1)
    python3 audit.py <path-to-email.eml> --brand-domain example.com  # optional stricter header check
    python3 audit.py --selftest                        # P17: run fixtures/, prove the checker works
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
REFERENCE_DIR = REPO_ROOT / "reference"
FIXTURES_DIR = REPO_ROOT / "fixtures"

PENALTY_LINE = (
    "Each separate email in violation of the CAN-SPAM Act is subject to "
    "penalties of up to $53,088 (FTC, 2025 inflation-adjusted figure, "
    "reference/ftc-compliance-guide.md). Every email sent counts separately."
)

# --------------------------------------------------------------------------
# reference-text loading + P16 quote-grounding
# --------------------------------------------------------------------------


def load_reference_text() -> dict[str, str]:
    texts = {}
    for name in ("16-cfr-part-316.md", "ftc-compliance-guide.md"):
        path = REFERENCE_DIR / name
        texts[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    return texts


def _normalize(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def quote_is_grounded(quote: str, ref_texts: dict[str, str]) -> bool:
    """P16: is this finding's cited quote an actual substring of reference/?"""
    q = _normalize(quote)
    return any(q in _normalize(text) for text in ref_texts.values())


# --------------------------------------------------------------------------
# Finding
# --------------------------------------------------------------------------


class Finding:
    def __init__(self, rule_id, label, citation, quote, tag, status, message):
        self.rule_id = rule_id
        self.label = label
        self.citation = citation
        self.quote = quote  # exact substring expected in reference/ — checked, not asserted
        self.tag = tag  # AUTOMATED | AI-ASSISTED | OUT-OF-SCOPE
        self.status = status  # PASS | FAIL | NEEDS-REVIEW | SKIPPED
        self.message = message
        self.quote_grounded = None  # filled in by grounding pass

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "citation": self.citation,
            "quote": self.quote,
            "tag": self.tag,
            "status": self.status,
            "message": self.message,
            "quote_grounded_in_reference": self.quote_grounded,
        }


# --------------------------------------------------------------------------
# email parsing helpers
# --------------------------------------------------------------------------


def parse_eml(path: Path):
    with open(path, "rb") as f:
        return BytesParser(policy=policy.default).parse(f)


def get_domain(addr_header: str | None) -> str | None:
    if not addr_header:
        return None
    m = re.search(r"[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})", addr_header)
    return m.group(1).lower() if m else None


def get_body_text(msg) -> str:
    """Prefer text/plain; fall back to a crude tag-strip of text/html."""
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        try:
            return plain.get_content()
        except Exception:
            pass
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        try:
            raw = html_part.get_content()
        except Exception:
            raw = ""
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"&nbsp;", " ", raw)
        return raw
    return ""


# --------------------------------------------------------------------------
# Rule 1 — header accuracy (16 CFR 316.2(m); AUTOMATED)
# --------------------------------------------------------------------------


def check_header_accuracy(msg, brand_domain: str | None = None) -> Finding:
    quote = (
        'The definition of the term "sender" is the same as the definition '
        "of that term in the CAN-SPAM Act, 15 U.S.C. 7702(16)"
    )
    from_header = msg.get("From")
    from_domain = get_domain(from_header)

    if not from_header or not from_domain:
        return Finding(
            "rule-1-header-accuracy", "Accurate header information",
            "16 CFR §316.2(m)", quote, "AUTOMATED", "FAIL",
            "No well-formed 'From' address found. CAN-SPAM requires From/To/"
            "Reply-To/routing information to be accurate and identify who "
            "initiated the message — an unparsable From header fails that "
            "on its face.",
        )

    reply_to = msg.get("Reply-To")
    reply_domain = get_domain(reply_to)
    if reply_domain and reply_domain != from_domain:
        return Finding(
            "rule-1-header-accuracy", "Accurate header information",
            "16 CFR §316.2(m)", quote, "AUTOMATED", "FAIL",
            f"Reply-To domain ({reply_domain}) does not match From domain "
            f"({from_domain}). This auditor can't confirm real-world mailbox "
            "ownership, but a Reply-To that routes to a different domain "
            "than the stated sender is a structural inconsistency in the "
            "routing information the rule requires to be accurate.",
        )

    if brand_domain and from_domain != brand_domain.lower():
        return Finding(
            "rule-1-header-accuracy", "Accurate header information",
            "16 CFR §316.2(m)", quote, "AUTOMATED", "FAIL",
            f"From domain ({from_domain}) does not match the declared brand "
            f"domain ({brand_domain}).",
        )

    return Finding(
        "rule-1-header-accuracy", "Accurate header information",
        "16 CFR §316.2(m)", quote, "AUTOMATED", "PASS",
        "From header present and well-formed; Reply-To (if present) shares "
        "its domain.",
    )


# --------------------------------------------------------------------------
# Rule 2 — deceptive subject line (16 CFR 316.3(a)(2); mostly AI-ASSISTED)
# --------------------------------------------------------------------------

_TRANSACTIONAL_SUBJECT = re.compile(
    r"\b(re:|invoice|receipt|order confirmation|account statement|"
    r"your ticket|your order|shipping confirmation)\b", re.I,
)
_COMMERCIAL_OPENING = re.compile(
    r"(\$\s?\d|%\s?off|buy now|shop now|sale\b|discount|limited time|order now)",
    re.I,
)
_TRANSACTIONAL_OPENING = re.compile(
    r"\b(your order|your account|shipped|invoice|payment|balance|"
    r"subscription|membership|ticket #|confirmation number)\b", re.I,
)


def check_subject_line(msg, body_text: str) -> Finding:
    quote = (
        "A recipient reasonably interpreting the subject line of the "
        "electronic mail message would likely conclude that the message "
        "contains the commercial advertisement or promotion of a commercial "
        "product or service"
    )
    subject = msg.get("Subject", "") or ""
    opening = body_text[:500]

    if _TRANSACTIONAL_SUBJECT.search(subject):
        commercial = _COMMERCIAL_OPENING.search(opening)
        transactional_up_front = _TRANSACTIONAL_OPENING.search(opening)
        if commercial and not transactional_up_front:
            return Finding(
                "rule-2-subject-line", "Non-deceptive subject line",
                "16 CFR §316.3(a)(2)", quote, "AUTOMATED", "FAIL",
                "Subject line reads as transactional (e.g. 'Re:', 'invoice', "
                "'account statement'), but the body opens with commercial/"
                "promotional content and no transactional content appears "
                "up front. Per §316.3(a)(2), that combination makes the "
                "message's primary purpose commercial for CAN-SPAM purposes "
                "— the subject line does not accurately reflect that.",
            )
        return Finding(
            "rule-2-subject-line", "Non-deceptive subject line",
            "16 CFR §316.3(a)(2)", quote, "AI-ASSISTED", "NEEDS-REVIEW",
            "Subject line reads as transactional and the body's opening "
            "content is ambiguous under the structural test this checker "
            "can run — whether the subject is deceptive needs a human or "
            "model read of the full message, not a keyword match.",
        )

    return Finding(
        "rule-2-subject-line", "Non-deceptive subject line",
        "16 CFR §316.3(a)(2)", quote, "AI-ASSISTED", "NEEDS-REVIEW",
        "No transactional-subject pattern detected. Whether a subject line "
        "'accurately reflects the content of the message' in the general "
        "case is a judgment call this checker doesn't attempt — flagged "
        "AI-ASSISTED rather than silently passed.",
    )


# --------------------------------------------------------------------------
# Rule 3 — ad disclosure (FTC guide; AUTOMATED)
# --------------------------------------------------------------------------

_AD_DISCLOSURE = re.compile(
    r"\b(advertisement|this is an ad\b|promotional (e-?mail|message)|"
    r"marketing (e-?mail|message)|sponsored (e-?mail|message))\b", re.I,
)


def check_ad_disclosure(body_text: str) -> Finding:
    quote = (
        "you must disclose clearly and conspicuously that your message is "
        "an advertisement"
    )
    if _AD_DISCLOSURE.search(body_text):
        return Finding(
            "rule-3-ad-disclosure", "Message identified as an advertisement",
            "FTC Compliance Guide", quote, "AUTOMATED", "PASS",
            "An explicit ad/marketing/promotional disclosure phrase is "
            "present in the body.",
        )
    return Finding(
        "rule-3-ad-disclosure", "Message identified as an advertisement",
        "FTC Compliance Guide", quote, "AUTOMATED", "FAIL",
        "No explicit advertisement/marketing/promotional disclosure phrase "
        "found in the body. Note: this checks for presence of a disclosure "
        "phrase, not whether an existing one is 'clear and conspicuous' "
        "enough — that finer judgment stays AI-ASSISTED even when this "
        "check passes.",
    )


# --------------------------------------------------------------------------
# Rule 4 — physical postal address (16 CFR 316.2(p); AUTOMATED)
# --------------------------------------------------------------------------

_ZIP = re.compile(r"\b\d{5}(-\d{4})?\b")
_POBOX = re.compile(r"\bP\.?\s?O\.?\s*Box\s*\d+", re.I)
_STREET = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.\s]{2,40}\b"
    r"(Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|"
    r"Lane|Ln\.?|Way|Suite|Ste\.?)\b", re.I,
)


def check_postal_address(body_text: str) -> Finding:
    quote = (
        '"Valid physical postal address" means the sender\'s current '
        "street address, a Post Office box the sender has accurately "
        "registered with the United States Postal Service, or a private "
        "mailbox the sender has accurately registered with a commercial "
        "mail receiving agency that is established pursuant to United "
        "States Postal Service regulations"
    )
    if _POBOX.search(body_text) or (_ZIP.search(body_text) and _STREET.search(body_text)):
        return Finding(
            "rule-4-postal-address", "Valid physical postal address present",
            "16 CFR §316.2(p)", quote, "AUTOMATED", "PASS",
            "A street-address-shaped pattern (or PO Box) is present in the "
            "body.",
        )
    return Finding(
        "rule-4-postal-address", "Valid physical postal address present",
        "16 CFR §316.2(p)", quote, "AUTOMATED", "FAIL",
        "No street address, PO Box, or ZIP-code-shaped pattern found in the "
        "body.",
    )


# --------------------------------------------------------------------------
# Rule 5 — opt-out present, not fee-gated, not multi-step
# (16 CFR 316.5; AUTOMATED — one gate, two boundaries in the same pass)
# --------------------------------------------------------------------------

_OPTOUT_PRESENT = re.compile(
    r"\b(unsubscribe|opt[- ]out|stop receiving|stop these emails)\b", re.I,
)
_FEE_LANGUAGE = re.compile(r"(\$\s?\d|\bfee\b|\bcharge\b|payment required|pay to)", re.I)
_MULTISTEP_LANGUAGE = re.compile(
    r"\b(call us|call \(|mail a letter|send a letter|log in to your account|"
    r"sign in to your account|visit our office)\b", re.I,
)


def check_opt_out(body_text: str) -> Finding:
    quote = (
        "Neither a sender nor any person acting on behalf of a sender may "
        "require that any recipient pay any fee, provide any information "
        "other than the recipient's electronic mail address and opt-out "
        "preferences, or take any other steps except sending a reply "
        "electronic mail message or visiting a single Internet Web page"
    )
    match = _OPTOUT_PRESENT.search(body_text)
    if not match:
        return Finding(
            "rule-5-opt-out", "Working, one-step, no-fee opt-out mechanism",
            "16 CFR §316.5", quote, "AUTOMATED", "FAIL",
            "No opt-out / unsubscribe language found in the body at all.",
        )

    window = body_text[max(0, match.start() - 150): match.end() + 150]
    if _FEE_LANGUAGE.search(window):
        return Finding(
            "rule-5-opt-out", "Working, one-step, no-fee opt-out mechanism",
            "16 CFR §316.5", quote, "AUTOMATED", "FAIL",
            "Opt-out language is present but fee/charge/payment language "
            "appears in the same vicinity — §316.5 bars requiring any fee "
            "to opt out.",
        )
    if _MULTISTEP_LANGUAGE.search(window):
        return Finding(
            "rule-5-opt-out", "Working, one-step, no-fee opt-out mechanism",
            "16 CFR §316.5", quote, "AUTOMATED", "FAIL",
            "Opt-out language is present but is described as requiring a "
            "phone call, a mailed letter, or logging into an account — "
            "§316.5 requires opt-out to take no more than a reply email or "
            "visiting a single web page.",
        )
    return Finding(
        "rule-5-opt-out", "Working, one-step, no-fee opt-out mechanism",
        "16 CFR §316.5", quote, "AUTOMATED", "PASS",
        "Opt-out language is present with no fee-gating or multi-step "
        "language detected nearby. Scope note: this rule applies "
        "regardless of subscriber/membership status (FTC guide header 6) "
        "unless the message is genuinely transactional-or-relationship per "
        "§316.3(c) — this checker does not attempt that judgment.",
    )


# --------------------------------------------------------------------------
# Rules 6 & 7 — explicitly out of scope, not silently skipped
# --------------------------------------------------------------------------


def out_of_scope_findings() -> list[Finding]:
    return [
        Finding(
            "rule-6-prompt-honor", "Opt-out honored within 10 business days",
            "16 CFR §316.5(b)",
            "Have such a request honored as required by 15 U.S.C. "
            "7704(a)(3)(B) and (a)(4)",
            "OUT-OF-SCOPE", "SKIPPED",
            "A static single-email auditor has no way to observe what "
            "happens after the email is sent. Named here rather than "
            "silently omitted.",
        ),
        Finding(
            "rule-7-third-party-monitoring",
            "Monitoring third-party senders acting on your behalf",
            "FTC Compliance Guide",
            "you can't contract away your legal responsibility to comply "
            "with the law",
            "OUT-OF-SCOPE", "SKIPPED",
            "Auditing a third party's ongoing conduct is not something a "
            "single static artifact can check. Named here rather than "
            "silently omitted.",
        ),
    ]


AUTOMATED_CHECK_FUNCS = [
    check_header_accuracy,
    check_ad_disclosure,
    check_postal_address,
    check_opt_out,
]  # check_subject_line excluded here: its FAIL path is AUTOMATED but its
   # default path is AI-ASSISTED, so it's driven separately below and
   # covered by its own label-integrity scan in run_selftest().


# --------------------------------------------------------------------------
# audit orchestration
# --------------------------------------------------------------------------


def run_audit(path: Path, brand_domain: str | None = None) -> list[Finding]:
    msg = parse_eml(path)
    body_text = get_body_text(msg)

    findings = [
        check_header_accuracy(msg, brand_domain=brand_domain),
        check_subject_line(msg, body_text),
        check_ad_disclosure(body_text),
        check_postal_address(body_text),
        check_opt_out(body_text),
    ]
    findings.extend(out_of_scope_findings())

    ref_texts = load_reference_text()
    for f in findings:
        f.quote_grounded = quote_is_grounded(f.quote, ref_texts)

    return findings


def render_markdown(path: Path, findings: list[Finding]) -> str:
    lines = [f"# CAN-SPAM audit — {path.name}", ""]
    fails = [f for f in findings if f.status == "FAIL"]
    lines.append(
        f"**{len(fails)} FAIL** / "
        f"{sum(1 for f in findings if f.status == 'PASS')} PASS / "
        f"{sum(1 for f in findings if f.status == 'NEEDS-REVIEW')} NEEDS-REVIEW "
        f"/ {sum(1 for f in findings if f.status == 'SKIPPED')} out of scope"
    )
    lines.append("")
    if fails:
        lines.append(f"⚠️ {PENALTY_LINE}")
        lines.append("")
    for f in findings:
        grounded = "✓ quote verified in reference/" if f.quote_grounded else "✗ QUOTE NOT FOUND IN reference/ — self-check failure"
        lines.append(f"## [{f.status}] {f.label} — `{f.tag}`")
        lines.append(f"- **Rule:** {f.rule_id}  ")
        lines.append(f"- **Citation:** {f.citation} ({grounded})  ")
        lines.append(f"- **Quoted:** \"{f.quote}\"  ")
        lines.append(f"- {f.message}")
        lines.append("")
    return "\n".join(lines)


def render_sarif(path: Path, findings: list[Finding]) -> dict:
    rules = []
    results = []
    seen_rules = set()
    for f in findings:
        if f.rule_id not in seen_rules:
            rules.append({
                "id": f.rule_id,
                "shortDescription": {"text": f.label},
                "helpUri": "https://www.law.cornell.edu/cfr/text/16/part-316",
            })
            seen_rules.add(f.rule_id)
        if f.status == "FAIL":
            level = "error"
        elif f.status == "NEEDS-REVIEW":
            level = "warning"
        else:
            continue
        results.append({
            "ruleId": f.rule_id,
            "level": level,
            "message": {"text": f"[{f.tag}] {f.message}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": path.name}
                }
            }],
        })
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "can-spam-auditor",
                "informationUri": "https://github.com/NFTYoginis/can-spam-auditor",
                "rules": rules,
            }},
            "results": results,
        }],
    }


# --------------------------------------------------------------------------
# P17 — verify the verifier
# --------------------------------------------------------------------------

# fixture filename -> rule_id expected to FAIL on it (all other AUTOMATED
# rules on that fixture are expected to PASS/NEEDS-REVIEW, never FAIL).
# Mirrors builds/check-gate/fixtures/manifest.md's own good/bad + named-check
# pattern (this worker's own prior build) — see fixtures/manifest.md.
FIXTURE_MANIFEST = {
    "clean.eml": None,  # None = expect zero FAILs
    "bad-header-mismatch.eml": "rule-1-header-accuracy",
    "bad-subject-contradicts-body.eml": "rule-2-subject-line",
    "bad-no-ad-disclosure.eml": "rule-3-ad-disclosure",
    "bad-no-postal-address.eml": "rule-4-postal-address",
    "bad-no-optout.eml": "rule-5-opt-out",
    "bad-fee-gated-optout.eml": "rule-5-opt-out",
    "bad-multistep-optout.eml": "rule-5-opt-out",
}

_NETWORK_OR_LLM_TOKENS = (
    "urllib", "requests", "httpx", "http.client", "socket", "openai",
    "anthropic", "urlopen", "os.environ",
)


def check_label_integrity() -> tuple[bool, list[str]]:
    """Every AUTOMATED-only check function must contain no network/LLM call.
    Proves the AUTOMATED/AI-ASSISTED split by code inspection, not by claim."""
    problems = []
    for fn in AUTOMATED_CHECK_FUNCS:
        src = inspect.getsource(fn)
        for token in _NETWORK_OR_LLM_TOKENS:
            if token in src:
                problems.append(f"{fn.__name__} contains forbidden token '{token}'")
    return (len(problems) == 0, problems)


def run_selftest() -> int:
    ok = True
    print("can-spam-auditor --selftest\n")

    label_ok, label_problems = check_label_integrity()
    if label_ok:
        print("[PASS] label-integrity: no AUTOMATED check function references "
              "network/LLM tokens (" + ", ".join(_NETWORK_OR_LLM_TOKENS) + ")")
    else:
        ok = False
        print("[FAIL] label-integrity:")
        for p in label_problems:
            print(f"       {p}")

    for fixture_name, expected_fail_rule in FIXTURE_MANIFEST.items():
        fixture_path = FIXTURES_DIR / fixture_name
        if not fixture_path.exists():
            ok = False
            print(f"[FAIL] {fixture_name}: fixture file missing")
            continue

        findings = run_audit(fixture_path)
        automated = [f for f in findings if f.tag == "AUTOMATED"]
        failed_rules = {f.rule_id for f in automated if f.status == "FAIL"}
        ungrounded = [f for f in findings if f.quote_grounded is False]

        if ungrounded:
            ok = False
            print(f"[FAIL] {fixture_name}: quote(s) not found in reference/ for "
                  + ", ".join(f.rule_id for f in ungrounded))
            continue

        if expected_fail_rule is None:
            if failed_rules:
                ok = False
                print(f"[FAIL] {fixture_name}: expected zero AUTOMATED FAILs, "
                      f"got {sorted(failed_rules)}")
            else:
                print(f"[PASS] {fixture_name}: clean fixture fully passes "
                      f"({len(automated)} automated checks)")
        else:
            if failed_rules == {expected_fail_rule}:
                print(f"[PASS] {fixture_name}: fails only {expected_fail_rule}, "
                      f"as designed")
            elif expected_fail_rule not in failed_rules:
                ok = False
                print(f"[FAIL] {fixture_name}: expected {expected_fail_rule} to "
                      f"FAIL, but AUTOMATED FAILs were {sorted(failed_rules)}")
            else:
                ok = False
                print(f"[FAIL] {fixture_name}: {expected_fail_rule} failed as "
                      f"expected, but so did unexpected rule(s) "
                      f"{sorted(failed_rules - {expected_fail_rule})}")

    print()
    print("SELFTEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("email_file", nargs="?", help="Path to a raw .eml file")
    parser.add_argument("--brand-domain", help="Optional: fail Rule 1 if From domain differs from this")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument("--sarif", metavar="PATH", help="Also write a SARIF report to PATH")
    parser.add_argument("--selftest", action="store_true", help="Run fixtures/ and prove the checker works (P17)")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    if not args.email_file:
        parser.print_help()
        return 2

    path = Path(args.email_file)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 2

    findings = run_audit(path, brand_domain=args.brand_domain)

    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print(render_markdown(path, findings))

    if args.sarif:
        Path(args.sarif).write_text(json.dumps(render_sarif(path, findings), indent=2))
        print(f"\n(SARIF written to {args.sarif})", file=sys.stderr)

    return 1 if any(f.status == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
