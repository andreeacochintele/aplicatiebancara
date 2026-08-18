# Diagrame arhitectură – Aplicație bancară web

Acest document conține diagramele principale ale arhitecturii aplicației bancare. Diagramele sunt scrise în **Mermaid** și pot fi randate în GitHub, GitLab, VS Code cu extensie Mermaid sau în alte editoare compatibile.

## 1. Arhitectura generală a aplicației

```mermaid
flowchart TB
    USER[User]
    ADMIN[Admin]

    subgraph FE["Frontend - React + TypeScript"]
        USER_UI[User Web Interface]
        ADMIN_UI[Admin Web Interface]
        CHAT[AI Chat / Assistant]
    end

    subgraph BE["Backend - FastAPI Modular Monolith"]
        AUTH[Auth & Security]
        USERS[Users]
        WALLETS[Wallets]
        FX[FX / Currency Exchange]
        TX[Transactions]
        PAY[Payments]
        CARDS[Cards]
        REWARDS[Rewards]
        MERCHANTS[Merchants & Cashback]
        FINANCE[Personal Finance]
        CREDIT[Credit & Loans]
        FRAUD[Fraud & Risk]
        EXPORTS[Statements & Exports]
        NOTIF[Notifications]
        AUDIT[Audit]
    end

    subgraph AI["Agentic AI Layer"]
        ORCH[Orchestrator Agent]
        PF_AGENT[Personal Finance Agent]
        CR_AGENT[Credit Agent]
        FR_AGENT[Fraud Investigation Agent]
        TOOLS[Agent Tools]
        LLM[Shared Azure AI Foundry Client\nGPT-5-mini]
    end

    DB[(PostgreSQL)]

    USER --> USER_UI
    USER --> CHAT
    ADMIN --> ADMIN_UI

    USER_UI --> BE
    ADMIN_UI --> BE
    CHAT --> ORCH

    ORCH --> PF_AGENT
    ORCH --> CR_AGENT
    ORCH --> FR_AGENT

    PF_AGENT --> TOOLS
    CR_AGENT --> TOOLS
    FR_AGENT --> TOOLS

    TOOLS --> FINANCE
    TOOLS --> CREDIT
    TOOLS --> FRAUD
    TOOLS --> WALLETS
    TOOLS --> TX
    TOOLS --> PAY

    ORCH --> LLM
    PF_AGENT --> LLM
    CR_AGENT --> LLM
    FR_AGENT --> LLM

    AUTH --> DB
    USERS --> DB
    WALLETS --> DB
    FX --> DB
    TX --> DB
    PAY --> DB
    CARDS --> DB
    REWARDS --> DB
    MERCHANTS --> DB
    FINANCE --> DB
    CREDIT --> DB
    FRAUD --> DB
    EXPORTS --> DB
    NOTIF --> DB
    AUDIT --> DB
```

## 2. Regula principală pentru agenții AI

```mermaid
flowchart LR
    U[User] --> A[AI Agent]
    A --> T[Tool]
    T --> S[Backend Service]
    S --> DB[(Database)]

    S --> DRAFT[Draft / Recommendation]
    DRAFT --> CONFIRM[User Confirmation]
    CONFIRM --> EXEC[Deterministic Banking Logic]
    EXEC --> DB
```

Regula de bază este `Agent -> Tool -> Backend Service -> Database`. Agenții nu accesează direct SQL-ul și nu execută direct tranzacții sensibile.

## 3. Domeniile principale

```mermaid
flowchart TB
    CORE[Banking Core]
    CORE --> ID[Identity & Security]
    CORE --> WAL[Wallets & FX]
    CORE --> TR[Transactions & Payments]
    CORE --> CA[Cards]
    CORE --> RE[Rewards & Cashback]
    CORE --> PF[Personal Finance]
    CORE --> CR[Credit & Loans]
    CORE --> FR[Fraud & Risk]
    CORE --> EX[Statements & Exports]
    CORE --> NO[Notifications & Audit]
    CORE --> AG[Agentic AI]

    PF --> ANA[Analytics]
    PF --> BUD[Budgets]
    PF --> SAV[Savings Goals]

    AG --> ORC[Orchestrator]
    AG --> PFA[Personal Finance Agent]
    AG --> CRA[Credit Agent]
    AG --> FRA[Fraud Investigation Agent]
```

