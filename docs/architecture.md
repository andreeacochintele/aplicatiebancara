# Arhitectura aplicației bancare web

## 1. Scopul aplicației

Aplicația este o platformă bancară web construită de o echipă de 4 persoane, cu două tipuri principale de interfață:

- **User / Personal Banking**
- **Admin Banking**
- suport pentru **Business users** prin funcționalități suplimentare de export și administrare

Arhitectura recomandată este un **modular monolith**: un singur backend și o singură bază de date, dar codul este separat pe domenii. Pentru dimensiunea echipei, această abordare este mai simplă și mai rapidă decât microserviciile.

---

# 2. Stack recomandat

## Frontend
- React
- TypeScript
- React Router
- Recharts pentru grafice
- bibliotecă UI la alegere

## Backend
- Python
- FastAPI
- SQLAlchemy ORM
- Alembic pentru migrations

## Database
- PostgreSQL

## Authentication
- JWT / access + refresh token
- roluri: `USER`, `ADMIN`
- tip utilizator: `PERSONAL`, `BUSINESS`

## AI
- Python în același backend pentru MVP
- Orchestrator Agent
- Personal Finance Agent
- Credit Agent
- Fraud Investigation Agent

## Export
- PDF
- CSV

---

# 3. Domeniile principale

Aplicația este împărțită în 11 domenii:

1. Identity & Security
2. Wallets & FX
3. Transactions & Payments
4. Cards
5. Rewards & Merchant Cashback
6. Personal Finance
7. Credit & Loans
8. Fraud & Risk
9. Statements & Business Exports
10. Notifications & Audit
11. Agentic AI

---

# 4. Identity & Security

## Funcționalități

- creare cont
- login/logout
- profil utilizator
- utilizatori personali și business
- rol USER / ADMIN
- sesiuni
- logout după 5 minute de inactivitate
- device management
- verificare biometrică mock

## Logout automat

Se păstrează `last_activity_at` pentru sesiune. Dacă au trecut mai mult de 5 minute fără activitate, sesiunea este invalidată.

Cu aproximativ 30 de secunde înainte poate fi afișat un warning în UI.

## Biometrie mock

Pentru acțiuni importante se poate afișa:

`Face ID / Fingerprint verification -> SUCCESS / FAILED`

Nu se implementează recunoaștere biometrică reală în MVP.

---

# 5. Wallets & FX

Fiecare utilizator poate avea câte un wallet pentru fiecare valută.

Exemplu:

```text
RON Wallet    8,450 RON   MAIN
EUR Wallet    1,240 EUR
USD Wallet      320 USD
GBP Wallet       80 GBP
```

Constraint recomandat:

```text
UNIQUE(user_id, currency)
```

## Main Wallet

Utilizatorul alege un wallet principal.

Acesta poate fi utilizat pentru plăți în alte valute numai dacă utilizatorul permite conversia valutară.

Exemplu:

```text
Plată: 50 EUR
Wallet selectat: RON

-> FX Quote
-> 249.73 RON
-> utilizatorul confirmă conversia
-> plata este executată
```

Setare posibilă:

`Allow payments using main wallet with currency exchange`

## FX Service

Responsabilități:

- `get_rate()`
- `get_quote()`
- `convert()`

Quote-ul trebuie să conțină:

- source currency
- target currency
- source amount
- target amount
- exchange rate
- fee
- expiration time

---

# 6. Transactions

`Transaction` este una dintre entitățile centrale ale întregii aplicații.

## Tipuri

- TRANSFER
- CARD_PAYMENT
- FX
- CASHBACK
- LOAN_PAYMENT
- SCHEDULED_PAYMENT
- BILL_SPLIT_PAYMENT

## Statusuri

```text
CREATED
PROCESSING
PENDING_REVIEW
COMPLETED
FAILED
REJECTED
CANCELLED
```

Flux normal:

```text
CREATED -> PROCESSING -> COMPLETED
```

Flux suspect:

```text
CREATED
   |
PROCESSING
   |
PENDING_REVIEW
   |         |
APPROVED   REJECTED
   |
COMPLETED
```

---

# 7. Wallet Ledger

Soldurile nu trebuie modificate fără urmă.

Pentru fiecare operație se creează intrări într-un ledger.

Tipuri:

- DEBIT
- CREDIT
- HOLD
- RELEASE

Exemplu transfer 100 RON:

```text
Bogdan Wallet -> DEBIT 100
Andrei Wallet -> CREDIT 100
```

Ambele entry-uri sunt asociate aceleiași tranzacții.

Pentru fraudă:

```text
HOLD 12,000 RON
```

Dacă tranzacția este aprobată:

```text
HOLD -> DEBIT
```

Dacă este respinsă:

```text
HOLD -> RELEASE
```

---

# 8. Transfers & Payments

## Transfer clasic

Câmpuri:

