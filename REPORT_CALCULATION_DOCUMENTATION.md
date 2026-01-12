# Report Calculation Documentation

## Overview
This document explains how turnover and profits are calculated in the Transaction Hub system, including how Company % and My Own % percentages are used.

---

## 1. Configuration Setup

### Percentage Configuration
Each client-exchange account has three percentage values:

- **My Total %**: Your total percentage share (e.g., 10%)
- **Company %**: Company's percentage share (e.g., 9.5%)
- **My Own %**: Your own percentage share (e.g., 0.5%)

**Validation Rule:**
```
Company % + My Own % = My Total %
```

**Example:**
- My Total % = 10%
- Company % = 9.5%
- My Own % = 0.5%
- Validation: 9.5% + 0.5% = 10% ✓

**Note:** These percentages support decimal values (e.g., 9.5, 0.5) and are stored with 2 decimal places precision in the database.

---

## 2. Turnover Calculation

### Formula
```
Turnover = Σ |Exchange Balance After - Exchange Balance Before|
```

**Where:**
- Only `TRADE` type transactions are included
- `Exchange Balance After` = Balance after the trade
- `Exchange Balance Before` = Balance before the trade
- Absolute value is used (always positive)

### Example
If a client makes trades:
- Trade 1: Balance changes from ₹10,000 to ₹12,000 → Movement = ₹2,000
- Trade 2: Balance changes from ₹12,000 to ₹8,000 → Movement = ₹4,000
- Trade 3: Balance changes from ₹8,000 to ₹9,500 → Movement = ₹1,500

**Total Turnover = ₹2,000 + ₹4,000 + ₹1,500 = ₹7,500**

**Important:** Turnover measures trading activity, NOT funding or settlements.

---

## 3. Profit/Loss Calculation

### Core Rule: RECORD_PAYMENT Transactions

**Single Source of Truth:** Only `RECORD_PAYMENT` transactions are used for profit/loss calculations.

### Sign Convention

| Payment Direction | Meaning | Amount Sign | Effect on You |
|-------------------|---------|-------------|---------------|
| Client → You | Client loss settlement | **+X** | ✅ Your PROFIT |
| You → Client | Client profit settlement | **-X** | ❌ Your LOSS |

### Total Profit Formula
```
Your Total Profit = Σ(RECORD_PAYMENT.amount)
```

**Where:**
- Positive amounts = Client paid you (your profit)
- Negative amounts = You paid client (your loss)
- Sum of all payment amounts = Your total profit/loss

### Example
If you have these payments:
- Payment 1: +₹9,000 (Client paid you)
- Payment 2: -₹5,000 (You paid client)
- Payment 3: +₹3,000 (Client paid you)

**Your Total Profit = ₹9,000 + (-₹5,000) + ₹3,000 = ₹7,000**

---

## 4. Profit Split Calculation (Company % vs My Own %)

### When Report Configuration Exists

If a client-exchange account has report configuration (Company % and My Own % set), the profit is split between you and the company.

### Split Formulas

```
My Profit = Payment Amount × (My Own % / My Total %)
Company Profit = Payment Amount × (Company % / My Total %)
```

### Example 1: Client Loss (Your Profit)

**Configuration:**
- My Total % = 10%
- Company % = 9.5%
- My Own % = 0.5%

**Payment:** +₹10,000 (Client paid you)

**Calculation:**
```
My Profit = ₹10,000 × (0.5 / 10) = ₹10,000 × 0.05 = ₹500
Company Profit = ₹10,000 × (9.5 / 10) = ₹10,000 × 0.95 = ₹9,500
```

**Verification:** ₹500 + ₹9,500 = ₹10,000 ✓

### Example 2: Client Profit (Your Loss)

**Configuration:**
- My Total % = 10%
- Company % = 9.5%
- My Own % = 0.5%

**Payment:** -₹8,000 (You paid client)

**Calculation:**
```
My Profit = -₹8,000 × (0.5 / 10) = -₹8,000 × 0.05 = -₹400
Company Profit = -₹8,000 × (9.5 / 10) = -₹8,000 × 0.95 = -₹7,600
```

**Verification:** -₹400 + (-₹7,600) = -₹8,000 ✓

### Example 3: Multiple Payments

**Configuration:**
- My Total % = 10%
- Company % = 9.5%
- My Own % = 0.5%

**Payments:**
- Payment 1: +₹10,000
- Payment 2: -₹5,000
- Payment 3: +₹3,000

**Calculation:**

**Payment 1 (+₹10,000):**
- My Profit = ₹10,000 × 0.05 = ₹500
- Company Profit = ₹10,000 × 0.95 = ₹9,500

**Payment 2 (-₹5,000):**
- My Profit = -₹5,000 × 0.05 = -₹250
- Company Profit = -₹5,000 × 0.95 = -₹4,750

**Payment 3 (+₹3,000):**
- My Profit = ₹3,000 × 0.05 = ₹150
- Company Profit = ₹3,000 × 0.95 = ₹2,850

**Totals:**
- **My Total Profit** = ₹500 + (-₹250) + ₹150 = ₹400
- **Company Total Profit** = ₹9,500 + (-₹4,750) + ₹2,850 = ₹7,600
- **Your Total Profit** = ₹400 + ₹7,600 = ₹8,000 ✓

