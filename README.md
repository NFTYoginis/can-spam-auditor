# can-spam-auditor

Audits a raw marketing email (`.eml` — full source, headers included) against the CAN-SPAM Act's core requirements, codified at **16 CFR Part 316**. Two-track: a deterministic checker for what's mechanically decidable, honest `AI-ASSISTED` labeling for what isn't, and two requirements named as out of scope rather than silently skipped.

**Zero API key. Zero network calls. Zero third-party dependencies** — `audit.py` uses only the Python 3 standard library. Clone the repo, run one script, get a real pass/fail report. That's the whole verification story.

```
$ python3 audit.py --selftest
can-spam-auditor --selftest

[PASS] label-integrity: no AUTOMATED check function references network/LLM tokens
[PASS] clean.eml: clean fixture fully passes (4 automated checks)
[PASS] bad-header-mismatch.eml: fails only rule-1-header-accuracy, as designed
[PASS] bad-subject-contradicts-body.eml: fails only rule-2-subject-line, as designed
[PASS] bad-no-ad-disclosure.eml: fails only rule-3-ad-disclosure, as designed
[PASS] bad-no-postal-address.eml: fails only rule-4-postal-address, as designed
[PASS] bad-no-optout.eml: fails only rule-5-opt-out, as designed
[PASS] bad-fee-gated-optout.eml: fails only rule-5-opt-out, as designed
[PASS] bad-multistep-optout.eml: fails only rule-5-opt-out, as designed

SELFTEST PASSED
```

## Why this exists

Every separate email that violates the CAN-SPAM Act is subject to a civil penalty of **up to $53,088** — the FTC's own 2025 inflation-adjusted figure, still current for 2026 (no OMB adjustment happened this year). Every email sent counts separately. That's real money for a mistake as small as a missing unsubscribe link or a mismatched Reply-To address. See `reference/ftc-compliance-guide.md` for the FTC's own text.

## Setup (2 minutes)

1. Clone this repo.
2. You need Python 3.9+ and nothing else — no `pip install`, no `requirements.txt`.
3. Run the self-test to confirm the checker works on your machine: `python3 audit.py --selftest`
4. Audit your own email: export it from your email client as raw source (most clients: "View Original" / "Show source" / "Download .eml"), then `python3 audit.py path/to/your-email.eml`

## Usage

```
python3 audit.py <email.eml>                          # Markdown report
python3 audit.py <email.eml> --json                    # machine-readable
python3 audit.py <email.eml> --sarif report.sarif       # also emit SARIF (GitHub Code Scanning, VS Code Problems panel)
python3 audit.py <email.eml> --brand-domain example.com # stricter Rule 1: also fail if From isn't on your declared domain
python3 audit.py --selftest                             # prove the checker works (P17-style: known-good + known-bad fixtures)
```

Exit code `0` if every automated check passes; `1` if any `FAIL` fired.

## What it checks (and what it honestly doesn't)

| Rule | Tag | What it means |
| --- | --- | --- |
| Accurate header info (From/Reply-To domain consistency) | `AUTOMATED` | |
| Non-deceptive subject line | `AUTOMATED` *(one narrow structural case)* / `AI-ASSISTED` *(everything else)* | See `reference/rule-map.md` |
| Ad disclosure present | `AUTOMATED` | |
| Physical postal address present | `AUTOMATED` | |
| Opt-out present, not fee-gated, not multi-step | `AUTOMATED` | one gate, two boundaries, same pass |
| Opt-out honored within 10 business days | **OUT OF SCOPE** | a static single-email auditor can't observe what happens after sending |
| Monitoring third-party senders | **OUT OF SCOPE** | a static single-email auditor can't observe a third party's ongoing conduct |

Full mapping — citation, exact quoted text, which function checks it — in [`reference/rule-map.md`](reference/rule-map.md). The regulation and the FTC's guide are reproduced near-verbatim in `reference/` (both are US federal government works, public domain under 17 U.S.C. §105) — open a finding, open the cited section, check the words match. `audit.py --selftest` checks that mechanically too (every finding's quote is verified as an actual substring of `reference/` before the selftest can pass).

**What "AUTOMATED" means here, provably:** `--selftest` includes a label-integrity pass that reads the source of every `AUTOMATED`-tagged check function and fails if any of them references a network or LLM-call token. The label isn't a comment — it's checked.

## What this is not

Not a legal compliance certification. A clean report means five structural checks passed on one email — not "this business is CAN-SPAM compliant." Two real requirements aren't checked at all, by design, and the report says so every run. See `rules.md` for the exact refusal language this specialist uses when asked to overclaim.

Not a multi-standard compliance tool. It checks one Act. Scope stays narrow on purpose — see `rules.md` § Never.

## Go-beyond (built or scoped, priority order)

1. **SARIF output** — `--sarif`, ships today, plugs into GitHub Code Scanning / VS Code Problems panel.
2. **GitHub Action** wrapping the same offline checker as a PR check for email templates in version control — not yet built, natural next step given #1.
3. **Drift tracking** across two versions of the same template — not yet built.

## Repo layout

```
audit.py                    ← the whole engine, stdlib only
fixtures/                   ← one clean base email + one broken variant per rule, generated by fixtures/generate_fixtures.py
reference/
  16-cfr-part-316.md        ← verbatim regulation text
  ftc-compliance-guide.md   ← verbatim FTC compliance guide
  rule-map.md               ← rule → citation → tag → check function
identity.md / rules.md / examples.md   ← the ICM specialist layer (load this repo into a Claude Project to get an assistant that runs the checker and explains findings honestly)
docs/index.html             ← this repo's own landing page (GitHub Pages)
```

## Sources

- FTC, *"CAN-SPAM Act: A Compliance Guide for Business"* — `ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business`
- 16 CFR Part 316, via Cornell Law School Legal Information Institute — `law.cornell.edu/cfr/text/16/part-316`

Both are US federal government works (public domain, 17 U.S.C. §105). Full text reproduced in `reference/`.

## License

MIT — see `LICENSE`.