- source wallet
- beneficiary
- IBAN
- amount
- currency
- description

## Transfer după telefon

```text
phone -> user lookup -> destination wallet -> transfer
```

Numărul de telefon trebuie să fie unic pentru utilizatorii aplicației.

## QR Payments

Utilizatorul poate crea un `payment_request`.

QR-ul conține doar un identificator al request-ului, nu informații bancare sensibile.

Flux:

```text
Generate QR
-> Scan QR
-> backend retrieves payment request
-> user confirms
-> transaction
```

---

# 9. Scheduled & Recurring Payments

## Scheduled

Exemplu:

`Plătește 750 RON pe 25 august.`

## Recurring

Exemplu:

`750 RON în fiecare lună pe data de 25.`

Frecvențe:

- ONCE
- DAILY
- WEEKLY
- MONTHLY
- YEARLY

Utilizatorul poate seta notificarea cu X zile înainte.

---

# 10. Cards

Tipuri:

- Debit Card
- Credit Card
- One-Time / Disposable Card

Statusuri:

- ACTIVE
- FROZEN
- EXPIRED
- CANCELLED

## Freeze

Dacă un card este `FROZEN`, orice plată este respinsă.

## One-Time Card

Cardul are o singură utilizare permisă.

După tranzacție:

```text
ACTIVE -> EXPIRED
```

Cardurile sunt mock/sandbox. Nu se păstrează PAN/CVV reale.

---

# 11. Rewards

Sistemul are două mecanisme distincte:

## Bank Reward Points

Exemplu:

```text
100 RON spent -> 100 points
```

Reward ledger:

```text
+120 Shopping
+80 Restaurant
-500 Cashback redemption
```

## Merchant Cashback

Companii mock pot oferi cashback.

Exemple:

```text
Nike       7%
Starbucks 10%
eMAG       5%
OMV        3%
Booking    4%
```

Un `CashbackOffer` poate avea:

- cashback percent
- minimum spend
- maximum cashback
- start/end date

Exemplu:

```text
Nike purchase: 400 RON
Cashback: 7%
Reward: 28 RON
```

Cashback-ul în bani poate fi salvat ca o tranzacție de tip `CASHBACK`.

---

# 12. Personal Finance

Include:

- spending analytics
- pie chart
- categorii
- comparații lunare
- budgets
- savings goals
- cash-flow forecast
- transaction search

Categorii exemple:

- Food
- Restaurants
- Transport
- Shopping
- Utilities
- Travel
- Entertainment
- Health
- Other

Dashboard:

```text
August spending: 2,840 RON

Groceries       30%
Restaurants     20%
Transport       15%
Shopping        15%
Bills           10%
Other           10%
```

---

# 13. Budgets

Exemplu:

```text
Restaurants
800 / 1,000 RON
80% used
```

Budget-ul poate fi săptămânal sau lunar și asociat unei categorii.

---

# 14. Savings Goals

Exemplu:

```text
Vacanță Japonia
7,500 / 15,000 RON
50%
Target: June 2027
```

Personal Finance Agent poate calcula cât trebuie economisit lunar pentru atingerea obiectivului.

---

# 15. Transaction Folders

Utilizatorul poate grupa tranzacții.

Exemplu:

```text
Greece Vacation

Hotel       1,200 RON
Fuel          450 RON
Restaurant    320 RON
Ferry         130 RON

Total:       2,100 RON
```

Relația dintre folders și transactions este many-to-many.

---

# 16. Split the Bill

Utilizatorul selectează o tranzacție și persoanele cu care vrea să o împartă.

Exemplu:

```text
Restaurant: 400 RON
4 persoane
100 RON / persoană
```

Fiecare participant primește un payment request.

Status participant:

- PENDING
- PAID
- DECLINED

Când plătește, se creează o tranzacție internă.

---

# 17. Credit Score

Scorul este calculat determinist, nu de LLM.

Poate lua în considerare date mock precum:

- venit
- economii
- account age
- existing debt
- credit utilization
- missed payments
- repayment history

Exemplu:

```text
Credit Score
742 / 850
VERY GOOD
```

Se păstrează și `credit_score_history` pentru afișarea evoluției.

AI-ul poate explica scorul, dar nu îl stabilește.

---

# 18. Credit Applications

Tipuri:

- PERSONAL_LOAN
- CREDIT_CARD

Flux:

```text
DRAFT
  |
PENDING
  |       |
APPROVED REJECTED
```

Adminul poate analiza și decide cererea.

---

# 19. Loans

Pentru fiecare credit se păstrează:

- principal
- annual interest rate
- term
- monthly payment
- outstanding principal
- start date
- maturity date
- next payment date

## Loan Installments

Pentru fiecare rată:

```text
Payment:    1,600 RON
Principal:  1,050 RON
Interest:     510 RON
Fees:          40 RON
```

## Loan Payments

Tipuri:

- REGULAR
- EARLY_REPAYMENT

