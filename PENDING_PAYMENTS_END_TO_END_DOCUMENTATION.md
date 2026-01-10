# PENDING PAYMENTS SYSTEM - END-TO-END DOCUMENTATION

**Version:** 2.0  
**Status:** Complete Implementation Guide  
**System Type:** Masked Share Settlement System  
**Last Updated:** January 2026

---

## TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Core Concepts](#2-core-concepts)
3. [Master Formulas](#3-master-formulas)
4. [Data Flow - End to End](#4-data-flow---end-to-end)
5. [Share Calculation Logic](#5-share-calculation-logic)
6. [Share Locking Mechanism](#6-share-locking-mechanism)
7. [Remaining Amount Calculation](#7-remaining-amount-calculation)
8. [Settlement Process](#8-settlement-process)
9. [Masked Capital Calculation](#9-masked-capital-calculation)
10. [Transaction Sign Logic](#10-transaction-sign-logic)
11. [Display Logic](#11-display-logic)
12. [Cycle Management](#12-cycle-management)
13. [Edge Cases and Validations](#13-edge-cases-and-validations)
14. [Complete Examples](#14-complete-examples)
15. [Code Implementation](#15-code-implementation)
16. [Database Schema](#16-database-schema)

---

## 1. SYSTEM OVERVIEW

### 1.1 Purpose

The Pending Payments System manages settlements between admin and clients using a **Masked Share Settlement Model**. This system ensures:

- **Fair Settlement**: Only share amounts are settled, not full capital
- **Dynamic Exposure Reduction**: Settlements reduce trading exposure proportionally
- **Share Locking**: Share is locked at first compute and never shrinks
- **Cycle Separation**: Settlements are tracked per PnL cycle
- **Always Visible**: All clients appear in pending list (even with N.A when not applicable)

### 1.2 Key Principles

1. **Share is decided by trading outcome, not by settlement**
2. **Share NEVER shrinks after payments** (locked at first compute)
3. **Clients MUST always appear in pending list** (for visibility)
4. **Settlements reduce exposure using masked capital**
5. **Sign convention: Always from YOUR point of view**
6. **Transaction sign depends ONLY on Client_PnL at payment time**

### 1.3 System Architecture

```
User Interface (Pending Summary Page)
    ↓
View Function (pending_summary)
    ↓
Model Methods (compute_client_pnl, compute_my_share, get_remaining_settlement_amount)
    ↓
Database (ClientExchangeAccount, Settlement, Transaction)
```

---

## 2. CORE CONCEPTS

### 2.1 Account Fields

| Field | Type | Description |
|-------|------|-------------|
| `funding` | Decimal | Capital given to client |
| `exchange_balance` | Decimal | Current balance on exchange |
| `my_percentage` | Integer | Default share percentage (0-100) |
| `loss_share_percentage` | Integer | Share % for losses (0-100, optional) |
| `profit_share_percentage` | Integer | Share % for profits (0-100, optional) |
| `locked_initial_final_share` | Integer | Locked share amount (immutable) |
| `locked_share_percentage` | Integer | Locked share percentage |
| `locked_initial_pnl` | Decimal | Locked PnL when share was computed |
| `locked_initial_funding` | Decimal | Funding when cycle started |
| `cycle_start_date` | DateTime | When current PnL cycle started |

### 2.2 Settlement Model

| Field | Type | Description |
|-------|------|-------------|
| `client_exchange` | ForeignKey | Account this settlement belongs to |
| `amount` | Integer | Share payment amount (always positive) |
| `date` | DateTime | When settlement occurred |
| `notes` | Text | Optional notes |

### 2.3 Transaction Model (RECORD_PAYMENT)

| Field | Type | Description |
|-------|------|-------------|
| `client_exchange` | ForeignKey | Account this transaction belongs to |
| `type` | String | Always 'RECORD_PAYMENT' |
| `amount` | Decimal | **Signed amount**: +X = client paid you, -X = you paid client |
| `date` | DateTime | When payment was recorded |
| `exchange_balance_after` | Decimal | Exchange balance after this payment |
| `notes` | Text | Optional notes |

---

## 3. MASTER FORMULAS

### 3.1 Formula 1: Client Profit/Loss (FOUNDATION)

**Formula:**
```
Client_PnL = ExchangeBalance − Funding
```

**Where:**
- `ExchangeBalance`: Current balance on exchange
- `Funding`: Capital given to client

**Interpretation:**
- `Client_PnL > 0`: Client is in profit (you owe client)
- `Client_PnL < 0`: Client is in loss (client owes you)
- `Client_PnL = 0`: Trading flat (no settlement needed)

**Example:**
```
ExchangeBalance = 12,000
Funding = 10,000
Client_PnL = 12,000 - 10,000 = 2,000 (profit)
```

---

### 3.2 Formula 2: Share Calculation

**Formula:**
```
FinalShare = floor(|Client_PnL| × SharePercentage / 100)
```

**Where:**
- `SharePercentage`: 
  - If `Client_PnL < 0`: Use `loss_share_percentage` (if > 0) else `my_percentage`
  - If `Client_PnL > 0`: Use `profit_share_percentage` (if > 0) else `my_percentage`
- `floor()`: Round down to nearest integer

**Critical Rules:**
1. Share is calculated from **absolute value** of PnL
2. Share uses **floor()** rounding (always rounds down)
3. Share percentage depends on PnL direction (loss vs profit)

**Example:**
```
Client_PnL = -1,000 (loss)
LossSharePercentage = 10%
FinalShare = floor(|-1,000| × 10 / 100) = floor(100) = 100
```

**Example 2:**
```
Client_PnL = 1,500 (profit)
ProfitSharePercentage = 8%
FinalShare = floor(|1,500| × 8 / 100) = floor(120) = 120
```

---

### 3.3 Formula 3: Remaining Amount Calculation

**Step 1: Core Remaining (ALWAYS POSITIVE)**
```
CoreRemaining = LockedInitialFinalShare − TotalSettled
```

**Step 2: Display Sign (BASED ON PnL)**
```
IF Client_PnL > 0:
    DisplayRemaining = -CoreRemaining  (you owe client)
ELSE:
    DisplayRemaining = +CoreRemaining  (client owes you)
```

**Where:**
- `LockedInitialFinalShare`: Share locked at first compute (never changes)
- `TotalSettled`: Sum of settlements from current cycle only

**Critical Rules:**
1. **Always use locked share** - Never recalculate from current PnL
2. **Only count current cycle settlements** - Filter by `cycle_start_date`
3. **Remaining can be 0** - When fully settled
4. **Overpaid can be > 0** - When settlements exceed locked share

**Example:**
```
LockedInitialFinalShare = 100
TotalSettled = 60
CoreRemaining = 100 - 60 = 40

IF Client_PnL = -500 (loss):
    DisplayRemaining = +40 (client owes you 40)
ELSE IF Client_PnL = +500 (profit):
    DisplayRemaining = -40 (you owe client 40)
```

---

### 3.4 Formula 4: Masked Capital Calculation

**Formula:**
```
MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
```

**Why This Formula:**
- Maps SharePayment back to PnL **linearly** (not exponentially)
- Prevents double-counting of share percentage
- Ensures settlements reduce exposure proportionally

**Example:**
```
LockedInitialPnL = -1,000 (loss)
LockedInitialFinalShare = 100 (10% share)
SharePayment = 50

MaskedCapital = (50 × 1,000) / 100 = 500
```

**Interpretation:**
- Paying 50 in share units reduces funding by 500 (the masked capital)
- Ratio: 1,000 / 100 = 10 (each share unit = 10 capital units)

---

### 3.5 Formula 5: Settlement Impact on Balances

#### LOSS CASE (Client_PnL < 0)

**Formula:**
```
NewFunding = OldFunding − MaskedCapital
ExchangeBalance = ExchangeBalance (unchanged)
```

**Validation:**
```
IF NewFunding < 0:
    BLOCK SETTLEMENT (cannot have negative funding)
```

**Example:**
```
OldFunding = 10,000
MaskedCapital = 500
NewFunding = 10,000 - 500 = 9,500 ✓
```

#### PROFIT CASE (Client_PnL > 0)

**Formula:**
```
NewExchangeBalance = OldExchangeBalance − MaskedCapital
Funding = Funding (unchanged)
```

**Validation:**
```
IF NewExchangeBalance < 0:
    BLOCK SETTLEMENT (cannot have negative exchange balance)
```

**Example:**
```
OldExchangeBalance = 12,000
MaskedCapital = 600
NewExchangeBalance = 12,000 - 600 = 11,400 ✓
```

---

### 3.6 Formula 6: Transaction Sign Logic (CORRECTNESS LOGIC)

**CORRECT RULE: Sign depends ONLY on Client_PnL at payment time**

**Formula:**
```
IF Client_PnL > 0 (client in profit):
    Transaction.amount = -SharePayment   # you paid client
ELSE IF Client_PnL < 0 (client in loss):
    Transaction.amount = +SharePayment   # client paid you
```

**Critical Rules:**
- ✅ No PnL checks needed in reports (sign is absolute truth)
- ✅ No locked_initial_pnl checks needed
- ✅ No fallback logic needed
- ✅ The sign itself is the truth

**Example:**
```
SharePayment = 50
Client_PnL = -1,000 (loss)

Transaction.amount = +50 (client paid you) ✓
```

**Example 2:**
```
SharePayment = 50
Client_PnL = +1,500 (profit)

Transaction.amount = -50 (you paid client) ✓
```

---

## 4. DATA FLOW - END TO END

### 4.1 User Request Flow

```
User navigates to Pending Summary Page
    ↓
URL: /pending/
    ↓
Django routes to: pending_summary(request)
    ↓
View function processes request
    ↓
For each client-exchange account:
    ├─ Calculate Client_PnL
    ├─ Calculate FinalShare
    ├─ Lock share if needed
    ├─ Calculate Remaining Amount
    └─ Determine display status
    ↓
Context dictionary prepared
    ↓
Template renders HTML
    ↓
User sees pending payments list
```

### 4.2 Settlement Recording Flow

```
User clicks "Record Payment" button
    ↓
URL: /exchanges/account/{id}/record-payment/
    ↓
Django routes to: record_payment(request, account_id)
    ↓
GET Request:
    ├─ Load account (no locking)
    ├─ Calculate Client_PnL
    ├─ Lock share if needed
    ├─ Calculate Remaining Amount
    └─ Display form
    ↓
POST Request:
    ├─ Lock account row (select_for_update)
    ├─ Validate payment amount
    ├─ Calculate MaskedCapital
    ├─ Validate balances won't go negative
    ├─ Update account balances
    ├─ Create Settlement record
    ├─ Create Transaction record (with correct sign)
    └─ Redirect to success page
```

### 4.3 Share Locking Flow

```
When compute_my_share() is called:
    ↓
Check if share should be locked:
    ├─ No locked share exists? → Lock it
    ├─ PnL sign flipped? → Lock new share (new cycle)
    ├─ Funding changed? → Reset locks (new cycle)
    └─ PnL magnitude reduced significantly? → Reset locks (new cycle)
    ↓
Lock share:
    ├─ Set locked_initial_final_share
    ├─ Set locked_share_percentage
    ├─ Set locked_initial_pnl
    ├─ Set cycle_start_date
    └─ Set locked_initial_funding
```

---

## 5. SHARE CALCULATION LOGIC

### 5.1 Share Percentage Selection

**Logic:**
```
IF Client_PnL < 0 (loss):
    IF loss_share_percentage > 0:
        SharePercentage = loss_share_percentage
    ELSE:
        SharePercentage = my_percentage
ELSE IF Client_PnL > 0 (profit):
    IF profit_share_percentage > 0:
        SharePercentage = profit_share_percentage
    ELSE:
        SharePercentage = my_percentage
ELSE:
    SharePercentage = my_percentage (default)
```

**Example:**
```
Client_PnL = -1,000 (loss)
loss_share_percentage = 10%
my_percentage = 5%

SharePercentage = 10% (uses loss_share_percentage)
```

**Example 2:**
```
Client_PnL = -1,000 (loss)
loss_share_percentage = 0 (not set)
my_percentage = 5%

SharePercentage = 5% (falls back to my_percentage)
```

### 5.2 Share Calculation with Floor Rounding

**Formula:**
```
FinalShare = floor(|Client_PnL| × SharePercentage / 100)
```

**Why Floor:**
- Ensures share never exceeds actual share percentage
- Prevents over-settlement
- Conservative approach

**Example:**
```
Client_PnL = -1,234 (loss)
SharePercentage = 10%

FinalShare = floor(|-1,234| × 10 / 100)
          = floor(123.4)
          = 123
```

**Example 2:**
```
Client_PnL = 987 (profit)
SharePercentage = 8%

FinalShare = floor(|987| × 8 / 100)
          = floor(78.96)
          = 78
```

---

## 6. SHARE LOCKING MECHANISM

### 6.1 When Share is Locked

**Share is locked when:**
1. **First compute**: When `compute_my_share()` is called and no locked share exists
2. **PnL sign flip**: When PnL changes from positive to negative (or vice versa)
3. **New cycle starts**: When funding changes or PnL magnitude reduces significantly

### 6.2 Locking Logic

**Code Flow:**
```python
def lock_initial_share_if_needed(self):
    client_pnl = self.compute_client_pnl()
    
    # Check if PnL magnitude reduced significantly (trading reduced exposure)
    if self.locked_initial_pnl is not None and client_pnl != 0:
        if abs(client_pnl) < abs(self.locked_initial_pnl) * 0.5:
            # PnL reduced by more than 50% → reset locks (new cycle)
            self.reset_locks()
    
    # Check if funding changed (new exposure)
    if self.locked_initial_funding is not None:
        if self.funding != self.locked_initial_funding:
            # Funding changed → reset locks (new cycle)
            self.reset_locks()
    
    # Lock share if needed
    if self.locked_initial_final_share is None:
        final_share = self.compute_my_share()
        if final_share > 0:
            # Lock the share
            self.locked_initial_final_share = final_share
            self.locked_share_percentage = share_pct
            self.locked_initial_pnl = client_pnl
            self.cycle_start_date = timezone.now()
            self.locked_initial_funding = self.funding
```

### 6.3 Critical Rules

1. **Share NEVER shrinks** - Once locked, it remains constant
2. **Share is decided by trading outcome** - Not by settlement
3. **New cycle = New share** - When PnL sign flips or funding changes

---

## 7. REMAINING AMOUNT CALCULATION

### 7.1 Step-by-Step Calculation

**Step 1: Lock Share if Needed**
```python
account.lock_initial_share_if_needed()
```

**Step 2: Get Locked Share**
```python
IF locked_initial_final_share exists:
    InitialFinalShare = locked_initial_final_share
ELSE:
    InitialFinalShare = 0
```

**Step 3: Count Settlements from Current Cycle**
```python
IF cycle_start_date exists:
    TotalSettled = SUM(settlements WHERE date >= cycle_start_date)
ELSE:
    TotalSettled = SUM(all settlements)
```

**Step 4: Calculate Remaining**
```python
CoreRemaining = max(0, InitialFinalShare - TotalSettled)
Overpaid = max(0, TotalSettled - InitialFinalShare)
```

**Step 5: Calculate Display Sign**
```python
IF Client_PnL > 0:
    DisplayRemaining = -CoreRemaining  (you owe client)
ELSE:
    DisplayRemaining = +CoreRemaining  (client owes you)
```

### 7.2 Complete Example

**Scenario:**
```
LockedInitialFinalShare = 100
TotalSettled = 60
Client_PnL = -500 (loss)
```

**Calculation:**
```
Step 1: CoreRemaining = 100 - 60 = 40
Step 2: Client_PnL < 0 → DisplayRemaining = +40
Step 3: Display: "40 (Client owes you)"
```

**Scenario 2:**
```
LockedInitialFinalShare = 100
TotalSettled = 60
Client_PnL = +500 (profit)
```

**Calculation:**
```
Step 1: CoreRemaining = 100 - 60 = 40
Step 2: Client_PnL > 0 → DisplayRemaining = -40
Step 3: Display: "-40 (You owe client)"
```

---

## 8. SETTLEMENT PROCESS

### 8.1 Complete Settlement Flow

**Step 1: User Enters Payment Amount**
```
User enters: SharePayment = 50
```

**Step 2: System Validates**
```
✓ SharePayment > 0
✓ SharePayment ≤ Remaining
✓ Account is locked (row-level lock)
✓ InitialFinalShare > 0
```

**Step 3: Calculate MaskedCapital**
```
MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
```

**Step 4: Validate Balances Won't Go Negative**
```
IF Client_PnL < 0:
    IF Funding - MaskedCapital < 0:
        BLOCK SETTLEMENT
ELSE:
    IF ExchangeBalance - MaskedCapital < 0:
        BLOCK SETTLEMENT
```

**Step 5: Update Account Balances**
```
IF Client_PnL < 0:
    Funding = Funding - MaskedCapital
ELSE:
    ExchangeBalance = ExchangeBalance - MaskedCapital
```

**Step 6: Create Settlement Record**
```
Settlement.amount = SharePayment (positive)
Settlement.date = NOW()
Settlement.client_exchange = account
```

**Step 7: Create Transaction Record (RECORD_PAYMENT)**
```
IF Client_PnL > 0:
    Transaction.amount = -SharePayment (you paid client)
ELSE IF Client_PnL < 0:
    Transaction.amount = +SharePayment (client paid you)

Transaction.type = 'RECORD_PAYMENT'
Transaction.date = NOW()
```

### 8.2 Database Row Locking

**Critical for Concurrency:**
```python
with transaction.atomic():
    # Lock account row
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    
    # Get remaining amount (with lock)
    remaining = account.get_remaining_settlement_amount()['remaining']
    
    # Validate
    if paid_amount > remaining:
        raise ValidationError("Cannot exceed remaining")
    
    # Process payment
    # ... (rest of settlement logic)
```

**Why:** Prevents race conditions where multiple admins could over-settle simultaneously.

---

## 9. MASKED CAPITAL CALCULATION

### 9.1 Formula Derivation

**Problem:** How to map SharePayment back to actual capital reduction?

**Solution:** Linear mapping using locked values

**Formula:**
```
MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
```

**Why This Works:**
```
Initial State:
  LockedInitialPnL = -1,000
  LockedInitialFinalShare = 100 (10% of 1,000)
  Ratio: 1,000 / 100 = 10 (each share unit = 10 capital units)

Payment:
  SharePayment = 50
  MaskedCapital = (50 × 1,000) / 100 = 500 ✓
  
Verification:
  50 share units × 10 ratio = 500 capital units ✓
```

### 9.2 Key Properties

1. **Linear Mapping**: SharePayment maps linearly to capital (not exponential)
2. **Uses Locked Values**: Based on initial state, not current state
3. **Prevents Double-Counting**: Share percentage is only applied once
4. **Proportional Reduction**: Exposure reduces proportionally to share payment

---

## 10. TRANSACTION SIGN LOGIC

### 10.1 CORRECTNESS LOGIC (THE LAW)

**Rule: Sign depends ONLY on Client_PnL at payment time**

**Formula:**
```
IF Client_PnL > 0 (client in profit):
    Transaction.amount = -SharePayment   # you paid client
ELSE IF Client_PnL < 0 (client in loss):
    Transaction.amount = +SharePayment   # client paid you
```

**Critical Rules:**
- ✅ No PnL checks needed in reports (sign is absolute truth)
- ✅ No locked_initial_pnl checks needed
- ✅ No fallback logic needed
- ✅ The sign itself is the truth

### 10.2 Financial Interpretation

| Client_PnL | Payment Direction | Transaction.amount | Meaning |
|------------|------------------|-------------------|---------|
| < 0 (loss) | Client pays you | +X (positive) | Your profit |
| > 0 (profit) | You pay client | -X (negative) | Your loss |

### 10.3 Code Implementation

```python
# CORRECTNESS LOGIC: Sign depends ONLY on Client_PnL at payment time
client_pnl = account.compute_client_pnl()

if client_pnl > 0:
    # PROFIT CASE: YOU pay client → amount is NEGATIVE (your loss)
    transaction_amount = -paid_amount
elif client_pnl < 0:
    # LOSS CASE: Client pays YOU → amount is POSITIVE (your profit)
    transaction_amount = paid_amount
else:
    # PnL = 0 (should not happen due to earlier check, but handle gracefully)
    transaction_amount = 0

Transaction.objects.create(
    type='RECORD_PAYMENT',
    amount=transaction_amount,
    client_exchange=account,
    date=timezone.now()
)
```

---

## 11. DISPLAY LOGIC

### 11.1 Pending Summary Page Display Rules

**Rule 1: All Clients Must Appear**
- Every client-exchange account appears in the list
- Even if no settlement is needed (shows "N.A")

**Rule 2: Remaining Amount Display**
```
IF FinalShare == 0:
    Display: "N.A" (No settlement allowed)
ELSE IF Remaining == 0:
    Display: "Settled"
ELSE:
    Display: DisplayRemaining (with sign and direction)
```

**Rule 3: Sign Display**
```
IF Client_PnL > 0:
    Display: "-X (You owe client)"
ELSE:
    Display: "+X (Client owes you)"
```

### 11.2 Record Payment Page Display

**Current Account Status:**
```
Funding: {funding}
Exchange Balance: {exchange_balance}
Final Share: {final_share}
Remaining to Settle: {display_remaining}
```

**Remaining Display Logic:**
```
IF final_share == 0:
    Display: "N.A"
ELSE:
    Display: display_remaining (with sign)
    IF display_remaining < 0:
        Show: "(You owe client)"
    ELSE:
        Show: "(Client owes you)"
```

---

## 12. CYCLE MANAGEMENT

### 12.1 What is a Cycle?

A **cycle** is a period where:
- PnL has the same sign (all profit or all loss)
- Funding remains constant
- Share is locked at the start

### 12.2 When Does a New Cycle Start?

**New cycle starts when:**
1. **PnL sign flips**: Loss → Profit or Profit → Loss
2. **Funding changes**: New funding = new exposure = new cycle
3. **PnL magnitude reduces significantly**: More than 50% reduction indicates trading reduced exposure

### 12.3 Cycle Separation Logic

**Critical Rule:**
- Settlements from old cycle must NOT mix with new cycle share
- Only count settlements from current cycle (filter by `cycle_start_date`)

**Example:**
```
Cycle 1 (Loss):
  LockedInitialFinalShare = 100
  Settlements: 60
  Remaining: 40

Cycle 2 (Profit - PnL flipped):
  LockedInitialFinalShare = 80 (new share)
  Settlements: 0 (old settlements NOT counted)
  Remaining: 80
```

---

## 13. EDGE CASES AND VALIDATIONS

### 13.1 Zero Share Case

**Scenario:** `FinalShare == 0`

**Behavior:**
- Settlement is blocked
- Display shows "N.A"
- No payment can be recorded

**Why:** Share percentage too small or PnL too small to generate share.

### 13.2 Negative Balance Prevention

**Validation:**
```
IF Client_PnL < 0:
    IF Funding - MaskedCapital < 0:
        BLOCK SETTLEMENT
        Error: "Funding would become negative"
```

**Validation:**
```
IF Client_PnL > 0:
    IF ExchangeBalance - MaskedCapital < 0:
        BLOCK SETTLEMENT
        Error: "Exchange balance would become negative"
```

### 13.3 Overpayment Case

**Scenario:** `TotalSettled > LockedInitialFinalShare`

**Behavior:**
- `Overpaid = TotalSettled - LockedInitialFinalShare`
- `Remaining = 0`
- Historical overpayment is tracked but doesn't affect current cycle

**Why:** Historical settlements may exceed current recalculated share by design.

### 13.4 PnL = 0 Case

**Scenario:** `Client_PnL == 0`

**Behavior:**
- Settlement is blocked
- Display shows appropriate message
- Only reset locks if fully settled

**Why:** Trading flat - no settlement needed.

---

## 14. COMPLETE EXAMPLES

### Example 1: Loss Case - Full Settlement

**Initial State:**
```
Funding = 10,000
Exchange Balance = 8,000
Client_PnL = 8,000 - 10,000 = -2,000 (loss)
Loss Share % = 10%
FinalShare = floor(|-2,000| × 10 / 100) = 200
```

**Lock Share:**
```
LockedInitialFinalShare = 200
LockedInitialPnL = -2,000
LockedSharePercentage = 10%
CycleStartDate = 2026-01-01
```

**Settlement 1 (Partial):**
```
SharePayment = 100
MaskedCapital = (100 × 2,000) / 200 = 1,000

New Funding = 10,000 - 1,000 = 9,000
New Exchange Balance = 8,000 (unchanged)
New Client_PnL = 8,000 - 9,000 = -1,000

TotalSettled = 100
Remaining = 200 - 100 = 100

Transaction.amount = +100 (client paid you)
```

**Settlement 2 (Complete):**
```
SharePayment = 100
MaskedCapital = (100 × 2,000) / 200 = 1,000

New Funding = 9,000 - 1,000 = 8,000
New Exchange Balance = 8,000 (unchanged)
New Client_PnL = 8,000 - 8,000 = 0 (settled)

TotalSettled = 200
Remaining = 200 - 200 = 0

Transaction.amount = +100 (client paid you)
```

### Example 2: Profit Case - Partial Settlement

**Initial State:**
```
Funding = 10,000
Exchange Balance = 13,000
Client_PnL = 13,000 - 10,000 = 3,000 (profit)
Profit Share % = 8%
FinalShare = floor(|3,000| × 8 / 100) = 240
```

**Lock Share:**
```
LockedInitialFinalShare = 240
LockedInitialPnL = 3,000
LockedSharePercentage = 8%
CycleStartDate = 2026-01-01
```

**Settlement 1 (Partial):**
```
SharePayment = 120
MaskedCapital = (120 × 3,000) / 240 = 1,500

New Funding = 10,000 (unchanged)
New Exchange Balance = 13,000 - 1,500 = 11,500
New Client_PnL = 11,500 - 10,000 = 1,500

TotalSettled = 120
Remaining = 240 - 120 = 120

Transaction.amount = -120 (you paid client)
```

**Display:**
```
Remaining: -120 (You owe client 120)
```

### Example 3: Cycle Separation

**Cycle 1 (Loss):**
```
Funding = 10,000
Exchange Balance = 8,000
Client_PnL = -2,000
LockedInitialFinalShare = 200
Settlements: 150
Remaining: 50
```

**PnL Flips to Profit:**
```
Funding = 10,000
Exchange Balance = 12,000
Client_PnL = +2,000
```

**New Cycle Starts:**
```
LockedInitialFinalShare = 160 (new share, 8% of 2,000)
CycleStartDate = 2026-01-15 (new date)
TotalSettled = 0 (old settlements NOT counted)
Remaining: 160
```

**Old Cycle Settlements:**
- Not counted in new cycle
- Historical record only
- New cycle starts fresh

---

## 15. CODE IMPLEMENTATION

### 15.1 Compute Client PnL

```python
def compute_client_pnl(self):
    """Calculate client profit/loss."""
    return self.exchange_balance - self.funding
```

### 15.2 Compute My Share

```python
def compute_my_share(self):
    """Calculate final share using floor rounding."""
    client_pnl = self.compute_client_pnl()
    
    # Determine share percentage
    if client_pnl < 0:
        share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
    else:
        share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
    
    # Calculate share with floor rounding
    final_share = int(abs(client_pnl) * share_pct / 100)
    
    return final_share
```

### 15.3 Get Remaining Settlement Amount

```python
def get_remaining_settlement_amount(self):
    """Calculate remaining settlement amount."""
    # Lock share if needed
    self.lock_initial_share_if_needed()
    
    # Count settlements from current cycle only
    if self.cycle_start_date:
        total_settled = self.settlements.filter(
            date__gte=self.cycle_start_date
        ).aggregate(total=Sum('amount'))['total'] or 0
    else:
        total_settled = self.settlements.aggregate(total=Sum('amount'))['total'] or 0
    
    # Get locked share
    if self.locked_initial_final_share is not None:
        initial_final_share = self.locked_initial_final_share
    else:
        initial_final_share = 0
    
    # Calculate remaining
    remaining = max(0, initial_final_share - total_settled)
    overpaid = max(0, total_settled - initial_final_share)
    
    return {
        'remaining': remaining,
        'overpaid': overpaid,
        'initial_final_share': initial_final_share,
        'total_settled': total_settled
    }
```

### 15.4 Record Payment (Complete Implementation)

```python
@login_required
def record_payment(request, account_id):
    """Record a payment for a client-exchange account."""
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    client_pnl = account.compute_client_pnl()
    
    # Lock share if needed
    account.lock_initial_share_if_needed()
    
    # Get settlement info
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    initial_final_share = settlement_info['initial_final_share']
    
    if request.method == "POST":
        paid_amount = int(request.POST.get("amount", 0))
        
        # Validate
        if paid_amount <= 0:
            return error_response("Amount must be greater than zero")
        
        if initial_final_share == 0:
            return error_response("No settlement allowed - share is zero")
        
        if paid_amount > remaining_amount:
            return error_response(f"Cannot exceed remaining amount: {remaining_amount}")
        
        # Database row locking
        with transaction.atomic():
            account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
            
            # Recalculate with lock
            client_pnl = account.compute_client_pnl()
            settlement_info = account.get_remaining_settlement_amount()
            remaining_amount = settlement_info['remaining']
            
            # Validate again with lock
            if paid_amount > remaining_amount:
                raise ValidationError("Amount exceeds remaining")
            
            # Calculate masked capital
            locked_initial_pnl = account.locked_initial_pnl
            masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)
            
            # Validate balances won't go negative
            if client_pnl < 0:
                if account.funding - masked_capital < 0:
                    raise ValidationError("Funding would become negative")
                account.funding -= masked_capital
            else:
                if account.exchange_balance - masked_capital < 0:
                    raise ValidationError("Exchange balance would become negative")
                account.exchange_balance -= masked_capital
            
            account.save()
            
            # Create Settlement record
            Settlement.objects.create(
                client_exchange=account,
                amount=paid_amount,
                notes=notes
            )
            
            # Create Transaction record (CORRECTNESS LOGIC)
            if client_pnl > 0:
                transaction_amount = -paid_amount  # you paid client
            elif client_pnl < 0:
                transaction_amount = paid_amount  # client paid you
            else:
                transaction_amount = 0
            
            Transaction.objects.create(
                client_exchange=account,
                type='RECORD_PAYMENT',
                amount=transaction_amount,
                date=timezone.now(),
                notes=notes
            )
            
            return redirect("exchange_account_detail", pk=account.pk)
```

---

## 16. DATABASE SCHEMA

### 16.1 ClientExchangeAccount Model

```python
class ClientExchangeAccount(TimeStampedModel):
    client = ForeignKey(Client)
    exchange = ForeignKey(Exchange)
    funding = DecimalField()  # Capital given to client
    exchange_balance = DecimalField()  # Current balance on exchange
    my_percentage = IntegerField()  # Default share %
    loss_share_percentage = IntegerField()  # Share % for losses
    profit_share_percentage = IntegerField()  # Share % for profits
    
    # Locked share fields
    locked_initial_final_share = IntegerField(null=True)
    locked_share_percentage = IntegerField(null=True)
    locked_initial_pnl = DecimalField(null=True)
    locked_initial_funding = DecimalField(null=True)
    cycle_start_date = DateTimeField(null=True)
```

### 16.2 Settlement Model

```python
class Settlement(TimeStampedModel):
    client_exchange = ForeignKey(ClientExchangeAccount)
    amount = IntegerField()  # Share payment (always positive)
    date = DateTimeField()
    notes = TextField(blank=True)
```

### 16.3 Transaction Model

```python
class Transaction(TimeStampedModel):
    client_exchange = ForeignKey(ClientExchangeAccount)
    type = CharField(choices=TRANSACTION_TYPES)  # 'RECORD_PAYMENT'
    amount = BigIntegerField()  # Signed: +X = client paid you, -X = you paid client
    date = DateTimeField()
    exchange_balance_after = DecimalField()
    notes = TextField(blank=True)
```

---

## APPENDIX A: FORMULA SUMMARY

### Master Formulas (PIN THESE 🔒)

1. **Client PnL**
   ```
   Client_PnL = ExchangeBalance − Funding
   ```

2. **Share**
   ```
   FinalShare = floor(|Client_PnL| × Share% / 100)
   ```

3. **Remaining (core)**
   ```
   Remaining = LockedInitialFinalShare − Σ(Settlements)
   ```

4. **Masked Capital**
   ```
   MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
   ```

5. **Transaction Sign**
   ```
   Client_PnL > 0  →  Transaction.amount = -X
   Client_PnL < 0  →  Transaction.amount = +X
   ```

6. **Display Remaining**
   ```
   IF Client_PnL > 0: DisplayRemaining = -CoreRemaining
   ELSE: DisplayRemaining = +CoreRemaining
   ```

---

## APPENDIX B: CORRECTNESS CHECKLIST

For any pending payment implementation, verify:

- [ ] Share is calculated using floor() rounding
- [ ] Share is locked at first compute
- [ ] Share never shrinks after payments
- [ ] Remaining uses locked share, not current share
- [ ] Only current cycle settlements are counted
- [ ] Masked capital uses locked values
- [ ] Transaction sign depends ONLY on Client_PnL
- [ ] Balances are validated before settlement
- [ ] Database row locking prevents race conditions
- [ ] All clients appear in pending list

---

**END OF DOCUMENT**

