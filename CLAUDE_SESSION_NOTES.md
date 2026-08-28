# ⚠️ DELETE THIS FILE BEFORE OPENING THE PR ⚠️

This is a handoff note from one Claude session to the next, on branch
`feature/onboarding-identity-document`. It is not documentation for the
team — it's scratch context so whoever (human or Claude) picks this branch
up next doesn't have to re-derive everything from the diff. Remove this
file as part of cleaning up the branch before it goes up for review.

Last updated: 2026-08-27/28 (late-night session, continuing into today).

## What this branch does

Implements onboarding Step 3 for real: uploading a Romanian ID card
("buletin"), extracting data from its MRZ (Machine Readable Zone) band,
cross-checking it against what the user entered at Step 2, and gating
onboarding progress on that — replacing the old placeholder button that
just said "De făcut când introducem buletine" and did nothing.

Full plan this was built from (already executed, kept for context) is
`buletin task.md` in the repo root if it's still there — check that too,
it explains the original scoping conversation.

**Everything is deterministic. No AI/OCR engine, no Tesseract, no
EasyOCR/PyTorch** — reading the MRZ band is template matching against a
real OCR-B font rendered with Pillow, compared via numpy correlation. This
was a deliberate constraint from the user (CLAUDE.md's Azure-only AI
rule, and a separate explicit "no AI for this feature" decision).

## Files, what each does

Backend (`backend/app/users/`):
- `mrz.py` — pure parsing + ICAO 9303 checksums for TD1 (new card,
  3-line/30-char MRZ) and TD2 (old card, 2-line/36-char MRZ). No image
  code here at all — just string-in, structured-and-validated-data-out.
  Also `reconstruct_romanian_cnp_from_td2()` — see "Unverified" below.
- `mrz_reader.py` — reads ONE already-cropped MRZ line image via template
  matching against `assets/ocrb/OCRB.ttf`. Bounding-box-normalizes each
  character crop before comparing (this was a real bug I hit and fixed —
  see git log / the file's own comments — naive fixed-position comparison
  fails because a source render and the reference render are rarely the
  same pixel scale).
- `mrz_extraction.py` — the glue: given a whole "back of card" photo,
  guesses where the MRZ band is (bottom ~28% of the image — see "Unverified"
  below), tries TD1 then TD2, returns whichever's checksums check out.
  Also `decode_base64_image()` (tolerant of `data:` URL prefixes, returns
  None rather than raising on garbage input — a bad upload is just a
  failed attempt, not a crash).
- `models.py` — new `IdentityDocument` table (1 row per user, overwritten
  on each attempt — no history), `MrzFormatCode` enum, `KycDocumentStatus`
  extended with `VERIFIED` / `NEEDS_REVIEW` / `APPROVED` / `REJECTED`
  (kept the old `NOT_STARTED`/`PLACEHOLDER` values for backward compat,
  never assign `PLACEHOLDER` going forward).