---

# 20. Early Repayment

Credit Agent poate simula o rambursare anticipată fără să modifice datele.

Exemplu:

```text
Current:
42 months remaining
Future interest: 13,400 RON

After 10,000 RON early repayment:
33 months remaining
Future interest: 9,100 RON

Estimated saving: 4,300 RON
```

Se poate permite alegerea între:

- reducerea perioadei
- reducerea ratei

Execuția reală se face numai după confirmarea utilizatorului.

---

# 21. Credit Cards

Cardul și contul de credit trebuie separate conceptual.

`Card` reprezintă instrumentul de plată.

`CreditCardAccount` conține:

- credit limit
- used amount
- available credit
- interest rate
- statement balance
- minimum payment
- next due date

---

# 22. Fraud Engine

Fraud Engine-ul este determinist și separat de AI.

Exemple de reguli:

- high amount
- unusual country
- new device
- unusual hour
- abnormal spending pattern

Exemplu:

```text
Transaction: 12,000 RON

NEW_DEVICE        +25
HIGH_AMOUNT       +30
UNUSUAL_COUNTRY   +20
UNUSUAL_TIME       +9

Risk Score = 84
```

Dacă scorul depășește pragul:

```text
transaction.status = PENDING_REVIEW
```

Suma este pusă în `HOLD`.

---

# 23. Admin Fraud Review

Admin dashboard-ul are o coadă de tranzacții suspecte.

Exemplu:

```text
Transaction   User       Amount      Score
TX1029        Bogdan     12,000      84
TX1041        Andrei      5,800      74
TX1098        Alex        3,000      68
```

Adminul poate deschide cazul și vedea:

- tranzacția
- istoricul utilizatorului
- device-ul
- flags
- risk score
- analiza Fraud Investigation Agent

Acțiuni:

- APPROVE
- REJECT

Agentul nu ia singur decizia finală.

---

# 24. Statements

Utilizatorul poate selecta:

- perioadă
- wallet
- currency
- transaction type

și genera:

- PDF
- CSV

Statement-ul poate conține:

- opening balance
- transactions
- total incoming
- total outgoing
- closing balance

---

# 25. Business Transaction Export

Business user poate exporta tranzacțiile folosind filtre:

- date range
- wallet
- currency
- incoming/outgoing
- transaction status
- category

Format inițial:

- CSV

Opțional ulterior:

- XLSX

Exemplu coloane:

```text
date
transaction_id
type
counterparty
description
amount
currency
status
```

---

# 26. Notifications

Notification Center poate conține:

- transaction notifications
- fraud notifications
- payment reminders
- cashback
- credit
- split bill
- system notifications

Exemple:

```text
Transaction requires verification.
Payment due in 3 days.
You received 250 RON.
You earned 28 RON cashback.
Andrei requested 80 RON for Split Bill.
```

---

# 27. Admin Audit Log

Orice acțiune administrativă importantă trebuie logată.

Exemple:

```text
ADMIN_A approved TX10293
ADMIN_B froze CARD291
ADMIN_A rejected FRAUD_CASE_31
```

Se păstrează:

- admin
- action
- entity type
- entity id
- old data
- new data
- timestamp

---

# 28. Agentic AI Architecture

Arhitectura AI recomandată:

```text
                       USER
                         |
                         v
                 BANKING CHATBOT
                         |
                         v
                 ORCHESTRATOR AGENT
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
 Personal Finance     Credit Agent     Fraud Agent
      Agent
        |                |                |
        v                v                v
 Finance Tools       Credit Tools      Fraud Tools
        |                |                |
        +----------------+----------------+
                         |
                         v
                  BACKEND SERVICES
                         |
                         v
                     DATABASE
```

Agenții nu accesează direct baza de date.

Flux corect:

```text
Agent -> Tool -> Backend Service -> Database
```

Nu:

```text
Agent -> SQL -> Database
```

---

# 29. Orchestrator Agent

Orchestratorul este agentul principal din chatbot.

Responsabilități:

- identifică intenția
- alege agentul specializat
- poate împărți cererea în mai multe task-uri
- agregă rezultatele
- formulează răspunsul final

Exemplu:

```text
User:
"Cât am cheltuit luna asta și îmi permit o rată de 1,500 RON?"

Orchestrator
 |
 +-> Personal Finance Agent
 |
 +-> Credit Agent
 |
 +-> combine results
```

---

# 30. Personal Finance Agent

Nu este necesar un Savings Agent separat în MVP.

Personal Finance Agent se ocupă de:

- spending analysis
- expense recommendations
- saving recommendations
- budgets
- savings goals
- recurring payments/subscriptions
- cash-flow forecasting
- cashback recommendations

Tools:

```text
get_transactions()
get_spending_by_category()
get_monthly_income()
get_recurring_payments()
get_wallet_balances()
get_budgets()
get_savings_goals()
get_cashback_offers()
forecast_month_end_balance()
```