---

## 5. When Report Configuration Doesn't Exist

If a client-exchange account does NOT have report configuration (Company % and My Own % not set), then:

```
My Profit = Payment Amount (100% goes to you)
Company Profit = ₹0
```

---

## 6. Decimal Precision

### Storage
All percentages are stored as `Decimal` with 2 decimal places:
- 9.5% is stored as `9.50`
- 0.5% is stored as `0.50`
- 10% is stored as `10.00`

### Calculation Precision
All calculations use `Decimal` type for precision:
- No rounding errors
- Exact decimal arithmetic
- Values are preserved exactly as entered

### Example with Decimals

**Configuration:**
- My Total % = 10.00%
- Company % = 9.50%
- My Own % = 0.50%

**Payment:** +₹1,000

**Calculation:**
```
My Profit = ₹1,000 × (0.50 / 10.00) = ₹1,000 × 0.05 = ₹50.00
Company Profit = ₹1,000 × (9.50 / 10.00) = ₹1,000 × 0.95 = ₹950.00
```

**Verification:** ₹50.00 + ₹950.00 = ₹1,000.00 ✓

---

## 7. Daily/Weekly/Monthly Reports

### Daily Reports
- **Turnover:** Sum of absolute exchange balance movements for TRADE transactions on that day
- **Profit:** Sum of RECORD_PAYMENT amounts on that day (split by Company % and My Own %)

### Weekly Reports
- **Turnover:** Sum of absolute exchange balance movements for TRADE transactions in that week
- **Profit:** Sum of RECORD_PAYMENT amounts in that week (split by Company % and My Own %)

### Monthly Reports
- **Turnover:** Sum of absolute exchange balance movements for TRADE transactions in that month
- **Profit:** Sum of RECORD_PAYMENT amounts in that month (split by Company % and My Own %)

---

## 8. Summary

### Key Points

1. **Turnover** = Trading activity (TRADE transactions only)
2. **Profit** = Payment settlements (RECORD_PAYMENT transactions only)
3. **Company % + My Own %** must equal **My Total %**
4. **Decimal values** (like 9.5% and 0.5%) are fully supported
5. **All calculations** use exact decimal arithmetic (no rounding errors)
6. **Split formula** applies to each payment individually, then totals are aggregated

### Formula Summary

```
Turnover = Σ |Exchange Balance After - Exchange Balance Before| (for TRADE transactions)

Your Total Profit = Σ(RECORD_PAYMENT.amount)

If Report Config Exists:
  My Profit = Σ[Payment × (My Own % / My Total %)]
  Company Profit = Σ[Payment × (Company % / My Total %)]
  
If No Report Config:
  My Profit = Your Total Profit (100%)
  Company Profit = 0
```

---

## 9. Real-World Example

**Client:** a1  
**Exchange:** CHERRYEXCH  
**Configuration:**
- My Total % = 10%
- Company % = 9.5%
- My Own % = 0.5%

**Transactions:**
1. Trade: Balance changed from ₹0 to ₹50,000
2. Record Payment: +₹5,000 (Client paid you)
3. Trade: Balance changed from ₹50,000 to ₹45,000
4. Record Payment: -₹2,000 (You paid client)

**Calculations:**

**Turnover:**
- Trade 1: |₹50,000 - ₹0| = ₹50,000
- Trade 2: |₹45,000 - ₹50,000| = ₹5,000
- **Total Turnover = ₹55,000**

**Profit Split:**

**Payment 1 (+₹5,000):**
- My Profit = ₹5,000 × (0.5 / 10) = ₹250
- Company Profit = ₹5,000 × (9.5 / 10) = ₹4,750

**Payment 2 (-₹2,000):**
- My Profit = -₹2,000 × (0.5 / 10) = -₹100
- Company Profit = -₹2,000 × (9.5 / 10) = -₹1,900

**Totals:**
- **My Total Profit** = ₹250 + (-₹100) = ₹150
- **Company Total Profit** = ₹4,750 + (-₹1,900) = ₹2,850
- **Your Total Profit** = ₹150 + ₹2,850 = ₹3,000 ✓

---

## 10. Technical Implementation

### Database Fields
- `friend_percentage`: DecimalField(max_digits=5, decimal_places=2) - Company %
- `my_own_percentage`: DecimalField(max_digits=5, decimal_places=2) - My Own %
- `my_percentage`: DecimalField(max_digits=5, decimal_places=2) - My Total %

### Calculation Code
```python
from decimal import Decimal

# Get percentages from report config
my_own_pct = Decimal(str(report_config.my_own_percentage))  # e.g., 0.50
friend_pct = Decimal(str(report_config.friend_percentage))  # e.g., 9.50
my_total_pct = Decimal(str(account.my_percentage))         # e.g., 10.00

# Split payment
my_profit_part = payment_amount * my_own_pct / my_total_pct
friend_profit_part = payment_amount * friend_pct / my_total_pct
```

### Validation
```python
# Validate: Company % + My Own % = My Total %
epsilon = Decimal('0.01')
sum_percentages = friend_pct + own_pct
if abs(sum_percentages - my_total_pct) >= epsilon:
    # Validation failed
    pass
```

---

**Document Version:** 1.0  
**Last Updated:** January 12, 2026  
**System:** Transaction Hub - Money Flow Control