## 4. Schema centrală simplificată a bazei de date

```mermaid
erDiagram
    USER ||--o{ WALLET : owns
    USER ||--o{ CARD : owns
    USER ||--o{ TRANSACTION : initiates
    USER ||--o{ USER_SESSION : has
    USER ||--o{ USER_DEVICE : uses
    USER ||--o| BUSINESS_PROFILE : may_have

    WALLET ||--o{ WALLET_LEDGER_ENTRY : contains
    TRANSACTION ||--o{ WALLET_LEDGER_ENTRY : produces
    WALLET ||--o{ TRANSACTION : source_or_destination

    TRANSACTION }o--o| MERCHANT : targets
    MERCHANT ||--o{ CASHBACK_OFFER : provides

    USER ||--o| REWARD_ACCOUNT : has
    REWARD_ACCOUNT ||--o{ REWARD_TRANSACTION : contains
    TRANSACTION ||--o{ REWARD_TRANSACTION : generates

    TRANSACTION ||--o| FRAUD_CASE : may_create
    FRAUD_CASE ||--o{ FRAUD_FLAG : contains

    USER ||--o{ BENEFICIARY : saves
    USER ||--o{ SCHEDULED_PAYMENT : creates
    USER ||--o{ PAYMENT_REQUEST : creates

    USER ||--o{ TRANSACTION_FOLDER : owns
    TRANSACTION_FOLDER ||--o{ TRANSACTION_FOLDER_ITEM : contains
    TRANSACTION ||--o{ TRANSACTION_FOLDER_ITEM : grouped_in

    USER ||--o{ BILL_SPLIT : creates
    BILL_SPLIT ||--o{ BILL_SPLIT_PARTICIPANT : contains

    USER ||--o{ BUDGET : defines
    USER ||--o{ SAVINGS_GOAL : defines

    USER ||--o| CREDIT_PROFILE : has
    CREDIT_PROFILE ||--o{ CREDIT_SCORE_HISTORY : history
    USER ||--o{ CREDIT_APPLICATION : submits
    USER ||--o{ LOAN : has

    LOAN ||--o{ LOAN_INSTALLMENT : contains
    LOAN ||--o{ LOAN_PAYMENT : receives

    USER ||--o{ NOTIFICATION : receives
    USER ||--o{ EXPORT : creates
    USER ||--o{ BIOMETRIC_VERIFICATION : performs
```

## 5. Wallet-uri multi-currency

```mermaid
flowchart TB
    USER[User]
    USER --> RON[RON Wallet\nMAIN]
    USER --> EUR[EUR Wallet]
    USER --> USD[USD Wallet]
    USER --> GBP[GBP Wallet]

    PAYMENT[Payment: 50 EUR] --> SELECT{Selected wallet?}
    SELECT -->|EUR| EUR
    SELECT -->|RON| FXQ[Request FX Quote]
    FXQ --> INFO[50 EUR = X RON\nShow exchange rate]
    INFO --> CONSENT{User accepts?}
    CONSENT -->|Yes| RON
    CONSENT -->|No| CANCEL[Cancel payment]
```

## 6. Lifecycle-ul unei tranzacții

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PROCESSING
    PROCESSING --> COMPLETED : normal transaction
    PROCESSING --> PENDING_REVIEW : suspicious transaction
    PROCESSING --> FAILED : processing error
    PENDING_REVIEW --> COMPLETED : admin approves
    PENDING_REVIEW --> REJECTED : admin rejects
    CREATED --> CANCELLED : user cancels
    PENDING_REVIEW --> CANCELLED : system/admin cancels
    COMPLETED --> [*]
    FAILED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
