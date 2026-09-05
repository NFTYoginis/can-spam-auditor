# Fixture manifest

Pattern modeled on `builds/check-gate/fixtures/manifest.md` in this same worker's own tree — a hand-readable table alongside the machine-checked one in `audit.py`'s `FIXTURE_MANIFEST` dict, so a reader can verify by eye that the code's expectations match this table, not just trust that they do.

All fixtures are generated from **one base clean email** by `generate_fixtures.py`, mutating exactly one thing per bad fixture. Re-run `python3 fixtures/generate_fixtures.py` to regenerate byte-identical copies.

| Fixture | Mutation from base | Expected `audit.py` result |
| --- | --- | --- |
| `clean.eml` | none — this *is* the base | All 4 `AUTOMATED` checks PASS; `rule-2-subject-line` is `AI-ASSISTED`/`NEEDS-REVIEW` (no transactional-subject pattern in a non-transactional subject — correctly ambiguous, not a FAIL) |
| `bad-header-mismatch.eml` | `Reply-To` domain changed to an unrelated domain | `rule-1-header-accuracy` FAILs; every other `AUTOMATED` check still PASSes |
| `bad-subject-contradicts-body.eml` | Subject changed to `Re: Your Order Confirmation`; body opens with promotional/sale language and no transactional content up front | `rule-2-subject-line` FAILs (this is the one case where the subject-line check is `AUTOMATED`, per `reference/rule-map.md`); everything else PASSes |
| `bad-no-ad-disclosure.eml` | "This is a promotional email..." line removed | `rule-3-ad-disclosure` FAILs; everything else PASSes |
| `bad-no-postal-address.eml` | Address block removed | `rule-4-postal-address` FAILs; everything else PASSes |
| `bad-no-optout.eml` | Unsubscribe line removed entirely | `rule-5-opt-out` FAILs (no mechanism at all); everything else PASSes |
| `bad-fee-gated-optout.eml` | Unsubscribe line rewritten to demand a $5 fee | `rule-5-opt-out` FAILs (fee-gated boundary); everything else PASSes |
| `bad-multistep-optout.eml` | Unsubscribe line rewritten to require a phone call or mailed letter | `rule-5-opt-out` FAILs (multi-step boundary); everything else PASSes |

## Parser robustness — same content, shaped like real-world ESP output

Real marketing email doesn't look like the clean plain-text base above. These two fixtures carry the *same compliant content* but structured the way actual sending platforms (Mailchimp/Klaviyo/Kajabi-style) actually output it — added after a build-time review flagged that only clean synthetic fixtures had ever been tested. Both must fully PASS; a FAIL here means the parser is broken, not the email.

| Fixture | What's messy about it | Expected `audit.py` result |
| --- | --- | --- |
| `clean-html-only-entities.eml` | No `text/plain` part at all — HTML-only body, address laid out across `<table>` rows, HTML entities (`&nbsp;`, `&#39;`) instead of literal characters, opt-out phrased "no longer receive these emails" instead of the word "unsubscribe" | All 4 `AUTOMATED` checks PASS |
| `clean-view-in-browser-stub.eml` | `multipart/alternative` where the `text/plain` part is a near-empty "View this email in your browser: `<url>`" stub and the real content lives only in the `text/html` part — extremely common real ESP output | All 4 `AUTOMATED` checks PASS |
| `clean-longform-commercial-pitch.eml` | ~280-word long-form soft-sell pitch — real-length, real-complexity prose (a paid offer described honestly, "here's who this is and isn't for," an embedded plain-text URL, no urgency pressure) instead of a short synthetic announcement. Fictional throughout; built as a synthetic stand-in after an earlier real-derived draft of this same shape turned out to contain a real domain in its body copy and was correctly not used | All 4 `AUTOMATED` checks PASS |

## Non-email input

| Fixture | What it tests | Expected `audit.py` result |
| --- | --- | --- |
| `not-an-email.txt` | Plain prose, zero RFC 5322 headers — not an email missing a field, not an email at all | `run_audit()` raises `NotAnEmailError`; the CLI exits 2 with an explanation, never a report |

This one exists because a blind adversarial test (2026-09-05) fed `audit.py` plain non-email text and got back a fully-formed "4 FAIL" report citing real CFR text — indistinguishable from a genuine finding to anyone who didn't know the input was garbage. Fixed the same day: `parse_eml()` now checks for at least one recognized header before proceeding at all. A real email that's merely *missing* its From header is a different case entirely and still produces a genuine `rule-1-header-accuracy` `FAIL` — see `audit.py`'s `parse_eml()` docstring for exactly where that line is drawn.

Run `python3 audit.py --selftest` to check all of the above mechanically, plus a **label-integrity pass** (no `AUTOMATED`-tagged check function may contain a network or LLM-call token — see `reference/rule-map.md` § Label integrity). 12 assertions total: 7 rule fixtures + 3 parser-robustness fixtures + 1 non-email-input check + 1 label-integrity pass.
