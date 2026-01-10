# PENDING PAYMENTS SYSTEM - COMPLETE GUIDE

**Version:** 3.0 (Complete & Comprehensive)  
**Status:** Production Ready  
**System Type:** Masked Share Settlement System  
**Last Updated:** January 2026

---

## TABLE OF CONTENTS

1. [System Overview](#system-overview)
2. [Core Definitions](#core-definitions)
3. [Master Formulas](#master-formulas)
4. [Database Schema](#database-schema)
5. [Share Calculation Logic](#share-calculation-logic)
6. [Share Locking Mechanism](#share-locking-mechanism)
7. [Cycle Management](#cycle-management)
8. [Remaining Amount Calculation](#remaining-amount-calculation)
9. [Settlement Process](#settlement-process)
10. [MaskedCapital Calculation](#maskedcapital-calculation)
11. [View Logic - Pending Summary](#view-logic---pending-summary)
12. [View Logic - Record Payment](#view-logic---record-payment)
13. [UI Components](#ui-components)
14. [Display Rules](#display-rules)
15. [Edge Cases & Validations](#edge-cases--validations)
16. [Complete Examples](#complete-examples)
17. [Code Reference](#code-reference)
18. [Testing Guide](#testing-guide)

---

## SYSTEM OVERVIEW

### Purpose

The **Pending Payments System** manages settlements between admin and clients using a **Masked Share Settlement Model**. This system ensures:

- **Masked Settlement**: Only share amounts are settled, not full capital
- **Share Locking**: Share is locked at first compute and never shrinks after payments
- **Cycle Separation**: Settlements are tracked per PnL cycle to prevent mixing
- **Always Visible**: All clients appear in pending list (even with N.A when not applicable)
- **Dynamic Recalculation**: Settlements reduce trading exposure proportionally

### Key Principles

1. **Share is decided by trading outcome, not by settlement**
2. **Share NEVER shrinks after payments** (locked at first compute)
3. **Clients MUST always appear in pending list** (for visibility)
4. **Settlements reduce exposure using masked capital**
5. **Sign convention: Always from YOUR point of view**
6. **Transaction sign depends ONLY on Client_PnL at payment time**

### Two Sections

1. **Clients Owe You** (Loss Cases)
   - Client PnL < 0 (loss)
   - Client must pay admin's share
   - Remaining amount is POSITIVE

2. **You Owe Clients** (Profit Cases)
   - Client PnL > 0 (profit)
   - Admin must pay client's share
   - Remaining amount is POSITIVE (but represents what you owe)

---

## CORE DEFINITIONS

### Account Fields

| Field | Type | Description |
|-------|------|-------------|
| `funding` | BIGINT | Capital given to client (≥ 0) |
| `exchange_balance` | BIGINT | Current balance on exchange (≥ 0) |
| `my_percentage` | Integer | Default share percentage (0-100) |
| `loss_share_percentage` | Integer | Share % for losses (0-100, optional) |
| `profit_share_percentage` | Integer | Share % for profits (0-100, optional) |
| `locked_initial_final_share` | Integer | Locked share amount (immutable) |
| `locked_share_percentage` | Integer | Locked share percentage |
| `locked_initial_pnl` | BIGINT | Locked PnL when share was computed |
| `locked_initial_funding` | BIGINT | Funding when cycle started |
| `cycle_start_date` | DateTime | When current PnL cycle started |

### Settlement Fields

| Field | Type | Description |
|-------|------|-------------|
| `client_exchange` | ForeignKey | Account this settlement belongs to |
| `amount` | Integer | Share payment amount (always positive) |
| `date` | DateTime | When settlement occurred (auto-set) |
| `notes` | Text | Optional notes |

### Transaction Fields (RECORD_PAYMENT)

| Field | Type | Description |
|-------|------|-------------|
| `client_exchange` | ForeignKey | Account this transaction belongs to |
| `type` | String | Always 'RECORD_PAYMENT' |
| `amount` | Decimal | **Signed amount**: +X = client paid you, -X = you paid client |
| `date` | DateTime | When payment was recorded |
| `exchange_balance_after` | Decimal | Exchange balance after this payment |
| `notes` | Text | Optional notes |

---

## MASTER FORMULAS

### Formula 1: Client Profit/Loss (FOUNDATION)

```
Client_PnL = ExchangeBalance − Funding
```

**Returns:** BIGINT (can be negative for loss, positive for profit)

**Example:**
- Funding = 1000
- Exchange Balance = 800
- Client PnL = 800 - 1000 = **-200** (Loss)

**Example:**
- Funding = 1000
- Exchange Balance = 1200
- Client PnL = 1200 - 1000 = **+200** (Profit)

---

### Formula 2: Share Percentage Selection

```
IF Client_PnL < 0:
    Share% = loss_share_percentage (or fallback to my_percentage)
ELSE IF Client_PnL > 0:
    Share% = profit_share_percentage (or fallback to my_percentage)
ELSE:
    Share% = 0 (no share)
```

**Rules:**
- Loss uses `loss_share_percentage` (immutable once data exists)
- Profit uses `profit_share_percentage` (can change anytime)
- If percentage is 0, fallback to `my_percentage`

---

### Formula 3: Exact Share (Before Rounding)

```
ExactShare = |Client_PnL| × (Share% / 100)
```

**Returns:** Float (full precision, internal only)

**Rules:**
- Uses absolute value of PnL
- Full precision maintained
- Never rounded at this step

**Example:**
- Client PnL = -200
- Share% = 10%
- ExactShare = 200 × (10 / 100) = **20.0**

---

### Formula 4: Final Share (After Floor Rounding)

```
FinalShare = floor(ExactShare)
```

**Returns:** BIGINT (always positive, integer)

**Rules:**
- **ONLY rounding step** in entire system
- **FLOOR method** (round down)
- Fractional values discarded permanently
- No decimals shown or settled

**Example:**
- ExactShare = 20.0 → FinalShare = **20**
- ExactShare = 20.9 → FinalShare = **20**
- ExactShare = 0.1 → FinalShare = **0**

---

### Formula 5: Remaining Settlement Amount

```
Remaining = max(0, LockedInitialFinalShare − TotalSettled (Current Cycle))
```

**Returns:** BIGINT (always ≥ 0)

**Critical Rules:**
1. **Uses locked share**, NOT current share
2. **Only counts settlements from current cycle** (filtered by `cycle_start_date`)
3. **Share NEVER shrinks** after payments

**Components:**
- `LockedInitialFinalShare`: Share locked when cycle started
- `TotalSettled`: Sum of all settlements in current cycle

**Example:**
- LockedInitialFinalShare = 10
- TotalSettled = 0
- Remaining = 10 - 0 = **10**

**Example:**
- LockedInitialFinalShare = 10
- TotalSettled = 5
- Remaining = 10 - 5 = **5**

---

### Formula 6: MaskedCapital (Settlement Impact)

```
MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
```

**Purpose:** Maps settlement payment back to actual capital change

**Why This Formula:**
- Proportional mapping: 50% of share → 50% of PnL
- Linear relationship, not exponential
- Prevents double-counting percentage

**Example:**
- SharePayment = 5
- LockedInitialPnL = -90
- LockedInitialFinalShare = 9
- MaskedCapital = (5 × 90) ÷ 9 = **50**

---

### Formula 7: Transaction Sign Logic

**CORRECT RULE: Sign depends ONLY on Client_PnL at payment time**

```
IF Client_PnL > 0 (client in profit):
    Transaction.amount = -SharePayment   # you paid client
ELSE IF Client_PnL < 0 (client in loss):
    Transaction.amount = +SharePayment   # client paid you
```

**Critical Rules:**
- ✅ No PnL checks needed in reports (sign is absolute truth)
- ✅ No locked_initial_pnl checks needed
- ✅ The sign itself is the truth

**Example:**
- SharePayment = 50
- Client_PnL = -1000 (loss)
- Transaction.amount = **+50** (client paid you) ✓

---

## DATABASE SCHEMA

### Model: ClientExchangeAccount

**Table:** `core_clientexchangeaccount`

**Key Fields:**
```python
funding = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
exchange_balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
my_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
loss_share_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
profit_share_percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
locked_initial_final_share = models.BigIntegerField(null=True, blank=True)
locked_share_percentage = models.IntegerField(null=True, blank=True)
locked_initial_pnl = models.BigIntegerField(null=True, blank=True)
locked_initial_funding = models.BigIntegerField(null=True, blank=True)
cycle_start_date = models.DateTimeField(null=True, blank=True)
```

**Relationships:**
- `client`: ForeignKey to Client (CASCADE)
- `exchange`: ForeignKey to Exchange (CASCADE)
- `settlements`: Reverse relation to Settlement
- `transactions`: Reverse relation to Transaction

---

### Model: Settlement

**Table:** `core_settlement`

**Fields:**
```python
client_exchange = models.ForeignKey(ClientExchangeAccount, on_delete=models.CASCADE, related_name='settlements')
amount = models.BigIntegerField(validators=[MinValueValidator(1)])
date = models.DateTimeField(auto_now_add=True)
notes = models.TextField(blank=True, null=True)
```

**Purpose:** Tracks individual settlement payments

---

### Model: Transaction

**Table:** `core_transaction`

**Key Fields:**
```python
client_exchange = models.ForeignKey(ClientExchangeAccount, on_delete=models.CASCADE, related_name='transactions')
transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
amount = models.DecimalField(max_digits=20, decimal_places=2)  # Signed amount
date = models.DateTimeField()
exchange_balance_after = models.DecimalField(max_digits=20, decimal_places=2)
notes = models.TextField(blank=True, null=True)
```

**Transaction Type:** `RECORD_PAYMENT`

---

## SHARE CALCULATION LOGIC

### Method: compute_client_pnl()

**Location:** `core/models.py` (lines 210-217)

**Code:**
```python
def compute_client_pnl(self):
    """
    MASTER PROFIT/LOSS FORMULA
    Client_PnL = exchange_balance - funding
    
    Returns: BIGINT (can be negative for loss)
    """
    return self.exchange_balance - self.funding
```

**Returns:** BIGINT (negative for loss, positive for profit, 0 for neutral)

---

### Method: compute_my_share()

**Location:** `core/models.py` (lines 219-248)

**Code:**
```python
def compute_my_share(self):
    """
    MASKED SHARE SETTLEMENT SYSTEM - PARTNER SHARE FORMULA
    
    Uses floor() rounding (round down) for final share.
    Separate percentages for loss and profit.
    
    Returns: BIGINT (always positive, floor rounded)
    """
    import math
    client_pnl = self.compute_client_pnl()
    
    if client_pnl == 0:
        return 0
    
    # Determine which percentage to use
    if client_pnl < 0:
        # LOSS: Use loss_share_percentage (or fallback to my_percentage)
        share_pct = self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
    else:
        # PROFIT: Use profit_share_percentage (or fallback to my_percentage)
        share_pct = self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
    
    # Exact Share (NO rounding)
    exact_share = abs(client_pnl) * (share_pct / 100.0)
    
    # Final Share (ONLY rounding step) - FLOOR (round down)
    final_share = math.floor(exact_share)
    
    return int(final_share)
```

**Steps:**
1. Calculate Client_PnL
2. If PnL = 0, return 0
3. Select share percentage (loss or profit)
4. Calculate exact share (no rounding)
5. Apply floor rounding
6. Return integer

---

## SHARE LOCKING MECHANISM

### Method: lock_initial_share_if_needed()

**Location:** `core/models.py` (lines 272-385)

**Purpose:** Locks share at first compute per PnL cycle

**Key Logic:**

#### 1. PnL Magnitude Reduction Check

```python
if self.locked_initial_pnl is not None and client_pnl != 0:
    locked_pnl_abs = abs(self.locked_initial_pnl)
    current_pnl_abs = abs(client_pnl)
    
    if current_pnl_abs < locked_pnl_abs:
        # PnL magnitude reduced → reset cycle
        # Reset all locks
```

**Why:** Trading reduced exposure = new trading outcome = new cycle

---

#### 2. Funding Change Check

```python
if self.locked_initial_funding is not None:
    if self.funding != self.locked_initial_funding:
        # Funding changed → new exposure → new cycle
        # Reset all locks
```

**Why:** New funding = new exposure = new trading cycle

---

#### 3. Sign Flip Check

```python
if (client_pnl < 0) != (self.locked_initial_pnl < 0):
    # PnL cycle changed - lock new share
    # Set cycle_start_date = now()
```

**Why:** Different direction = different settlement direction = new cycle

---

#### 4. First Lock

```python
if self.locked_initial_final_share is None or self.locked_initial_pnl is None:
    # First time - lock the share
    final_share = self.compute_my_share()
    if final_share > 0:
        # Lock share, percentage, PnL, cycle_start_date, funding
```

**Why:** Lock share at first compute to prevent shrinking

---

#### 5. Zero PnL Handling

```python
elif client_pnl == 0:
    # Only reset if fully settled
    if cycle_settled >= (self.locked_initial_final_share or 0):
        # Fully settled - safe to reset
```

**Why:** Don't reset locks if settlements are pending

---

## CYCLE MANAGEMENT

### Cycle Reset Conditions

A cycle resets (new cycle starts) when:

1. **PnL Sign Flips**
   ```
   (Current PnL < 0) != (Locked PnL < 0)
   ```

2. **PnL Magnitude Reduces**
   ```
   abs(Current PnL) < abs(Locked PnL)
   ```

3. **Funding Changes**
   ```
   Current Funding != Locked Initial Funding
   ```

### Cycle Tracking Fields

| Field | Purpose | When Set | When Reset |
|-------|---------|----------|------------|
| `locked_initial_final_share` | Share locked at cycle start | First compute or cycle reset | Cycle reset or fully settled |
| `locked_share_percentage` | Percentage used for locked share | Same as above | Same as above |
| `locked_initial_pnl` | PnL at cycle start (for sign detection) | Same as above | Same as above |
| `cycle_start_date` | Timestamp when cycle started | Same as above | Same as above |
| `locked_initial_funding` | Funding at cycle start (for change detection) | Same as above | Same as above |

### Settlement Filtering by Cycle

**Critical Rule:** Only count settlements from current cycle

**Implementation:**
```python
if self.cycle_start_date:
    # Only count settlements after cycle started
    total_settled = self.settlements.filter(
        date__gte=self.cycle_start_date
    ).aggregate(total=models.Sum('amount'))['total'] or 0
else:
    # Backward compatibility: count all settlements
    total_settled = self.settlements.aggregate(total=models.Sum('amount'))['total'] or 0
```

**Why:** Prevents old cycle settlements from mixing with new cycle shares

---

## REMAINING AMOUNT CALCULATION

### Method: get_remaining_settlement_amount()

**Location:** `core/models.py` (lines 387-459)

**Purpose:** Calculates remaining settlement amount using locked share

**Code Flow:**

```python
def get_remaining_settlement_amount(self):
    # Step 1: Lock share if needed
    self.lock_initial_share_if_needed()
    
    # Step 2: Count settlements from current cycle
    if self.cycle_start_date:
        total_settled = self.settlements.filter(
            date__gte=self.cycle_start_date
        ).aggregate(total=models.Sum('amount'))['total'] or 0
    else:
        total_settled = self.settlements.aggregate(total=models.Sum('amount'))['total'] or 0
    
    # Step 3: Get locked share (or lock current if > 0)
    if self.locked_initial_final_share is not None:
        initial_final_share = self.locked_initial_final_share
    else:
        # Lock current share if > 0
        current_share = self.compute_my_share()
        if current_share > 0:
            # Lock it now
            initial_final_share = current_share
        else:
            return {'remaining': 0, 'overpaid': 0, 'initial_final_share': 0, 'total_settled': total_settled}
    
    # Step 4: Calculate remaining
    remaining = max(0, initial_final_share - total_settled)
    overpaid = max(0, total_settled - initial_final_share)
    
    return {
        'remaining': remaining,
        'overpaid': overpaid,
        'initial_final_share': initial_final_share,
        'total_settled': total_settled
    }
```

**Returns:** Dictionary with:
- `remaining`: Amount still to settle (≥ 0)
- `overpaid`: Amount paid beyond locked share (≥ 0)
- `initial_final_share`: Locked share amount
- `total_settled`: Total settled in current cycle

---

## SETTLEMENT PROCESS

### View: record_payment

**Location:** `core/views.py` (lines ~3257+)

**Flow:**

```
1. User clicks "Record Payment" button
2. GET Request:
   - Load account (no locking)
   - Calculate Client_PnL
   - Lock share if needed
   - Calculate Remaining Amount
   - Display form
3. POST Request:
   - Lock account row (select_for_update)
   - Validate payment amount
   - Calculate MaskedCapital
   - Validate balances won't go negative
   - Update account balances
   - Create Settlement record
   - Create Transaction record (with correct sign)
   - Redirect to success page
```

**Key Validations:**

1. **Final Share Must Be > 0**
   ```python
   if initial_final_share == 0:
       raise ValidationError("No settlement allowed: Final share is zero")
   ```

2. **Remaining Must Be > 0**
   ```python
   if remaining_amount == 0:
       # Already fully settled
   ```

3. **Payment Amount Must Be ≤ Remaining**
   ```python
   if paid_amount > remaining_amount:
       raise ValidationError(f"Over-settlement: {paid_amount} > {remaining_amount}")
   ```

4. **Payment Amount Must Be > 0**
   ```python
   if paid_amount <= 0:
       raise ValidationError("Paid amount must be greater than zero")
   ```

5. **Balance Won't Go Negative**
   ```python
   if account.funding - masked_capital < 0:
       raise ValidationError("Funding would become negative")
   ```

---

## MASKEDCAPITAL CALCULATION

### Formula

```
MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare
```

### Implementation

**Location:** `core/views.py` (in `record_payment` view)

**Code:**
```python
# Calculate MaskedCapital using CORRECT formula
locked_pnl_abs = abs(account.locked_initial_pnl)
masked_capital = (Decimal(paid_amount) * Decimal(locked_pnl_abs)) / Decimal(account.locked_initial_final_share)
```

### Why This Formula

- **Proportional mapping:** 50% of share → 50% of PnL
- **Linear relationship:** Not exponential
- **Prevents double-counting:** Doesn't apply percentage twice

### Example

**Scenario:**
- SharePayment = 5
- LockedInitialPnL = -90
- LockedInitialFinalShare = 9

**Calculation:**
```
MaskedCapital = (5 × 90) ÷ 9 = 450 ÷ 9 = 50
```

**Result:** Funding reduced by 50 (proportional to share payment)

---

### Balance Updates

**Loss Case (Client Pays Admin):**
```python
account.funding = account.funding - masked_capital
```

**Profit Case (Admin Pays Client):**
```python
account.exchange_balance = account.exchange_balance - masked_capital
```

---

## VIEW LOGIC - PENDING SUMMARY

### Function: pending_summary

**Location:** `core/views.py` (lines 1098-1355)

**Purpose:** Displays pending payments list with two sections

**Flow:**

```
1. Extract filters (search, client_type, report_type)
2. Get all client exchanges for user
3. Apply search filter if provided
4. For each client exchange:
   a. Calculate Client_PnL
   b. Determine case (loss/profit/neutral)
   c. Lock share if needed
   d. Get remaining settlement amount
   e. Add to appropriate list
5. Sort lists by share amount
6. Calculate totals
7. Build context
8. Render template
```

**Key Logic:**

#### Loss Case (Clients Owe You)

```python
if client_pnl < 0:
    client_exchange.lock_initial_share_if_needed()
    settlement_info = client_exchange.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    show_na = (final_share == 0)
    
    clients_owe_list.append({
        "client": client_exchange.client,
        "exchange": client_exchange.exchange,
        "account": client_exchange,
        "client_pnl": client_pnl,
        "remaining_amount": remaining_amount,  # POSITIVE
        "share_percentage": share_pct,
        "show_na": show_na,
    })
```

#### Profit Case (You Owe Clients)

```python
if client_pnl > 0:
    client_exchange.lock_initial_share_if_needed()
    settlement_info = client_exchange.get_remaining_settlement_amount()
    remaining_amount = settlement_info['remaining']
    show_na = (final_share == 0)
    
    you_owe_list.append({
        "client": client_exchange.client,
        "exchange": client_exchange.exchange,
        "account": client_exchange,
        "client_pnl": client_pnl,
        "remaining_amount": remaining_amount,  # POSITIVE (but you owe)
        "share_percentage": share_pct,
        "show_na": show_na,
    })
```

#### Neutral Case (PnL = 0)

```python
if client_pnl == 0:
    # Client MUST always appear in pending list
    show_na = True
    remaining_amount = 0
    
    clients_owe_list.append({
        # ... add with show_na = True
    })
```

---

## VIEW LOGIC - RECORD PAYMENT

### Function: record_payment

**Location:** `core/views.py` (lines ~3257+)

**GET Request:**

```python
def record_payment(request, account_id):
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    
    # Lock share if needed
    account.lock_initial_share_if_needed()
    
    # Get remaining settlement amount
    settlement_info = account.get_remaining_settlement_amount()
    
    # Render form
    return render(request, "core/exchanges/record_payment.html", {
        "account": account,
        "settlement_info": settlement_info,
    })
```

**POST Request:**

```python
if request.method == "POST":
    # Lock account row (prevent concurrent payments)
    account = ClientExchangeAccount.objects.select_for_update().get(
        pk=account_id,
        client__user=request.user
    )
    
    # Re-lock share and get remaining
    account.lock_initial_share_if_needed()
    settlement_info = account.get_remaining_settlement_amount()
    
    # Extract payment amount
    paid_amount = int(request.POST.get("paid_amount", 0))
    
    # Validate
    if settlement_info['initial_final_share'] == 0:
        raise ValidationError("No settlement allowed")
    if settlement_info['remaining'] == 0:
        raise ValidationError("Already fully settled")
    if paid_amount > settlement_info['remaining']:
        raise ValidationError("Over-settlement")
    
    # Calculate MaskedCapital
    masked_capital = (paid_amount * abs(account.locked_initial_pnl)) / account.locked_initial_final_share
    
    # Update balances
    client_pnl = account.compute_client_pnl()
    if client_pnl < 0:
        # Loss case: reduce funding
        account.funding = account.funding - masked_capital
    else:
        # Profit case: reduce exchange balance
        account.exchange_balance = account.exchange_balance - masked_capital
    
    account.save()
    
    # Create Settlement record
    Settlement.objects.create(
        client_exchange=account,
        amount=paid_amount,
        notes=notes
    )
    
    # Create Transaction record (with correct sign)
    transaction_amount = -paid_amount if client_pnl > 0 else paid_amount
    Transaction.objects.create(
        client_exchange=account,
        transaction_type=Transaction.TYPE_RECORD_PAYMENT,
        amount=transaction_amount,
        date=timezone.now(),
        exchange_balance_after=account.exchange_balance,
        notes=notes
    )
    
    # Redirect
    return redirect(reverse("pending_summary"))
```

---

## UI COMPONENTS

### Template: summary.html

**File:** `core/templates/core/pending/summary.html`

**Structure:**

1. **Search Bar**
   - Search by client name, code, or exchange name
   - Clear button if search active

2. **Section Toggle Buttons**
   - "Clients Owe You" button
   - "You Owe Clients" button
   - JavaScript to toggle sections

3. **Summary Cards**
   - Total Clients Owe
   - Total You Owe
   - Your Share amounts

4. **Clients Owe You Table**
   - Columns: Client, Code, Exchange, Funding, Exchange Balance, Client PnL, Remaining, Share %, Actions
   - Shows "N.A" when `show_na = True`
   - "Record Payment" button when `remaining_amount > 0`

5. **You Owe Clients Table**
   - Same columns as above
   - Shows "N.A" when `show_na = True`
   - "Record Payment" button when `remaining_amount != 0`

---

### Display Rules

#### Client PnL Display

**Loss Case:**
```django
{% if item.show_na %}
    <span style="color: var(--muted);">N.A</span>
{% else %}
    <span class="negative">{{ item.client_pnl|floatformat:0 }}</span>
{% endif %}
```

**Profit Case:**
```django
{% if item.show_na %}
    <span style="color: var(--muted);">N.A</span>
{% else %}
    <span class="positive">{{ item.client_pnl|floatformat:0 }}</span>
{% endif %}
```

#### Remaining Amount Display

**Clients Owe You:**
```django
{% if item.show_na %}
    <span style="color: var(--muted);">N.A</span>
{% else %}
    <strong style="color: var(--accent);">{{ item.remaining_amount|floatformat:0 }}</strong>
{% endif %}
```

**You Owe Clients:**
```django
{% if item.show_na %}
    <span style="color: var(--muted);">N.A</span>
{% else %}
    <strong style="color: var(--danger);">{{ item.remaining_amount|floatformat:0 }}</strong>
{% endif %}
```

#### Record Payment Button

**Condition:**
```django
{% if item.show_na %}
    <span>N.A</span>
{% elif item.remaining_amount > 0 %}
    <a href="{% url 'record_payment' item.account.pk %}">Record Payment</a>
{% else %}
    <span>Settled</span>
{% endif %}
```

---

## DISPLAY RULES

### show_na Flag

**When show_na = True:**
- Final Share = 0 (no share to settle)
- Remaining = 0
- No settlement allowed
- Shows "N.A" in UI

**When show_na = False:**
- Final Share > 0
- Can have remaining > 0 or = 0
- Settlement allowed (if remaining > 0)

### Always Show Clients

**Rule:** Clients MUST always appear in pending list

**Implementation:**
- Even when PnL = 0, client is added to list
- Even when Final Share = 0, client is added to list
- Shows "N.A" when not applicable

---

## EDGE CASES & VALIDATIONS

### Edge Case 1: Zero Share Account

**Scenario:**
- Funding = 100
- Exchange Balance = 100
- Client PnL = 0
- Final Share = 0

**Behavior:**
- show_na = True
- Remaining = 0
- "Record Payment" button hidden
- Shows "N.A" in pending list

**This is by design, not a bug.**

---

### Edge Case 2: Very Small Share

**Scenario:**
- Funding = 100
- Exchange Balance = 95
- Client PnL = -5
- Loss Share % = 1%
- ExactShare = 0.05
- FinalShare = floor(0.05) = 0

**Behavior:**
- Same as zero share account
- Shows "N.A"

---

### Edge Case 3: Partial Payment Sequence

**Scenario:**
- LockedInitialFinalShare = 10
- Remaining = 10

**Payment Sequence:**
1. Pay 3 → Remaining = 7
2. Pay 4 → Remaining = 3
3. Pay 2 → Remaining = 1
4. Pay 1 → Remaining = 0 ✅ Settled

**Each payment:**
- Creates Settlement record
- Updates funding/exchange_balance
- Recalculates remaining
- Shows updated remaining in UI

---

### Edge Case 4: Over-Settlement Attempt

**Scenario:**
- Remaining = 5
- User tries to pay 10

**Validation:**
```python
if paid_amount > remaining_amount:
    raise ValidationError("Over-settlement not allowed")
```

**Result:**
- Payment blocked
- Error message shown
- Remaining unchanged

---

### Edge Case 5: Cycle Reset During Partial Payments

**Scenario:**
```
Old Cycle:
  - Share = 9
  - Paid 5
  - Remaining = 4

PnL Sign Flips (New Cycle):
  - New Share = 10
  - Old settlement (5) NOT counted
  - Remaining = 10 (not 4)
```

**Behavior:**
- Old cycle closes
- New cycle starts
- Old settlement preserved but not counted
- Remaining recalculates from new share

---

### Edge Case 6: Funding Change During Settlement

**Scenario:**
```
Step 1: Funding = 100, PnL = -90, Share = 9
Step 2: Pay 5, Remaining = 4
Step 3: Funding = 300, PnL = -200
```

**Behavior:**
- Funding change detected
- Cycle resets
- New Share = 20
- Old settlement (5) NOT counted
- Remaining = 20

---

### Edge Case 7: PnL Reduction During Settlement

**Scenario:**
```
Step 1: Profit = +100, Share = 10
Step 2: Pay 5, Remaining = 5
Step 3: Profit = +1, Share = 0
```

**Behavior:**
- PnL magnitude reduction detected
- Cycle resets
- New Share = 0
- Old settlement (5) NOT counted
- Remaining = 0
- Shows "Settled"

---

### Edge Case 8: Concurrent Payments

**Scenario:**
- Two users try to record payment simultaneously
- Remaining = 10

**Protection:**
```python
account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
```

**Behavior:**
- Database row locking prevents race condition
- First payment processes
- Second payment sees updated remaining
- No double-counting

---

### Edge Case 9: Negative Balance Prevention

**Scenario:**
- Funding = 50
- Remaining = 9
- Payment would reduce funding to -10

**Validation:**
```python
if account.funding - masked_capital < 0:
    raise ValidationError("Funding would become negative")
```

**Result:**
- Payment blocked
- Error shown
- Balance unchanged

---

### Edge Case 10: Loss Share % Change Prevention

**Scenario:**
- Account has transactions/settlements
- User tries to change loss_share_percentage

**Validation:**
```python
def clean(self):
    if self.pk:
        old_instance = ClientExchangeAccount.objects.get(pk=self.pk)
        if old_instance.loss_share_percentage != self.loss_share_percentage:
            if has_transactions or has_settlements:
                raise ValidationError("Loss share percentage cannot be changed after data exists")
```

**Result:**
- Change blocked
- Error shown
- Percentage unchanged

---

## COMPLETE EXAMPLES

### Example 1: Basic Loss Settlement

**Setup:**
- Funding: 1000
- Exchange Balance: 100
- Loss Share %: 10%

**Calculation:**
```
Client_PnL = 100 - 1000 = -900
ExactShare = 900 × 10% = 90.0
FinalShare = floor(90.0) = 90
```

**Lock Share:**
- locked_initial_final_share = 90
- locked_initial_pnl = -900
- cycle_start_date = now()

**Remaining:**
- Remaining = 90 - 0 = 90

**Payment 1: Pay 50**
- Settlement: amount = 50
- MaskedCapital = (50 × 900) ÷ 90 = 500
- New Funding = 1000 - 500 = 500
- New Exchange Balance = 100
- New PnL = 100 - 500 = -400
- Remaining = 90 - 50 = 40

**Payment 2: Pay 40**
- Settlement: amount = 40
- MaskedCapital = (40 × 900) ÷ 90 = 400
- New Funding = 500 - 400 = 100
- New Exchange Balance = 100
- New PnL = 100 - 100 = 0
- Remaining = 90 - 90 = 0 ✅ Settled

---

### Example 2: Basic Profit Settlement

**Setup:**
- Funding: 500
- Exchange Balance: 1000
- Profit Share %: 20%

**Calculation:**
```
Client_PnL = 1000 - 500 = +500
ExactShare = 500 × 20% = 100.0
FinalShare = floor(100.0) = 100
```

**Lock Share:**
- locked_initial_final_share = 100
- locked_initial_pnl = +500
- cycle_start_date = now()

**Remaining:**
- Remaining = 100 - 0 = 100

**Payment: Pay 100**
- Settlement: amount = 100
- MaskedCapital = (100 × 500) ÷ 100 = 500
- New Exchange Balance = 1000 - 500 = 500
- New Funding = 500
- New PnL = 500 - 500 = 0
- Remaining = 100 - 100 = 0 ✅ Settled
- Transaction.amount = -100 (you paid client)

---

### Example 3: Cycle Reset (Sign Flip)

**Setup:**
- Step 1: Funding = 1000, Balance = 100, PnL = -900, Share = 90
- Step 2: Pay 50, Remaining = 40
- Step 3: Balance = 1200, PnL = +200

**Cycle Reset:**
- Sign flip detected: (-900) → (+200)
- New cycle starts
- New Share = floor(200 × 20%) = 40
- Old settlement (50) NOT counted
- Remaining = 40 - 0 = 40

---

## CODE REFERENCE

### Model Methods

#### compute_client_pnl()
**File:** `core/models.py` (lines 210-217)
**Returns:** BIGINT

#### compute_my_share()
**File:** `core/models.py` (lines 219-248)
**Returns:** BIGINT

#### lock_initial_share_if_needed()
**File:** `core/models.py` (lines 272-385)
**Returns:** None (modifies instance)

#### get_remaining_settlement_amount()
**File:** `core/models.py` (lines 387-459)
**Returns:** dict

---

### Views

#### pending_summary()
**File:** `core/views.py` (lines 1098-1355)
**URL:** `/pending/`
**Method:** GET

#### record_payment()
**File:** `core/views.py` (lines ~3257+)
**URL:** `/exchanges/account/{id}/record-payment/`
**Method:** GET and POST

#### export_pending_csv()
**File:** `core/views.py` (lines 1359+)
**URL:** `/pending/export-csv/`
**Method:** GET

---

### Templates

#### summary.html
**File:** `core/templates/core/pending/summary.html`
**Displays:** Pending payments list

#### record_payment.html
**File:** `core/templates/core/exchanges/record_payment.html`
**Displays:** Payment form

---

## TESTING GUIDE

### Test Scenario 1: Basic Loss Settlement

**Steps:**
1. Create account: funding=1000, balance=100, loss%=10%
2. View pending summary
3. Verify remaining = 90
4. Record payment of 50
5. Verify remaining = 40
6. Record payment of 40
7. Verify remaining = 0 (settled)

**Expected:**
- ✅ Share locked at 90
- ✅ Remaining decreases correctly
- ✅ Funding reduces proportionally
- ✅ Settled when remaining = 0

---

### Test Scenario 2: Basic Profit Settlement

**Steps:**
1. Create account: funding=500, balance=1000, profit%=20%
2. View pending summary
3. Verify remaining = 100
4. Record payment of 100
5. Verify remaining = 0 (settled)

**Expected:**
- ✅ Share locked at 100
- ✅ Exchange balance reduces
- ✅ Transaction amount is negative
- ✅ Settled when remaining = 0

---

### Test Scenario 3: Partial Payments

**Steps:**
1. Create account with remaining = 10
2. Pay 3 → Verify remaining = 7
3. Pay 4 → Verify remaining = 3
4. Pay 3 → Verify remaining = 0

**Expected:**
- ✅ Each payment creates settlement record
- ✅ Remaining updates correctly
- ✅ All settlements tracked

---

### Test Scenario 4: Cycle Reset (Sign Flip)

**Steps:**
1. Create loss account: Share = 9, Pay 5
2. Change balance to create profit
3. View pending summary

**Expected:**
- ✅ New cycle starts
- ✅ Old settlement NOT counted
- ✅ Remaining = new share

---

### Test Scenario 5: Zero Share Account

**Steps:**
1. Create account: funding=100, balance=100
2. View pending summary

**Expected:**
- ✅ Account appears in list
- ✅ Shows "N.A" for PnL and Remaining
- ✅ "Record Payment" button hidden

---

### Test Scenario 6: Over-Settlement Prevention

**Steps:**
1. Create account with remaining = 5
2. Try to pay 10

**Expected:**
- ❌ Payment blocked
- ✅ Error message shown
- ✅ Remaining unchanged

---

### Test Scenario 7: Concurrent Payments

**Steps:**
1. Create account with remaining = 10
2. User 1: Pay 5
3. User 2: Try to pay 6 (should see remaining = 5)

**Expected:**
- ✅ Database locking prevents race condition
- ✅ Second payment sees updated remaining

---

### Test Scenario 8: Funding Change Reset

**Steps:**
1. Create account: funding=100, Share=9
2. Change funding to 300
3. View pending summary

**Expected:**
- ✅ Cycle resets
- ✅ New share calculated
- ✅ Old settlement NOT counted

---

### Test Scenario 9: PnL Reduction Reset

**Steps:**
1. Create account: Profit=+100, Share=10
2. Change balance: Profit=+1
3. View pending summary

**Expected:**
- ✅ Cycle resets
- ✅ New share = 0
- ✅ Shows "N.A"

---

### Test Scenario 10: CSV Export

**Steps:**
1. Create multiple accounts with pending payments
2. Click "Download CSV"
3. Verify CSV file

**Expected:**
- ✅ CSV file downloaded
- ✅ Contains all accounts
- ✅ Matches UI table format

---

## SUMMARY

### Key Formulas

1. **PnL:** `Client_PnL = ExchangeBalance − Funding`
2. **Exact Share:** `ExactShare = |PnL| × (Share% / 100)`
3. **Final Share:** `FinalShare = floor(ExactShare)`
4. **Remaining:** `Remaining = LockedInitialFinalShare − TotalSettled (Current Cycle)`
5. **MaskedCapital:** `MaskedCapital = (SharePayment × |LockedInitialPnL|) ÷ LockedInitialFinalShare`

### Key Rules

1. **Shares are locked** at first compute per PnL cycle
2. **Cycles reset** when:
   - PnL sign changes (LOSS ↔ PROFIT)
   - PnL magnitude reduces (trading reduced exposure)
   - Funding changes (new exposure = new cycle)
3. **Old cycle settlements** never mix with new cycle shares
4. **Remaining uses locked share**, not current share
5. **Partial payments allowed** until remaining = 0
6. **MaskedCapital maps proportionally** to PnL
7. **Clients always appear** in pending list (even with N.A)

### System Guarantees

- ✅ Deterministic math
- ✅ No rounding drift
- ✅ Ledger stability
- ✅ Safe manual control
- ✅ Support for changing profit %
- ✅ No historical corruption
- ✅ Cycle separation
- ✅ Concurrency safety
- ✅ Partial payment support
- ✅ Accurate remaining calculation

---

**END OF DOCUMENTATION**