```

## 7. Flux antifraudă

```mermaid
flowchart TB
    START[User initiates transaction] --> ENGINE[Deterministic Fraud Engine]
    ENGINE --> SCORE{Risk score}
    SCORE -->|Low| NORMAL[Continue transaction]
    NORMAL --> COMPLETE[COMPLETED]

    SCORE -->|High| HOLD[Create HOLD on wallet]
    HOLD --> PENDING[Transaction = PENDING_REVIEW]
    PENDING --> CASE[Create Fraud Case]
    CASE --> ADMIN[Admin Fraud Queue]
    ADMIN --> AGENT[Fraud Investigation Agent]

    AGENT --> DATA[Fraud Tools]
    DATA --> HISTORY[Transaction history]
    DATA --> DEVICE[Known devices]
    DATA --> FLAGS[Fraud flags]
    DATA --> PROFILE[User behaviour]

    AGENT --> RECOMMEND[Risk explanation + recommendation]
    RECOMMEND --> DECISION{Admin decision}
    DECISION -->|Approve| DEBIT[Convert HOLD to DEBIT]
    DEBIT --> COMPLETE
    DECISION -->|Reject| RELEASE[RELEASE reserved funds]
    RELEASE --> REJECTED[REJECTED]
```

## 8. Card payment architecture

```mermaid
flowchart TB
    CARD[Card] --> PREF[Card Payment Preferences]
    PREF --> PW[Preferred Wallet]
    PREF --> FX[Allow Main Wallet FX]

    PAYMENT[Merchant payment] --> CARD
    CARD --> CHECK{Card status}
    CHECK -->|FROZEN| FAIL[Reject]
    CHECK -->|ACTIVE| WALLET{Wallet currency matches?}
    WALLET -->|Yes| PAY[Execute payment]
    WALLET -->|No| ALLOW{FX allowed?}
    ALLOW -->|No| REQUEST[Ask user to select wallet]
    ALLOW -->|Yes| QUOTE[Create FX quote]
    QUOTE --> CONFIRM[User confirmation]
    CONFIRM --> PAY
```

## 9. Transfer după numărul de telefon

```mermaid
sequenceDiagram
    actor S as Sender
    participant UI as Web App
    participant U as User Service
    participant P as Payment Service
    participant DB as PostgreSQL

    S->>UI: Send 100 RON to phone number
    UI->>U: Find user by phone
    U->>DB: Find user
    DB-->>U: Recipient
    U-->>UI: Recipient preview
    S->>UI: Confirm transfer
    UI->>P: Execute internal transfer
    P->>DB: Sender DEBIT
    P->>DB: Recipient CREDIT
    P-->>UI: COMPLETED
```

## 10. QR Payments

```mermaid
flowchart LR
    A[User A] --> CREATE[Create Payment Request]
    CREATE --> DB[(payment_requests)]
    DB --> QR[Generate QR with request ID]
    QR --> B[User B scans]
    B --> API[Load payment request]
    API --> DETAILS[Show amount + recipient]
    DETAILS --> CONFIRM[User B confirms]
    CONFIRM --> PAYMENT[Payment Service]
    PAYMENT --> TX[Transaction]
```

## 11. Scheduled și recurring payments

```mermaid
flowchart TB
    USER[User] --> CREATE[Create Scheduled Payment]
    CREATE --> TYPE{Frequency}
    TYPE --> ONCE[Once]
    TYPE --> WEEKLY[Weekly]
    TYPE --> MONTHLY[Monthly]
    TYPE --> YEARLY[Yearly]
    ONCE --> SCHED[(scheduled_payments)]
    WEEKLY --> SCHED
    MONTHLY --> SCHED
    YEARLY --> SCHED
    SCHED --> REMINDER[Notification X days before]
    SCHED --> EXEC[Scheduler executes]
    EXEC --> PAYMENT[Payment Service]
    PAYMENT --> TX[Transaction]
    TX --> NEXT{Recurring?}
    NEXT -->|Yes| UPDATE[Calculate next_execution_at]
    NEXT -->|No| DONE[COMPLETED]
