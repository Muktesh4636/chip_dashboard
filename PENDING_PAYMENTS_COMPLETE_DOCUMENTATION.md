# Pending Payments System - Complete Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Concepts](#core-concepts)
3. [Formulas](#formulas)
4. [PnL Cycle Management](#pnl-cycle-management)
5. [Share Locking Mechanism](#share-locking-mechanism)
6. [Settlement Logic](#settlement-logic)
7. [Display Logic](#display-logic)
8. [Edge Cases and Validations](#edge-cases-and-validations)
9. [Database Models](#database-models)
10. [Key Methods](#key-methods)
11. [Example Scenarios](#example-scenarios)

---

## System Overview

The Pending Payments System is a **Masked Share Settlement System** that tracks and manages profit/loss settlements between clients and administrators. The system ensures:

- **Share is locked** at first compute per PnL cycle
- **Share never shrinks** after payments (decided by trading outcome, not settlement)
- **Cycle separation** prevents mixing settlements from different PnL directions
- **Masked capital** maps share payments linearly back to PnL
- **Concurrent payment protection** using database row locking

---

## Core Concepts

### 1. Client PnL (Profit/Loss)
The fundamental metric that determines settlement direction:
- **Client_PnL = ExchangeBalance - Funding**
- If Client_PnL < 0: **LOSS** → Client owes you
- If Client_PnL > 0: **PROFIT** → You owe client
- If Client_PnL = 0: **NEUTRAL** → Trading flat (no settlement needed)

### 2. Share Percentage
Separate percentages for loss and profit:
- **loss_share_percentage**: Admin share for losses (IMMUTABLE once data exists)
- **profit_share_percentage**: Admin share for profits (can change anytime)
- **my_percentage**: Legacy fallback if loss/profit percentages not set

### 3. PnL Cycle
A period where Client_PnL maintains the same sign (positive or negative):
- **New cycle starts** when:
  - PnL sign flips (LOSS → PROFIT or PROFIT → LOSS)
  - Funding changes (new exposure = new cycle)
  - PnL magnitude reduces significantly (trading reduced exposure)
- **Settlements are tracked per cycle** to prevent mixing

### 4. Locked Share
Share amount locked at the start of a PnL cycle:
- **LockedInitialFinalShare**: Share amount when cycle started
- **LockedSharePercentage**: Share percentage when cycle started
- **LockedInitialPnL**: PnL value when cycle started
- **CycleStartDate**: Timestamp when cycle started
- **LockedInitialFunding**: Funding amount when cycle started

---

## Formulas

### Formula 1: Client PnL Calculation
```
Client_PnL = ExchangeBalance - Funding
```

**Where:**
- `ExchangeBalance`: Current balance on exchange (BIGINT, ≥ 0)
- `Funding`: Total real money given to client (BIGINT, ≥ 0)
- `Client_PnL`: Can be negative (loss), zero, or positive (profit)

**Implementation:**
```python
def compute_client_pnl(self):
    return self.exchange_balance - self.funding
```

---

### Formula 2: Exact Share (Before Rounding)
```
ExactShare = |Client_PnL| × (SharePercentage / 100.0)
```

**Where:**
- `Client_PnL`: Profit/Loss value (can be negative)
- `SharePercentage`: Appropriate share percentage based on PnL direction
  - If Client_PnL < 0: Use `loss_share_percentage` (or `my_percentage` fallback)
  - If Client_PnL > 0: Use `profit_share_percentage` (or `my_percentage` fallback)
  - If Client_PnL = 0: SharePercentage = 0
- `ExactShare`: Float value before rounding

**Implementation:**
```python
def compute_exact_share(self):
    client_pnl = self.compute_client_pnl()
    if client_pnl == 0:
        return 0.0
    
    share_pct = self.get_share_percentage(client_pnl)
    exact_share = abs(client_pnl) * (share_pct / 100.0)
    return exact_share
```

---

### Formula 3: Final Share (After Floor Rounding)
```
FinalShare = floor(ExactShare)
```

**Where:**
- `ExactShare`: Value from Formula 2
- `floor()`: Round down to nearest integer
- `FinalShare`: BIGINT (always positive, floor rounded)

**Implementation:**
```python
def compute_my_share(self):
    import math
    client_pnl = self.compute_client_pnl()
    if client_pnl == 0:
        return 0
    
    share_pct = self.get_share_percentage(client_pnl)
    exact_share = abs(client_pnl) * (share_pct / 100.0)
    final_share = math.floor(exact_share)
    return int(final_share)
```

**Example:**
- ExactShare = 123.7 → FinalShare = 123
- ExactShare = 123.2 → FinalShare = 123
- ExactShare = 0.9 → FinalShare = 0

---

### Formula 4: Remaining Settlement Amount
```
RemainingRaw = max(0, LockedInitialFinalShare - Sum(SharePayments))
Overpaid = max(0, Sum(SharePayments) - LockedInitialFinalShare)
```

**Where:**
- `LockedInitialFinalShare`: Share locked at start of current PnL cycle
- `Sum(SharePayments)`: Sum of all settlements from CURRENT cycle only
  - Only settlements with `date >= cycle_start_date` are counted
- `RemainingRaw`: Always ≥ 0 (raw remaining amount)
- `Overpaid`: Amount paid beyond locked share (if any)

**Critical Rules:**
1. **Share NEVER shrinks** - always use locked share, never recalculate from current PnL
2. **Cycle separation** - only count settlements from current cycle
3. **RemainingRaw is always ≥ 0** - sign is applied at display time

**Implementation:**
```python
def get_remaining_settlement_amount(self):
    self.lock_initial_share_if_needed()
    
    # Only count settlements from CURRENT cycle
    if self.cycle_start_date:
        total_settled = self.settlements.filter(
            date__gte=self.cycle_start_date
        ).aggregate(total=models.Sum('amount'))['total'] or 0
    else:
        total_settled = self.settlements.aggregate(
            total=models.Sum('amount')
        )['total'] or 0
    
    # Always use locked share - NEVER recalculate
    if self.locked_initial_final_share is not None:
        initial_final_share = self.locked_initial_final_share
    else:
        # No locked share - lock current share if > 0
        current_share = self.compute_my_share()
        if current_share > 0:
            # Lock it now
            # ... locking logic ...
            initial_final_share = current_share
        else:
            return {'remaining': 0, 'overpaid': 0, 'initial_final_share': 0, 'total_settled': total_settled}
    
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

### Formula 5: Display Remaining (With Sign)
```
DisplayRemaining = sign(Client_PnL) × RemainingRaw
```

**Where:**
- `Client_PnL`: Current profit/loss value
- `RemainingRaw`: Raw remaining amount (always ≥ 0) from Formula 4
- `DisplayRemaining`: Signed remaining for display

**Sign Logic:**
- **IF Client_PnL < 0 (LOSS)**: DisplayRemaining = +RemainingRaw (client owes you)
- **IF Client_PnL > 0 (PROFIT)**: DisplayRemaining = -RemainingRaw (you owe client)
- **IF Client_PnL = 0**: DisplayRemaining = 0 (no settlement)

**Implementation:**
```python
def calculate_display_remaining(client_pnl, remaining_amount):
    if client_pnl > 0:
        return -remaining_amount  # You owe client (negative)
    else:
        return remaining_amount  # Client owes you (positive)
```

---

### Formula 6: Masked Capital
```
MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
```

**Where:**
- `SharePayment`: Settlement payment amount (integer, > 0)
- `LockedInitialPnL`: PnL value when share was locked
- `LockedInitialFinalShare`: Share amount when cycle started
- `MaskedCapital`: Amount to deduct from funding/exchange_balance

**Purpose:**
- Maps SharePayment linearly back to PnL
- Prevents double-counting of share percentage
- Ensures settlement reduces balances proportionally

**Implementation:**
```python
def compute_masked_capital(self, share_payment):
    settlement_info = self.get_remaining_settlement_amount()
    initial_final_share = settlement_info['initial_final_share']
    locked_initial_pnl = self.locked_initial_pnl
    
    if initial_final_share == 0 or locked_initial_pnl is None:
        return 0
    
    return int((share_payment * abs(locked_initial_pnl)) / initial_final_share)
```

**Example:**
- LockedInitialPnL = -1000 (loss)
- LockedInitialFinalShare = 200 (20% share)
- SharePayment = 50
- MaskedCapital = (50 × 1000) / 200 = 250

---

### Formula 7: Balance Updates After Settlement

#### LOSS CASE (Client_PnL < 0):
```
Funding = Funding - MaskedCapital
ExchangeBalance = ExchangeBalance (unchanged)
```

#### PROFIT CASE (Client_PnL > 0):
```
        ExchangeBalance = ExchangeBalance - MaskedCapital
Funding = Funding (NO CHANGE - NEVER INCREASES)
```

**Critical Rules:**
1. **Funding NEVER increases** when paying profits
2. **Both balances must remain ≥ 0** after settlement
3. **MaskedCapital is calculated BEFORE balance update**

---

### Formula 8: Transaction Amount Sign
```
IF Client_PnL > 0 (PROFIT):
    Transaction.amount = -SharePayment (you paid client)
    
ELSE IF Client_PnL < 0 (LOSS):
    Transaction.amount = +SharePayment (client paid you)
    
ELSE (Client_PnL = 0):
    Transaction.amount = 0 (no transaction)
```

**Critical Rule:**
- **Sign is decided BEFORE balance update** (prevents race conditions)

---

## PnL Cycle Management

### Cycle Start Conditions

A new PnL cycle starts when:

1. **PnL Sign Flip**
   - LOSS → PROFIT: New cycle starts
   - PROFIT → LOSS: New cycle starts
   - Zero crossing triggers new cycle

2. **Funding Change**
   - New funding = new exposure = new cycle
   - Tracked via `locked_initial_funding`

3. **PnL Magnitude Reduction**
   - If current |PnL| < locked |PnL|: Trading reduced exposure → reset cycle
   - Prevents stale locked shares from persisting

### Cycle Reset Conditions

Cycle resets (locks cleared) when:

1. **Full Settlement Complete**
   - Remaining = 0 AND PnL = 0
   - All settlements from cycle are complete

2. **Re-funding Occurs**
   - New capital injection (LOSS case only)
   - Resets cycle to allow new share calculation

3. **Manual Funding Added**
   - New funding changes exposure
   - Cycle must reset

### Cycle Tracking

**Fields:**
- `cycle_start_date`: Timestamp when cycle started
- `locked_initial_funding`: Funding when cycle started
- `locked_initial_pnl`: PnL when cycle started

**Settlement Filtering:**
```python
# Only count settlements from current cycle
if self.cycle_start_date:
    total_settled = self.settlements.filter(
        date__gte=self.cycle_start_date
    ).aggregate(total=models.Sum('amount'))['total'] or 0
```

---

## Share Locking Mechanism

### Purpose
Prevent share from shrinking after payments. Share is decided by trading outcome, not by settlement.

### Locking Logic

**When Share is Locked:**
1. **First compute** when FinalShare > 0
2. **PnL cycle change** (sign flip)
3. **Manual trigger** via `lock_initial_share_if_needed()`

**What Gets Locked:**
- `locked_initial_final_share`: FinalShare value
- `locked_share_percentage`: Share percentage used
- `locked_initial_pnl`: PnL value
- `cycle_start_date`: Timestamp
- `locked_initial_funding`: Funding amount

**Locking Implementation:**
```python
def lock_initial_share_if_needed(self):
    client_pnl = self.compute_client_pnl()
    
    # Check for PnL magnitude reduction (reset cycle)
    if self.locked_initial_pnl is not None and client_pnl != 0:
        if abs(client_pnl) < abs(self.locked_initial_pnl):
            # Reset cycle - trading reduced exposure
            self.locked_initial_final_share = None
            # ... reset all locks ...
    
    # Check for funding change (reset cycle)
    if self.locked_initial_final_share is not None:
        if self.locked_initial_funding is not None:
            if self.funding != self.locked_initial_funding:
                # Reset cycle - new exposure
                # ... reset all locks ...
    
    # Lock share if needed
    if self.locked_initial_final_share is None or self.locked_initial_pnl is None:
        # First time - lock the share
        final_share = self.compute_my_share()
        if final_share > 0:
            share_pct = self.get_share_percentage(client_pnl)
            self.locked_initial_final_share = final_share
            self.locked_share_percentage = share_pct
            self.locked_initial_pnl = client_pnl
            self.cycle_start_date = timezone.now()
            self.locked_initial_funding = self.funding
            self.save(update_fields=[...])
    
    elif client_pnl != 0 and self.locked_initial_pnl != 0:
        # Check if PnL cycle changed (sign flip)
        if (client_pnl < 0) != (self.locked_initial_pnl < 0):
            # PnL cycle changed - lock new share
            final_share = self.compute_my_share()
            if final_share > 0:
                # ... lock new share ...
```

### Share Never Shrinks Rule

**Critical Principle:**
- Share is calculated once at cycle start
- Share remains fixed throughout cycle
- Payments reduce remaining, NOT share

**Example:**
- Initial: PnL = -1000, Share = 200 (20%)
- Payment: 50
- After: Remaining = 150 (NOT 150 recalculated from new PnL)

---

## Settlement Logic

### Settlement Recording Flow

1. **Validate PnL**
   - Check Client_PnL ≠ 0 (no settlement if trading flat)
   - Calculate Client_PnL BEFORE any balance updates

2. **Lock Share**
   - Call `lock_initial_share_if_needed()`
   - Ensure share is locked for current cycle

3. **Get Remaining**
   - Call `get_remaining_settlement_amount()`
   - Get `initial_final_share`, `remaining_amount`, `overpaid_amount`

4. **Validate Settlement**
   - Check `initial_final_share > 0` (block if zero)
   - Check `paid_amount ≤ remaining_amount` (prevent over-settlement)

5. **Calculate Masked Capital**
   - Use Formula 6: `MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare`

6. **Validate Balances**
   - LOSS: Check `funding - masked_capital ≥ 0`
   - PROFIT: Check `exchange_balance - masked_capital ≥ 0`

7. **Update Balances**
   - LOSS: `funding -= masked_capital`
   - PROFIT: `exchange_balance -= masked_capital`

8. **Create Records**
   - Create `Settlement` record (tracks share payments)
   - Create `Transaction` record (audit trail with correct sign)

9. **Handle Re-funding** (LOSS case only)
   - Optional: Re-add capital to funding
   - This is NEW capital, NOT settlement

### Settlement Recording Implementation

   ```python
@login_required
def record_payment(request, account_id):
    account = get_object_or_404(ClientExchangeAccount, pk=account_id, client__user=request.user)
    
    if request.method == "POST":
        paid_amount = int(request.POST.get("amount"))
        payment_date = parse_date(request.POST.get("payment_date"))
        
        with transaction.atomic():
            # Lock row to prevent concurrent modifications
            account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
            
            # CRITICAL: Calculate PnL BEFORE balance update
            client_pnl_before = account.compute_client_pnl()
            
            # Validate PnL ≠ 0
            if client_pnl_before == 0:
                return error("Account PnL is zero. No settlement needed.")
            
            # Lock share
            account.lock_initial_share_if_needed()
            
            # Get remaining
            settlement_info = account.get_remaining_settlement_amount()
            initial_final_share = settlement_info['initial_final_share']
            remaining_amount = settlement_info['remaining']
            
            # Validate share > 0
            if initial_final_share == 0:
                return error("No settlement allowed. Initial final share is zero.")
            
            # Validate amount ≤ remaining
            if paid_amount > remaining_amount:
                raise ValidationError(f"Paid amount ({paid_amount}) cannot exceed remaining ({remaining_amount})")
            
            # Calculate masked capital
            masked_capital = account.compute_masked_capital(paid_amount)
            
            # Decide transaction sign BEFORE balance update
            if client_pnl_before > 0:
                transaction_amount = -paid_amount  # You paid client
            else:
                transaction_amount = paid_amount  # Client paid you
            
            # Update balances
            if client_pnl_before < 0:
                # LOSS: Reduce funding
                if account.funding - masked_capital < 0:
                    raise ValidationError("Funding would become negative")
                account.funding -= masked_capital
            else:
                # PROFIT: Reduce exchange balance
                if account.exchange_balance - masked_capital < 0:
                    raise ValidationError("Exchange balance would become negative")
                account.exchange_balance -= masked_capital
            
            account.save()
            
            # Create settlement record
            Settlement.objects.create(
                client_exchange=account,
                amount=paid_amount,
                date=payment_date,
                notes=notes
            )
            
            # Create transaction record
            Transaction.objects.create(
                client_exchange=account,
                type='RECORD_PAYMENT',
                amount=transaction_amount,  # Signed correctly
                date=payment_date,
                exchange_balance_after=account.exchange_balance,
                notes=notes
            )
```

### Concurrent Payment Protection

**Database Row Locking:**
```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    # ... settlement logic ...
```

**Prevents:**
- Race conditions when multiple payments occur simultaneously
- Double-counting of settlements
- Incorrect remaining calculations

---

## Display Logic

### Pending Summary View

**Two Sections:**
1. **Clients Owe You** (Client_PnL < 0, LOSS case)
2. **You Owe Clients** (Client_PnL > 0, PROFIT case)

**For Each Client-Exchange:**

1. **Calculate Client_PnL**
```python
   client_pnl = client_exchange.compute_client_pnl()
   ```

2. **Lock Share**
   ```python
   client_exchange.lock_initial_share_if_needed()
   ```

3. **Get Settlement Info**
```python
   settlement_info = client_exchange.get_remaining_settlement_amount()
   initial_final_share = settlement_info['initial_final_share']
   remaining_amount = settlement_info['remaining']
   ```

4. **Calculate Display Values**
```python
   final_share = initial_final_share if initial_final_share > 0 else client_exchange.compute_my_share()
   display_remaining = calculate_display_remaining(client_pnl, remaining_amount)
   remaining_display = abs(display_remaining)  # Always positive for display
   ```

5. **Handle N.A Cases**
```python
   show_na = (final_share == 0)  # Show N.A if share is zero
   ```

6. **Add to Appropriate List**
   - LOSS: Add to `clients_owe_list`
   - PROFIT: Add to `you_owe_list`
   - NEUTRAL (PnL = 0): Add to `clients_owe_list` with `show_na = True`

### Display Fields

**For Each Entry:**
- `client`: Client object
- `exchange`: Exchange object
- `account`: ClientExchangeAccount object
- `client_pnl`: Client PnL value (masked in template)
- `amount_owed`: Total amount owed (masked in template)
- `my_share_amount`: Final share (floor rounded)
- `remaining_amount`: Remaining settlement (absolute value, always positive)
- `share_percentage`: Share percentage used
- `show_na`: Flag to show "N.A" instead of values

### Sorting

**Sort Key:**
```python
def get_sort_key(item):
    if item.get("show_na", False):
        return 0  # N.A items sort to bottom
    return abs(item["my_share_amount"])
```

**Sort Order:** Descending (largest share first)

---

## Edge Cases and Validations

### Edge Case 1: PnL = 0 (Trading Flat)

**Behavior:**
- Client appears in pending list with `show_na = True`
- All values show as "N.A"
- No settlement allowed

**Implementation:**
```python
if client_pnl == 0:
    show_na = True
    remaining_amount = 0
    # Add to clients_owe_list with N.A flag
```

### Edge Case 2: FinalShare = 0

**Causes:**
- Share percentage too small
- PnL too small (floor rounding results in 0)

**Behavior:**
- Client appears in pending list with `show_na = True`
- Settlement blocked (InitialFinalShare = 0)

**Validation:**
```python
if initial_final_share == 0:
    return error("No settlement allowed. Initial final share is zero.")
```

### Edge Case 3: Over-Settlement

**Prevention:**
```python
if paid_amount > remaining_amount:
    raise ValidationError(f"Paid amount ({paid_amount}) cannot exceed remaining ({remaining_amount})")
```

**Detection:**
```python
overpaid = max(0, total_settled - initial_final_share)
```

### Edge Case 4: Negative Balances

**Prevention:**
```python
# LOSS case
if account.funding - masked_capital < 0:
    raise ValidationError("Funding would become negative")

# PROFIT case
if account.exchange_balance - masked_capital < 0:
    raise ValidationError("Exchange balance would become negative")
```

### Edge Case 5: Funding Increase in Profit Case

**Rule:** Funding NEVER increases when paying profits

**Validation:**
```python
if client_pnl_before > 0:
    # PROFIT: Re-add capital is FORBIDDEN
    if re_add_capital:
        raise ValidationError("Re-add capital option is not allowed for profit cases.")
```

### Edge Case 6: PnL Sign Change During Settlement

**Prevention:**
- Calculate Client_PnL BEFORE balance update
- Lock share BEFORE settlement
- Use locked PnL for transaction sign

**Implementation:**
```python
# CRITICAL: Calculate PnL BEFORE balance update
client_pnl_before = account.compute_client_pnl()

# Lock share
account.lock_initial_share_if_needed()

# Decide sign based on PnL BEFORE update
if client_pnl_before > 0:
    transaction_amount = -paid_amount
else:
    transaction_amount = paid_amount
```

### Edge Case 7: Concurrent Payments

**Prevention:**
- Database row locking (`select_for_update()`)
- Atomic transactions

**Implementation:**
```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    # ... settlement logic ...
```

### Edge Case 8: Cycle Mixing

**Prevention:**
- Track `cycle_start_date` for each cycle
- Filter settlements by cycle

**Implementation:**
```python
if self.cycle_start_date:
    total_settled = self.settlements.filter(
        date__gte=self.cycle_start_date
    ).aggregate(total=models.Sum('amount'))['total'] or 0
```

---

## Database Models

### ClientExchangeAccount

**Core Fields:**
- `funding`: BIGINT, ≥ 0 (total real money given to client)
- `exchange_balance`: BIGINT, ≥ 0 (current balance on exchange)
- `loss_share_percentage`: INT, 0-100 (admin share for losses, IMMUTABLE)
- `profit_share_percentage`: INT, 0-100 (admin share for profits, can change)
- `my_percentage`: INT, 0-100 (legacy fallback)

**Locking Fields:**
- `locked_initial_final_share`: BIGINT (share locked at cycle start)
- `locked_share_percentage`: INT (percentage locked at cycle start)
- `locked_initial_pnl`: BIGINT (PnL locked at cycle start)
- `cycle_start_date`: DateTime (when cycle started)
- `locked_initial_funding`: BIGINT (funding locked at cycle start)

### Settlement

**Fields:**
- `client_exchange`: ForeignKey to ClientExchangeAccount
- `amount`: BIGINT, > 0 (share payment amount)
- `date`: DateTime (when payment was made)
- `notes`: Text (optional notes)

**Purpose:** Track individual settlement payments per cycle

### Transaction

**Fields:**
- `client_exchange`: ForeignKey to ClientExchangeAccount
- `type`: CharField ('RECORD_PAYMENT', 'FUNDING', 'TRADE', etc.)
- `amount`: BIGINT (signed: positive if client pays you, negative if you pay client)
- `date`: DateTime
- `exchange_balance_after`: BIGINT (balance after transaction, for audit)
- `notes`: Text (optional)

**Purpose:** Audit trail only, NEVER used to recompute balances

---

## Key Methods

### ClientExchangeAccount Methods

#### `compute_client_pnl()`
```python
def compute_client_pnl(self):
    """Formula 1: Client_PnL = ExchangeBalance - Funding"""
    return self.exchange_balance - self.funding
```

#### `get_share_percentage(client_pnl=None)`
```python
def get_share_percentage(self, client_pnl=None):
    """Get appropriate share percentage based on PnL direction"""
    if client_pnl is None:
        client_pnl = self.compute_client_pnl()
    
    if client_pnl < 0:
        # LOSS: Use loss_share_percentage or my_percentage fallback
        return self.loss_share_percentage if self.loss_share_percentage > 0 else self.my_percentage
    elif client_pnl > 0:
        # PROFIT: Use profit_share_percentage or my_percentage fallback
        return self.profit_share_percentage if self.profit_share_percentage > 0 else self.my_percentage
    else:
        return 0
```

#### `compute_exact_share()`
```python
def compute_exact_share(self):
    """Formula 2: ExactShare = |Client_PnL| × (SharePercentage / 100.0)"""
    client_pnl = self.compute_client_pnl()
    if client_pnl == 0:
        return 0.0
    
    share_pct = self.get_share_percentage(client_pnl)
    return abs(client_pnl) * (share_pct / 100.0)
```

#### `compute_my_share()`
```python
def compute_my_share(self):
    """Formula 3: FinalShare = floor(ExactShare)"""
    import math
    client_pnl = self.compute_client_pnl()
    if client_pnl == 0:
        return 0
    
    share_pct = self.get_share_percentage(client_pnl)
    exact_share = abs(client_pnl) * (share_pct / 100.0)
    return int(math.floor(exact_share))
```

#### `lock_initial_share_if_needed()`
```python
def lock_initial_share_if_needed(self):
    """Lock share at first compute per PnL cycle"""
    # ... see Share Locking Mechanism section ...
```

#### `get_remaining_settlement_amount()`
```python
def get_remaining_settlement_amount(self):
    """Formula 4: RemainingRaw = max(0, LockedInitialFinalShare - Sum(SharePayments))"""
    # ... see Formula 4 section ...
```

#### `compute_masked_capital(share_payment)`
```python
def compute_masked_capital(self, share_payment):
    """Formula 6: MaskedCapital = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare"""
    # ... see Formula 6 section ...
```

#### `close_cycle()`
```python
def close_cycle(self):
    """Close current settlement cycle by resetting all locks"""
    self.locked_initial_final_share = None
    self.locked_share_percentage = None
    self.locked_initial_pnl = None
    self.cycle_start_date = None
    self.locked_initial_funding = None
    self.save(update_fields=[...])
```

### View Helper Functions

#### `calculate_display_remaining(client_pnl, remaining_amount)`
```python
def calculate_display_remaining(client_pnl, remaining_amount):
    """Formula 5: DisplayRemaining = sign(Client_PnL) × RemainingRaw"""
    if client_pnl > 0:
        return -remaining_amount  # You owe client (negative)
    else:
        return remaining_amount  # Client owes you (positive)
```

---

## Example Scenarios

### Scenario 1: Simple Loss Settlement

**Initial State:**
- Funding = 10,000
- ExchangeBalance = 8,000
- Client_PnL = 8,000 - 10,000 = -2,000 (LOSS)
- loss_share_percentage = 20%

**Step 1: Calculate Share**
- ExactShare = 2,000 × 0.20 = 400.0
- FinalShare = floor(400.0) = 400
- LockedInitialFinalShare = 400
- LockedInitialPnL = -2,000

**Step 2: Record Payment (50)**
- SharePayment = 50
- MaskedCapital = (50 × 2,000) / 400 = 250
- New Funding = 10,000 - 250 = 9,750
- New ExchangeBalance = 8,000 (unchanged)
- Remaining = 400 - 50 = 350

**Step 3: Record Payment (350)**
- SharePayment = 350
- MaskedCapital = (350 × 2,000) / 400 = 1,750
- New Funding = 9,750 - 1,750 = 8,000
- New ExchangeBalance = 8,000 (unchanged)
- Remaining = 400 - 400 = 0 (fully settled)

**Final State:**
- Funding = 8,000
- ExchangeBalance = 8,000
- Client_PnL = 0 (settlement complete)
- Remaining = 0

---

### Scenario 2: Simple Profit Settlement

**Initial State:**
- Funding = 10,000
- ExchangeBalance = 12,000
- Client_PnL = 12,000 - 10,000 = +2,000 (PROFIT)
- profit_share_percentage = 20%

**Step 1: Calculate Share**
- ExactShare = 2,000 × 0.20 = 400.0
- FinalShare = floor(400.0) = 400
- LockedInitialFinalShare = 400
- LockedInitialPnL = +2,000

**Step 2: Record Payment (100)**
- SharePayment = 100
- MaskedCapital = (100 × 2,000) / 400 = 500
- New Funding = 10,000 (unchanged)
- New ExchangeBalance = 12,000 - 500 = 11,500
- Remaining = 400 - 100 = 300

**Step 3: Record Payment (300)**
- SharePayment = 300
- MaskedCapital = (300 × 2,000) / 400 = 1,500
- New Funding = 10,000 (unchanged)
- New ExchangeBalance = 11,500 - 1,500 = 10,000
- Remaining = 400 - 400 = 0 (fully settled)

**Final State:**
- Funding = 10,000 (unchanged)
- ExchangeBalance = 10,000
- Client_PnL = 0 (settlement complete)
- Remaining = 0

---

### Scenario 3: PnL Sign Flip (Cycle Change)

**Initial State (LOSS Cycle):**
- Funding = 10,000
- ExchangeBalance = 8,000
- Client_PnL = -2,000 (LOSS)
- loss_share_percentage = 20%
- LockedInitialFinalShare = 400
- Settled = 200
- Remaining = 200

**Trading Activity:**
- ExchangeBalance increases to 12,000
- New Client_PnL = 12,000 - 10,000 = +2,000 (PROFIT)

**New Cycle Starts:**
- PnL sign flipped: LOSS → PROFIT
- Old cycle settlements (200) are NOT counted
- New cycle: Lock new share
- profit_share_percentage = 20%
- New LockedInitialFinalShare = 400
- New Remaining = 400 (old settlements ignored)

**Settlement:**
- Old cycle: 200 settled (ignored in new cycle)
- New cycle: Can settle up to 400

---

### Scenario 4: Floor Rounding Edge Case

**Initial State:**
- Funding = 10,000
- ExchangeBalance = 10,099
- Client_PnL = +99 (PROFIT)
- profit_share_percentage = 20%

**Calculate Share:**
- ExactShare = 99 × 0.20 = 19.8
- FinalShare = floor(19.8) = 19
- LockedInitialFinalShare = 19

**Settlement:**
- Can settle up to 19
- If PnL changes to 98: Share recalculates to 19.6 → floor(19.6) = 19 (same)
- If PnL changes to 100: Share recalculates to 20.0 → floor(20.0) = 20 (new share)

---

### Scenario 5: Over-Settlement Prevention

**Initial State:**
- LockedInitialFinalShare = 400
- Already Settled = 350
- Remaining = 50

**Attempted Payment:**
- PaidAmount = 100

**Validation:**
```python
if paid_amount > remaining_amount:
    raise ValidationError("Paid amount (100) cannot exceed remaining (50)")
```

**Result:** Payment rejected, no balance changes

---

### Scenario 6: Concurrent Payment Protection

**Scenario:**
- Two users try to settle 200 each simultaneously
- Remaining = 300

**Without Locking:**
- Both payments succeed
- Total settled = 400 (exceeds remaining)

**With Locking:**
```python
with transaction.atomic():
    account = ClientExchangeAccount.objects.select_for_update().get(pk=account_id)
    # First payment locks row, second waits
    # First payment: Remaining = 300 - 200 = 100
    # Second payment: Remaining = 100 - 200 = ERROR (rejected)
```

**Result:** Only first payment succeeds, second is rejected

---

## Summary

### Key Principles

1. **Share Never Shrinks**: Share is locked at cycle start and remains fixed
2. **Cycle Separation**: Settlements are tracked per PnL cycle
3. **Masked Capital**: Share payments map linearly back to PnL
4. **Sign Before Update**: Transaction sign decided BEFORE balance mutation
5. **Funding Never Increases**: In profit cases, funding remains unchanged
6. **Concurrent Protection**: Database row locking prevents race conditions

### Formula Summary

1. **Client_PnL** = ExchangeBalance - Funding
2. **ExactShare** = |Client_PnL| × (SharePercentage / 100.0)
3. **FinalShare** = floor(ExactShare)
4. **RemainingRaw** = max(0, LockedInitialFinalShare - Sum(SharePayments))
5. **DisplayRemaining** = sign(Client_PnL) × RemainingRaw
6. **MaskedCapital** = (SharePayment × |LockedInitialPnL|) / LockedInitialFinalShare
7. **LOSS**: Funding = Funding - MaskedCapital
8. **PROFIT**: ExchangeBalance = ExchangeBalance - MaskedCapital

### Critical Rules

- ✅ Share locked at first compute per cycle
- ✅ Only count settlements from current cycle
- ✅ Transaction sign decided BEFORE balance update
- ✅ Funding NEVER increases in profit cases
- ✅ Database row locking for concurrent payments
- ✅ Validate balances remain ≥ 0
- ✅ Block settlement when FinalShare = 0
- ✅ Prevent over-settlement

---

**Document Version:** 1.0  
**Last Updated:** 2024  
**System:** Masked Share Settlement System

