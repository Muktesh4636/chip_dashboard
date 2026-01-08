# MASKED SHARE SETTLEMENT SYSTEM

(Final Specification with Dynamic Profit % Support)

**Version:** 2.0 (Final & Frozen)  
**Status:** Approved for Production  
**Control Type:** Manual-first, system-assisted  
**Sensitivity:** High (PnL intentionally masked)

## 1. PURPOSE

This system is designed to:

- Settle only the admin's share
- Hide actual profit/loss amounts
- Hide remaining percentages
- Avoid decimals completely
- Allow partial and manual settlements
- Allow profit percentage to change anytime
- Keep math simple, deterministic, and safe

**Precision is intentionally sacrificed for simplicity and control.**

## 2. CORE DEFINITIONS

| Term | Meaning |
|------|---------|
| Funding (F) | Capital given to client |
| Exchange Balance (EB) | Final balance on exchange |
| Loss (L) | `max(F − EB, 0)` |
| Profit (P) | `max(EB − F, 0)` |
| Loss Share % | Fixed percentage for losses |
| Profit Share % | Percentage for profits (can change anytime) |
| Exact Share | Share before rounding |
| Final Share | Share after rounding |
| Settlement | Actual payment recorded |

## 3. PnL CALCULATION (NO ROUNDING)

### Loss
```
Loss = max(Funding − ExchangeBalance, 0)
```

### Profit
```
Profit = max(ExchangeBalance − Funding, 0)
```

**Only one of Loss or Profit can be greater than zero.**

## 4. SHARE CALCULATION (AUTHORITATIVE)

### 4.1 Exact Share (NO rounding)
```
ExactShare = PnL × (Share% / 100)
```

**Rules:**
- Percentages are never rounded
- Full precision is used internally

### 4.2 Final Share (ONLY rounding step)
```
FinalShare = floor(ExactShare)
```

🔒 **Rounding Policy**

- Rounding happens **ONLY ONCE**
- Method = **FLOOR** (round down)
- Applies to both client and admin
- No decimals are shown or settled
- Fractional values are discarded permanently

## 5. LOSS SETTLEMENT LOGIC

### Direction
If `Loss > 0` → Client pays admin

### Amount
```
Amount Due = FinalLossShare
```

**If:**
```
FinalLossShare == 0
```
→ **No settlement allowed.**

## 6. PROFIT SETTLEMENT LOGIC (DYNAMIC % SUPPORTED)

### 6.1 Key Rule (CRITICAL)

**Profit percentage is applied per profit event and frozen forever.**  
Percentage changes affect only future profits.

### 6.2 Profit Share Calculation (At Time of Profit)

Let:
- `ProfitShare%_current` = profit % active at that time

```
ExactProfitShare = Profit × (ProfitShare%_current / 100)
FinalProfitShare = floor(ExactProfitShare)
```

**This `FinalProfitShare` is stored and never recalculated, even if % changes later.**

### 6.3 Direction
If `Profit > 0` → Admin pays client

## 7. SETTLEMENT RULES (COMMON)

### Partial Settlements
- ✅ Allowed
- Integer values only

### Remaining Share
```
RemainingShare = FinalShare − SumOfSettlementsSoFar
```

### Validation
```
0 < SettlementAmount ≤ RemainingShare
```

## 8. ZERO-SHARE BEHAVIOR (INTENTIONAL)

**If:**
```
FinalShare == 0
```

**Then:**
- No pending amount
- No settlement allowed
- Client treated as settled

**This is by design, not a bug.**

## 9. MASKING POLICY (INTENTIONAL)

The system does **NOT** expose:
- Actual PnL values
- Exact percentages used historically
- Remaining fractional amounts
- Accumulated fractions

**Fractional money is lost intentionally for both sides.**

## 10. ACCEPTED EDGE CASES (NOT BUGS)

The following are explicitly accepted behaviors:
- Very small % resulting in `FinalShare = 0`
- Fractional amounts discarded
- Many small trades yielding zero payout
- Manual handling of Loss → Profit flip
- Single admin (no concurrency protection)
- Manual overrides with notes

## 11. BLOCKED EDGE CASES (MUST NOT HAPPEN)

### 11.1 Share % Changed After Data Exists (LOSS SIDE)

❌ **Not allowed**

Loss share % must be immutable once data exists

### 11.2 Recalculating Old Profits with New %

❌ **Not allowed**

Corrupts history

### 11.3 Settlement When FinalShare = 0

❌ **Must be blocked**

### 11.4 Over-Settlement
```
SettlementAmount > RemainingShare
```

❌ **Must be blocked**

## 12. INPUT VALIDATIONS (MINIMAL)

```
Funding > 0
ExchangeBalance ≥ 0
Share% > 0
SettlementAmount > 0
```

**No additional automation is required.**

## 13. SYSTEM GUARANTEES

This system guarantees:
- Deterministic math
- No rounding drift
- Ledger stability
- Safe manual control
- Support for changing profit %
- No historical corruption

## 14. SYSTEM NON-GOALS

This system does **NOT** attempt to:
- Recover fractional money
- Auto-adjust old records
- Handle multi-admin concurrency
- Maximize earnings precision

## 15. FINAL ONE-LINE POLICY (PIN THIS)

**PnL is calculated exactly, shares are rounded down once to whole numbers, and profit percentages apply only to future profits and are never retroactive.**

