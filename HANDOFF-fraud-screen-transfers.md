# Branch `feature/fraud/screen-transfers` — note de continuare

Document de handoff pentru reluarea lucrului de pe alt calculator.
Șterge-l înainte de merge.

---

## 1. Ce e pe branch

Două schimbări logice independente, în două commit-uri separate.

### A. Motorul anti-fraudă acoperă și transferurile

Până acum `FraudService.evaluate_transaction` era apelat **dintr-un singur loc**:
`create_card_payment`, doar pentru carduri debit/one-time. Acum acoperă și
`TRANSFER` (`SCREENED_TRANSACTION_TYPES = {CARD_PAYMENT, TRANSFER}`).

Cel mai important lucru rezolvat: **`approve()` creditează acum destinația.**
Un `HOLD` scoate banii doar din portofelul plătitorului; un transfer are un al
doilea picior pe care hold-ul nu-l atinge, deci fără asta banii ar fi
dispărut la aprobare. Limitarea era documentată explicit în
`backend/app/ai/actions/fraud_screen.py` ca follow-up cunoscut — ăsta e
follow-up-ul.

Alte decizii:

- **Sumele sunt mereu latura sursă** (`_screened_amount` = `source_amount or
  amount`). La un transfer valutar `amount`/`currency` descriu ce primește
  destinatarul; hold-ul, scorul și `hold_currency` folosesc ce pleacă efectiv
  din portofel.
- **Baseline-urile sunt scoped pe 3 axe**: aceeași monedă, același tip de
  tranzacție, și doar ce a inițiat userul (`list_for_user` returnează și
  transferurile *primite*, care nu spun nimic despre cât e normal să trimiți).
- **Flag nou `REPEATED_TRANSFER_PATTERN`** — echivalentul pe transferuri al
  lui `REWARD_ABUSE_PATTERN`, cu cheia pe `destination_wallet_id`. Aceeași
  calibrare (3 repetări / 10 min, cap 70). Cod separat, nu refolosit, pentru
  că adminul are nevoie de alt ghidaj de review.
- **Bill-split și payment-request NU sunt scanate** — opt-out explicit prin
  `create_internal_transfer(..., screen_for_fraud=False)`. Motivul:
  `pay_participant` marchează participantul PAID și notifică „payment
  received" imediat după, ceea ce ar fi fals cât timp banii sunt pe hold.

### B. Performanță pe backend-ul Supabase REST

Diagnosticat pornind de la „se încarcă greu tot". Două cauze:

1. `app/supabase.py` folosea `urlopen` per apel → **conexiune TCP+TLS nouă la
   fiecare interogare**. Măsurat pe instanța comună:

   | Starea Supabase | Conexiune nouă | Keep-alive |
   |---|---|---|
   | Degradată | **4021 ms** | 653 ms (**6.2×**) |
   | Sănătoasă | 110 ms | 83 ms (1.41×) |

   Sub încărcare cedează *stabilirea* conexiunii, nu interogarea.

2. `evaluate_transaction` cerea aceeași listă de tranzacții de trei ori
   (`HIGH_AMOUNT`, velocity, `UNUSUAL_TIME`), fiecare = 2 round-trip-uri.

Soluție: client `httpx` pooled partajat între cereri (thread-safe, contează
pentru că FastAPI rulează endpoint-urile sync într-un threadpool), plus o
singură aducere a istoricului. **6 round-trip-uri → 2** pe calea de fraudă.

Detalii deliberate în implementare, **nu le strica**:

- Formatul mesajului din `RuntimeError` e load-bearing — repository-uri din
  tot codul îl parsează ca să detecteze tabele/coloane lipsă.
- `TimeoutError` e păstrat ca tip de excepție, deși httpx aruncă altceva.
- Query string-ul rămâne construit manual: filtrele PostgREST (`or=(...)`)
  depind de encoding-ul exact.
- **Retry doar pe GET.** Un POST/PATCH/DELETE rejucat poate duplica un INSERT,
  adică o tranzacție sau o linie de ledger.

`httpx==0.28.1` adăugat explicit în `requirements.txt` — era deja instalat
tranzitiv prin `openai`, deci nu se descarcă nimic nou.

---

## 2. Baza branch-ului și ordinea de merge

```
master
  └── feature/ai/actionable-agent      (migrarea 0048)
        └── feature/fraud/screen-transfers   ← AICI (migrarea 0049)
```

**Nu e pornit din master, intenționat.** Migrarea `0049` se leagă de `0048`,
care există doar pe `feature/ai/actionable-agent`.

> **Acest PR trebuie să intre după `feature/ai/actionable-agent`.**
> Altfel `down_revision` din 0049 rămâne orfan și `alembic upgrade head` crapă
> pentru toată lumea. Dacă ordinea se schimbă, rebazează 0049 pe noul head.

`alembic heads` returnează **un singur head** (`0049_fraud_repeated_transfer_pattern`).
Verifică asta înainte de PR — cu 4 oameni în paralel apar heads multiple des.

---

## 3. Bază de date — atenție

`.env` are `DATABASE_BACKEND=supabase_rest` și pointează spre **Supabase-ul
comun al echipei**. Migrarea 0049 **nu a fost aplicată acolo** — deliberat,
pentru că un `ALTER TYPE` afectează toți cei 4 înainte ca PR-ul să fie agreat.

Consecință: dacă rulezi backend-ul cu acest cod pe Supabase-ul comun și faci
un transfer care declanșează `REPEATED_TRANSFER_PATTERN`, scrierea flag-ului
crapă (valoarea nu există în enum acolo).

