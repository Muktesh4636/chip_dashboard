# PENDING PAYMENTS SYSTEM - COMPLETE DOCUMENTATION
## End-to-End Logic, Formulas, Edge Cases, and Implementation Details

---

## TABLE OF CONTENTS

1. [System Overview](#1-system-overview)
2. [Core Formulas](#2-core-formulas)
3. [Locked Share Mechanism](#3-locked-share-mechanism)
4. [Data Structure](#4-data-structure)
5. [Pending Payments View Logic](#5-pending-payments-view-logic)
6. [Edge Cases](#6-edge-cases)
7. [Failure Cases and Why They're Prevented](#7-failure-cases-and-why-theyre-prevented)
8. [Record Payment Logic](#8-record-payment-logic)
9. [CSV Export Logic](#9-csv-export-logic)
10. [UI Behavior](#10-ui-behavior)
11. [Sorting and Filtering](#11-sorting-and-filtering)
12. [Business Rules Summary](#12-business-rules-summary)
13. [Concurrency and Race Conditions](#13-concurrency-and-race-conditions)
14. [Code Reference](#14-code-reference)
15. [Testing Scenarios](#15-testing-scenarios)

---

## 1. SYSTEM OVERVIEW

### 1.1 Purpose
The Pending Payments system displays all client-exchange accounts that have outstanding settlements:
- **Clients Owe You**: Accounts where Client_PnL < 0 (loss case)
- **You Owe Clients**: Accounts where Client_PnL > 0 (profit case)
- **Fully Settled**: Accounts where Client_PnL = 0 (shown with N.A values)

### 1.2 Key Principles
- **MASKED SHARE SETTLEMENT SYSTEM**: Uses floor-rounded shares, not raw PnL
- **LOCKED INITIAL SHARE**: FinalShare is locked at first compute and doesn't shrink after payments
- **Always Show Clients**: Even if FinalShare = 0 or Client_PnL = 0, client appears with "N.A" values
- **Share Stability**: Share is decided by trading outcome, not by settlement
- **Remaining Amount Tracking**: Shows how much is left to settle after partial payments (using locked share)
- **Separate Percentages**: Loss and profit use different share percentages
- **Settlement Prevention**: Blocks over-settlement and zero-share settlements
- **Concurrency Safety**: Uses database row locking to prevent race conditions

### 1.3 Three Main Cases

#### Case 1: "Clients Owe You" (Loss Case)
- Client is in loss (Client_PnL < 0)
- Client owes you the full loss amount
- Your share is calculated using `loss_share_percentage`
- You receive settlement payments from client
- Payment reduces `funding` by MaskedCapital
- Share is locked at first compute (doesn't shrink)

#### Case 2: "You Owe Clients" (Profit Case)
- Client is in profit (Client_PnL > 0)
- You owe client your share of the profit
- Your share is calculated using `profit_share_percentage`
- You pay settlement to client
- Payment reduces `exchange_balance` by MaskedCapital
- Share is locked at first compute (doesn't shrink)

#### Case 3: "Fully Settled" (PnL = 0)
- Client_PnL = 0 (fully settled)
- Account appears in "Clients Owe You" section with N.A values
- InitialFinalShare = 0, RemainingAmount = 0
- Locks are reset (no locked share)
- No settlement allowed

---

## 2. CORE FORMULAS

### 2.1 Master Profit/Loss Formula

```
Client_PnL = exchange_balance - funding
```

**Interpretation:**
- `Client_PnL > 0` → Client in PROFIT (you owe client)
- `Client_PnL < 0` → Client in LOSS (client owes you)
- `Client_PnL = 0` → Fully settled (account appears with N.A)

**Data Types:**
- `funding`: BIGINT (stored in database)
- `exchange_balance`: BIGINT (stored in database)
- `Client_PnL`: BIGINT (computed, can be negative)

**Code Location:** `core/models.py` line 114

### 2.2 Exact Share Formula (Before Rounding)

```
ExactShare = ABS(Client_PnL) × (share_percentage / 100.0)
```

**Where:**
- If `Client_PnL < 0` (LOSS): `share_percentage = loss_share_percentage` (or fallback to `my_percentage`)
- If `Client_PnL > 0` (PROFIT): `share_percentage = profit_share_percentage` (or fallback to `my_percentage`)
- If `Client_PnL = 0`: `ExactShare = 0`

**Data Types:**
- `ExactShare`: FLOAT (decimal precision)
- `share_percentage`: INT (0-100, stored as whole number)

**Code Location:** `core/models.py` lines 180-181

### 2.3 Final Share Formula (After Floor Rounding)

```
FinalShare = FLOOR(ExactShare)
```

**Key Points:**
- Uses `math.floor()` to round DOWN (never round up)
- Returns integer (BIGINT)
- Always positive (even for loss cases, we use ABS)
- **This is the amount that can be settled**

**Examples:**
- `ExactShare = 123.99` → `FinalShare = 123`
- `ExactShare = 0.99` → `FinalShare = 0`
- `ExactShare = 0.01` → `FinalShare = 0`
- `ExactShare = 0.0` → `FinalShare = 0`

**Code Location:** `core/models.py` line 184

### 2.4 Initial Final Share (Locked Share)

```
InitialFinalShare = FinalShare (locked at first compute)
```

**Key Points:**
- Locked when first computed (when PnL ≠ 0 and no locked share exists)
- Stored in `locked_initial_final_share` field
- Does NOT change after settlements
- Ensures share is decided by trading outcome, not settlement

**Locking Conditions:**
1. First compute: `Client_PnL ≠ 0` AND `locked_initial_final_share IS NULL`
2. PnL cycle change: Sign flip (loss ↔ profit) AND `FinalShare > 0`
3. Reset: `Client_PnL = 0` → locks reset to NULL

**Code Location:** `core/models.py` lines 170-220

### 2.5 Remaining Settlement Amount Formula (Using Locked Share)

```
RemainingAmount = max(0, InitialFinalShare - SumOfAllSettlements)
OverpaidAmount = max(0, SumOfAllSettlements - InitialFinalShare)
```

**Where:**
- `InitialFinalShare`: LOCKED share (doesn't change after settlements)
- `SumOfAllSettlements = SUM(Settlement.amount WHERE client_exchange = account)`
- `RemainingAmount`: Amount left to settle (clamped to >= 0)
- `OverpaidAmount`: Amount settled beyond locked share (clamped to >= 0)

**CRITICAL:** RemainingAmount uses LOCKED InitialFinalShare, not recalculated share. This ensures:
- Share doesn't shrink after payments
- Share is decided by trading outcome
- Historical settlements don't affect share calculation

**Data Types:**
- `InitialFinalShare`: BIGINT (locked, doesn't change)
- `SumOfAllSettlements`: BIGINT
- `RemainingAmount`: BIGINT (always >= 0)
- `OverpaidAmount`: BIGINT (always >= 0)

**Returns:** Dictionary with:
- `'remaining'`: RemainingAmount
- `'overpaid'`: OverpaidAmount
- `'initial_final_share'`: InitialFinalShare
- `'total_settled'`: SumOfAllSettlements

**Code Location:** `core/models.py` lines 222-257

### 2.6 Masked Capital Formula (Used in Record Payment)

```
MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
```

**Where:**
- `SharePayment`: Amount entered by user (in share units, BIGINT)
- `LockedInitialPnL`: The PnL value when share was locked (BIGINT, absolute value)
- `LockedInitialFinalShare`: The locked share amount (BIGINT)
- `MaskedCapital`: Amount that reduces funding/exchange_balance (BIGINT, converted to int)

**CRITICAL:** This formula maps SharePayment linearly back to PnL, preventing double-counting of share percentage.

**Why This Formula:**
- SharePayment is a portion of FinalShare
- We need to find what portion of the original PnL that represents
- Formula: `(SharePayment / FinalShare) × OriginalPnL = MaskedCapital`
- This ensures proportional reduction of PnL, not exponential

**Application:**
- If `Client_PnL < 0` (LOSS): `Funding = Funding - MaskedCapital`
- If `Client_PnL > 0` (PROFIT): `ExchangeBalance = ExchangeBalance - MaskedCapital`

**Code Location:** `core/views.py` line 3383

**Example:**
- LockedInitialPnL = -70 (loss)
- LockedInitialFinalShare = 7 (10% of 70)
- SharePayment = 3
- MaskedCapital = (3 × 70) ÷ 7 = 30
- Funding reduced by 30
- New PnL = (30 - 30) - 70 = -40 (proportional reduction)

**Why NOT `SharePayment × share_percentage`:**
- ❌ That would be: 3 × 10 = 30 (accidentally correct for this example)
- ❌ But fails for partial payments and different percentages
- ❌ Double-counts the percentage (already applied in FinalShare calculation)
- ❌ Example failure: If SharePayment = 1, share_percentage = 10, MaskedCapital = 10 (wrong!)
- ✅ Correct formula: (1 × 70) ÷ 7 = 10 (proportional to share paid)
- ✅ Correct formula works for ALL cases, ALL percentages, ALL partial payments

**Failure Case Example:**
- Funding = 100, Balance = 30, PnL = -70, Loss % = 10%
- FinalShare = 7 (10% of 70)
- Client pays partial: SharePayment = 3
- ❌ WRONG: MaskedCapital = 3 × 10 = 30 → Funding = 70, New PnL = -40 (not proportional)
- ✅ CORRECT: MaskedCapital = (3 × 70) ÷ 7 = 30 → Same result, but works for ALL cases
- The correct formula ensures SharePayment maps linearly to PnL reduction

---

## 3. LOCKED SHARE MECHANISM

### 3.1 Purpose

The locked share mechanism ensures that:
1. **Share Stability**: Share is decided by trading outcome, not by settlement
2. **No Shrinking**: Share doesn't shrink after payments
3. **Consistency**: Same share amount throughout settlement cycle
4. **Fairness**: Trading PnL determines share, not payment timing

### 3.2 Locking Logic

**Method:** `lock_initial_share_if_needed()`

**Location:** `core/models.py` lines 170-220

#### Step 1: Check if Lock Needed

```python
client_pnl = self.compute_client_pnl()
```

#### Step 2: First Compute Lock

**Condition:** `Client_PnL ≠ 0` AND `locked_initial_final_share IS NULL`

**Action:**
```python
final_share = self.compute_my_share()
if final_share > 0:
    # Determine share percentage
    if client_pnl < 0:
        share_pct = loss_share_percentage or my_percentage
    else:
        share_pct = profit_share_percentage or my_percentage
    
    # Lock the share
    self.locked_initial_final_share = final_share
    self.locked_share_percentage = share_pct
    self.locked_initial_pnl = client_pnl
    self.save()
```

**Result:** Share is locked at first compute.

#### Step 3: PnL Cycle Change Lock

**Condition:** `Client_PnL ≠ 0` AND `locked_initial_pnl ≠ 0` AND sign flip detected

**Action:**
```python
if (client_pnl < 0) != (self.locked_initial_pnl < 0):
    # Sign flip detected (loss ↔ profit)
    final_share = self.compute_my_share()
    if final_share > 0:
        # Lock new share for new cycle
        self.locked_initial_final_share = final_share
        self.locked_share_percentage = share_pct
        self.locked_initial_pnl = client_pnl
        self.save()
```

**Result:** New share locked for new PnL cycle.

#### Step 4: Reset Locks

**Condition:** `Client_PnL = 0`

**Action:**
```python
self.locked_initial_final_share = None
self.locked_share_percentage = None
self.locked_initial_pnl = None
self.save()
```

**Result:** Locks reset, ready for next cycle.

### 3.3 Locked Share Fields

```python
locked_initial_final_share: BIGINT (nullable)
locked_share_percentage: INT (nullable)
locked_initial_pnl: BIGINT (nullable)
```

**Purpose:**
- `locked_initial_final_share`: The locked share amount (doesn't change)
- `locked_share_percentage`: The percentage used to compute locked share
- `locked_initial_pnl`: The PnL value when share was locked (for cycle detection)

### 3.4 Remaining Amount Calculation (Using Locked Share)

**Method:** `get_remaining_settlement_amount()`

**Location:** `core/models.py` lines 222-257

**Algorithm:**
```python
# Lock share if needed
self.lock_initial_share_if_needed()

# Use locked share if available
if self.locked_initial_final_share is not None and self.locked_initial_final_share > 0:
    initial_final_share = self.locked_initial_final_share
else:
    # No locked share yet - use current computed share
    initial_final_share = self.compute_my_share()

# Calculate remaining and overpaid
total_settled = SUM(Settlement.amount)
remaining = max(0, initial_final_share - total_settled)
overpaid = max(0, total_settled - initial_final_share)

return {
    'remaining': remaining,
    'overpaid': overpaid,
    'initial_final_share': initial_final_share,
    'total_settled': total_settled
}
```

**Key Points:**
- Uses locked share if available
- Falls back to current share if not locked yet
- Calculates both remaining and overpaid amounts
- Returns dictionary with all values

### 3.5 Edge Cases in Locking

#### Edge Case: Share Locked Before First Settlement

**Scenario:**
- Client_PnL = -300
- FinalShare = 30 (computed)
- Share locked: InitialFinalShare = 30
- No settlements yet

**Result:**
- RemainingAmount = 30
- OverpaidAmount = 0

#### Edge Case: Partial Settlement

**Scenario:**
- InitialFinalShare = 100 (locked)
- Settlement 1 = 30
- Settlement 2 = 20

**Result:**
- RemainingAmount = 50 (100 - 30 - 20)
- OverpaidAmount = 0

#### Edge Case: Over-Settlement (Prevented by Validation)

**Scenario:**
- InitialFinalShare = 100 (locked)
- Settlement 1 = 100
- Attempt Settlement 2 = 10

**Result:**
- Validation error: "Cannot exceed remaining settlement amount"
- Settlement 2 not processed

#### Edge Case: PnL Cycle Change (Loss → Profit)

**Scenario:**
- Initial: PnL = -300, InitialFinalShare = 30 (locked)
- After trading: PnL = +200
- Sign flip detected

**Result:**
- New share computed: FinalShare = 30 (15% of 200)
- New share locked: InitialFinalShare = 30
- Old settlements still tracked separately
- RemainingAmount = 30 (for new cycle)

#### Edge Case: PnL Returns to Zero

**Scenario:**
- InitialFinalShare = 100 (locked)
- Settlements = 50
- After trading: PnL = 0

**Result:**
- Locks reset: InitialFinalShare = NULL
- RemainingAmount = 0 (no locked share)
- Account shows as fully settled

---

## 4. DATA STRUCTURE

### 4.1 Account Fields (ClientExchangeAccount)

```python
funding: BIGINT              # Total real money given to client
exchange_balance: BIGINT    # Current balance on exchange
my_percentage: INT          # Legacy percentage (0-100)
loss_share_percentage: INT  # Share % for losses (0-100, immutable after data exists)
profit_share_percentage: INT # Share % for profits (0-100, can change anytime)

# Locked Share Fields (CRITICAL FIX)
locked_initial_final_share: BIGINT (nullable)  # Locked share amount
locked_share_percentage: INT (nullable)        # Percentage used for locked share
locked_initial_pnl: BIGINT (nullable)          # PnL when share was locked
```

**Code Location:** `core/models.py` lines 64-84, 170-220

### 4.2 Settlement Model

```python
client_exchange: ForeignKey(ClientExchangeAccount)
amount: BIGINT              # Settlement amount (must be > 0)
date: DateTime             # When settlement was recorded
notes: Text                 # Optional notes
```

**Code Location:** `core/models.py` lines 330-355

### 4.3 Pending Payments List Item Structure

```python
{
    "client": Client object,
    "exchange": Exchange object,
    "account": ClientExchangeAccount object,
    "client_pnl": BIGINT,              # Computed: exchange_balance - funding
    "amount_owed": BIGINT,              # ABS(client_pnl) for loss, client_pnl for profit
    "my_share_amount": BIGINT,          # InitialFinalShare (locked, floor rounded)
    "remaining_amount": BIGINT,         # RemainingAmount (InitialFinalShare - Settlements)
    "overpaid_amount": BIGINT,         # OverpaidAmount (Settlements - InitialFinalShare, if any)
    "share_percentage": INT,            # loss_share_percentage or profit_share_percentage
    "show_na": BOOLEAN                  # True if InitialFinalShare == 0 OR Client_PnL == 0
}
```

**Code Location:** `core/views.py` lines 1038-1048, 1063-1073

---

## 5. PENDING PAYMENTS VIEW LOGIC

### 5.1 View Function: `pending_summary`

**Location:** `core/views.py` lines 913-1125

### 5.2 Step-by-Step Algorithm

#### Step 1: Fetch All Client Exchanges
```python
client_exchanges = ClientExchangeAccount.objects.filter(
    client__user=request.user
).select_related("client", "exchange")
```

**Filtering:**
- Only accounts belonging to the logged-in user
- Uses `select_related` for performance (avoids N+1 queries)

**Code Location:** `core/views.py` lines 990-992

#### Step 2: Apply Search Filter (Optional)
```python
if search_query:
    client_exchanges = client_exchanges.filter(
        Q(client__name__icontains=search_query) |
        Q(client__code__icontains=search_query) |
        Q(exchange__name__icontains=search_query) |
        Q(exchange__code__icontains=search_query)
    )
```

**Search Fields:**
- Client name (case-insensitive)
- Client code (case-insensitive)
- Exchange name (case-insensitive)
- Exchange code (case-insensitive)

**Code Location:** `core/views.py` lines 993-999

#### Step 3: Process Each Account

**For each `client_exchange`:**

1. **Compute Client_PnL**
   ```python
   client_pnl = client_exchange.compute_client_pnl()
   # Formula: exchange_balance - funding
   ```

2. **Determine Case Type**
   ```python
   is_loss_case = client_pnl < 0   # Client owes you
   is_profit_case = client_pnl > 0 # You owe client
   ```

3. **Process Loss Case**
   ```python
   if is_loss_case:
       # CRITICAL FIX: Lock share and use locked share
       client_exchange.lock_initial_share_if_needed()
       settlement_info = client_exchange.get_remaining_settlement_amount()
       initial_final_share = settlement_info['initial_final_share']
       remaining_amount = settlement_info['remaining']
       overpaid_amount = settlement_info['overpaid']
       
       final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
       show_na = (final_share == 0)
       share_pct = loss_share_percentage if loss_share_percentage > 0 else my_percentage
       
       clients_owe_list.append({...})
   ```

4. **Process Profit Case**
   ```python
   if is_profit_case:
       # CRITICAL FIX: Lock share and use locked share
       client_exchange.lock_initial_share_if_needed()
       settlement_info = client_exchange.get_remaining_settlement_amount()
       initial_final_share = settlement_info['initial_final_share']
       remaining_amount = settlement_info['remaining']
       overpaid_amount = settlement_info['overpaid']
       
       final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
       show_na = (final_share == 0)
       share_pct = profit_share_percentage if profit_share_percentage > 0 else my_percentage
       
       you_owe_list.append({...})
   ```

**CRITICAL RULE:** Account is added to list **ALWAYS**, even if `InitialFinalShare == 0` or `Client_PnL == 0`. The `show_na` flag controls UI display.

**Code Location:** `core/views.py` lines 1002-1073

#### Step 4: Sort Lists

**Sort Function:**
```python
def get_sort_key(item):
    if item.get("show_na", False):
        return 0  # N.A items sort to bottom
    if "my_share_amount" in item:
        return abs(item["my_share_amount"])
    elif "amount_owed" in item:
        return abs(item["amount_owed"])
    elif "client_pnl" in item:
        return abs(item["client_pnl"])
    else:
        return 0
```

**Sort Order:**
- Descending by InitialFinalShare (highest first)
- N.A items (InitialFinalShare = 0 or Client_PnL = 0) sort to bottom
- Uses absolute value for sorting

**Code Location:** `core/views.py` lines 1077-1090

#### Step 5: Calculate Totals

```python
total_clients_owe = sum(item.get("amount_owed", 0) for item in clients_owe_list)
total_my_share_clients_owe = sum(item.get("remaining_amount", 0) for item in clients_owe_list)
total_you_owe = sum(item.get("amount_owed", 0) for item in you_owe_list)
total_my_share_you_owe = sum(item.get("remaining_amount", 0) for item in you_owe_list)
```

**Key Points:**
- Totals use `remaining_amount` (not `my_share_amount`) for settlement tracking
- `amount_owed` totals show full amounts (for reference)

**Code Location:** `core/views.py` lines 1093-1096

---

## 6. EDGE CASES

### 6.1 Edge Case: Client_PnL = 0 (Fully Settled)

**Behavior:**
- Account **IS** added to pending list (in "Clients Owe You" section)
- `show_na = True` flag is set
- `initial_final_share = 0` (locks reset)
- `remaining_amount = 0`
- UI displays "N.A" for all values
- "Record Payment" button is hidden or disabled

**Reason:**
- Client must always appear in pending list (business rule)
- Fully settled accounts show N.A to indicate no action needed
- Locks are reset when PnL = 0

**Code:**
```python
if client_pnl == 0:
    # Locks reset
    self.locked_initial_final_share = None
    show_na = True
    clients_owe_list.append({...})
```

**Code Location:** `core/models.py` lines 215-220, `core/views.py` lines 1076-1101

**UI Display:**
- Client PnL: "N.A"
- Final Share: "N.A"
- Remaining: "N.A"
- Record Payment button: Hidden or shows "No Settlement Allowed"

### 6.2 Edge Case: InitialFinalShare = 0 (Zero Share, PnL ≠ 0)

**Behavior:**
- Account **IS** added to pending list
- `show_na = True` flag is set
- `initial_final_share = 0` (but Client_PnL ≠ 0)
- `remaining_amount = 0`
- UI displays "N.A" for Final Share, Remaining, and Client PnL
- "Record Payment" button is hidden or disabled

**Reason:**
- Client must always appear in pending list (business rule)
- Zero share means share percentage too small or PnL too small
- Cannot settle zero share (blocked in record_payment)

**Code:**
```python
show_na = (final_share == 0)
# Account still added to list
```

**Code Location:** `core/views.py` lines 1027, 1066

**UI Display:**
- Final Share: "N.A"
- Remaining: "N.A"
- Client PnL: "N.A" (masked)
- Record Payment button: Hidden or shows "No Settlement Allowed"

### 6.3 Edge Case: RemainingAmount = 0 (Fully Settled Share, PnL ≠ 0)

**Behavior:**
- Account appears in pending list
- `remaining_amount = 0`
- `initial_final_share` may still be > 0 (locked share)
- "Record Payment" button shows "Settled" or is disabled
- Client_PnL may not be zero yet

**Reason:**
- Share has been fully settled, but Client_PnL may not be zero yet
- Account remains in list until Client_PnL = 0
- RemainingAmount uses locked share, so it's stable

**Code:**
```python
remaining_amount = max(0, initial_final_share - total_settled)
# Clamped to 0 if negative
```

**Code Location:** `core/models.py` line 249

**UI Display:**
- Remaining: "0" or "Settled"
- Record Payment button: Disabled or shows "Fully Settled"

### 6.4 Edge Case: OverpaidAmount > 0 (Settlements Exceed Locked Share)

**Behavior:**
- Account appears in pending list
- `overpaid_amount > 0`
- `remaining_amount = 0` (clamped)
- Historical settlements exceed locked share
- "Record Payment" button disabled

**Reason:**
- Can occur if share was locked after some settlements
- Or if PnL cycle changed and new share is smaller
- System tracks overpaid but doesn't allow more settlements

**Code:**
```python
overpaid = max(0, total_settled - initial_final_share)
```

**Code Location:** `core/models.py` line 250

**UI Display:**
- Remaining: "0"
- Overpaid: Tracked but may not be shown in UI
- Record Payment button: Disabled

### 6.5 Edge Case: RemainingAmount < InitialFinalShare (Partial Settlement)

**Behavior:**
- Account appears in pending list
- `remaining_amount < initial_final_share`
- "Record Payment" button is enabled
- User can record additional partial payments

**Example:**
- InitialFinalShare = 100 (locked)
- Settlements = 30
- RemainingAmount = 70

**Code:**
```python
remaining_amount = initial_final_share - total_settled
# Can be less than InitialFinalShare if partial payments made
```

**Code Location:** `core/models.py` line 249

### 6.6 Edge Case: loss_share_percentage = 0 (Uses Fallback)

**Behavior:**
- Falls back to `my_percentage`
- If `my_percentage` also = 0, InitialFinalShare = 0

**Code:**
```python
share_pct = loss_share_percentage if loss_share_percentage > 0 else my_percentage
```

**Code Location:** `core/models.py` line 192, `core/views.py` line 1035

**Reason:**
- Backward compatibility with old accounts
- Ensures percentage always has a value

### 6.7 Edge Case: profit_share_percentage = 0 (Uses Fallback)

**Behavior:**
- Falls back to `my_percentage`
- If `my_percentage` also = 0, InitialFinalShare = 0

**Code:**
```python
share_pct = profit_share_percentage if profit_share_percentage > 0 else my_percentage
```

**Code Location:** `core/models.py` line 194, `core/views.py` line 1060

### 6.8 Edge Case: ExactShare < 1.0 (Rounds to Zero)

**Behavior:**
- `ExactShare = 0.99` → `FinalShare = 0`
- `ExactShare = 0.01` → `FinalShare = 0`
- Account appears with `show_na = True`
- Share not locked (FinalShare = 0)

**Code:**
```python
final_share = math.floor(exact_share)
# Floor rounds down, so 0.99 → 0
```

**Code Location:** `core/models.py` line 184

**Reason:**
- Floor rounding ensures no fractional settlements
- Small amounts round to zero (business rule)
- Zero share not locked

### 6.9 Edge Case: Multiple Settlements (Sum > InitialFinalShare)

**Behavior:**
- **PREVENTED** by validation in `record_payment`
- Cannot record settlement if `paid_amount > remaining_amount`
- System ensures `SumOfSettlements <= InitialFinalShare` (at time of settlement)

**Code:**
```python
if paid_amount > remaining_amount:
    raise ValidationError("Cannot exceed remaining settlement amount")
```

**Code Location:** `core/views.py` lines 3340-3344

**Reason:**
- Prevents over-settlement
- Ensures data integrity
- Uses locked share for validation

### 6.10 Edge Case: Account Has No Settlements Yet

**Behavior:**
- `total_settled = 0`
- `remaining_amount = initial_final_share`
- Account appears with full remaining amount
- Share locked at first compute

**Code:**
```python
total_settled = self.settlements.aggregate(total=Sum('amount'))['total'] or 0
remaining_amount = initial_final_share - total_settled
```

**Code Location:** `core/models.py` lines 244-249

### 6.11 Edge Case: Search Returns No Results

**Behavior:**
- Empty list passed to template
- Template shows "No clients found" message
- Totals show 0

**Code:**
```python
if not clients_owe_list:
    # Template shows empty state
```

### 6.12 Edge Case: PnL Cycle Change (Loss → Profit or Vice Versa)

**Behavior:**
- Sign flip detected: `(client_pnl < 0) != (locked_initial_pnl < 0)`
- New share computed and locked
- Old settlements still tracked
- RemainingAmount calculated from new locked share

**Example:**
- Initial: PnL = -300, InitialFinalShare = 30 (locked)
- After trading: PnL = +200
- New share: FinalShare = 30 (15% of 200)
- New share locked: InitialFinalShare = 30

**Code:**
```python
if (client_pnl < 0) != (self.locked_initial_pnl < 0):
    # Sign flip - lock new share
    final_share = self.compute_my_share()
    if final_share > 0:
        self.locked_initial_final_share = final_share
```

**Code Location:** `core/models.py` lines 200-214

### 6.13 Edge Case: Share Locked After Some Settlements

**Behavior:**
- Some settlements exist before share is locked
- Share locked at first compute
- RemainingAmount = InitialFinalShare - SumOfSettlements
- May result in OverpaidAmount > 0 if settlements exceed locked share

**Example:**
- Settlements = 50 (before locking)
- Share computed: FinalShare = 30
- Share locked: InitialFinalShare = 30
- RemainingAmount = 30 - 50 = -20 → clamped to 0
- OverpaidAmount = 50 - 30 = 20

**Code Location:** `core/models.py` lines 249-250

---

## 7. FAILURE CASES AND WHY THEY'RE PREVENTED

### 7.1 Failure Case 1: MaskedCapital Double-Counting Percentage

#### ❌ WRONG FORMULA (Old Implementation)

**Formula:**
```
MaskedCapital = SharePayment × share_percentage
```

**Why This Fails:**

1. **Double-Counting**: The percentage is already applied in FinalShare calculation
   - FinalShare = FLOOR(ABS(PnL) × share_percentage / 100)
   - Using `SharePayment × share_percentage` applies the percentage AGAIN

2. **Not Proportional**: Doesn't map SharePayment linearly to PnL
   - SharePayment is a portion of FinalShare
   - Should map proportionally: `(SharePayment / FinalShare) × OriginalPnL`

3. **Works Only by Coincidence**: In some cases, results match by accident
   - Example: SharePayment = 3, share_percentage = 10 → MaskedCapital = 30
   - But fails for different percentages or partial payments

**Example Failure:**

**Given:**
- Funding = 100
- Exchange Balance = 30
- PnL = -70 (loss)
- Loss % = 10%

**Share Calculation (OK):**
- ExactShare = 70 × 10% = 7
- FinalShare = 7

**Client pays partial:**
- SharePayment = 3

**❌ WRONG Formula Does:**
```
MaskedCapital = SharePayment × share_percentage
MaskedCapital = 3 × 10 = 30
```

**❌ Result:**
- Funding = 100 − 30 = 70
- New PnL = 30 − 70 = -40
- Client paid 3 / 7 = ~42.8% of share
- Loss reduced by 30, not proportional to PnL
- This only "looks OK" because numbers are small

**✅ CORRECT Formula Does:**
```
MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
MaskedCapital = (3 × 70) ÷ 7 = 30
```

**✅ Result:**
- Same result here, BUT works for ALL partials, ALL percentages, ALL rounding
- Maps SharePayment linearly to PnL reduction
- Proportional: 3/7 of share = 3/7 of PnL reduction

**Why Correct Formula Works:**

The correct formula ensures:
- **Proportional Mapping**: SharePayment maps linearly to PnL
- **No Double-Counting**: Percentage applied only once (in FinalShare)
- **Universal**: Works for all percentages, all partial payments, all rounding cases

**Code Prevention:**
```python
# CORRECT FORMULA: MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)
```

**Code Location:** `core/views.py` line 3383

---

### 7.2 Failure Case 2: Settlement Shrinks Share (Without Lock)

#### ❌ WRONG SYSTEM (Dynamic Recalculation - Old)

**Problem:** Share recalculated after each settlement, causing it to shrink.

**Example:**

**Initial:**
- Funding = 1000
- Exchange Balance = 700
- PnL = -300
- Loss % = 10%
- FinalShare = 30

**Client pays full share:**
- SharePayment = 30
- MaskedCapital = 300 (using wrong formula: 30 × 10)
- Funding = 700

**❌ Recalculation (WRONG):**
- New PnL = 700 − 700 = 0
- New FinalShare = 0

**❌ Problem:**
- Share disappears because settlement changed PnL
- Historical settlements become invalid
- Cannot track what was originally owed

#### ✅ CORRECT SYSTEM (Locked Share - Current)

**Solution:** Lock InitialFinalShare at first compute, never recalculate.

**Example:**

**Initial:**
- Funding = 1000
- Exchange Balance = 700
- PnL = -300
- Loss % = 10%
- FinalShare = 30
- **Share LOCKED**: InitialFinalShare = 30

**Client pays full share:**
- SharePayment = 30
- MaskedCapital = (30 × 300) ÷ 30 = 300
- Funding = 700

**✅ Result (CORRECT):**
- New PnL = 700 − 700 = 0
- **InitialFinalShare = 30** (still locked, doesn't change)
- RemainingAmount = 30 − 30 = 0
- Share history preserved

**Why Locked Share Works:**

1. **Share Stability**: Share decided by trading outcome, not settlement
2. **No Shrinking**: Share doesn't shrink after payments
3. **History Preserved**: Can always see original share amount
4. **Consistency**: Same share amount throughout settlement cycle

**Code Prevention:**
```python
# Lock share at first compute
self.lock_initial_share_if_needed()

# Use locked share for remaining calculation
if self.locked_initial_final_share is not None:
    initial_final_share = self.locked_initial_final_share
```

**Code Location:** `core/models.py` lines 176-220, 239-240

---

### 7.3 Failure Case 3: Concurrent Payment Race Condition

#### ❌ WRONG SYSTEM (No Locking)

**Problem:** Multiple users can pay simultaneously, causing over-settlement.

**Example:**

**Initial:**
- InitialFinalShare = 100 (locked)
- RemainingAmount = 100

**User A and User B try to pay simultaneously:**
- Both see RemainingAmount = 100
- Both try to pay 100
- Both payments succeed
- Result: 200 paid when only 100 should be paid

#### ✅ CORRECT SYSTEM (Database Row Locking)

**Solution:** Use `select_for_update()` to lock database row during payment.

**Code Prevention:**
```python
with transaction.atomic():
    # Lock the account row to prevent concurrent modifications
    account = (
        ClientExchangeAccount.objects
        .select_for_update()
        .get(pk=account_id, client__user=request.user)
    )
    
    # Recalculate values with locked account
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    
    # Validate against locked account
    if paid_amount > remaining_amount:
        raise ValidationError("Cannot exceed remaining amount")
    
    # Process payment
    # ...
```

**Code Location:** `core/views.py` lines 3307-3313

**Why Database Locking Works:**

1. **Atomic Operations**: Payment validation and processing are atomic
2. **Sequential Processing**: Other transactions wait for lock
3. **Prevents Race Conditions**: Cannot over-settle
4. **Data Integrity**: Ensures accurate remaining amounts

---

### 7.4 Failure Case 4: Negative Balance After Payment

#### ❌ WRONG SYSTEM (No Validation)

**Problem:** Payment could reduce funding/exchange_balance below zero.

**Example:**

**Initial:**
- Funding = 50
- PnL = -300
- InitialFinalShare = 30
- User tries to pay 30
- MaskedCapital = 300

**❌ Without Validation:**
- Funding = 50 − 300 = -250 (NEGATIVE!)
- System breaks

#### ✅ CORRECT SYSTEM (Validation Before Payment)

**Solution:** Validate that payment won't cause negative balance.

**Code Prevention:**
```python
# Calculate MaskedCapital
masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)

# Validate funding/exchange_balance won't go negative
if client_pnl < 0:
    if account.funding - int(masked_capital) < 0:
        raise ValidationError(
            f"Cannot record payment. Funding would become negative "
            f"(Current: {account.funding}, Masked Capital: {int(masked_capital)})."
        )
else:
    if account.exchange_balance - int(masked_capital) < 0:
        raise ValidationError(
            f"Cannot record payment. Exchange balance would become negative "
            f"(Current: {account.exchange_balance}, Masked Capital: {int(masked_capital)})."
        )
```

**Code Location:** `core/views.py` lines 3385-3403

**Why Validation Works:**

1. **Prevents Negative Balances**: Ensures funding/exchange_balance >= 0
2. **Clear Error Messages**: User knows why payment failed
3. **Data Integrity**: Maintains valid account states
4. **User-Friendly**: Prevents system errors

---

### 7.5 Summary: All Failure Cases Prevented

| Failure Case | Wrong Approach | Correct Approach | Status |
|--------------|----------------|------------------|--------|
| **Double-Counting %** | `MaskedCapital = SharePayment × share_percentage` | `MaskedCapital = (SharePayment × \|LockedInitialPnL\|) ÷ LockedInitialFinalShare` | ✅ PREVENTED |
| **Share Shrinking** | Recalculate share after each settlement | Lock share at first compute | ✅ PREVENTED |
| **Race Conditions** | No database locking | `select_for_update()` row locking | ✅ PREVENTED |
| **Negative Balance** | No validation | Validate before payment | ✅ PREVENTED |
| **Over-Settlement** | No validation | Validate against RemainingAmount | ✅ PREVENTED |

**All failure cases are prevented by the current implementation.**

---

## 8. RECORD PAYMENT LOGIC

### 7.1 View Function: `record_payment`

**Location:** `core/views.py` lines 3244-3450

### 7.2 Step-by-Step Algorithm

#### Step 1: Fetch Account and Calculate Values (GET Request)
```python
account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
client_pnl = account.compute_client_pnl()
redirect_to = request.GET.get('redirect_to', 'exchange_account_detail')

# Lock share if needed
account.lock_initial_share_if_needed()

# Calculate FinalShare using MASKED SHARE SETTLEMENT SYSTEM
final_share = account.compute_my_share()
settlement_info = account.get_remaining_settlement_amount()
remaining_amount = settlement_info['remaining']
overpaid_amount = settlement_info['overpaid']
initial_final_share = settlement_info['initial_final_share']
```

**Code Location:** `core/views.py` lines 3262-3275

#### Step 2: Validate Input (POST Request)

**2.1 Check Paid Amount Provided**
```python
paid_amount_str = request.POST.get("amount", "").strip()
if not paid_amount_str:
    return error("Paid amount is required.")
```

**Code Location:** `core/views.py` lines 3277-3288

**2.2 Validate Paid Amount is Integer**
```python
try:
    paid_amount = int(paid_amount_str)
except ValueError:
    return error("Invalid amount. Must be an integer.")
```

**Code Location:** `core/views.py` lines 3290-3300

**2.3 Validate Paid Amount > 0**
```python
if paid_amount <= 0:
    return error("Paid amount must be greater than zero.")
```

**Code Location:** `core/views.py` lines 3292-3300

#### Step 3: Database Row Locking (CRITICAL for Concurrency)

```python
with transaction.atomic():
    # Lock the account row to prevent concurrent modifications
    account = (
        ClientExchangeAccount.objects
        .select_for_update()
        .get(pk=account_id, client__user=request.user)
    )
```

**Key Points:**
- Uses `select_for_update()` to lock row
- Prevents race conditions in concurrent payments
- Ensures atomic settlement validation

**Code Location:** `core/views.py` lines 3302-3313

#### Step 4: Recalculate Values with Locked Account

```python
# Recalculate values with locked account (may have changed)
client_pnl = account.compute_client_pnl()

# CRITICAL FIX: Lock share at first compute per PnL cycle
account.lock_initial_share_if_needed()

# Get settlement info using LOCKED share
settlement_info = account.get_remaining_settlement_amount()
initial_final_share = settlement_info['initial_final_share']
remaining_amount = settlement_info['remaining']
overpaid_amount = settlement_info['overpaid']
total_settled = settlement_info['total_settled']
```

**Code Location:** `core/views.py` lines 3315-3326

#### Step 5: Validate Settlement

**5.1 Block if InitialFinalShare = 0**
```python
if initial_final_share == 0:
    return warning("No settlement allowed. Initial final share is zero.")
    # Redirects back, does not process payment
```

**Code Location:** `core/views.py` lines 3328-3337

**5.2 Validate Against Remaining Amount**
```python
if paid_amount > remaining_amount:
    raise ValidationError(
        f"Paid amount ({paid_amount}) cannot exceed remaining settlement amount ({remaining_amount}). "
        f"Initial share: {initial_final_share}, Already settled: {total_settled}"
    )
```

**Code Location:** `core/views.py` lines 3339-3344

**5.3 Check if Already Settled**
```python
if client_pnl == 0:
    return warning("Account is already fully settled. No payment needed.")
    # Redirects back, does not process payment
```

**Code Location:** `core/views.py` lines 3346-3352

**5.4 Prevent Negative Funding/Balance**
```python
                    # Calculate MaskedCapital using CORRECT formula
                    # Formula: MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
                    locked_initial_pnl = account.locked_initial_pnl
                    if locked_initial_pnl is None:
                        locked_initial_pnl = abs(client_pnl)
                    
                    masked_capital = int((paid_amount * abs(locked_initial_pnl)) / initial_final_share)

# Check if payment would result in negative balance
if client_pnl < 0:
    if account.funding < masked_capital:
        raise ValidationError(f"Insufficient funding. Current: {account.funding}, Required: {masked_capital}")
else:
    if account.exchange_balance < masked_capital:
        raise ValidationError(f"Insufficient exchange balance. Current: {account.exchange_balance}, Required: {masked_capital}")
```

**Code Location:** `core/views.py` lines 3354-3368

#### Step 6: Apply Payment to Account

**6.1 Loss Case (Client_PnL < 0)**
```python
if client_pnl < 0:
    old_funding = account.funding
    account.funding -= int(masked_capital)
    account.save()
    # Funding reduced by MaskedCapital
```

**Code Location:** `core/views.py` lines 3370-3375

**6.2 Profit Case (Client_PnL > 0)**
```python
else:
    old_balance = account.exchange_balance
    account.exchange_balance -= int(masked_capital)
    account.save()
    # Exchange Balance reduced by MaskedCapital
```

**Code Location:** `core/views.py` lines 3376-3381

**Key Points:**
- MaskedCapital is converted to integer (truncated, not rounded)
- Only one field changes (funding OR exchange_balance)
- Never change both simultaneously
- Transaction is atomic (within `transaction.atomic()`)

#### Step 7: Create Settlement Record

```python
Settlement.objects.create(
    client_exchange=account,
    amount=paid_amount,  # Store SharePayment amount
    notes=notes or f"Payment recorded: {paid_amount}..."
)
```

**Key Points:**
- Stores `paid_amount` (SharePayment), not MaskedCapital
- Settlement records track share payments
- Used to calculate remaining settlement amount

**Code Location:** `core/views.py` lines 3383-3387

#### Step 8: Create Transaction Record (Audit Trail)

```python
Transaction.objects.create(
    client_exchange=account,
    date=timezone.now(),
    type='RECORD_PAYMENT',
    amount=paid_amount,
    exchange_balance_after=account.exchange_balance,
    notes=notes
)
```

**Key Points:**
- Audit trail for all money movements
- Not used for balance recomputation
- For reporting and history only

**Code Location:** `core/views.py` lines 3389-3397

#### Step 9: Recompute Values and Show Success

```python
new_pnl = account.compute_client_pnl()
new_final_share = account.compute_my_share()
new_settlement_info = account.get_remaining_settlement_amount()
new_remaining = new_settlement_info['remaining']

if new_pnl == 0:
    messages.success(request, "Account is now fully settled!")
elif new_remaining == 0:
    messages.success(request, "Share is now fully settled!")
else:
    messages.success(request, "Payment recorded successfully.")
```

**Code Location:** `core/views.py` lines 3399-3410

### 7.3 Validation Rules Summary

| Rule | Condition | Action |
|------|-----------|--------|
| Amount Required | `paid_amount` is empty | Error: "Paid amount is required." |
| Amount Must Be Integer | `paid_amount` is not integer | Error: "Invalid amount." |
| Amount Must Be Positive | `paid_amount <= 0` | Error: "Must be greater than zero." |
| Block Zero Share | `initial_final_share == 0` | Warning: "No settlement allowed." |
| Prevent Over-Settlement | `paid_amount > remaining_amount` | Error: "Cannot exceed remaining amount." |
| Block Settled Account | `client_pnl == 0` | Warning: "Already fully settled." |
| Prevent Negative Funding | `funding < masked_capital` (loss case) | Error: "Insufficient funding." |
| Prevent Negative Balance | `exchange_balance < masked_capital` (profit case) | Error: "Insufficient exchange balance." |

### 7.4 Edge Cases in Record Payment

#### Edge Case: Partial Payment Leaves Remaining Amount

**Example:**
- InitialFinalShare = 100 (locked)
- RemainingAmount = 100
- User pays 30
- New RemainingAmount = 70

**Behavior:**
- Payment is recorded
- Account remains in pending list
- User can record additional payments

#### Edge Case: Full Payment (RemainingAmount = 0)

**Example:**
- InitialFinalShare = 100 (locked)
- RemainingAmount = 100
- User pays 100
- New RemainingAmount = 0

**Behavior:**
- Payment is recorded
- Account remains in pending list (until Client_PnL = 0)
- "Record Payment" button disabled or shows "Settled"

#### Edge Case: Concurrent Payment Attempts (Race Condition)

**Scenario:**
- User A and User B try to pay simultaneously
- Both see RemainingAmount = 100
- Both try to pay 100

**Behavior:**
- Database row locking prevents race condition
- First payment succeeds
- Second payment fails validation (RemainingAmount = 0)

**Code:**
```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(...)
    # Row is locked, other transactions wait
```

**Code Location:** `core/views.py` lines 3307-3313

---

## 9. CSV EXPORT LOGIC

### 8.1 View Function: `export_pending_csv`

**Location:** `core/views.py` lines 1138-1325

### 8.2 Key Features

1. **Mirrors UI Logic**: Uses exact same data building logic as `pending_summary`
2. **Search Filtering**: Applies same search filter as UI
3. **Section Filtering**: Can export "clients-owe", "you-owe", or "all"
4. **N.A Handling**: Shows "N.A" for zero-share accounts and settled accounts
5. **Same Sorting**: Uses same sort function as UI
6. **Locked Share**: Uses locked share for remaining calculation

### 8.3 CSV Columns

```
Client Name, Client Code, Exchange Name, Exchange Code,
Funding, Exchange Balance, Client PnL, Final Share, Remaining, Share %
```

**Column Details:**
- **Client Name**: `client.name`
- **Client Code**: `client.code` (or empty)
- **Exchange Name**: `exchange.name`
- **Exchange Code**: `exchange.code` (or empty)
- **Funding**: `account.funding` (integer)
- **Exchange Balance**: `account.exchange_balance` (integer)
- **Client PnL**: `client_pnl` (or "N.A" if `show_na`)
- **Final Share**: `my_share_amount` (InitialFinalShare, or "N.A" if `show_na`)
- **Remaining**: `remaining_amount` (or "N.A" if `show_na`)
- **Share %**: `share_percentage` (integer)

**Code Location:** `core/views.py` lines 1293-1305

### 8.4 N.A Handling in CSV

```python
'N.A' if item.get("show_na", False) else int(item["client_pnl"])
'N.A' if item.get("show_na", False) else int(item["my_share_amount"])
'N.A' if item.get("show_na", False) else int(item.get("remaining_amount", 0))
```

**Behavior:**
- If `show_na = True`, column shows "N.A" (string)
- If `show_na = False`, column shows integer value
- Ensures CSV matches UI display exactly

**Code Location:** `core/views.py` lines 1317, 1318, 1319, 1328, 1329, 1330

### 8.5 CSV File Naming

```python
filename = f"pending_payments_{date.today().strftime('%Y%m%d')}.csv"
# Example: pending_payments_20260108.csv
```

**Code Location:** `core/views.py` line 1287

---

## 10. UI BEHAVIOR

### 9.1 Two-Tab Interface

**Tab 1: "Clients Owe You"**
- Shows accounts where Client_PnL < 0 OR Client_PnL = 0
- Displays loss amounts
- Shows your share (using loss_share_percentage)
- Uses locked share for remaining calculation

**Tab 2: "You Owe Clients"**
- Shows accounts where Client_PnL > 0
- Displays profit amounts
- Shows your share (using profit_share_percentage)
- Uses locked share for remaining calculation

### 9.2 Table Columns

**Columns Displayed:**
1. Client (name and code)
2. Exchange (name and code)
3. Funding (BIGINT, displayed as integer)
4. Exchange Balance (BIGINT, displayed as integer)
5. Client PnL (BIGINT or "N.A")
6. Final Share (BIGINT or "N.A") - Shows InitialFinalShare (locked)
7. Remaining (BIGINT or "N.A") - Shows RemainingAmount (using locked share)
8. Share % (INT, 0-100)
9. Actions (Record Payment button, View Account link)

**Hidden Columns (Masked):**
- Amount Owed (not shown, only Remaining)
- Overpaid Amount (tracked but may not be shown)

### 9.3 N.A Display Rules

**When to Show "N.A":**
- `show_na = True` (InitialFinalShare = 0 OR Client_PnL = 0)

**What Shows "N.A":**
- Client PnL column
- Final Share column
- Remaining column

**What Still Shows Values:**
- Funding (always shows value)
- Exchange Balance (always shows value)
- Share % (always shows percentage)

**Code Location:** `core/templates/core/pending/summary.html` lines 93-100, 99-106

### 9.4 Record Payment Button

**Visibility Rules:**
- **Shown**: If `remaining_amount > 0` AND `initial_final_share > 0` AND `client_pnl != 0`
- **Hidden**: If `remaining_amount = 0` OR `initial_final_share = 0` OR `client_pnl = 0`
- **Disabled**: If `show_na = True`

**Button States:**
- **Enabled**: "Record Payment" (clickable)
- **Disabled**: "No Settlement Allowed" or "Settled" (not clickable)

**Code Location:** `core/templates/core/pending/summary.html` lines 108-115

### 9.5 Totals Display

**Totals Shown:**
- Total Clients Owe: Sum of `amount_owed` (for reference)
- Total My Share (Clients Owe): Sum of `remaining_amount` (for settlement tracking)
- Total You Owe: Sum of `amount_owed` (for reference)
- Total My Share (You Owe): Sum of `remaining_amount` (for settlement tracking)

**Key Point:** Totals use `remaining_amount` (not `my_share_amount`) to show how much is left to settle.

**Code Location:** `core/templates/core/pending/summary.html` lines 45-53

### 9.6 Search Bar

**Search Fields:**
- Client name (case-insensitive)
- Client code (case-insensitive)
- Exchange name (case-insensitive)
- Exchange code (case-insensitive)

**Behavior:**
- Filters accounts in real-time
- Applies to both "Clients Owe You" and "You Owe Clients" sections
- Search is case-insensitive partial match

**Code Location:** `core/templates/core/pending/summary.html` lines 8-22

---

## 11. SORTING AND FILTERING

### 10.1 Sort Function

```python
def get_sort_key(item):
    if item.get("show_na", False):
        return 0  # N.A items sort to bottom
    if "my_share_amount" in item:
        return abs(item["my_share_amount"])
    elif "amount_owed" in item:
        return abs(item["amount_owed"])
    elif "client_pnl" in item:
        return abs(item["client_pnl"])
    else:
        return 0
```

**Sort Order:**
- Descending (highest first)
- N.A items (InitialFinalShare = 0 or Client_PnL = 0) sort to bottom
- Uses absolute value for sorting

**Priority:**
1. `my_share_amount` (InitialFinalShare) - primary sort key
2. `amount_owed` - fallback if InitialFinalShare not available
3. `client_pnl` - fallback if amount_owed not available
4. `0` - for N.A items or missing data

**Code Location:** `core/views.py` lines 1077-1090

### 10.2 Search Filtering

**Filter Applied:**
```python
Q(client__name__icontains=search_query) |
Q(client__code__icontains=search_query) |
Q(exchange__name__icontains=search_query) |
Q(exchange__code__icontains=search_query)
```

**Behavior:**
- Case-insensitive partial match
- Searches across client and exchange names/codes
- Applied before list building (filters accounts)

**Code Location:** `core/views.py` lines 993-999

---

## 12. BUSINESS RULES SUMMARY

### 11.1 Core Rules

1. **Always Show Clients**: Even if InitialFinalShare = 0 or Client_PnL = 0, client appears with "N.A" values
2. **Locked Share**: FinalShare is locked at first compute and doesn't shrink after payments
3. **Share Stability**: Share is decided by trading outcome, not by settlement
4. **Floor Rounding**: FinalShare always uses floor() (round down)
5. **Separate Percentages**: Loss and profit use different share percentages
6. **Remaining Tracking**: Shows remaining amount after settlements (using locked share)
7. **Prevent Over-Settlement**: Cannot settle more than RemainingAmount
8. **Block Zero Share**: Cannot settle if InitialFinalShare = 0
9. **Block Settled Account**: Cannot settle if Client_PnL = 0
10. **Concurrency Safety**: Uses database row locking to prevent race conditions

### 11.2 Data Integrity Rules

1. **Settlement Sum <= RemainingAmount**: System ensures settlements never exceed RemainingAmount at time of settlement
2. **RemainingAmount >= 0**: Clamped to 0 if negative
3. **OverpaidAmount >= 0**: Clamped to 0 if negative
4. **MaskedCapital Calculation**: Uses same percentage as FinalShare
5. **Single Field Update**: Only funding OR exchange_balance changes, never both
6. **Locked Share Stability**: InitialFinalShare doesn't change after locking
7. **No Negative Balances**: Prevents funding/exchange_balance from going negative

### 11.3 Display Rules

1. **Mask PnL Values**: Client PnL is masked, only Final Share shown prominently
2. **N.A for Zero Share**: Shows "N.A" when InitialFinalShare = 0
3. **N.A for Settled**: Shows "N.A" when Client_PnL = 0
4. **Remaining Amount**: Always shows remaining (using locked share)
5. **Share Percentage**: Shows correct percentage (loss or profit)

### 11.4 Validation Rules

1. **Amount Required**: Paid amount must be provided
2. **Amount Must Be Integer**: No decimals allowed
3. **Amount Must Be Positive**: Must be > 0
4. **Block Zero Share**: Cannot settle if InitialFinalShare = 0
5. **Prevent Over-Settlement**: Cannot exceed RemainingAmount
6. **Block Settled Account**: Cannot settle if Client_PnL = 0
7. **Prevent Negative Funding**: Cannot reduce funding below 0 (loss case)
8. **Prevent Negative Balance**: Cannot reduce exchange_balance below 0 (profit case)

---

## 13. CONCURRENCY AND RACE CONDITIONS

### 12.1 Problem

**Race Condition Scenario:**
- User A and User B view pending payments simultaneously
- Both see RemainingAmount = 100
- Both try to pay 100
- Without locking, both payments could succeed
- Result: Over-settlement (200 paid when only 100 should be)

### 12.2 Solution: Database Row Locking

**Implementation:**
```python
with transaction.atomic():
    # Lock the account row to prevent concurrent modifications
    account = (
        ClientExchangeAccount.objects
        .select_for_update()
        .get(pk=account_id, client__user=request.user)
    )
    
    # Recalculate values with locked account
    settlement_info = account.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    
    # Validate against locked account
    if paid_amount > remaining_amount:
        raise ValidationError("Cannot exceed remaining amount")
    
    # Process payment
    # ...
```

**Key Points:**
- `select_for_update()` locks the database row
- Other transactions wait until lock is released
- Ensures atomic validation and settlement
- Prevents race conditions

**Code Location:** `core/views.py` lines 3307-3313

### 12.3 Lock Behavior

**When Lock is Acquired:**
- At start of `transaction.atomic()` block
- When `select_for_update()` is called
- Lock held until transaction commits or rolls back

**What Happens to Other Transactions:**
- Wait for lock to be released
- Then proceed with their own validation
- Ensures sequential processing

**Performance Impact:**
- Minimal for normal usage
- Only affects concurrent payment attempts
- Lock released immediately after transaction

---

## 14. CODE REFERENCE

### 13.1 Key Functions

**Models (`core/models.py`):**
- `compute_client_pnl()`: Calculates Client_PnL (line 114)
- `compute_my_share()`: Calculates FinalShare with floor rounding (lines 123-198)
- `lock_initial_share_if_needed()`: Locks share at first compute (lines 170-220)
- `get_remaining_settlement_amount()`: Calculates RemainingAmount using locked share (lines 222-257)
- `clean()`: Validates loss_share_percentage immutability (lines 267-294)

**Views (`core/views.py`):**
- `pending_summary()`: Main pending payments view (lines 913-1125)
- `export_pending_csv()`: CSV export view (lines 1138-1325)
- `record_payment()`: Record payment view with concurrency safety (lines 3244-3450)

**Templates:**
- `core/templates/core/pending/summary.html`: Main pending payments UI
- `core/templates/core/exchanges/record_payment.html`: Record payment form

### 13.2 Database Queries

**Pending Payments Query:**
```python
ClientExchangeAccount.objects.filter(
    client__user=request.user
).select_related("client", "exchange")
```

**Settlement Query:**
```python
Settlement.objects.filter(client_exchange=account).aggregate(
    total=Sum('amount')
)
```

**Row Locking Query:**
```python
ClientExchangeAccount.objects.select_for_update().get(
    pk=account_id, client__user=request.user
)
```

---

## 15. TESTING SCENARIOS

### 14.1 Scenario 1: Normal Loss Case

**Setup:**
- Funding = 1000
- Exchange Balance = 700
- Client_PnL = -300 (loss)
- loss_share_percentage = 10

**Expected:**
- FinalShare = 30 (floor(300 * 0.10))
- Share locked: InitialFinalShare = 30
- RemainingAmount = 30 (if no settlements)
- Appears in "Clients Owe You" section
- show_na = False

### 14.2 Scenario 2: Normal Profit Case

**Setup:**
- Funding = 1000
- Exchange Balance = 1500
- Client_PnL = +500 (profit)
- profit_share_percentage = 15

**Expected:**
- FinalShare = 75 (floor(500 * 0.15))
- Share locked: InitialFinalShare = 75
- RemainingAmount = 75 (if no settlements)
- Appears in "You Owe Clients" section
- show_na = False

### 14.3 Scenario 3: Zero Share Case

**Setup:**
- Funding = 1000
- Exchange Balance = 1005
- Client_PnL = +5 (profit)
- profit_share_percentage = 1

**Expected:**
- ExactShare = 0.05
- FinalShare = 0 (floor(0.05))
- Share not locked (FinalShare = 0)
- RemainingAmount = 0
- show_na = True
- Appears with "N.A" values

### 14.4 Scenario 4: Fully Settled Case (Client_PnL = 0)

**Setup:**
- Funding = 1000
- Exchange Balance = 1000
- Client_PnL = 0

**Expected:**
- FinalShare = 0
- Locks reset: InitialFinalShare = NULL
- RemainingAmount = 0
- show_na = True
- Appears in "Clients Owe You" section with "N.A" values

### 14.5 Scenario 5: Partial Settlement

**Setup:**
- InitialFinalShare = 100 (locked)
- Settlement 1 = 30
- Settlement 2 = 20

**Expected:**
- RemainingAmount = 50 (100 - 30 - 20)
- OverpaidAmount = 0
- Account still appears in pending
- Can record additional payments up to RemainingAmount

### 14.6 Scenario 6: Locked Share After Settlement

**Setup:**
- Initial: Funding=1000, Balance=700, PnL=-300, FinalShare=30
- Share locked: InitialFinalShare = 30, LockedInitialPnL = -300
- Settlement: Pay 30, MaskedCapital = (30 × 300) ÷ 30 = 300

**Expected:**
- After: Funding=700, Balance=700, PnL=0, FinalShare=0
- InitialFinalShare = 30 (still locked, doesn't change)
- RemainingAmount = 30 - 30 = 0
- OverpaidAmount = 0
- Account shows as fully settled (PnL = 0)
- Locks reset when PnL = 0

### 14.7 Scenario 7: Over-Settlement Attempt

**Setup:**
- InitialFinalShare = 100 (locked)
- RemainingAmount = 50
- User tries to pay 60

**Expected:**
- Validation error: "Cannot exceed remaining settlement amount"
- Payment not processed
- Account unchanged

### 14.8 Scenario 8: Concurrent Payment Attempts

**Setup:**
- InitialFinalShare = 100 (locked)
- RemainingAmount = 100
- User A and User B try to pay 100 simultaneously

**Expected:**
- Database row locking prevents race condition
- First payment succeeds (RemainingAmount = 0)
- Second payment fails validation (RemainingAmount = 0)
- No over-settlement

### 14.9 Scenario 9: PnL Cycle Change

**Setup:**
- Initial: PnL = -300, InitialFinalShare = 30 (locked)
- After trading: PnL = +200
- Sign flip detected

**Expected:**
- New share computed: FinalShare = 30 (15% of 200)
- New share locked: InitialFinalShare = 30
- Old settlements still tracked
- RemainingAmount = 30 (for new cycle)

### 14.10 Scenario 10: Share Locked After Settlements

**Setup:**
- Settlements = 50 (before locking)
- Share computed: FinalShare = 30
- Share locked: InitialFinalShare = 30

**Expected:**
- RemainingAmount = 30 - 50 = -20 → clamped to 0
- OverpaidAmount = 50 - 30 = 20
- Account shows as fully settled (RemainingAmount = 0)
- No more settlements allowed

---

## 16. CONCLUSION

This document covers all aspects of the Pending Payments system:

✅ **Core Formulas**: Client_PnL, ExactShare, FinalShare, InitialFinalShare, RemainingAmount, MaskedCapital
✅ **Locked Share Mechanism**: Complete explanation of locking logic
✅ **Data Structure**: Account fields, Settlement model, List item structure
✅ **View Logic**: Step-by-step algorithm for pending_summary
✅ **Edge Cases**: 13+ edge cases with detailed explanations
✅ **Failure Cases**: Complete explanation of why wrong formulas fail and how they're prevented
✅ **Record Payment**: Complete validation and processing logic with concurrency safety
✅ **CSV Export**: Export logic matching UI exactly
✅ **UI Behavior**: Display rules, button states, totals
✅ **Sorting/Filtering**: Sort function and search logic
✅ **Business Rules**: All rules summarized
✅ **Concurrency Safety**: Database row locking to prevent race conditions
✅ **Code Reference**: Key functions and locations
✅ **Testing Scenarios**: 10 test scenarios

**System Status**: ✅ FULLY DOCUMENTED AND READY FOR USE

---

**Document Version**: 3.0
**Last Updated**: 2026-01-08
**Author**: System Documentation