---

# 31. Credit Agent

Responsabilități:

- explicarea credit score-ului
- eligibility
- credit offers
- credit status
- remaining principal
- payment breakdown
- amortization schedule
- early repayment simulation

Tools:

```text
get_credit_score()
get_loan_details()
calculate_monthly_payment()
get_remaining_principal()
calculate_interest()
generate_amortization_schedule()
calculate_payment_breakdown()
simulate_early_repayment()
calculate_total_interest()
```

Matematica este făcută de tools, nu de LLM.

---

# 32. Fraud Investigation Agent

Agentul ajută administratorul să investigheze tranzacțiile suspecte.

Tools:

```text
get_transaction()
get_user_transaction_history()
get_known_devices()
get_recent_activity()
get_fraud_flags()
get_user_spending_profile()
```

Output exemplu:

```text
Risk assessment: HIGH

Reasons:
- transaction is 14x higher than user's average
- new device
- unusual geographical location
- unusual transaction time

Recommendation:
Manual verification recommended
```

Decizia finală aparține adminului.

---

# 33. Regula pentru operațiile AI

## Read operations

Agentul poate executa direct operații precum:

- get balance
- get transactions
- get credit details
- spending analysis
- cashback offers

## Write / financial operations

Agentul nu execută direct operația finală.

Exemplu:

```text
User:
"Trimite-i lui Andrei 100 RON"

Agent
-> create_transfer_draft()

UI
-> afișează suma + destinatarul

User
-> CONFIRM

Backend
-> execute_transfer()
```

Același principiu pentru:

- transfers
- FX
- early repayment
- scheduled payments
- card changes importante

---

# 34. Schema centrală a bazei de date

## Users

```text
users
------------------------------
id UUID PK
email VARCHAR UNIQUE
phone VARCHAR UNIQUE
password_hash VARCHAR
first_name VARCHAR
last_name VARCHAR
role ENUM(USER, ADMIN)
user_type ENUM(PERSONAL, BUSINESS)
status ENUM(ACTIVE, BLOCKED, SUSPENDED)
created_at TIMESTAMP
updated_at TIMESTAMP
last_login_at TIMESTAMP
```

## Business Profiles

```text
business_profiles
------------------------------
id UUID PK
user_id UUID FK -> users.id
company_name VARCHAR
tax_id VARCHAR
registration_number VARCHAR
business_category VARCHAR
created_at TIMESTAMP
```

## Wallets

```text
wallets
------------------------------
id UUID PK
user_id UUID FK -> users.id
currency CHAR(3)
available_balance DECIMAL(18,2)
reserved_balance DECIMAL(18,2)
is_main BOOLEAN
status ENUM(ACTIVE, FROZEN, CLOSED)
created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE(user_id, currency)
```

## FX Quotes

```text
fx_quotes
------------------------------
id UUID PK
user_id UUID FK
source_currency CHAR(3)
target_currency CHAR(3)
source_amount DECIMAL
target_amount DECIMAL
exchange_rate DECIMAL
fee DECIMAL
status ENUM(CREATED, ACCEPTED, EXPIRED)
expires_at TIMESTAMP
created_at TIMESTAMP
```

## Transactions

```text
transactions
------------------------------------
id UUID PK
initiator_user_id UUID FK
source_wallet_id UUID FK NULL
destination_wallet_id UUID FK NULL
counterparty_user_id UUID FK NULL
merchant_id UUID FK NULL
type ENUM
status ENUM
amount DECIMAL(18,2)
currency CHAR(3)
source_amount DECIMAL(18,2)
source_currency CHAR(3)
exchange_rate DECIMAL NULL
fx_quote_id UUID NULL
description VARCHAR
category_id UUID NULL
fraud_score DECIMAL NULL
created_at TIMESTAMP
processed_at TIMESTAMP NULL
completed_at TIMESTAMP NULL
```

## Wallet Ledger

```text
wallet_ledger_entries
------------------------------
id UUID PK
wallet_id UUID FK
transaction_id UUID FK
entry_type ENUM(DEBIT, CREDIT, HOLD, RELEASE)
amount DECIMAL
currency CHAR(3)
balance_after DECIMAL
created_at TIMESTAMP
```

## Cards

```text
cards
------------------------------
id UUID PK
user_id UUID FK
default_wallet_id UUID FK NULL
type ENUM(DEBIT, CREDIT, ONE_TIME)
status ENUM(ACTIVE, FROZEN, EXPIRED, CANCELLED)
masked_pan VARCHAR
last_four CHAR(4)
expiration_month INTEGER
expiration_year INTEGER
one_time_remaining INTEGER NULL
created_at TIMESTAMP
```

## Card Payment Preferences

```text
card_payment_preferences
------------------------------
card_id UUID PK/FK
preferred_wallet_id UUID FK
allow_main_wallet_fx BOOLEAN
updated_at TIMESTAMP
```