Opțiuni:

1. **Postgres local** (recomandat) — `docker-compose.yml` are deja serviciul,
   pus exact pentru cazul „Supabase-ul comun nu e accesibil".
2. Aplici `supabase/sql/supabase_add_fraud_repeated_transfer_pattern.sql` pe
   Supabase comun — aditiv și nedistructiv, dar **anunță echipa întâi**.

---

## 4. Cum verifici de la zero pe alt calculator

Testele rulează în container, nu ai nevoie de venv local:

```bash
docker run --rm -v "$PWD/backend:/app" -w /app python:3.12-slim \
  sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

Frontend (type-check; `Record<FraudFlagCode, string>` e exhaustiv, deci
prinde flag-uri lipsă la compilare):

```bash
cd frontend && npm ci && npx tsc -b
```

Migrări pe un Postgres de unică folosință:

```bash
docker network create fv
docker run -d --name fv-pg --network fv \
  -e POSTGRES_USER=banking -e POSTGRES_PASSWORD=banking -e POSTGRES_DB=banking \
  postgres:16-alpine
docker run --rm --network fv -v "$PWD/backend:/app" -w /app \
  -e DATABASE_URL="postgresql+psycopg://banking:banking@fv-pg:5432/banking" \
  python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && alembic upgrade head"
```

### Stare la ultima rulare

| Verificare | Rezultat |
|---|---|
| `pytest` (toată suita) | **799 passed** |
| `pytest tests/test_fraud.py` | 48 passed (9 teste noi) |
| `tsc -b` frontend | exit 0 |
| `alembic upgrade head` de la zero pe Postgres | OK, un singur head |
| Scenariu end-to-end pe Postgres real | 21/21 |

Scenariul end-to-end a acoperit ceva ce SQLite din teste **nu poate**: pe
SQLite enum-urile sunt doar text, deci testele ar fi trecut și cu migrarea
greșită. Pe Postgres, un flag inexistent în enum ar fi crăpat la scriere.

### Verificare manuală în UI

1. Ca user normal: 6 transferuri de aceeași sumă către același destinatar, în
   sub 10 minute. Al 6-lea rămâne `PENDING_REVIEW`, banii apar rezervați.
2. Ca admin: Fraud Review arată cazul cu flag-ul **Repeated Transfer Pattern**.
3. **Approve** → soldul destinatarului trebuie să crească. Ăsta e testul
   decisiv, era exact bug-ul documentat în `fraud_screen.py`.
4. Sau **Reject** → banii se întorc integral la plătitor.

Pentru varianta „sumă mare": 3 transferuri mici (50 RON), apoi unul de 500.

---

## 5. Ce a rămas de făcut

- [ ] **Teste unitare pentru `_send`** din `app/supabase.py` — că GET-ul se
      reia și POST-ul nu. E cod nou, relevant pentru siguranța financiară, și
      **necaoperit de suită**: testele existente fac monkeypatch pe
      `session.request`, adică exact metoda rescrisă. Am verificat manual pe
      Supabase real (fetch, get, formatul de eroare), dar nu e automatizat.
- [ ] **Split în două PR-uri** dacă vrei review mai curat. Fișierele sunt
      aproape disjuncte: `supabase.py` + `requirements.txt` vs restul.
      Singura suprapunere e deduplicarea din `fraud/service.py`, care a intrat
      în commit-ul de fraudă.
- [ ] **Formularea din evidence pack** pentru cazurile de transfer — textele
      din `build_investigation_context` au fost scrise inițial pentru plăți
      card. Logica e corectată (scoped pe tip), dar cum arată efectiv în UI-ul
      de admin se vede doar cu ochiul.
- [ ] Decis dacă bill-split / payment-request intră și ele la screening. Cere
      întâi tratarea lui `PENDING_REVIEW` în acele fluxuri (participant să
      rămână PENDING, notificarea să nu plece, split-ul să nu se marcheze
      SETTLED).

## 6. Limitări cunoscute (asumate, nu bug-uri)

- **Repetările către același IBAN extern nu sunt detectabile.** IBAN-ul e
  stocat doar în `description` (text liber), deci `REPEATED_TRANSFER_PATTERN`
  n-are cheie de counterparty. Prinse doar de `HIGH_VELOCITY`. Un fix ar cere
  un câmp nou pe `Transaction` — entitate shared, high-impact.
- **Pooling-ul nu rezolvă tot.** Am văzut și timeout-uri la *citire*
  (serverul acceptă conexiunea, apoi nu răspunde 30s), inclusiv un outlier de
  13.6s. Alea sunt stall-uri server-side ale instanței Supabase free tier
  partajate de 4 oameni. Pentru dezvoltare, Postgres local.
- `approve()` folosește `get_by_id` (fără lock) pentru wallet-ul sursă —
  preexistent, lăsat așa. Pentru destinație am folosit `get_by_id_for_update`,
  conform regulii din repo.

## 7. Contracte atinse (pentru ceilalți 3)

- `FraudFlagCode` + tipul TS capătă `REPEATED_TRANSFER_PATTERN` — **aditiv**,
  rândurile existente rămân valide.
- `create_internal_transfer(..., *, screen_for_fraud: bool = True)` — kwarg
  nou cu default, non-breaking. Default `True` ca orice apelant nou să fie
  acoperit automat.
- `FraudService.get_recent_activity(..., history=None)` — parametru opțional.
- `hold_currency` returnează acum moneda sursă (corectură pentru FX; identic
  pentru restul).
