# Pending Payments System - Complete Documentation

**Version:** 2.0  
**Last Updated:** January 2025  
**Status:** Production Ready

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Definitions](#core-definitions)
3. [Master Formulas](#master-formulas)
4. [Data Flow](#data-flow)
5. [Share Calculation Logic](#share-calculation-logic)
6. [Share Locking Mechanism](#share-locking-mechanism)
7. [Remaining Amount Calculation](#remaining-amount-calculation)
8. [Settlement Process](#settlement-process)
9. [Masked Capital Calculation](#masked-capital-calculation)
10. [Transaction Sign Logic](#transaction-sign-logic)
11. [Display Rules](#display-rules)
12. [Cycle Management](#cycle-management)
13. [Edge Cases and Validations](#edge-cases-and-validations)
14. [Complete Examples](#complete-examples)
15. [Database Schema](#database-schema)
16. [API Reference](#api-reference)

---

## System Overview

### Purpose

The Pending Payments System tracks and manages settlement amounts between administrators and clients based on trading outcomes. It uses a **Masked Share Settlement System** that ensures:

- Share amounts are locked at the start of each PnL cycle
- Share never shrinks after payments (decided by trading, not settlement)
- Remaining amounts are calculated accurately across multiple partial payments
- Transaction signs correctly reflect money direction

### Two Main Sections

1. **Clients Owe You** (Loss Case)
   - `Client_PnL < 0` (Client is in loss)
   - Client owes you settlement
   - DisplayRemaining is **POSITIVE** (client owes you)

2. **You Owe Clients** (Profit Case)
   - `Client_PnL > 0` (Client is in profit)
   - You owe client settlement
   - DisplayRemaining is **NEGATIVE** (you owe client)

### Key Principles

- **Share Locking**: Share is locked at first compute per PnL cycle and never changes
- **Cycle Separation**: Each PnL sign change starts a new cycle with new locked share
- **Linear Mapping**: MaskedCapital maps share payments back to PnL linearly
- **Sign Consistency**: Transaction signs are determined BEFORE balance updates

---

## Core Definitions

### Client_PnL (Client Profit/Loss)

**Formula:**
```
Client_PnL = ExchangeBalance - Funding
```

**Interpretation:**
- `Client_PnL > 0`: Client is in profit (you owe client)
- `Client_PnL < 0`: Client is in loss (client owes you)
- `Client_PnL = 0`: Trading flat (no settlement needed)

**Storage:**
- NOT stored in database
- Computed on-demand from `exchange_balance` and `funding`
- Returns `BigInteger` (can be negative)

### FinalShare (Your Share Amount)

**Formula:**
```
FinalShare = floor(|Client_PnL| × SharePercentage / 100)
```

**Where:**
- `SharePercentage` depends on PnL direction:
  - If `Client_PnL < 0`: Use `loss_share_percentage` (or `my_percentage` if not set)
  - If `Client_PnL > 0`: Use `profit_share_percentage` (or `my_percentage` if not set)
  - If `Client_PnL = 0`: Return 0 (no share)

**Rounding:**
- Uses `floor()` (round down) for final share
- Always returns integer ≥ 0

**Storage:**
- NOT stored directly
- Locked as `locked_initial_final_share` when cycle starts

### RemainingRaw (Core Remaining Amount)

**Formula:**
```
RemainingRaw = max(0, LockedInitialFinalShare - TotalSettled)
```

**Where:**
- `LockedInitialFinalShare`: Share locked at cycle start
- `TotalSettled`: Sum of all settlements in current cycle
- Always returns value ≥ 0

**Storage:**
- Computed on-demand
- Returned by `get_remaining_settlement_amount()`

### DisplayRemaining (Signed Remaining for Display)

**Formula:**
```
IF Client_PnL < 0 (LOSS):
    DisplayRemaining = +RemainingRaw  (client owes you)
ELSE IF Client_PnL > 0 (PROFIT):
    DisplayRemaining = -RemainingRaw  (you owe client)
ELSE:
    DisplayRemaining = 0  (no settlement)
```

**Key Point:**
- `RemainingRaw` is always positive (internal calculation)
- Sign is applied ONLY at display time based on `Client_PnL` direction

### MaskedCapital

**Formula:**
```
MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
```

**Purpose:**
- Maps share payment back to PnL linearly
- Prevents exponential growth
- Ensures consistent settlement ratio

**Impact:**
- If `Client_PnL < 0`: Reduces `funding` by `MaskedCapital`
- If `Client_PnL > 0`: Reduces `exchange_balance` by `MaskedCapital`

---

## Master Formulas

### Formula 1: Client PnL Calculation

```
Client_PnL = ExchangeBalance - Funding
```

**When:** Computed on-demand  
**Returns:** `BigInteger` (can be negative)  
**Used For:** Determining profit/loss direction, share calculation

### Formula 2: Share Calculation

```
IF Client_PnL == 0:
    FinalShare = 0
ELSE:
    SharePercentage = get_share_percentage(Client_PnL)
    FinalShare = floor(|Client_PnL| × SharePercentage / 100)
```

**When:** First compute per PnL cycle  
**Returns:** `BigInteger` ≥ 0  
**Used For:** Locking initial share

### Formula 3: Remaining Amount (Raw)

```
RemainingRaw = max(0, LockedInitialFinalShare - TotalSettled)
```

**Where:**
- `LockedInitialFinalShare`: Share locked at cycle start
- `TotalSettled`: Sum of settlements in current cycle (filtered by `cycle_start_date`)

**When:** Computed on-demand  
**Returns:** `BigInteger` ≥ 0  
**Used For:** Internal calculations

### Formula 4: Display Remaining (Signed)

```
IF Client_PnL < 0:
    DisplayRemaining = +RemainingRaw  (client owes you)
ELSE IF Client_PnL > 0:
    DisplayRemaining = -RemainingRaw  (you owe client)
ELSE:
    DisplayRemaining = 0
```

**When:** Applied at display time  
**Returns:** `BigInteger` (signed)  
**Used For:** UI display, user-facing values

### Formula 5: Masked Capital

```
MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
```

**When:** Computed during payment recording  
**Returns:** `BigInteger` ≥ 0  
**Used For:** Mapping share payment to PnL reduction

### Formula 6: Settlement Impact

```
IF Client_PnL < 0 (LOSS):
    Funding = Funding - MaskedCapital
ELSE IF Client_PnL > 0 (PROFIT):
    ExchangeBalance = ExchangeBalance - MaskedCapital
```

**When:** Applied during payment recording  
**Impact:** Reduces the appropriate balance by masked capital

### Formula 7: Transaction Sign Logic

```
# CRITICAL: Calculate Client_PnL BEFORE balance update
Client_PnL_before = compute_client_pnl()

IF Client_PnL_before > 0:
    Transaction.amount = -SharePayment  (you paid client)
ELSE IF Client_PnL_before < 0:
    Transaction.amount = +SharePayment  (client paid you)
ELSE:
    Transaction.amount = 0  (no payment)
```

**Golden Rule:** Transaction sign must be decided BEFORE balance mutation

---

## Data Flow

### 1. Initial Setup

```
User creates ClientExchangeAccount
    ↓
Sets funding, exchange_balance
    ↓
System computes Client_PnL = exchange_balance - funding
    ↓
If Client_PnL != 0:
    System locks initial share
    System sets cycle_start_date
```

### 2. Share Locking Flow

```
lock_initial_share_if_needed() called
    ↓
Check if locked_initial_final_share exists
    ↓
IF NOT EXISTS:
    Compute Client_PnL
    IF Client_PnL == 0:
        Return (no share)
    ELSE:
        Compute FinalShare = floor(|Client_PnL| × SharePercentage / 100)
        Lock FinalShare as locked_initial_final_share
        Lock SharePercentage as locked_share_percentage
        Lock Client_PnL as locked_initial_pnl
        Set cycle_start_date = now()
        Set locked_initial_funding = current_funding
    ↓
ELSE:
    Check for cycle changes:
        - PnL sign flip?
        - PnL magnitude reduction?
        - Funding change?
    IF cycle changed:
        Reset all locks
        Start new cycle
```

### 3. Remaining Amount Calculation Flow

```
get_remaining_settlement_amount() called
    ↓
Lock share if needed
    ↓
Filter settlements by cycle_start_date (current cycle only)
    ↓
Calculate TotalSettled = Sum(settlement.amount)
    ↓
Get LockedInitialFinalShare
    ↓
Calculate RemainingRaw = max(0, LockedInitialFinalShare - TotalSettled)
    ↓
Calculate Overpaid = max(0, TotalSettled - LockedInitialFinalShare)
    ↓
Return {
    'remaining': RemainingRaw,
    'overpaid': Overpaid,
    'initial_final_share': LockedInitialFinalShare,
    'total_settled': TotalSettled
}
```

### 4. Payment Recording Flow

```
record_payment() called
    ↓
Lock account row (select_for_update)
    ↓
Calculate Client_PnL_before (BEFORE any updates)
    ↓
Decide transaction sign based on Client_PnL_before
    ↓
Lock share if needed
    ↓
Get remaining settlement amount
    ↓
Validate payment amount ≤ remaining
    ↓
Calculate MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
    ↓
Apply balance update:
    IF Client_PnL < 0:
        Funding = Funding - MaskedCapital
    ELSE:
        ExchangeBalance = ExchangeBalance - MaskedCapital
    ↓
Create Settlement record (amount = SharePayment)
    ↓
Create Transaction record (amount = signed SharePayment)
    ↓
Save account
```

---

## Share Calculation Logic

### Share Percentage Selection

**Method:** `get_share_percentage(client_pnl)`

**Logic:**
```python
IF client_pnl < 0 (LOSS):
    IF loss_share_percentage > 0:
        return loss_share_percentage
    ELSE:
        return my_percentage
ELSE IF client_pnl > 0 (PROFIT):
    IF profit_share_percentage > 0:
        return profit_share_percentage
    ELSE:
        return my_percentage
ELSE:
    return 0  # No share on zero PnL
```

**Key Points:**
- Share percentage depends on PnL direction
- Loss and profit can have different percentages
- Zero PnL returns 0 (no share)

### Final Share Calculation

**Method:** `compute_my_share()`

**Logic:**
```python
client_pnl = compute_client_pnl()

IF client_pnl == 0:
    return 0

share_pct = get_share_percentage(client_pnl)

# Exact Share (no rounding)
exact_share = abs(client_pnl) * share_pct / 100

# Final Share (floor rounding)
final_share = floor(exact_share)

return final_share
```

**Rounding:**
- Uses `floor()` (round down)
- Always returns integer ≥ 0
- Example: `exact_share = 9.9` → `final_share = 9`

---

## Share Locking Mechanism

### Purpose

Share locking ensures that:
- Share amount is decided by trading outcome, not settlement
- Share never shrinks after payments
- Historical settlements don't affect current calculations
- Each PnL cycle has its own locked share

### Locked Fields

1. **locked_initial_final_share**: Share amount locked at cycle start
2. **locked_share_percentage**: Percentage used to calculate share
3. **locked_initial_pnl**: PnL value when share was locked
4. **cycle_start_date**: Timestamp when cycle started
5. **locked_initial_funding**: Funding amount when cycle started

### When Share is Locked

Share is locked when:
- First time `lock_initial_share_if_needed()` is called AND `Client_PnL != 0`
- PnL cycle changes (sign flip)
- PnL magnitude reduces significantly
- Funding changes (new exposure = new cycle)

### Cycle Reset Conditions

Cycle resets (locks cleared) when:

1. **PnL Sign Flip:**
   ```
   (Client_PnL < 0) != (LockedInitialPnL < 0)
   ```
   - Loss → Profit: New cycle
   - Profit → Loss: New cycle

2. **PnL Magnitude Reduction:**
   ```
   |Current_PnL| < |LockedInitialPnL|
   ```
   - Trading reduced exposure
   - Old lock becomes invalid

3. **Funding Change:**
   ```
   CurrentFunding != LockedInitialFunding
   ```
   - New exposure = new cycle
   - Funding increase/decrease resets cycle

### Lock Persistence

Once locked, share persists until:
- Cycle resets (sign flip, magnitude reduction, funding change)
- Account is deleted
- Manual reset (admin action)

---

## Remaining Amount Calculation

### Core Formula

```
RemainingRaw = max(0, LockedInitialFinalShare - TotalSettled)
```

**Components:**
- `LockedInitialFinalShare`: Share locked at cycle start (never changes)
- `TotalSettled`: Sum of settlements in current cycle only

### Cycle Filtering

**Critical:** Only count settlements from current cycle

```python
IF cycle_start_date exists:
    TotalSettled = Sum(settlements WHERE date >= cycle_start_date)
ELSE:
    TotalSettled = Sum(all settlements)  # Backward compatibility
```

**Why:** Prevents mixing settlements from different PnL cycles

### Display Sign Application

**Raw Value:** Always ≥ 0 (internal calculation)

**Display Value:** Signed based on PnL direction

```python
IF Client_PnL < 0 (LOSS):
    DisplayRemaining = +RemainingRaw  # Client owes you (positive)
ELSE IF Client_PnL > 0 (PROFIT):
    DisplayRemaining = -RemainingRaw  # You owe client (negative)
ELSE:
    DisplayRemaining = 0
```

### Overpaid Calculation

```
Overpaid = max(0, TotalSettled - LockedInitialFinalShare)
```

**When:** `TotalSettled > LockedInitialFinalShare`  
**Meaning:** More was paid than required  
**Handling:** System allows but tracks overpayment

---

## Settlement Process

### Step-by-Step Process

1. **User Initiates Payment**
   - Navigates to "Record Payment" page
   - Enters payment amount
   - Optionally adds notes

2. **System Validates**
   - Checks `Client_PnL != 0` (no settlement if flat)
   - Checks `InitialFinalShare > 0` (no settlement if no share)
   - Validates `PaidAmount > 0`
   - Validates `PaidAmount ≤ RemainingRaw`

3. **System Locks Account**
   - Uses `select_for_update()` for row-level locking
   - Prevents concurrent payment race conditions

4. **System Calculates Client_PnL Before**
   - **CRITICAL:** Calculate BEFORE any balance updates
   - Used to determine transaction sign

5. **System Decides Transaction Sign**
   ```python
   IF Client_PnL_before > 0:
       transaction_amount = -paid_amount  # You paid client
   ELSE:
       transaction_amount = +paid_amount  # Client paid you
   ```

6. **System Calculates MaskedCapital**
   ```
   MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
   ```

7. **System Updates Balance**
   ```python
   IF Client_PnL < 0:
       Funding = Funding - MaskedCapital
   ELSE:
       ExchangeBalance = ExchangeBalance - MaskedCapital
   ```

8. **System Creates Records**
   - Creates `Settlement` record (amount = SharePayment, always positive)
   - Creates `Transaction` record (amount = signed SharePayment)

9. **System Saves Changes**
   - Saves account with updated balance
   - Commits transaction

### Validation Rules

1. **Zero PnL Check:**
   ```
   IF Client_PnL == 0:
       Block settlement (trading flat)
   ```

2. **Zero Share Check:**
   ```
   IF InitialFinalShare == 0:
       Block settlement (no share to settle)
   ```

3. **Remaining Amount Check:**
   ```
   IF PaidAmount > RemainingRaw:
       Raise ValidationError
   ```

4. **Balance Validation:**
   ```python
   IF Client_PnL < 0:
       IF Funding - MaskedCapital < 0:
           Raise ValidationError
   ELSE:
       IF ExchangeBalance - MaskedCapital < 0:
           Raise ValidationError
   ```

---

## Masked Capital Calculation

### Purpose

MaskedCapital maps share payments back to PnL linearly, ensuring:
- Consistent settlement ratio
- No exponential growth
- Accurate balance reduction

### Formula

```
MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
```

**Where:**
- `SharePayment`: Amount being paid (always positive)
- `LockedInitialPnL`: PnL when share was locked (can be negative, use absolute value)
- `LockedInitialFinalShare`: Share locked at cycle start

### Example

**Scenario:**
- `LockedInitialPnL = -90` (loss)
- `LockedInitialFinalShare = 9`
- `SharePayment = 3`

**Calculation:**
```
MaskedCapital = (3 × 90) / 9 = 270 / 9 = 30
```

**Result:**
- Funding reduced by 30
- Share payment of 3 maps to PnL reduction of 30

### Balance Impact

**Loss Case (`Client_PnL < 0`):**
```
Funding = Funding - MaskedCapital
```

**Profit Case (`Client_PnL > 0`):**
```
ExchangeBalance = ExchangeBalance - MaskedCapital
```

### Why "Masked"?

The capital is "masked" because:
- It's not the actual PnL amount
- It's calculated to maintain linear mapping
- It ensures share payments reduce balances proportionally

---

## Transaction Sign Logic

### Golden Rule

**Transaction sign must be decided BEFORE balance mutation**

### Correct Flow

```python
# Step 1: Calculate PnL BEFORE any updates
client_pnl_before = account.compute_client_pnl()

# Step 2: Decide sign based on PnL BEFORE
IF client_pnl_before > 0:
    transaction_amount = -paid_amount  # You paid client
ELSE:
    transaction_amount = +paid_amount  # Client paid you

# Step 3: THEN update balances
apply_masked_capital()
```

### Sign Convention

**From YOUR point of view:**

- **Positive (`+X`)**: Client paid YOU → Your profit
- **Negative (`-X`)**: YOU paid client → Your loss

**Based on Client_PnL:**

- **IF `Client_PnL > 0` (Profit):**
  - You owe client
  - Transaction amount = **-SharePayment** (negative)
  - Meaning: You paid client

- **IF `Client_PnL < 0` (Loss):**
  - Client owes you
  - Transaction amount = **+SharePayment** (positive)
  - Meaning: Client paid you

### Why This Matters

If sign is calculated AFTER balance update:
- PnL might flip (e.g., from loss to profit)
- Sign would be wrong
- Reports would show incorrect profit/loss

**Example of Wrong Flow:**
```python
# WRONG ORDER
apply_masked_capital()  # Funding becomes 10
client_pnl = compute_client_pnl()  # 10 - 10 = 0
transaction_amount = -paid  # Treated as profit ❌
```

**Correct Flow:**
```python
# CORRECT ORDER
client_pnl_before = compute_client_pnl()  # -90 (loss)
transaction_amount = +paid  # Positive (client paid you) ✅
apply_masked_capital()  # THEN update balances
```

---

## Display Rules

### Pending Summary Display

**Two Sections:**

1. **Clients Owe You** (`Client_PnL < 0`)
   - DisplayRemaining: **POSITIVE** (client owes you)
   - Color: Usually green/positive styling
   - Meaning: Money coming to you

2. **You Owe Clients** (`Client_PnL > 0`)
   - DisplayRemaining: **NEGATIVE** (you owe client)
   - Color: Usually red/negative styling
   - Meaning: Money going out from you

### Record Payment Page Display

**Remaining Amount:**
```python
IF Client_PnL > 0:
    display_remaining = -remaining_amount  # You owe client
    Show: "-X (You owe client)"
ELSE:
    display_remaining = remaining_amount  # Client owes you
    Show: "+X (Client owes you)"
```

### N.A Display

**When to Show N.A:**
- `Client_PnL == 0` (trading flat)
- `FinalShare == 0` (share too small)

**Display:**
- Show "N.A" instead of amount
- Still show client in list
- No action buttons (can't record payment)

---

## Cycle Management

### Cycle Definition

A **PnL Cycle** is a period where:
- PnL sign remains constant (all profit OR all loss)
- Share is locked at cycle start
- Settlements are tracked per cycle

### Cycle Start

Cycle starts when:
- First non-zero PnL is computed
- PnL sign flips (loss → profit or profit → loss)
- PnL magnitude reduces significantly
- Funding changes

### Cycle End

Cycle ends when:
- New cycle starts (sign flip, magnitude reduction, funding change)
- Account is deleted
- Manual reset

### Cycle Separation

**Critical:** Settlements from different cycles must NOT mix

**Implementation:**
```python
IF cycle_start_date exists:
    settlements = Settlement.objects.filter(
        client_exchange=account,
        date__gte=cycle_start_date
    )
ELSE:
    settlements = Settlement.objects.filter(
        client_exchange=account
    )
```

**Why:** Prevents old cycle settlements from affecting new cycle calculations

---

## Edge Cases and Validations

### Edge Case 1: Zero PnL

**Scenario:** `Client_PnL = 0` (trading flat)

**Handling:**
- Show client in pending list with "N.A"
- Block settlement (no payment needed)
- Return 0 for share calculation

**Code:**
```python
IF Client_PnL == 0:
    show_na = True
    remaining_amount = 0
    Block settlement
```

### Edge Case 2: Zero Share

**Scenario:** `FinalShare = 0` (share percentage too small or PnL too small)

**Handling:**
- Show client in pending list with "N.A"
- Block settlement (no share to settle)
- Return 0 for remaining amount

**Code:**
```python
IF FinalShare == 0:
    show_na = True
    remaining_amount = 0
    Block settlement
```

### Edge Case 3: Overpayment

**Scenario:** `TotalSettled > LockedInitialFinalShare`

**Handling:**
- System allows overpayment (tracks it)
- `Overpaid = TotalSettled - LockedInitialFinalShare`
- `RemainingRaw = 0` (no more remaining)

**Code:**
```python
overpaid = max(0, TotalSettled - LockedInitialFinalShare)
remaining = max(0, LockedInitialFinalShare - TotalSettled)
```

### Edge Case 4: Concurrent Payments

**Scenario:** Multiple users try to record payment simultaneously

**Handling:**
- Use database row locking (`select_for_update()`)
- Lock account row before calculations
- Prevent race conditions

**Code:**
```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    # ... perform calculations and updates
```

### Edge Case 5: PnL Flips During Payment

**Scenario:** PnL sign changes between page load and payment submission

**Handling:**
- Recalculate `Client_PnL` with locked account
- Use `Client_PnL_before` for sign decision
- Lock prevents concurrent changes

### Edge Case 6: Negative Balance Prevention

**Scenario:** Payment would make balance negative

**Handling:**
- Validate before updating
- Raise `ValidationError` if balance would go negative
- Show user-friendly error message

**Code:**
```python
IF Client_PnL < 0:
    IF Funding - MaskedCapital < 0:
        Raise ValidationError("Funding would become negative")
ELSE:
    IF ExchangeBalance - MaskedCapital < 0:
        Raise ValidationError("Exchange balance would become negative")
```

---

## Complete Examples

### Example 1: Loss Case - Single Payment

**Initial State:**
- Funding: 100
- Exchange Balance: 10
- Loss Share Percentage: 10%

**Step 1: Calculate Client_PnL**
```
Client_PnL = 10 - 100 = -90 (LOSS)
```

**Step 2: Calculate FinalShare**
```
FinalShare = floor(|-90| × 10 / 100) = floor(9) = 9
```

**Step 3: Lock Share**
```
locked_initial_final_share = 9
locked_share_percentage = 10
locked_initial_pnl = -90
cycle_start_date = 2025-01-10 10:00:00
```

**Step 4: Calculate Remaining**
```
RemainingRaw = max(0, 9 - 0) = 9
DisplayRemaining = +9 (client owes you)
```

**Step 5: Record Payment of 5**
```
SharePayment = 5
MaskedCapital = (5 × 90) / 9 = 50

Funding = 100 - 50 = 50
ExchangeBalance = 10 (unchanged)

New Client_PnL = 10 - 50 = -40

Transaction.amount = +5 (client paid you)

RemainingRaw = max(0, 9 - 5) = 4
DisplayRemaining = +4 (client owes you)
```

### Example 2: Profit Case - Multiple Payments

**Initial State:**
- Funding: 100
- Exchange Balance: 290
- Profit Share Percentage: 20%

**Step 1: Calculate Client_PnL**
```
Client_PnL = 290 - 100 = +190 (PROFIT)
```

**Step 2: Calculate FinalShare**
```
FinalShare = floor(190 × 20 / 100) = floor(38) = 38
```

**Step 3: Lock Share**
```
locked_initial_final_share = 38
locked_share_percentage = 20
locked_initial_pnl = +190
cycle_start_date = 2025-01-10 10:00:00
```

**Step 4: Calculate Remaining**
```
RemainingRaw = max(0, 38 - 0) = 38
DisplayRemaining = -38 (you owe client)
```

**Step 5: Record Payment 1 of 15**
```
SharePayment = 15
MaskedCapital = (15 × 190) / 38 = 75

ExchangeBalance = 290 - 75 = 215
Funding = 100 (unchanged)

New Client_PnL = 215 - 100 = +115

Transaction.amount = -15 (you paid client)

RemainingRaw = max(0, 38 - 15) = 23
DisplayRemaining = -23 (you owe client)
```

**Step 6: Record Payment 2 of 23**
```
SharePayment = 23
MaskedCapital = (23 × 190) / 38 = 115

ExchangeBalance = 215 - 115 = 100
Funding = 100 (unchanged)

New Client_PnL = 100 - 100 = 0 (settled!)

Transaction.amount = -23 (you paid client)

RemainingRaw = max(0, 38 - 38) = 0
DisplayRemaining = 0 (settled)
```

### Example 3: Cycle Change (Sign Flip)

**Initial State (Loss Cycle):**
- Funding: 100
- Exchange Balance: 10
- Client_PnL = -90 (LOSS)
- Locked Share: 9

**Trading Changes:**
- Exchange Balance: 10 → 200
- New Client_PnL = 200 - 100 = +100 (PROFIT)

**Cycle Reset:**
```
Old cycle locks cleared
New cycle starts
```

**New Cycle:**
```
Client_PnL = +100 (PROFIT)
FinalShare = floor(100 × 20 / 100) = 20

locked_initial_final_share = 20
locked_share_percentage = 20
locked_initial_pnl = +100
cycle_start_date = 2025-01-10 11:00:00 (new timestamp)

Old settlements (from loss cycle) are NOT counted
RemainingRaw = max(0, 20 - 0) = 20
DisplayRemaining = -20 (you owe client)
```

---

## Database Schema

### ClientExchangeAccount Model

**Core Fields:**
```python
funding = BigIntegerField(default=0)  # Real money given to client
exchange_balance = BigIntegerField(default=0)  # Current balance on exchange

# Share percentages
my_percentage = IntegerField(default=0)  # Deprecated
loss_share_percentage = IntegerField(default=0)  # For losses
profit_share_percentage = IntegerField(default=0)  # For profits

# Locked values (for cycle management)
locked_initial_final_share = BigIntegerField(null=True, blank=True)
locked_share_percentage = IntegerField(null=True, blank=True)
locked_initial_pnl = BigIntegerField(null=True, blank=True)
cycle_start_date = DateTimeField(null=True, blank=True)
locked_initial_funding = BigIntegerField(null=True, blank=True)
```

### Settlement Model

**Fields:**
```python
client_exchange = ForeignKey(ClientExchangeAccount)
amount = BigIntegerField()  # Share payment amount (always positive)
date = DateTimeField()  # Payment date (used for cycle filtering)
notes = TextField(blank=True)
```

### Transaction Model

**Fields:**
```python
client_exchange = ForeignKey(ClientExchangeAccount)
type = CharField()  # 'RECORD_PAYMENT'
amount = BigIntegerField()  # Signed: +X if client paid you, -X if you paid client
date = DateTimeField()
exchange_balance_after = BigIntegerField()  # Balance after transaction
notes = TextField(blank=True)
```

---

## API Reference

### Methods

#### `compute_client_pnl()`

**Purpose:** Calculate client profit/loss

**Formula:**
```
Client_PnL = ExchangeBalance - Funding
```

**Returns:** `BigInteger` (can be negative)

**Usage:**
```python
account = ClientExchangeAccount.objects.get(pk=1)
client_pnl = account.compute_client_pnl()
```

#### `get_share_percentage(client_pnl=None)`

**Purpose:** Get appropriate share percentage based on PnL direction

**Parameters:**
- `client_pnl`: Optional PnL value (if None, computes from balances)

**Returns:** `int` (0-100)

**Logic:**
- If `client_pnl < 0`: Returns `loss_share_percentage` or `my_percentage`
- If `client_pnl > 0`: Returns `profit_share_percentage` or `my_percentage`
- If `client_pnl == 0`: Returns 0

#### `compute_my_share()`

**Purpose:** Calculate final share amount

**Formula:**
```
IF Client_PnL == 0:
    return 0
ELSE:
    SharePercentage = get_share_percentage(Client_PnL)
    return floor(|Client_PnL| × SharePercentage / 100)
```

**Returns:** `BigInteger` ≥ 0

#### `lock_initial_share_if_needed()`

**Purpose:** Lock share at first compute per PnL cycle

**Logic:**
- Checks if share is already locked
- If not locked and `Client_PnL != 0`, locks share
- Detects cycle changes and resets locks if needed

**Returns:** None (modifies instance)

#### `get_remaining_settlement_amount()`

**Purpose:** Calculate remaining settlement amount

**Formula:**
```
RemainingRaw = max(0, LockedInitialFinalShare - TotalSettled)
```

**Returns:** `dict` with:
- `remaining`: `BigInteger` ≥ 0 (raw value)
- `overpaid`: `BigInteger` ≥ 0
- `initial_final_share`: `BigInteger` ≥ 0
- `total_settled`: `BigInteger` ≥ 0

**Important:** Returns raw value (always ≥ 0). Sign must be applied at display time.

#### `compute_masked_capital(share_payment)`

**Purpose:** Calculate masked capital from share payment

**Formula:**
```
MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
```

**Parameters:**
- `share_payment`: `BigInteger` ≥ 0

**Returns:** `BigInteger` ≥ 0

### Views

#### `pending_summary(request)`

**Purpose:** Display pending payments summary

**URL:** `/pending/`

**Returns:** Two lists:
- `clients_owe_you`: Clients in loss (owe you)
- `you_owe_clients`: Clients in profit (you owe)

**Display Logic:**
- Applies sign to remaining amounts based on PnL direction
- Shows N.A for zero PnL or zero share

#### `record_payment(request, account_id)`

**Purpose:** Record a payment for a client-exchange account

**URL:** `/exchanges/account/<id>/record-payment/`

**Method:** GET (show form) or POST (record payment)

**POST Parameters:**
- `amount`: Payment amount (required)
- `notes`: Optional notes

**Process:**
1. Locks account row
2. Calculates `Client_PnL_before`
3. Decides transaction sign
4. Validates payment amount
5. Calculates masked capital
6. Updates balance
7. Creates settlement and transaction records

**Returns:** Redirect to pending summary or account detail

---

## Summary

The Pending Payments System is a comprehensive settlement tracking system that:

1. **Locks shares** at the start of each PnL cycle
2. **Tracks remaining** amounts accurately across multiple payments
3. **Maps payments** to balance reductions linearly via masked capital
4. **Maintains sign consistency** by deciding transaction signs before balance updates
5. **Separates cycles** to prevent mixing settlements from different periods
6. **Handles edge cases** gracefully (zero PnL, zero share, overpayment, etc.)

**Key Principles:**
- Share is decided by trading, not settlement
- Transaction sign is determined BEFORE balance mutation
- Remaining is stored positive, signed at display time
- Cycles are separated to maintain accuracy

This system ensures accurate, consistent, and reliable settlement tracking for all client-exchange accounts.

---

**End of Documentation**