## Beneficiaries

```text
beneficiaries
------------------------------
id UUID PK
owner_user_id UUID FK
beneficiary_user_id UUID FK NULL
name VARCHAR
iban VARCHAR NULL
phone VARCHAR NULL
is_favorite BOOLEAN
created_at TIMESTAMP
```

## Payment Requests / QR

```text
payment_requests
------------------------------
id UUID PK
creator_user_id UUID FK
destination_wallet_id UUID FK
amount DECIMAL NULL
currency CHAR(3)
status ENUM(ACTIVE, PAID, CANCELLED, EXPIRED)
expires_at TIMESTAMP
created_at TIMESTAMP
```

## Scheduled Payments

```text
scheduled_payments
------------------------------
id UUID PK
user_id UUID FK
source_wallet_id UUID FK
beneficiary_id UUID FK
amount DECIMAL
currency CHAR(3)
frequency ENUM(ONCE, DAILY, WEEKLY, MONTHLY, YEARLY)
next_execution_at TIMESTAMP
notify_days_before INTEGER
status ENUM(ACTIVE, PAUSED, COMPLETED, CANCELLED)
created_at TIMESTAMP
```

## Merchants

```text
merchants
------------------------------
id UUID PK
name VARCHAR
logo_url VARCHAR NULL
category VARCHAR
status VARCHAR
```

## Cashback Offers

```text
cashback_offers
------------------------------
id UUID PK
merchant_id UUID FK
cashback_percent DECIMAL
maximum_cashback DECIMAL NULL
minimum_spend DECIMAL NULL
start_date DATE
end_date DATE
status ENUM(ACTIVE, EXPIRED)
```

## Reward Accounts

```text
reward_accounts
------------------------------
id UUID PK
user_id UUID UNIQUE
points_balance INTEGER
```

## Reward Transactions

```text
reward_transactions
------------------------------
id UUID PK
reward_account_id UUID FK
source_transaction_id UUID FK NULL
type ENUM(EARN, SPEND, ADJUSTMENT)
points INTEGER
created_at TIMESTAMP
```

## Transaction Categories

```text
transaction_categories
------------------------------
id UUID PK
name VARCHAR UNIQUE
```

## Transaction Folders

```text
transaction_folders
------------------------------
id UUID PK
user_id UUID FK
name VARCHAR
created_at TIMESTAMP
```

```text
transaction_folder_items
------------------------------
folder_id UUID FK
transaction_id UUID FK
PRIMARY KEY(folder_id, transaction_id)
```

## Bill Splits

```text
bill_splits
------------------------------
id UUID PK
creator_user_id UUID FK
source_transaction_id UUID FK
total_amount DECIMAL
currency CHAR(3)
status VARCHAR
created_at TIMESTAMP
```

```text
bill_split_participants
------------------------------
id UUID PK
bill_split_id UUID FK
user_id UUID FK
amount_due DECIMAL
amount_paid DECIMAL
status ENUM(PENDING, PAID, DECLINED)
```

## Budgets

```text
budgets
------------------------------
id UUID PK
user_id UUID FK
category_id UUID FK
period_type ENUM(MONTHLY, WEEKLY)
limit_amount DECIMAL
currency CHAR(3)
start_date DATE
end_date DATE
created_at TIMESTAMP
```

## Savings Goals

```text
savings_goals
------------------------------
id UUID PK
user_id UUID FK
name VARCHAR
target_amount DECIMAL
current_amount DECIMAL
currency CHAR(3)
target_date DATE NULL
status ENUM(ACTIVE, COMPLETED, CANCELLED)
created_at TIMESTAMP
```

## Credit Profiles

```text
credit_profiles
------------------------------
id UUID PK
user_id UUID UNIQUE
current_score INTEGER
income DECIMAL
existing_debt DECIMAL
updated_at TIMESTAMP
```

## Credit Score History

```text
credit_score_history
------------------------------
id UUID PK
credit_profile_id UUID FK
score INTEGER
reason_data JSONB
created_at TIMESTAMP
```

## Credit Applications

```text
credit_applications
------------------------------
id UUID PK
user_id UUID FK
type ENUM(PERSONAL_LOAN, CREDIT_CARD)
requested_amount DECIMAL
requested_term_months INTEGER NULL
offered_interest_rate DECIMAL NULL
offered_amount DECIMAL NULL
credit_score_at_application INTEGER
status ENUM(DRAFT, PENDING, APPROVED, REJECTED)
created_at TIMESTAMP
resolved_at TIMESTAMP NULL
```

## Loans

```text
loans
------------------------------
id UUID PK
user_id UUID FK
credit_application_id UUID FK
principal_amount DECIMAL
annual_interest_rate DECIMAL
term_months INTEGER
monthly_payment DECIMAL
outstanding_principal DECIMAL
start_date DATE
maturity_date DATE
next_payment_date DATE
status ENUM(ACTIVE, PAID, DEFAULTED, CLOSED)
created_at TIMESTAMP
```

