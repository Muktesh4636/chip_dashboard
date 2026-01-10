# PENDING PAYMENTS SYSTEM - COMPLETE DOCUMENTATION
## End-to-End Guide with All Formulas and Logic

**Version:** FINAL  
**Status:** Approved & Frozen  
**System Type:** Masked Share Settlement System  
**Last Updated:** 2026-01-09

---

## TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Core Definitions](#2-core-definitions)
3. [Master Formulas](#3-master-formulas)
4. [Share Calculation Logic](#4-share-calculation-logic)
5. [Share Locking Mechanism](#5-share-locking-mechanism)
6. [Remaining Amount Calculation](#6-remaining-amount-calculation)
7. [Settlement Process](#7-settlement-process)
8. [Masked Capital Calculation](#8-masked-capital-calculation)
9. [Sign Logic and Financial Interpretation](#9-sign-logic-and-financial-interpretation)
10. [Display Rules](#10-display-rules)
11. [Cycle Management](#11-cycle-management)
12. [Edge Cases and Validations](#12-edge-cases-and-validations)
13. [Complete Examples](#13-complete-examples)
14. [Database Schema](#14-database-schema)
15. [API Reference](#15-api-reference)

---

## 1. SYSTEM OVERVIEW

### 1.1 Purpose

The Pending Payments System manages settlements between admin and clients using a **Masked Share Settlement Model**. Key characteristics:

- **Masked Settlement**: Client/admin settle only the share amount, not raw capital
- **Dynamic Recalculation**: Settlements reduce trading exposure dynamically
- **Share Locking**: Share is locked at first compute and never shrinks after payments
- **Always Visible**: Clients always appear in pending list (even with N.A when not applicable)
- **Cycle Separation**: Settlements are tracked per PnL cycle to prevent mixing

### 1.2 Key Principles

1. **Share is decided by trading outcome, not by settlement**
2. **Share NEVER shrinks after payments** (locked at first compute)
3. **Clients MUST always appear in pending list** (for visibility)
4. **Settlements reduce exposure using masked capital**
5. **Sign convention: Always from YOUR point of view**

---

## 2. CORE DEFINITIONS

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

### 2.2 Settlement Fields

| Field | Type | Description |
|-------|------|-------------|
| `client_exchange` | ForeignKey | Account this settlement belongs to |
| `amount` | Integer | Share payment amount (always positive) |
| `date` | DateTime | When settlement occurred |
| `notes` | Text | Optional notes |

### 2.3 Transaction Fields (RECORD_PAYMENT)

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

### 3.1 Client Profit/Loss (FOUNDATION)

```
Client_PnL = ExchangeBalance − Funding
```

**Where:**
- `ExchangeBalance` = Current balance on exchange
- `Funding` = Capital given to client

**Result Interpretation:**
- `Client_PnL < 0` → **LOSS** (Client owes you)
- `Client_PnL > 0` → **PROFIT** (You owe client)
- `Client_PnL = 0` → **NEUTRAL** (No exposure)

**Implementation:**
```python
def compute_client_pnl(self):
    return self.exchange_balance - self.funding
```

---

### 3.2 Share Calculation (CORE LOGIC)

#### Step 1: Determine Share Percentage

```
IF Client_PnL < 0 (LOSS):
    Share% = loss_share_percentage IF loss_share_percentage > 0
            ELSE my_percentage

IF Client_PnL > 0 (PROFIT):
    Share% = profit_share_percentage IF profit_share_percentage > 0
            ELSE my_percentage

IF Client_PnL = 0:
    Share = 0 (no share)
```

#### Step 2: Calculate Exact Share

```
ExactShare = |Client_PnL| × (Share% / 100)
```

**Note:** Uses absolute value of PnL (always positive for calculation)

#### Step 3: Calculate Final Share (Floor Rounding)

```
FinalShare = floor(ExactShare)
```

**Rounding Rules:**
- **Method**: FLOOR (round down)
- **Applied**: Only once, at final step
- **Percentages**: NEVER rounded
- **Result**: Always integer (BIGINT)

**Implementation:**
```python
import math

def compute_my_share(self):
client_pnl = self.compute_client_pnl()
    
    if client_pnl == 0:
        return 0
    
    # Determine share percentage
    if client_pnl < 0:
        share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
    else:
        share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
    
    # Calculate exact share
    exact_share = abs(client_pnl) * (share_pct / 100.0)
    
    # Floor round to get final share
    final_share = math.floor(exact_share)
    
    return int(final_share)
```

**Example:**
```
Funding = 1000
Exchange Balance = 700
Client_PnL = 700 - 1000 = -300 (LOSS)
Share% = 10%
ExactShare = 300 × 10% = 30.0
FinalShare = floor(30.0) = 30
```

---

### 3.3 Remaining Settlement Amount

```
Remaining = LockedInitialFinalShare − Sum(SharePayments from Current Cycle)
Overpaid = max(0, Sum(SharePayments) − LockedInitialFinalShare)
```

**Critical Rules:**
1. **Always use locked share** - NEVER recalculate from current PnL
2. **Only count settlements from current cycle** - Filter by `cycle_start_date`
3. **Share NEVER shrinks** - It's locked at initial compute

**Implementation:**
```python
def get_remaining_settlement_amount(self):
# Lock share if needed
self.lock_initial_share_if_needed()

    # Count settlements from CURRENT cycle only
    if self.cycle_start_date:
        total_settled = self.settlements.filter(
            date__gte=self.cycle_start_date
        ).aggregate(total=Sum('amount'))['total'] or 0
    else:
        total_settled = self.settlements.aggregate(total=Sum('amount'))['total'] or 0
    
    # Use locked share
    if self.locked_initial_final_share is not None:
    initial_final_share = self.locked_initial_final_share
else:
        initial_final_share = 0

# Calculate remaining and overpaid
remaining = max(0, initial_final_share - total_settled)
overpaid = max(0, total_settled - initial_final_share)

return {
    'remaining': remaining,
    'overpaid': overpaid,
    'initial_final_share': initial_final_share,
    'total_settled': total_settled
}
```

---

### 3.4 Masked Capital Calculation

**CRITICAL FORMULA:**

```
MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
```

**Why This Formula:**
- Maps SharePayment back to PnL **linearly** (not exponentially)
- Prevents double-counting of share percentage
- Ensures settlements reduce exposure proportionally

**Example:**
```
LockedInitialPnL = -1000 (loss)
LockedInitialFinalShare = 100 (10% share)
SharePayment = 50

MaskedCapital = (50 × 1000) / 100 = 500
```

This means: Paying 50 in share units reduces funding by 500 (the masked capital).

---

### 3.5 Settlement Impact on Balances

#### LOSS CASE (Client_PnL < 0)

```
Funding = Funding − MaskedCapital
ExchangeBalance = ExchangeBalance (unchanged)
```

**Formula:**
```
NewFunding = OldFunding − MaskedCapital
```

**Validation:**
```
IF NewFunding < 0:
    BLOCK SETTLEMENT (cannot go negative)
```

#### PROFIT CASE (Client_PnL > 0)

```
ExchangeBalance = ExchangeBalance − MaskedCapital
Funding = Funding (unchanged)
```

**Formula:**
```
NewExchangeBalance = OldExchangeBalance − MaskedCapital
```

**Validation:**
```
IF NewExchangeBalance < 0:
    BLOCK SETTLEMENT (cannot go negative)
```

---

## 4. SHARE CALCULATION LOGIC

### 4.1 Complete Flow

```
1. Calculate Client_PnL
   Client_PnL = ExchangeBalance − Funding

2. Determine Share Percentage
   IF Client_PnL < 0:
       Share% = loss_share_percentage OR my_percentage
   ELSE IF Client_PnL > 0:
       Share% = profit_share_percentage OR my_percentage
   ELSE:
       Share = 0

3. Calculate Exact Share
   ExactShare = |Client_PnL| × (Share% / 100)

4. Floor Round
   FinalShare = floor(ExactShare)

5. Lock Share (if not already locked)
   IF locked_initial_final_share is None AND FinalShare > 0:
       locked_initial_final_share = FinalShare
       locked_share_percentage = Share%
       locked_initial_pnl = Client_PnL
       cycle_start_date = NOW()
       locked_initial_funding = Funding
```

### 4.2 Share Percentage Priority

1. **For Losses (Client_PnL < 0)**:
   - Use `loss_share_percentage` if set (> 0)
   - Otherwise use `my_percentage`

2. **For Profits (Client_PnL > 0)**:
   - Use `profit_share_percentage` if set (> 0)
   - Otherwise use `my_percentage`

3. **Default**:
   - If no specific percentage set, use `my_percentage` for both

---

## 5. SHARE LOCKING MECHANISM

### 5.1 Why Locking is Critical

**Problem Without Locking:**
```
Initial:
  Funding = 1000
  Exchange Balance = 300
  PnL = -700
  Share% = 10%
  FinalShare = 70

After Payment of 30:
  MaskedCapital = 300
  Funding = 1000 - 300 = 700
  New PnL = 300 - 700 = -400
  New FinalShare = 40  ❌ WRONG! (was 70, now 40)
```

**Solution With Locking:**
```
Initial:
  LockedInitialFinalShare = 70  ✅ LOCKED

After Payment of 30:
  Remaining = 70 - 30 = 40  ✅ CORRECT
  LockedInitialFinalShare = 70  ✅ STILL LOCKED
```

### 5.2 Locking Rules

1. **Lock at First Compute**: When share is first calculated and > 0
2. **Never Shrink**: Locked share never changes after payments
3. **Cycle Reset**: Lock resets when:
   - PnL sign changes (LOSS ↔ PROFIT)
   - Funding changes (new exposure)
   - PnL magnitude reduces significantly (trading reduced exposure)
   - PnL becomes 0 AND share is fully settled

### 5.3 Locking Implementation

```python
def lock_initial_share_if_needed(self):
    client_pnl = self.compute_client_pnl()
    
    # Check if cycle should reset
    # 1. Funding change check
    if self.locked_initial_funding is not None:
        if self.funding != self.locked_initial_funding:
            # Funding changed → reset cycle
            self.reset_locks()
    
    # 2. PnL magnitude reduction check
    if self.locked_initial_pnl is not None and client_pnl != 0:
        if abs(client_pnl) < abs(self.locked_initial_pnl):
            # PnL magnitude reduced → reset cycle
            self.reset_locks()
    
    # 3. PnL sign change check
    if self.locked_initial_pnl is not None:
        if (client_pnl < 0) != (self.locked_initial_pnl < 0):
            # Sign changed → reset cycle
            self.reset_locks()
    
    # Lock new share if needed
    if self.locked_initial_final_share is None:
        final_share = self.compute_my_share()
        if final_share > 0:
            # Lock it
            self.locked_initial_final_share = final_share
            self.locked_share_percentage = share_pct
            self.locked_initial_pnl = client_pnl
            self.cycle_start_date = timezone.now()
            self.locked_initial_funding = self.funding
            self.save()
```

---

## 6. REMAINING AMOUNT CALCULATION

### 6.1 Formula

```
Remaining = max(0, LockedInitialFinalShare − TotalSettled)
Overpaid = max(0, TotalSettled − LockedInitialFinalShare)
```

### 6.2 Step-by-Step Calculation

```
Step 1: Lock share if needed
  lock_initial_share_if_needed()

Step 2: Get locked share
  IF locked_initial_final_share exists:
    InitialFinalShare = locked_initial_final_share
  ELSE:
    InitialFinalShare = 0

Step 3: Count settlements from current cycle
  IF cycle_start_date exists:
    TotalSettled = SUM(settlements WHERE date >= cycle_start_date)
  ELSE:
    TotalSettled = SUM(all settlements)

Step 4: Calculate remaining
  Remaining = max(0, InitialFinalShare − TotalSettled)
  Overpaid = max(0, TotalSettled − InitialFinalShare)
```

### 6.3 Critical Rules

1. **Always use locked share** - Never recalculate from current PnL
2. **Only count current cycle settlements** - Prevents mixing old/new cycles
3. **Remaining can be 0** - When fully settled
4. **Overpaid can be > 0** - When settlements exceed locked share (historical overpayment)

---

## 7. SETTLEMENT PROCESS

### 7.1 Complete Settlement Flow

```
1. User enters SharePayment amount

2. System validates:
   ✓ SharePayment > 0
   ✓ SharePayment ≤ Remaining
   ✓ Account is locked (row-level lock)
   ✓ InitialFinalShare > 0

3. Calculate MaskedCapital:
   MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare

4. Validate balances won't go negative:
   IF Client_PnL < 0:
       IF Funding − MaskedCapital < 0:
           BLOCK SETTLEMENT
   ELSE:
       IF ExchangeBalance − MaskedCapital < 0:
           BLOCK SETTLEMENT

5. Update account balances:
   IF Client_PnL < 0:
       Funding = Funding − MaskedCapital
   ELSE:
       ExchangeBalance = ExchangeBalance − MaskedCapital

6. Create Settlement record:
   Settlement.amount = SharePayment (positive)
   Settlement.date = NOW()
   Settlement.client_exchange = account

7. Create Transaction record (RECORD_PAYMENT):
   IF Client_PnL < 0:
       Transaction.amount = +SharePayment (client paid you)
   ELSE:
       Transaction.amount = −SharePayment (you paid client)
   Transaction.type = 'RECORD_PAYMENT'
   Transaction.date = NOW()
```

### 7.2 Database Row Locking

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

## 8. MASKED CAPITAL CALCULATION

### 8.1 Formula Derivation

**Problem:** How to map SharePayment back to actual capital reduction?

**Solution:** Linear mapping using locked values

```
MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
```

**Why This Works:**

```
Initial State:
  LockedInitialPnL = -1000
  LockedInitialFinalShare = 100 (10% of 1000)
  Ratio: 1000 / 100 = 10 (each share unit = 10 capital units)

Payment:
  SharePayment = 50
  MaskedCapital = (50 × 1000) / 100 = 500 ✅
  
Verification:
  50 share units × 10 ratio = 500 capital units ✅
```

### 8.2 Key Properties

1. **Linear Mapping**: SharePayment maps linearly to capital (not exponential)
2. **Uses Locked Values**: Based on initial state, not current state
3. **Prevents Double-Counting**: Share percentage is only applied once
4. **Proportional Reduction**: Exposure reduces proportionally to share payment

---

## 9. SIGN LOGIC AND FINANCIAL INTERPRETATION

### 9.1 FINAL SIGN LOGIC (THE LAW)

**Always from YOUR point of view:**

| Who Paid Whom | Reality | Amount Shown |
|---------------|---------|--------------|
| Client paid YOU | Your profit | **+X (POSITIVE)** |
| YOU paid client | Your loss | **-X (NEGATIVE)** |

**Rules:**
- ✅ Positive amount = money came to you
- ✅ Negative amount = money went from you
- ❌ Minus NEVER means "client paid"
- ❌ Minus ALWAYS means "you paid"

### 9.2 Application to RECORD_PAYMENT

```python
# When creating RECORD_PAYMENT transaction:

if client_pnl < 0:
    # LOSS CASE: Client pays YOU → amount is POSITIVE
    transaction_amount = +paid_amount
else:
    # PROFIT CASE: YOU pay client → amount is NEGATIVE
    transaction_amount = -paid_amount

Transaction.objects.create(
    type='RECORD_PAYMENT',
    amount=transaction_amount,  # Signed correctly
    ...
)
```

### 9.3 Application to Remaining Amounts

**In Pending Payments Display:**

```
IF Client_PnL < 0 (LOSS):
    Remaining = +share_amount  ✅ POSITIVE (they owe you)

IF Client_PnL > 0 (PROFIT):
    Remaining = -share_amount  ✅ NEGATIVE (you owe them)
```

**Implementation:**
```python
if client_pnl < 0:
    remaining_amount = remaining_amount  # Positive
else:
    remaining_amount = -remaining_amount  # Negative
```

### 9.4 Sanity Check

```
Your Total Profit + Client Net Result = 0

Where:
  Your Total Profit = SUM(RECORD_PAYMENT.amount)
  Client Net Result = -SUM(RECORD_PAYMENT.amount)

Example:
  Your Total Profit = +9 - 19 - 19 = -29
  Client Net Result = -(-29) = +29
  Total = -29 + 29 = 0 ✅
```

---

## 10. DISPLAY RULES

### 10.1 Pending List Display

**Rule:** Client MUST always appear in pending list

**Display Logic:**

```
IF FinalShare == 0:
    Show "N.A" for:
      - Client PnL
      - My Share
      - Remaining
    Disable payment button
ELSE:
    Show actual values
    Enable payment button if Remaining > 0
```

### 10.2 Section Categorization

**"Clients Owe You" Section:**
- `Client_PnL < 0` (LOSS)
- `Remaining` is **POSITIVE** (green)
- Client pays you

**"You Owe Clients" Section:**
- `Client_PnL > 0` (PROFIT)
- `Remaining` is **NEGATIVE** (red)
- You pay client

**Neutral Case:**
- `Client_PnL == 0`
- Show in "Clients Owe You" with N.A
- No payment allowed

### 10.3 Color Coding

- **Green (Positive)**: Money coming to you (clients owe you)
- **Red (Negative)**: Money going from you (you owe clients)
- **Gray (N.A)**: Not applicable (zero share)

---

## 11. CYCLE MANAGEMENT

### 11.1 What is a Cycle?

A **PnL Cycle** is a period where:
- PnL sign remains constant (all LOSS or all PROFIT)
- Share is locked at first compute
- Settlements are tracked within this cycle

### 11.2 Cycle Reset Conditions

A new cycle starts when:

1. **PnL Sign Changes:**
   ```
   OLD: Client_PnL = -500 (LOSS)
   NEW: Client_PnL = +300 (PROFIT)
   → NEW CYCLE
   ```

2. **Funding Changes:**
   ```
   OLD: Funding = 1000
   NEW: Funding = 1500
   → NEW CYCLE (new exposure)
   ```

3. **PnL Magnitude Reduces Significantly:**
   ```
   OLD: |Client_PnL| = 1000
   NEW: |Client_PnL| = 500
   → NEW CYCLE (trading reduced exposure)
   ```

4. **PnL Becomes 0 AND Share Fully Settled:**
   ```
   Client_PnL = 0
   AND Remaining = 0
   → NEW CYCLE (can start fresh)
   ```

### 11.3 Cycle Tracking

```python
# When cycle starts:
cycle_start_date = timezone.now()
locked_initial_funding = self.funding

# When counting settlements:
if self.cycle_start_date:
    settlements = self.settlements.filter(date__gte=self.cycle_start_date)
else:
    settlements = self.settlements.all()
```

---

## 12. EDGE CASES AND VALIDATIONS

### 12.1 Zero Share (N.A Case)

**Condition:** `FinalShare == 0`

**Causes:**
- Very small PnL (e.g., PnL = 2, Share% = 10% → ExactShare = 0.2 → FinalShare = 0)
- Floor rounding to zero

**Behavior:**
- Client appears in pending list
- All values show "N.A"
- Payment button disabled
- No settlement allowed

### 12.2 Overpayment

**Condition:** `TotalSettled > LockedInitialFinalShare`

**Handling:**
```
Overpaid = max(0, TotalSettled - LockedInitialFinalShare)
Remaining = max(0, LockedInitialFinalShare - TotalSettled)
```

**Display:**
- `Remaining` shows as 0
- `Overpaid` amount is tracked (for audit)
- Historical overpayments are preserved

### 12.3 Negative Balance Prevention

**Validation Before Settlement:**

```python
if client_pnl < 0:
    if account.funding - masked_capital < 0:
        raise ValidationError("Funding cannot go negative")
else:
    if account.exchange_balance - masked_capital < 0:
        raise ValidationError("Exchange balance cannot go negative")
```

### 12.4 Concurrent Payment Prevention

**Database Row Locking:**

```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    # ... validate and process payment
```

**Why:** Prevents two admins from over-settling simultaneously.

### 12.5 PnL = 0 Handling

**When PnL = 0:**
- Client appears in pending list with N.A
- No settlement allowed
- Locked share persists if not fully settled
- Locked share resets if fully settled

---

## 13. COMPLETE EXAMPLES

### Example 1: Loss Case (Client Pays You)

**Initial State:**
```
Funding = 1000
Exchange Balance = 300
Client_PnL = 300 - 1000 = -700 (LOSS)
Loss Share% = 10%
```

**Share Calculation:**
```
ExactShare = 700 × 10% = 70.0
FinalShare = floor(70.0) = 70
LockedInitialFinalShare = 70 ✅ LOCKED
```

**Payment 1:**
```
SharePayment = 30
MaskedCapital = (30 × 700) / 70 = 300

New Funding = 1000 - 300 = 700
New Exchange Balance = 300 (unchanged)
New PnL = 300 - 700 = -400

Remaining = 70 - 30 = 40 ✅
LockedInitialFinalShare = 70 ✅ (still locked)

Transaction.amount = +30 ✅ (client paid you)
```

**Payment 2:**
```
SharePayment = 40
MaskedCapital = (40 × 700) / 70 = 400

New Funding = 700 - 400 = 300
New Exchange Balance = 300 (unchanged)
New PnL = 300 - 300 = 0

Remaining = 70 - 70 = 0 ✅
LockedInitialFinalShare = 70 ✅ (still locked)

Transaction.amount = +40 ✅ (client paid you)
```

**Final:**
```
Total Settled = 70
Remaining = 0
Overpaid = 0
PnL = 0 (settled)
```

---

### Example 2: Profit Case (You Pay Client)

**Initial State:**
```
Funding = 500
Exchange Balance = 1200
Client_PnL = 1200 - 500 = +700 (PROFIT)
Profit Share% = 15%
```

**Share Calculation:**
```
ExactShare = 700 × 15% = 105.0
FinalShare = floor(105.0) = 105
LockedInitialFinalShare = 105 ✅ LOCKED
```

**Payment 1:**
```
SharePayment = 50
MaskedCapital = (50 × 700) / 105 = 333.33 → 333

New Exchange Balance = 1200 - 333 = 867
New Funding = 500 (unchanged)
New PnL = 867 - 500 = 367

Remaining = 105 - 50 = 55 ✅
LockedInitialFinalShare = 105 ✅ (still locked)

Transaction.amount = -50 ✅ (you paid client)
```

**Payment 2:**
```
SharePayment = 55
MaskedCapital = (55 × 700) / 105 = 366.67 → 366

New Exchange Balance = 867 - 366 = 501
New Funding = 500 (unchanged)
New PnL = 501 - 500 = 1

Remaining = 105 - 105 = 0 ✅
LockedInitialFinalShare = 105 ✅ (still locked)

Transaction.amount = -55 ✅ (you paid client)
```

**Final:**
```
Total Settled = 105
Remaining = 0
Overpaid = 0
PnL = 1 (nearly settled)
```

---

### Example 3: Zero Share (N.A Case)

**Initial State:**
```
Funding = 100
Exchange Balance = 98
Client_PnL = 98 - 100 = -2 (LOSS)
Loss Share% = 10%
```

**Share Calculation:**
```
ExactShare = 2 × 10% = 0.2
FinalShare = floor(0.2) = 0 ❌
```

**Display:**
```
Client PnL: N.A
My Share: N.A
Remaining: N.A
Payment Button: Disabled
```

---

### Example 4: Overpayment

**Initial State:**
```
LockedInitialFinalShare = 100
Total Settled = 120
```

**Calculation:**
```
Remaining = max(0, 100 - 120) = 0
Overpaid = max(0, 120 - 100) = 20 ✅
```

**Display:**
```
Remaining: 0
Overpaid: 20 (tracked for audit)
```

---

## 14. DATABASE SCHEMA

### 14.1 ClientExchangeAccount Model

```python
class ClientExchangeAccount(models.Model):
    client = ForeignKey(Client)
    exchange = ForeignKey(Exchange)
    funding = DecimalField()
    exchange_balance = DecimalField()
    my_percentage = IntegerField()
    loss_share_percentage = IntegerField(null=True)
    profit_share_percentage = IntegerField(null=True)
    
    # Locking fields
    locked_initial_final_share = IntegerField(null=True)
    locked_share_percentage = IntegerField(null=True)
    locked_initial_pnl = DecimalField(null=True)
    locked_initial_funding = DecimalField(null=True)
    cycle_start_date = DateTimeField(null=True)
```

### 14.2 Settlement Model

```python
class Settlement(models.Model):
    client_exchange = ForeignKey(ClientExchangeAccount)
    amount = IntegerField()  # Share payment (always positive)
    date = DateTimeField()
    notes = TextField()
```

### 14.3 Transaction Model (RECORD_PAYMENT)

```python
class Transaction(models.Model):
    client_exchange = ForeignKey(ClientExchangeAccount)
    type = CharField()  # 'RECORD_PAYMENT'
    amount = DecimalField()  # Signed: +X or -X
    date = DateTimeField()
    exchange_balance_after = DecimalField()
    notes = TextField()
```

---

## 15. API REFERENCE

### 15.1 Methods

#### `compute_client_pnl()`

**Returns:** `Decimal` (can be negative)

**Formula:**
```python
return self.exchange_balance - self.funding
```

---

#### `compute_my_share()`

**Returns:** `int` (always positive, floor rounded)

**Formula:**
```python
client_pnl = self.compute_client_pnl()
if client_pnl == 0:
    return 0

# Determine share percentage
if client_pnl < 0:
    share_pct = self.loss_share_percentage or self.my_percentage
else:
    share_pct = self.profit_share_percentage or self.my_percentage

# Calculate and floor round
exact_share = abs(client_pnl) * (share_pct / 100.0)
return int(math.floor(exact_share))
```

---

#### `lock_initial_share_if_needed()`

**Purpose:** Lock share at first compute per PnL cycle

**Behavior:**
- Locks share if not already locked
- Resets lock if cycle conditions change
- Tracks cycle start date and initial funding

---

#### `get_remaining_settlement_amount()`

**Returns:** `dict` with:
- `remaining`: `int` - Remaining share to settle
- `overpaid`: `int` - Overpaid amount (if any)
- `initial_final_share`: `int` - Locked initial share
- `total_settled`: `int` - Total settled in current cycle

**Formula:**
```python
remaining = max(0, locked_initial_final_share - total_settled)
overpaid = max(0, total_settled - locked_initial_final_share)
```

---

## 16. SUMMARY OF KEY RULES

### 16.1 Golden Rules

1. **Share is locked at first compute** - Never shrinks after payments
2. **Clients always appear in pending list** - Even with N.A when not applicable
3. **Sign convention is absolute** - +X = client paid you, -X = you paid client
4. **Settlements reduce exposure** - Using masked capital calculation
5. **Cycles separate settlements** - Old cycle settlements don't mix with new cycle shares

### 16.2 Critical Formulas

```
Client_PnL = ExchangeBalance − Funding
FinalShare = floor(|Client_PnL| × Share% / 100)
Remaining = LockedInitialFinalShare − Sum(Settlements)
MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
```

### 16.3 Validation Rules

1. SharePayment > 0
2. SharePayment ≤ Remaining
3. Funding ≥ 0 (after settlement)
4. ExchangeBalance ≥ 0 (after settlement)
5. InitialFinalShare > 0 (to allow settlement)

---

## END OF DOCUMENTATION

**Version:** FINAL  
**Status:** Approved & Frozen  
**Last Updated:** 2026-01-09

This document contains all formulas, logic, and rules for the Pending Payments System. Every calculation, validation, and display rule is documented above.