- `service.py` — `submit_identity_document()`. Used from BOTH onboarding
  step 3 AND the Profile page's "re-verify" flow (see behavior split
  below). `_cross_check_identity()` compares MRZ-extracted name/CNP/DOB
  against `User`/`UserProfile`, with Romanian-diacritic normalization
  (MRZ text is ICAO-transliterated, plain Romanian names aren't).
- `router.py` — `POST /users/me/onboarding/step-3/identity-document`.

Backend assets/migration:
- `assets/ocrb/OCRB.ttf` + `NOTICE.md` — the OCR-B font, sourced from the
  Tsukurimashou Project (Matthew Skala), license explained in the NOTICE.
- `migrations/versions/0040_identity_documents.py` — new table + enum
  values. **Branches off `0039_ai_insights_currency`, which was ALREADY
  one of three unmerged alembic heads before this branch existed**
  (`0036_card_pin_hash` and `0037_wallet_iban` are the other two — not
  caused by this branch, not fixed by it either; see the migration file's
  own docstring). Whoever merges this will need a reconciliation merge
  migration regardless of this branch.
- `supabase/sql/supabase_identity_documents.sql` — the hand-written
  Supabase-sync companion (the team's Supabase project can't run Alembic
  directly — see `docs/supabase_rest_backend.md`). **The user already ran
  this successfully tonight against the shared Supabase project.** Also
  discovered while testing: that Supabase project is missing at least
  `loan_installments` (probably more of the credit/loan-era tables) —
  it's behind head by more than just this branch's migration. Not
  something I fixed; just noting it's a pre-existing gap.

Frontend:
- `features/auth/FileField.tsx` — extracted shared file→base64 input,
  used by both `OnboardingPage.tsx` (step 3) and `ProfilePage.tsx`
  (re-verify section).
- `OnboardingPage.tsx` step 3 — real upload form, shows `failure_reason`
  and attempt count, handles `NEEDS_REVIEW`/`REJECTED` states.
- `ProfilePage.tsx` — filled in the "Identity document" section a
  teammate had left as "coming in a future update."

## Behavior: two different flows through one endpoint

- **During onboarding** (`state.pending_step == 3`): hard 3-attempt limit,
  then `NEEDS_REVIEW` (blocks resubmission, needs an admin — **no admin
  review UI/endpoint exists yet**, that's the obvious next piece).
- **From Profile, after onboarding is done** (`state.completed`,
  re-verifying e.g. a renewed ID): NO attempt limit, and — this was an
  explicit user decision — a failed re-verification attempt does **not**
  touch the existing `VERIFIED` record at all (raises a plain 422, no
  document row is even written to). The user can just retry anytime.

## Explicitly UNVERIFIED — flag these to whoever tests with a real photo

1. **MRZ band location heuristic** (`mrz_extraction.py`,
   `_MRZ_BAND_FRACTION = 0.28`): assumes the band is in the bottom 28% of
   whatever photo gets uploaded. No perspective correction, no rotation
   handling. This is the single most likely thing to need tuning.
2. **Old card (TD2) format assumption entirely**: verified via HG
   839/2006 (the Romanian regulation) that the old buletin's MRZ zone
   dimensions (102×17mm) match TD2, and that it holds the CNP "without the
   birth date" (13 - 6 = 7 digits, matching TD2's optional-data field
   width exactly) — but never confirmed against an actual old-format card
   photo. New-card (TD1) parsing is much higher-confidence (it's a
   straightforward implementation of the public ICAO 9303 spec).
3. **New card (TD1) CNP placement**: assumed the full 13-digit CNP sits in
   TD1's optional-data field (15 chars). Also unverified — this one wasn't
   even confirmed against a legal document the way TD2's was; it's just
   the common EU convention.
4. **Real-photo OCR accuracy in general**: `test_mrz_reader.py` and
   `test_mrz_extraction.py` prove the template-matching pipeline works
   against synthetically-rendered text using the same OCR-B font — they
   say nothing about accuracy against camera angle, lighting, focus, JPEG
   artifacts on a real photo.

The user was going to test with their own real ID card tonight, right
before this note was written. **Check with them how it went** before
assuming any of the above is fine or trusting it needs rework.

## Also worth knowing

- Deleted the user's own real test account from the shared Supabase
  project tonight (email `cherascubogdan@gmail.com`) to free up their CNP
  for a clean re-test — this was a one-off manual SQL operation the user
  ran themselves in the Supabase SQL Editor, not part of this branch's
  code. Nothing to do here, just context for why that account won't be
  found if anyone goes looking for old test data.
- Full backend suite was green (693 passed) as of the last run before
  this note.
- Not built yet, natural next steps: admin `NEEDS_REVIEW` approve/reject
  endpoint (pattern: `CreditService.review_document` /
  `PATCH /credit/admin/documents/{id}/review`), and whatever the real
  photo test reveals needs fixing in the MRZ pipeline.