## Loan Installments

```text
loan_installments
------------------------------
id UUID PK
loan_id UUID FK
installment_number INTEGER
due_date DATE
payment_amount DECIMAL
principal_amount DECIMAL
interest_amount DECIMAL
fees_amount DECIMAL
remaining_principal DECIMAL
status ENUM(PENDING, PAID, PARTIAL, OVERDUE)
```

## Loan Payments

```text
loan_payments
------------------------------
id UUID PK
loan_id UUID FK
transaction_id UUID FK
amount DECIMAL
principal_paid DECIMAL
interest_paid DECIMAL
fees_paid DECIMAL
payment_type ENUM(REGULAR, EARLY_REPAYMENT)
created_at TIMESTAMP
```

## Credit Card Accounts

```text
credit_card_accounts
------------------------------
id UUID PK
user_id UUID FK
card_id UUID FK
credit_limit DECIMAL
used_amount DECIMAL
available_credit DECIMAL
annual_interest_rate DECIMAL
statement_balance DECIMAL
minimum_payment DECIMAL
next_due_date DATE
status VARCHAR
```

## Fraud Cases

```text
fraud_cases
------------------------------
id UUID PK
transaction_id UUID UNIQUE
risk_score DECIMAL
status ENUM(OPEN, UNDER_REVIEW, APPROVED, REJECTED)
assigned_admin_id UUID FK NULL
agent_summary TEXT NULL
admin_notes TEXT NULL
created_at TIMESTAMP
resolved_at TIMESTAMP NULL
```

## Fraud Flags

```text
fraud_flags
------------------------------
id UUID PK
fraud_case_id UUID FK
code VARCHAR
severity ENUM(LOW, MEDIUM, HIGH)
description VARCHAR
metadata JSONB
```

## User Devices

```text
user_devices
------------------------------
id UUID PK
user_id UUID FK
device_name VARCHAR
device_type VARCHAR
browser VARCHAR
operating_system VARCHAR
mock_location VARCHAR
trusted BOOLEAN
first_seen_at TIMESTAMP
last_seen_at TIMESTAMP
```

## User Sessions

```text
user_sessions
------------------------------
id UUID PK
user_id UUID FK
device_id UUID FK NULL
token_hash VARCHAR
created_at TIMESTAMP
last_activity_at TIMESTAMP
expires_at TIMESTAMP
status ENUM(ACTIVE, EXPIRED, REVOKED)
```

## Biometric Verifications

```text
biometric_verifications
------------------------------
id UUID PK
user_id UUID FK
transaction_id UUID FK NULL
verification_type ENUM(FACE_ID, FINGERPRINT)
result ENUM(SUCCESS, FAILED)
is_mock BOOLEAN
created_at TIMESTAMP
```

## Notifications

```text
notifications
------------------------------
id UUID PK
user_id UUID FK
type VARCHAR
title VARCHAR
message TEXT
related_transaction_id UUID FK NULL
is_read BOOLEAN
created_at TIMESTAMP
```

## Exports

```text
exports
------------------------------
id UUID PK
user_id UUID FK
type ENUM(STATEMENT, BUSINESS_TRANSACTIONS)
format ENUM(PDF, CSV)
date_from DATE
date_to DATE
filters JSONB
status ENUM(PROCESSING, READY, FAILED)
file_path VARCHAR NULL
created_at TIMESTAMP
```

## Admin Audit Logs

```text
admin_audit_logs
------------------------------
id UUID PK
admin_user_id UUID FK
action VARCHAR
entity_type VARCHAR
entity_id UUID
old_data JSONB NULL
new_data JSONB NULL
created_at TIMESTAMP
```

---

# 35. Relațiile centrale

```text
USER 1 -------- N WALLET
USER 1 -------- N CARD
USER 1 -------- N TRANSACTION
USER 1 -------- N DEVICE
USER 1 -------- N SESSION
USER 1 -------- N LOAN
USER 1 -------- N BUDGET
USER 1 -------- N SAVINGS GOAL

WALLET 1 ------ N LEDGER ENTRY
TRANSACTION 1 -- N LEDGER ENTRY

TRANSACTION 0 -- 1 FRAUD CASE
FRAUD CASE 1 --- N FRAUD FLAG

MERCHANT 1 ----- N CASHBACK OFFER

LOAN 1 --------- N INSTALLMENT
LOAN 1 --------- N LOAN PAYMENT

TRANSACTION N --- N TRANSACTION FOLDER

BILL SPLIT 1 ---- N PARTICIPANT
```

---

# 36. Structura backend-ului

