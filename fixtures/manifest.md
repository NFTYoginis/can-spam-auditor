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

Run `python3 audit.py --selftest` to check all of the above mechanically, plus a **label-integrity pass** (no `AUTOMATED`-tagged check function may contain a network or LLM-call token — see `reference/rule-map.md` § Label integrity).