```

## 12. Rewards și merchant cashback

```mermaid
flowchart TB
    TX[Completed Card Transaction] --> MERCHANT[Identify Merchant]
    MERCHANT --> OFFER{Active cashback offer?}
    OFFER -->|No| BANK_REWARD[Calculate bank reward points]
    OFFER -->|Yes| CASHBACK[Calculate merchant cashback]
    CASHBACK --> CASH_TX[Create CASHBACK transaction]
    CASH_TX --> WALLET[Credit user's wallet]
    TX --> BANK_REWARD
    BANK_REWARD --> REWARD_TX[Reward transaction]
    REWARD_TX --> ACCOUNT[Reward account]
```

## 13. Personal Finance Agent

```mermaid
flowchart TB
    AGENT[Personal Finance Agent]
    AGENT --> T1[get_transactions]
    AGENT --> T2[get_spending_by_category]
    AGENT --> T3[get_monthly_income]
    AGENT --> T4[get_recurring_payments]
    AGENT --> T5[get_wallet_balances]
    AGENT --> T6[get_budgets]
    AGENT --> T7[get_savings_goals]
    AGENT --> T8[get_cashback_offers]
    AGENT --> T9[forecast_month_end_balance]

    T1 --> SERVICES[Backend Services]
    T2 --> SERVICES
    T3 --> SERVICES
    T4 --> SERVICES
    T5 --> SERVICES
    T6 --> SERVICES
    T7 --> SERVICES
    T8 --> SERVICES
    T9 --> SERVICES
    SERVICES --> DB[(PostgreSQL)]

    AGENT --> OUTPUT[Analysis + Recommendations]
    OUTPUT --> SPEND[Spending recommendations]
    OUTPUT --> SAVE[Savings recommendations]
    OUTPUT --> BUDGET[Budget recommendations]
    OUTPUT --> OFFER[Cashback opportunities]
```

## 14. Credit architecture

```mermaid
flowchart TB
    USER[User] --> PROFILE[Credit Profile]
    PROFILE --> SCORE[Credit Score]
    USER --> APP[Credit Application]
    SCORE --> DECISION[Credit Decision Engine]
    APP --> DECISION
    DECISION -->|Approved| LOAN[Loan]
    DECISION -->|Credit Card| CCA[Credit Card Account]
    LOAN --> INSTALLMENTS[Loan Installments]
    LOAN --> PAYMENTS[Loan Payments]

    CREDIT_AGENT[Credit Agent] --> PROFILE
    CREDIT_AGENT --> LOAN
    CREDIT_AGENT --> CALC[Loan Calculator Tools]
    CALC --> PAYMENT_CALC[Monthly Payment]
    CALC --> REMAINING[Remaining Principal]
    CALC --> BREAKDOWN[Principal / Interest]
    CALC --> EARLY[Early Repayment Simulation]
    CALC --> SCHEDULE[Amortization Schedule]
    CREDIT_AGENT --> EXPLAIN[Explanation / Recommendation]
```

## 15. Plată anticipată credit

```mermaid
flowchart TB
    USER[User asks for early repayment] --> AGENT[Credit Agent]
    AGENT --> TOOL[simulate_early_repayment]
    TOOL --> CURRENT[Current loan schedule]
    TOOL --> SIM[Simulation]
    SIM --> OPTION1[Reduce loan period]
    SIM --> OPTION2[Reduce monthly payment]
    OPTION1 --> RESULT[Show interest saved + new schedule]
    OPTION2 --> RESULT
    RESULT --> CONFIRM{User confirms?}
    CONFIRM -->|No| END[No changes]
    CONFIRM -->|Yes| SERVICE[Loan Service]
    SERVICE --> PAYMENT[Create EARLY_REPAYMENT]
    PAYMENT --> RECALC[Recalculate installments]
```

## 16. Orchestrator Agent

```mermaid
flowchart TB
    USER[User message] --> ORCH[Orchestrator Agent]
    ORCH --> INTENT{Determine task}
    INTENT -->|Spending / Savings| PF[Personal Finance Agent]
    INTENT -->|Loan / Credit| CR[Credit Agent]
    INTENT -->|Fraud question| FR[Fraud Investigation Agent]
    INTENT -->|Banking info| BT[Banking Tools]

    PF --> RESULT1[Finance Result]
    CR --> RESULT2[Credit Result]
    FR --> RESULT3[Fraud Result]
    BT --> RESULT4[Banking Result]

    RESULT1 --> ORCH
    RESULT2 --> ORCH
    RESULT3 --> ORCH
    RESULT4 --> ORCH
    ORCH --> RESPONSE[Final combined response]
```

## 17. Azure AI Foundry

```mermaid
flowchart TB
    ORCH[Orchestrator Agent] --> CLIENT[Shared LLM Client]
    PF[Personal Finance Agent] --> CLIENT
    CR[Credit Agent] --> CLIENT
    FR[Fraud Investigation Agent] --> CLIENT
    CLIENT --> AZURE[Azure AI Foundry\nGPT-5-mini]
```

Singurul LLM disponibil este GPT-5-mini din Azure AI Foundry. Configurația trebuie ținută în environment variables, iar aplicația trebuie să poată porni și fără credentialele Azure în fazele fără AI.

## 18. Statements și business exports

```mermaid
flowchart TB
    USER[User / Business] --> FILTER[Select Filters]
    FILTER --> PERIOD[Date Range]
    FILTER --> CURRENCY[Currency]
    FILTER --> STATUS[Transaction Status]
    FILTER --> DIRECTION[Incoming / Outgoing]
    PERIOD --> EXPORT[Export Service]
    CURRENCY --> EXPORT
    STATUS --> EXPORT
    DIRECTION --> EXPORT
    EXPORT --> DB[(Transactions)]
    DB --> FORMAT{Format}
    FORMAT --> PDF[PDF Statement]
    FORMAT --> CSV[CSV Export]
    CSV --> BUSINESS[Business Accounting / Reconciliation]
```

## 19. Split the Bill

```mermaid
flowchart TB
    TX[Restaurant transaction\n400 RON] --> SPLIT[Create Bill Split]
    SPLIT --> U1[User A - 100 RON]
    SPLIT --> U2[User B - 100 RON]
    SPLIT --> U3[User C - 100 RON]
    SPLIT --> U4[User D - 100 RON]
    U2 --> REQ2[Payment request]
    U3 --> REQ3[Payment request]
    U4 --> REQ4[Payment request]
    REQ2 --> PAY[Internal Payment Service]
    REQ3 --> PAY
    REQ4 --> PAY
    PAY --> CREATOR[Credit creator wallet]
```

## 20. Transaction folders

```mermaid
flowchart TB
    USER[User] --> FOLDER[Folder: Greece Vacation]
    FOLDER --> T1[Hotel - 1,200 RON]
    FOLDER --> T2[Fuel - 450 RON]
    FOLDER --> T3[Restaurant - 320 RON]
    FOLDER --> T4[Ferry - 130 RON]
    FOLDER --> TOTAL[Total calculated from transactions]
```

## 21. Backend modular monolith

```mermaid
flowchart TB
    API[FastAPI /api/v1]
    API --> AUTH[auth]
    API --> USERS[users]
    API --> WALLETS[wallets]
    API --> TX[transactions]
    API --> FX[fx]
    API --> PAY[payments]
    API --> CARDS[cards]
    API --> REWARDS[rewards]
    API --> MERCHANTS[merchants]
    API --> PF[personal_finance]
    API --> CREDIT[credit]
    API --> FRAUD[fraud]
    API --> NOTIF[notifications]
    API --> EXPORTS[exports]

    AUTH --> SERVICES[Service Layer]
    USERS --> SERVICES
    WALLETS --> SERVICES
    TX --> SERVICES
    FX --> SERVICES
    PAY --> SERVICES
    CARDS --> SERVICES
    REWARDS --> SERVICES
    MERCHANTS --> SERVICES
    PF --> SERVICES
    CREDIT --> SERVICES
    FRAUD --> SERVICES
    NOTIF --> SERVICES
    EXPORTS --> SERVICES

    SERVICES --> ORM[SQLAlchemy]
    ORM --> DB[(PostgreSQL)]
    MIG[Alembic Migrations] --> DB
```

## 22. Structura repository-ului

```text
banking-app/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── features/
│   │   ├── api/
│   │   ├── hooks/
│   │   └── types/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── security.py
│   │   ├── modules/
│   │   │   ├── auth/
│   │   │   ├── users/
│   │   │   ├── wallets/
│   │   │   ├── transactions/
│   │   │   ├── fx/
│   │   │   ├── payments/
│   │   │   ├── cards/
│   │   │   ├── rewards/
│   │   │   ├── merchants/
│   │   │   ├── personal_finance/
│   │   │   ├── credit/
│   │   │   ├── fraud/
│   │   │   ├── notifications/
│   │   │   └── exports/
│   │   └── ai/
│   │       ├── client/
│   │       ├── orchestrator/
│   │       ├── personal_finance/
│   │       ├── credit/
│   │       ├── fraud/
│   │       └── tools/
│   ├── migrations/
│   └── tests/
├── docs/
│   ├── architecture.md
│   └── architecture_diagrams.md
├── docker-compose.yml
├── .env.example
└── README.md
```

## 23. Împărțirea pe cei 4 developeri

```mermaid
flowchart TB
    FOUNDATION[Shared Foundation\nAuth + Users + DB + Wallet + Transaction]
    FOUNDATION --> D1[Developer 1\nCore Banking]
    FOUNDATION --> D2[Developer 2\nPayments]
    FOUNDATION --> D3[Developer 3\nCards & Credit]
    FOUNDATION --> D4[Developer 4\nIntelligence]

    D1 --> F1[Wallets]
    D1 --> F2[FX]
    D1 --> F3[Ledger]
    D1 --> F4[Statements]

    D2 --> P1[Transfers]
    D2 --> P2[QR]
    D2 --> P3[Recurring Payments]
    D2 --> P4[Split Bill]
    D2 --> P5[Business Export]

    D3 --> C1[Cards]
    D3 --> C2[Freeze / One-time]
    D3 --> C3[Credit Score]
    D3 --> C4[Loans]
    D3 --> C5[Loan Calculator]

    D4 --> I1[Analytics]
    D4 --> I2[Rewards / Cashback]
    D4 --> I3[Budgets / Savings]
    D4 --> I4[Fraud]
    D4 --> I5[AI Agents]
```

## 24. Ordinea recomandată de dezvoltare

```mermaid
flowchart LR
    P1[Phase 1\nFoundation] --> P2[Phase 2\nBanking Engine]
    P2 --> P3[Phase 3\nAdvanced Banking]
    P3 --> P4[Phase 4\nRisk & Intelligence]
    P4 --> P5[Phase 5\nAgentic AI]
```

### Phase 1
- Auth
- Users
- PostgreSQL
- Wallet
- Transaction
- Ledger

### Phase 2
- FX
- Transfers
- Cards

### Phase 3
- QR
- Split Bill
- Rewards
- Cashback
- Scheduled/Recurring Payments
- Credit
- PDF/CSV Exports

### Phase 4
- Fraud Engine
- Analytics
- Budgets
- Savings Goals

### Phase 5
- Orchestrator Agent
- Personal Finance Agent
- Credit Agent
- Fraud Investigation Agent

## 25. MVP

```mermaid
flowchart LR
    LOGIN[Login] --> DASH[Dashboard]
    DASH --> WALLET[Wallets]
    WALLET --> TX[Transactions]
    TX --> TRANSFER[Transfer]
    WALLET --> FX[Exchange]
    DASH --> CARDS[Cards]
    CARDS --> FREEZE[Freeze / Unfreeze]
    DASH --> ANALYTICS[Basic Analytics]
```

## Principii arhitecturale

1. Aplicația este un **modular monolith**, nu microservicii.
2. `User`, `Wallet`, `Transaction` și `WalletLedgerEntry` formează nucleul.
3. Mișcările financiare importante sunt reprezentate prin tranzacții și ledger entries.
4. Agenții AI nu modifică direct baza de date.
5. Agenții AI folosesc tools care apelează serviciile backend.
6. Operațiile financiare sensibile necesită confirmarea utilizatorului.
7. Fraud Engine-ul este determinist; Fraud Investigation Agent explică și asistă adminul.
8. Calculele de credit sunt deterministe și realizate de Loan Calculator Tools.
9. GPT-5-mini din Azure AI Foundry este singurul LLM disponibil.
10. Aplicația trebuie să poată rula local fără Azure AI configurat.
11. Cardurile, biometria, comercianții și integrarea bancară sunt mock/sandbox pentru proiect.
12. PostgreSQL este baza de date centrală.
13. SQLAlchemy este ORM-ul backend.
14. Alembic gestionează migrations.
15. Frontend-ul comunică cu backend-ul prin REST API sub `/api/v1`.