```text
backend/
|
|-- app/
|   |
|   |-- main.py
|   |-- config.py
|   |-- database.py
|   |
|   |-- auth/
|   |-- users/
|   |
|   |-- wallets/
|   |-- fx/
|   |
|   |-- transactions/
|   |-- payments/
|   |-- scheduled_payments/
|   |
|   |-- cards/
|   |
|   |-- merchants/
|   |-- rewards/
|   |
|   |-- analytics/
|   |-- budgets/
|   |-- savings/
|   |
|   |-- credit/
|   |-- fraud/
|   |
|   |-- statements/
|   |-- exports/
|   |
|   |-- notifications/
|   |-- audit/
|   |
|   `-- ai/
|       |-- orchestrator/
|       |-- personal_finance/
|       |-- credit_agent/
|       |-- fraud_agent/
|       `-- tools/
|
|-- migrations/
|-- tests/
`-- requirements.txt / pyproject.toml
```

Fiecare modul ar trebui să aibă conceptual:

```text
router
service
repository
models
schemas
```

Exemplu:

```text
wallets/
|-- router.py
|-- service.py
|-- repository.py
|-- models.py
`-- schemas.py
```

---

# 37. Structura frontend-ului

```text
frontend/
|
|-- src/
|   |
|   |-- api/
|   |-- components/
|   |-- hooks/
|   |-- layouts/
|   |-- pages/
|   |-- services/
|   |-- store/
|   |-- types/
|   |-- utils/
|   |
|   `-- features/
|       |-- auth/
|       |-- dashboard/
|       |-- wallets/
|       |-- payments/
|       |-- cards/
|       |-- rewards/
|       |-- analytics/
|       |-- credit/
|       |-- assistant/
|       |-- profile/
|       |-- business/
|       `-- admin/
```

---

# 38. User UI

Navigația principală poate fi:

```text
Dashboard
Wallets
Cards
Payments
Transactions
Analytics
Rewards
Credit
Assistant
Notifications
Profile
```

Business user primește suplimentar:

```text
Business
└── Transaction Export
```

---

# 39. Admin UI

```text
Admin Dashboard

Users
Transactions
Fraud Review
Credit Applications
Cards
Merchants
Cashback Offers
Audit Logs
```

Admin Dashboard poate afișa:

- total users
- transaction volume
- pending fraud cases
- pending credit applications
- active cards
- recent admin actions

---

# 40. Împărțirea pe 4 developeri

## Developer 1 — Core Banking

Responsabilități:

- users integration
- wallets
- balances
- transaction engine
- ledger
- FX
- statements
- PDF/CSV

## Developer 2 — Payments

Responsabilități:

- transfers
- phone transfers
- beneficiaries
- QR payments
- scheduled payments
- recurring payments
- split bill
- transaction folders
- business exports

## Developer 3 — Cards & Credit

Responsabilități:

- cards
- freeze/unfreeze
- one-time cards
- credit score
- credit applications
- loans
- installments
- loan calculator
- early repayment
- credit cards

## Developer 4 — Intelligence & Risk

Responsabilități:

- analytics
- budgets
- savings goals
- rewards
- merchant cashback
- fraud engine
- fraud admin UI
- AI orchestrator
- Personal Finance Agent
- Credit Agent
- Fraud Agent

---

# 41. Ce se poate dezvolta în paralel

După ce sunt definite modelele comune și API contracts:

```text
                   FOUNDATION
                       |
          +------------+------------+
          |            |            |
          v            v            v
      Core/FX       Payments    Cards/Credit
          |            |            |
          +------------+------------+
                       |
                  AI / Analytics
```

Developerul AI poate lucra în paralel cu date mock până când API-urile reale sunt gata.

---

# 42. Ordinea de dezvoltare

## Faza 1 — Foundation

- repository
- database
- User
- Auth
- Roles
- Wallet
- Transaction
- Ledger
- Session
- Device
- API conventions

Primul obiectiv end-to-end:

```text
Login
-> Dashboard
-> RON Wallet
-> Transfer 100 RON
-> Ledger entries
-> balances update
-> transaction history
```

## Faza 2 — Banking Engine

Dezvoltare paralelă:

- multi-currency wallets
- FX
- transfers
- cards
- transaction history

## Faza 3 — Advanced Banking

- QR
- split bill
- folders
- scheduled/recurring payments
- rewards
- merchant cashback
- statements
- business exports
- credit

## Faza 4 — Risk & Intelligence

- credit score
- fraud engine
- budgets
- savings goals
- analytics
- notifications
- admin workflows

## Faza 5 — Agentic AI

- tools
- Personal Finance Agent
- Credit Agent
- Fraud Investigation Agent
- Orchestrator
- chatbot integration

---

# 43. Database migrations recomandate

## Migration 1 — Banking Core

```text
users
wallets
transactions
wallet_ledger_entries
user_sessions
user_devices
```

## Migration 2 — Cards & Basic Payments

```text
cards
card_payment_preferences
beneficiaries
fx_quotes
transaction_categories
```

