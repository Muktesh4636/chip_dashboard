# Pending Payments System - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Core Concepts](#core-concepts)
3. [Formulas and Calculations](#formulas-and-calculations)
4. [Masked Share Settlement System](#masked-share-settlement-system)
5. [PnL Cycles and Locking Mechanism](#pnl-cycles-and-locking-mechanism)
6. [Settlement Recording Logic](#settlement-recording-logic)
7. [Pending Summary View Logic](#pending-summary-view-logic)
8. [Display Logic](#display-logic)
9. [Edge Cases and Validations](#edge-cases-and-validations)
10. [Database Models](#database-models)
11. [Key Methods Reference](#key-methods-reference)

---

## Overview

The Pending Payments system tracks outstanding settlement amounts between the admin and clients based on trading profits and losses. It uses a **Masked Share Settlement System** that ensures:

- Share amounts are locked at the start of each PnL cycle
- Settlements are tracked separately from trading activity
- Partial payments are fully supported
- Historical settlements remain valid even if PnL changes

### Key Principles

1. **Share Locking**: Once a share is calculated for a PnL cycle, it never shrinks
2. **Cycle Separation**: Each PnL sign change (profit ↔ loss) starts a new cycle
3. **Masked Capital**: Settlement payments map linearly back to PnL, not exponentially
4. **Always Visible**: Clients always appear in pending list, even when PnL = 0

---

## Core Concepts

### Client PnL (Profit/Loss)

**Formula 1: Client_PnL**
```
Client_PnL = ExchangeBalance − Funding
```

- **Returns**: BIGINT (can be negative for loss, positive for profit, zero for flat)
- **Interpretation**:
  - `Client_PnL < 0`: Client is in LOSS → Client owes admin
  - `Client_PnL > 0`: Client is in PROFIT → Admin owes client
  - `Client_PnL = 0`: Trading flat (no pending, but may have historical settlements)

### Share Percentages

The system uses **separate percentages** for losses and profits:

- **`loss_share_percentage`**: Admin's share of client losses (0-100)
- **`profit_share_percentage`**: Admin's share of client profits (0-100)
- **`my_percentage`**: Legacy fallback if specific percentages not set

**Rules**:
- Loss share percentage is **IMMUTABLE** once data exists
- Profit share percentage can change anytime (affects only future profits)
- System automatically selects appropriate percentage based on PnL direction

---

## Formulas and Calculations

### Formula 2: Exact Share (Before Rounding)

```
ExactShare = ABS(Client_PnL) × SharePercentage / 100
```

- **Returns**: Float (exact value before rounding)
- **Used for**: Internal calculations, display precision

### Formula 3: Final Share (After Floor Rounding)

```
FinalShare = FLOOR(ExactShare)
```

- **Returns**: BIGINT (always positive, rounded down)
- **Rounding**: Uses `math.floor()` - always rounds DOWN
- **Purpose**: Ensures admin never gets more than calculated share

**Example**:
- ExactShare = 123.99 → FinalShare = 123
- ExactShare = 123.01 → FinalShare = 123
- ExactShare = 0.99 → FinalShare = 0

### Formula 4: Share Percentage Selection

```
IF Client_PnL < 0 (LOSS):
    SharePercentage = loss_share_percentage (if > 0) ELSE my_percentage
ELSE IF Client_PnL > 0 (PROFIT):
    SharePercentage = profit_share_percentage (if > 0) ELSE my_percentage
ELSE (PnL = 0):
    SharePercentage = 0
```

### Formula 5: Remaining Settlement Amount

```
RemainingRaw = LockedInitialFinalShare − Sum(SharePayments)
Overpaid = max(0, Sum(SharePayments) − LockedInitialFinalShare)
```

**Key Points**:
- Uses **LockedInitialFinalShare**, NOT current calculated share
- Only counts settlements from **current PnL cycle**
- RemainingRaw is always ≥ 0 (raw value)
- Sign is applied at **display time** based on PnL direction

### Formula 6: Masked Capital

```
MaskedCapital = (SharePayment × ABS(LockedInitialPnL)) / LockedInitialFinalShare
```

**Purpose**: Maps share payment linearly back to PnL, preventing double-counting of share percentage.

**Why Linear Mapping?**
- SharePayment is a percentage of PnL
- MaskedCapital should map back to original PnL linearly
- Prevents exponential effects when applying share percentage twice

**Example**:
- LockedInitialPnL = -1000 (loss)
- LockedInitialFinalShare = 100 (10% share)
- SharePayment = 50
- MaskedCapital = (50 × 1000) / 100 = 500

---

## Masked Share Settlement System

### Core Principles

1. **Share Locking**: Share is locked at first compute per PnL cycle
2. **Never Shrinks**: Locked share never decreases after payments
3. **Cycle Isolation**: Each PnL cycle has separate settlement tracking
4. **Linear Mapping**: MaskedCapital maps linearly to PnL

### Settlement Flow

```
1. Client trades → PnL changes
2. System detects new PnL cycle (sign change or first PnL)
3. Lock InitialFinalShare and InitialPnL
4. Calculate Remaining = LockedShare - Sum(Settlements)
5. Record payment → Create Settlement record
6. Update balances using MaskedCapital
7. Recalculate Remaining
```

### Balance Updates

**LOSS Case (Client_PnL < 0)**:
```
Funding = Funding − MaskedCapital
ExchangeBalance = ExchangeBalance (unchanged)
```

**PROFIT Case (Client_PnL > 0)**:
```
ExchangeBalance = ExchangeBalance − MaskedCapital
Funding = Funding (unchanged)
```

**Rationale**:
- Loss settlement reduces funding (money given to client)
- Profit settlement reduces exchange balance (money on exchange)

---

## PnL Cycles and Locking Mechanism

### What is a PnL Cycle?

A **PnL cycle** starts when:
1. First PnL is detected (was 0, now non-zero)
2. PnL sign changes (profit ↔ loss)
3. Funding changes (new exposure = new cycle)

### Locking Logic

**When Share is Locked**:
- First time share > 0 is calculated
- PnL cycle changes (sign flip)
- Funding changes (new exposure)

**What Gets Locked**:
- `locked_initial_final_share`: FinalShare at cycle start
- `locked_share_percentage`: Share percentage at cycle start
- `locked_initial_pnl`: Client_PnL at cycle start
- `cycle_start_date`: Timestamp when cycle started
- `locked_initial_funding`: Funding amount at cycle start

### Cycle Reset Conditions

Share locks are reset when:

1. **PnL Magnitude Reduction**: Current PnL magnitude < Locked PnL magnitude
   - Indicates trading reduced exposure
   - Old lock becomes invalid

2. **Funding Change**: Current funding ≠ Locked funding
   - New exposure = new cycle
   - All locks reset

3. **PnL Sign Change**: Current PnL sign ≠ Locked PnL sign
   - New cycle starts
   - Old cycle locks preserved for historical settlements

4. **Zero PnL + Fully Settled**: PnL = 0 AND remaining settlement = 0
   - Cycle complete
   - Safe to reset

### Cycle Separation for Settlements

**CRITICAL**: Settlements are filtered by `cycle_start_date`:

```python
if cycle_start_date:
    settlements = Settlement.objects.filter(
        client_exchange=account,
        date__gte=cycle_start_date
    )
else:
    settlements = Settlement.objects.filter(
        client_exchange=account
    )
```

This ensures:
- Old cycle settlements don't mix with new cycle shares
- Each cycle is independently settled
- Historical accuracy is maintained

---

## Settlement Recording Logic

### Record Payment Flow

1. **Load Account** (no locking for GET requests)
2. **Calculate Current PnL**
3. **Lock Share** (if needed)
4. **Get Settlement Info** (remaining, overpaid, etc.)
5. **Validate Payment** (POST request):
   - Amount > 0
   - PnL ≠ 0 (trading flat check)
   - InitialFinalShare > 0 (no settlement if share = 0)
   - PaidAmount ≤ RemainingAmount
   - Balance won't go negative

6. **Calculate Transaction Sign** (BEFORE balance update):
   ```
   IF Client_PnL > 0: Transaction.amount = -SharePayment (you pay client)
   IF Client_PnL < 0: Transaction.amount = +SharePayment (client pays you)
   ```

7. **Calculate MaskedCapital**:
   ```
   MaskedCapital = (SharePayment × ABS(LockedInitialPnL)) / LockedInitialFinalShare
   ```

8. **Update Balances**:
   ```
   IF Loss: Funding -= MaskedCapital
   IF Profit: ExchangeBalance -= MaskedCapital
   ```

9. **Create Records**:
   - Settlement record (tracks share payment)
   - Transaction record (audit trail with sign)

10. **Save Account**

### Database Row Locking

**CRITICAL**: Uses `select_for_update()` to prevent concurrent payment race conditions:

```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    # ... process payment ...
```

This ensures:
- Only one payment processed at a time per account
- No double-spending
- Consistent settlement tracking

### Transaction Sign Logic

**Golden Rule**: Transaction sign is decided **BEFORE** balance update, based on **Client_PnL BEFORE payment**.

**Why?**
- Sign represents direction of money flow
- Should reflect trading outcome, not settlement state
- Prevents sign flipping during settlement

---

## Pending Summary View Logic

### View Function: `pending_summary()`

**Purpose**: Display all clients with pending settlement amounts.

### Data Collection

1. **Get All Client Exchanges**:
   ```python
   client_exchanges = ClientExchangeAccount.objects.filter(
       client__user=request.user
   ).select_related("client", "exchange")
   ```

2. **Filter by Search Query** (optional):
   - Client name/code
   - Exchange name/code

3. **For Each Account**:
   - Calculate `Client_PnL`
   - Lock share if needed
   - Get settlement info
   - Categorize into lists

### Categorization Logic

**Three Cases**:

1. **Neutral Case (PnL = 0)**:
   - Show in "Clients Owe You" section
   - Display "N.A" for amounts
   - Always visible (even if no settlement)

2. **Loss Case (PnL < 0)**:
   - Show in "Clients Owe You" section
   - Client owes admin
   - DisplayRemaining = +RemainingRaw (positive)

3. **Profit Case (PnL > 0)**:
   - Show in "You Owe Clients" section
   - Admin owes client
   - DisplayRemaining = -RemainingRaw (negative)

### Display Remaining Sign Logic

**CRITICAL FIX**: Sign is applied at display time:

```python
IF Client_PnL < 0:
    DisplayRemaining = +RemainingRaw  # Client owes you (positive)
ELSE IF Client_PnL > 0:
    DisplayRemaining = -RemainingRaw  # You owe client (negative)
```

**Financial Interpretation**:
- Positive remaining = money owed TO admin
- Negative remaining = money owed BY admin

### Sorting

- Sort by Final Share (descending)
- N.A items sort to bottom (sort key = 0)

### Totals Calculation

```python
total_clients_owe = sum(amount_owed for loss cases)
total_my_share_clients_owe = sum(remaining_amount for loss cases)
total_you_owe = sum(amount_owed for profit cases)
total_my_share_you_owe = sum(remaining_amount for profit cases)
```

**Note**: Uses `remaining_amount` (not total share) for settlement tracking totals.

---

## Display Logic

### Template: `core/pending/summary.html`

### Key Display Rules

1. **Mask Sensitive Values**:
   - Client PnL is masked (not shown directly)
   - Amount owed is masked
   - Only share amounts and remaining are visible

2. **N.A Display**:
   - Show "N.A" when `show_na = True`
   - Occurs when:
     - PnL = 0 (trading flat)
     - FinalShare = 0 (share too small)

3. **Remaining Amount Display**:
   - Positive = Client owes admin
   - Negative = Admin owes client
   - Zero = Fully settled

4. **Share Percentage Display**:
   - Shows current share percentage
   - Uses locked percentage if available

### Sections

1. **Clients Owe You**:
   - Loss cases (PnL < 0)
   - Neutral cases (PnL = 0)
   - DisplayRemaining is positive or N.A

2. **You Owe Clients**:
   - Profit cases (PnL > 0)
   - DisplayRemaining is negative or N.A

---

## Edge Cases and Validations

### Edge Case 1: PnL = 0 (Trading Flat)

**Behavior**:
- Client appears in pending list
- Shows "N.A" for amounts
- No settlement allowed (PnL = 0 check)

**Why Always Visible?**
- May have historical settlements
- User needs to see account status
- Prevents confusion about missing accounts

### Edge Case 2: FinalShare = 0

**Behavior**:
- Client appears in pending list
- Shows "N.A" for amounts
- Settlement blocked (InitialFinalShare = 0 check)

**When Occurs**:
- Share percentage too small
- PnL too small (floor rounding → 0)

### Edge Case 3: Overpayment

**Behavior**:
- Overpaid amount tracked separately
- Historical settlements may exceed current share
- System allows overpayment (by design)

**Why Allowed?**
- Historical accuracy
- Prevents blocking valid historical data
- Overpaid tracked but not blocked

### Edge Case 4: Concurrent Payments

**Prevention**:
- Database row locking (`select_for_update()`)
- Atomic transactions
- Validation before balance update

**Result**:
- Only one payment processed at a time
- No race conditions
- Consistent settlement tracking

### Edge Case 5: Funding Change During Cycle

**Behavior**:
- Cycle resets when funding changes
- Old cycle locks preserved
- New cycle starts with new funding

**Why Reset?**
- New exposure = new cycle
- Old share calculations invalid
- Prevents incorrect settlements

### Edge Case 6: PnL Sign Change

**Behavior**:
- New cycle starts
- Old cycle locks preserved
- Settlements filtered by cycle_start_date

**Result**:
- Each cycle independently settled
- No mixing of old/new settlements
- Historical accuracy maintained

### Validations

1. **Payment Amount**:
   - Must be > 0
   - Must be integer
   - Must be ≤ RemainingAmount

2. **Account State**:
   - PnL ≠ 0 (trading flat check)
   - InitialFinalShare > 0
   - Balance won't go negative

3. **Share Percentage**:
   - Loss share % immutable after data exists
   - Profit share % can change anytime
   - Percentages must be 0-100

---

## Database Models

### ClientExchangeAccount

**Core Fields**:
- `funding`: BIGINT (total money given to client)
- `exchange_balance`: BIGINT (current balance on exchange)
- `loss_share_percentage`: INT (admin share of losses, 0-100)
- `profit_share_percentage`: INT (admin share of profits, 0-100)

**Locking Fields**:
- `locked_initial_final_share`: BIGINT (share locked at cycle start)
- `locked_share_percentage`: INT (percentage locked at cycle start)
- `locked_initial_pnl`: BIGINT (PnL locked at cycle start)
- `cycle_start_date`: DateTime (when cycle started)
- `locked_initial_funding`: BIGINT (funding locked at cycle start)

### Settlement

**Fields**:
- `client_exchange`: ForeignKey (account)
- `amount`: BIGINT (share payment amount, > 0)
- `date`: DateTime (when payment recorded)
- `notes`: Text (optional notes)

**Purpose**: Track individual settlement payments per account per cycle.

### Transaction

**Fields**:
- `client_exchange`: ForeignKey (account)
- `type`: CharField ('RECORD_PAYMENT', etc.)
- `amount`: BIGINT (signed: positive if client pays, negative if admin pays)
- `date`: DateTime
- `exchange_balance_after`: BIGINT (balance after transaction, for audit)
- `notes`: Text

**Purpose**: Audit trail of all transactions.

---

## Key Methods Reference

### `compute_client_pnl()`

**Purpose**: Calculate client profit/loss.

**Formula**: `Client_PnL = ExchangeBalance − Funding`

**Returns**: BIGINT (can be negative)

**Location**: `ClientExchangeAccount.compute_client_pnl()`

---

### `get_share_percentage(client_pnl=None)`

**Purpose**: Get appropriate share percentage based on PnL direction.

**Logic**:
- If PnL < 0: Use `loss_share_percentage` (if > 0) else `my_percentage`
- If PnL > 0: Use `profit_share_percentage` (if > 0) else `my_percentage`
- If PnL = 0: Return 0

**Returns**: INT (0-100)

**Location**: `ClientExchangeAccount.get_share_percentage()`

---

### `compute_my_share()`

**Purpose**: Calculate admin's share using floor rounding.

**Formula**:
```
ExactShare = ABS(Client_PnL) × SharePercentage / 100
FinalShare = FLOOR(ExactShare)
```

**Returns**: BIGINT (always positive, floor rounded)

**Location**: `ClientExchangeAccount.compute_my_share()`

---

### `lock_initial_share_if_needed()`

**Purpose**: Lock share at first compute per PnL cycle.

**When Locked**:
- First time share > 0 is calculated
- PnL cycle changes (sign flip)
- Funding changes

**What Gets Locked**:
- `locked_initial_final_share`
- `locked_share_percentage`
- `locked_initial_pnl`
- `cycle_start_date`
- `locked_initial_funding`

**Location**: `ClientExchangeAccount.lock_initial_share_if_needed()`

---

### `get_remaining_settlement_amount()`

**Purpose**: Calculate remaining settlement amount using locked share.

**Formula**:
```
RemainingRaw = LockedInitialFinalShare − Sum(Settlements from current cycle)
Overpaid = max(0, Sum(Settlements) − LockedInitialFinalShare)
```

**Returns**: Dict with:
- `remaining`: BIGINT (≥ 0, raw value)
- `overpaid`: BIGINT (≥ 0)
- `initial_final_share`: BIGINT (locked share)
- `total_settled`: BIGINT (sum of settlements)

**Location**: `ClientExchangeAccount.get_remaining_settlement_amount()`

---

### `compute_masked_capital(share_payment)`

**Purpose**: Calculate masked capital from share payment.

**Formula**:
```
MaskedCapital = (SharePayment × ABS(LockedInitialPnL)) / LockedInitialFinalShare
```

**Returns**: INT (masked capital amount)

**Location**: `ClientExchangeAccount.compute_masked_capital()`

---

### `pending_summary(request)`

**Purpose**: Display pending payments summary page.

**Logic**:
1. Get all client exchanges for user
2. Filter by search query (optional)
3. For each account:
   - Calculate PnL
   - Lock share
   - Get settlement info
   - Categorize (loss/profit/neutral)
4. Sort lists
5. Calculate totals
6. Render template

**Returns**: HttpResponse (rendered template)

**Location**: `core.views.pending_summary()`

---

### `record_payment(request, account_id)`

**Purpose**: Record a settlement payment.

**Flow**:
1. Load account
2. Validate payment amount
3. Lock account row (prevent concurrent payments)
4. Calculate PnL BEFORE balance update
5. Lock share
6. Get settlement info
7. Validate payment (amount ≤ remaining, balances won't go negative)
8. Calculate transaction sign (BEFORE balance update)
9. Calculate masked capital
10. Update balances
11. Create Settlement record
12. Create Transaction record
13. Save account

**Returns**: HttpResponse (redirect or error)

**Location**: `core.views.record_payment()`

---

## Summary

The Pending Payments system is a comprehensive settlement tracking system that:

1. **Tracks** outstanding settlement amounts between admin and clients
2. **Locks** share amounts at cycle start to prevent shrinkage
3. **Separates** PnL cycles to maintain historical accuracy
4. **Maps** settlements linearly back to PnL using masked capital
5. **Validates** all payments to prevent errors
6. **Displays** clear information about pending amounts

### Key Takeaways

- **Share Locking**: Share never shrinks after payments
- **Cycle Separation**: Each PnL sign change starts new cycle
- **Linear Mapping**: MaskedCapital maps linearly to PnL
- **Always Visible**: Clients always appear in pending list
- **Sign Logic**: Transaction sign based on PnL BEFORE payment
- **Row Locking**: Prevents concurrent payment race conditions

---

## Appendix: Example Scenarios

### Scenario 1: Loss Settlement

**Initial State**:
- Funding = 1000
- Exchange Balance = 500
- Client_PnL = 500 - 1000 = -500 (LOSS)
- Loss Share % = 10%
- FinalShare = FLOOR(500 × 10 / 100) = 50

**After Locking**:
- LockedInitialFinalShare = 50
- LockedInitialPnL = -500

**Payment 1**: SharePayment = 30
- MaskedCapital = (30 × 500) / 50 = 300
- Funding = 1000 - 300 = 700
- Remaining = 50 - 30 = 20

**Payment 2**: SharePayment = 20
- MaskedCapital = (20 × 500) / 50 = 200
- Funding = 700 - 200 = 500
- Remaining = 50 - 50 = 0 (fully settled)

---

### Scenario 2: Profit Settlement

**Initial State**:
- Funding = 500
- Exchange Balance = 1000
- Client_PnL = 1000 - 500 = +500 (PROFIT)
- Profit Share % = 20%
- FinalShare = FLOOR(500 × 20 / 100) = 100

**After Locking**:
- LockedInitialFinalShare = 100
- LockedInitialPnL = +500

**Payment 1**: SharePayment = 60
- MaskedCapital = (60 × 500) / 100 = 300
- Exchange Balance = 1000 - 300 = 700
- Remaining = 100 - 60 = 40

**Payment 2**: SharePayment = 40
- MaskedCapital = (40 × 500) / 100 = 200
- Exchange Balance = 700 - 200 = 500
- Remaining = 100 - 100 = 0 (fully settled)

---

### Scenario 3: PnL Sign Change

**Cycle 1 (Loss)**:
- Funding = 1000, Exchange = 500
- Client_PnL = -500
- LockedInitialFinalShare = 50
- Settlements: 30 (remaining = 20)

**Cycle 2 (Profit)**:
- Funding = 1000, Exchange = 1500 (trading improved)
- Client_PnL = +500 (sign changed!)
- New cycle starts
- LockedInitialFinalShare = 100 (new cycle)
- Old cycle settlements (30) don't count toward new cycle
- Remaining = 100 - 0 = 100 (new cycle)

---

**End of Documentation**