## Migration 3 — Advanced Payments

```text
scheduled_payments
payment_requests
bill_splits
bill_split_participants
transaction_folders
transaction_folder_items
```

## Migration 4 — Finance & Rewards

```text
merchants
cashback_offers
reward_accounts
reward_transactions
budgets
savings_goals
```

## Migration 5 — Credit, Fraud & Operations

```text
credit_profiles
credit_score_history
credit_applications
loans
loan_installments
loan_payments
credit_card_accounts
fraud_cases
fraud_flags
notifications
biometric_verifications
exports
admin_audit_logs
business_profiles
```

---

# 44. Principii arhitecturale

## 1. Business logic în services

Router-ele HTTP nu trebuie să conțină logica bancară.

```text
API Router
-> Service
-> Repository
-> Database
```

## 2. Agenții nu accesează direct DB

```text
AI Agent
-> Tool
-> Service
-> Repository
-> DB
```

## 3. Operațiile financiare importante sunt deterministe

LLM-ul nu calculează direct:

- solduri
- curs FX
- credit score
- dobândă
- rate
- fraud score
- cashback

Acestea sunt calculate de cod/tools.

## 4. AI explică și recomandă

LLM-ul poate:

- interpreta date
- explica
- recomanda
- căuta prin datele utilizatorului prin tools
- pregăti draft-uri de acțiuni

## 5. Human confirmation pentru write actions

Acțiunile financiare propuse de agent necesită confirmarea utilizatorului.

## 6. Admin confirmation pentru fraudă

Fraud Agent recomandă, dar adminul aprobă sau respinge.

## 7. Auditability

Operațiile importante trebuie să poată fi urmărite prin:

- transactions
- ledger entries
- fraud flags
- admin audit logs

---

# 45. Arhitectura completă high-level

```text
+----------------------------------------------------------+
|                         WEB APP                          |
|                                                          |
| Personal User       Business User          Admin         |
+----------------------------+-----------------------------+
                             |
                             v
+----------------------------------------------------------+
|                       BACKEND API                        |
|                                                          |
| Auth / Users                                             |
|                                                          |
| Wallets ------ FX                                        |
|    |                                                     |
| Transactions ---- Payments ---- Cards                    |
|    |                |                                    |
|    |                +-- QR                               |
|    |                +-- Scheduled                        |
|    |                +-- Recurring                        |
|    |                +-- Split Bill                       |
|    |                                                     |
|    +-- Rewards ---- Merchants ---- Cashback              |
|    |                                                     |
|    +-- Analytics ---- Budgets ---- Savings               |
|    |                                                     |
|    +-- Credit ---- Loans ---- Credit Cards               |
|    |                                                     |
|    +-- Fraud ---- Fraud Cases ---- Admin Review          |
|                                                          |
| Statements / Exports / Notifications / Audit             |
+----------------------------+-----------------------------+
                             |
             +---------------+---------------+
             |                               |
             v                               v
+--------------------------+      +--------------------------+
|        PostgreSQL        |      |         AI Layer         |
|                          |      |                          |
| Users                    |      | Orchestrator             |
| Wallets                  |      |      |                   |
| Transactions             |      |      +-- Finance Agent   |
| Ledger                   |<-----|      +-- Credit Agent    |
| Cards                    |tools |      +-- Fraud Agent     |
| Loans                    |      |                          |
| Fraud                    |      | Tools -> Backend APIs    |
| Rewards                  |      |                          |
| etc.                     |      +--------------------------+
+--------------------------+
```

---

# 46. MVP recomandat

Pentru primul demo funcțional:

1. Login
2. Dashboard
3. Multi-currency wallets
4. Main wallet
5. Transaction history
6. Transfer intern
7. Transfer după telefon
8. FX
9. Cards
10. Freeze/unfreeze
11. Spending analytics

După ce acestea sunt stabile:

12. QR Payments
13. Scheduled payments
14. Recurring payments
15. Split Bill
16. Transaction Folders
17. Rewards
18. Merchant Cashback
19. Credit Score
20. Loans
21. Statements PDF/CSV
22. Business Export
23. Fraud Engine
24. Admin Review
25. AI Agents

---

# 47. Obiectivul arhitecturii

Aplicația trebuie să aibă trei straturi conceptuale principale:

```text
BANKING CORE
     +
MODERN BANKING EXPERIENCE
     +
AGENTIC AI
```

**Banking Core** gestionează banii și regulile deterministe.

**Modern Banking Experience** oferă wallet-uri multi-currency, QR, split bill, cashback, analytics, budgets și savings.

**Agentic AI** folosește datele și serviciile existente pentru a explica, recomanda și orchestra acțiuni, fără să înlocuiască regulile financiare și controalele de securitate.

Această separare permite celor 4 developeri să lucreze în paralel și păstrează proiectul extensibil fără complexitatea unor microservicii premature.
