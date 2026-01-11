# Client Guide: Adding Money to Exchange Accounts

## Overview

This guide explains how to add money (funding) to your exchange trading accounts in the Transaction Hub system. Funding increases both your total funding amount and your exchange balance simultaneously.

---

## Table of Contents

1. [Understanding Funding](#understanding-funding)
2. [How to Add Funding](#how-to-add-funding)
3. [Funding Rules](#funding-rules)
4. [What Happens When You Add Funding](#what-happens-when-you-add-funding)
5. [Viewing Your Account Status](#viewing-your-account-status)
6. [Important Notes](#important-notes)
7. [Troubleshooting](#troubleshooting)

---

## Understanding Funding

### What is Funding?

**Funding** is the process of adding money to your exchange trading account. When you add funding:

- **Funding Amount**: The total amount of real money you have given to the system for trading
- **Exchange Balance**: The current balance available on the exchange for trading

### Key Concepts

- **Funding**: Represents the total capital you have invested
- **Exchange Balance**: Represents the current balance available for trading on the exchange
- **Both values increase together**: When you add funding, both values increase by the same amount

---

## How to Add Funding

### Step-by-Step Instructions

1. **Log in to Your Account**
   - Navigate to the Transaction Hub login page
   - Enter your username and password
   - Click "Login"

2. **Navigate to Exchanges**
   - From the main navigation menu, click on **"Exchanges"**
   - You will see a list of all exchanges where you have accounts

3. **Select Your Exchange Account**
   - Find the exchange account you want to add funding to
   - Click on the account to view its details
   - You will see:
     - Current Funding amount
     - Current Exchange Balance
     - Profit/Loss information
     - Settlement status

4. **Add Funding**
   - On the account detail page, click the **"Add Funding"** button
   - You will be taken to the funding form

5. **Enter Funding Details**
   - **Amount**: Enter the amount you want to add
     - Enter the amount in the smallest currency unit (e.g., paise for rupees, cents for dollars)
     - Example: For ₹10,000, enter `1000000` (10,000 × 100 paise)
     - Minimum amount: 1 unit
   - **Notes (Optional)**: Add any notes about this funding transaction
     - Examples: "Initial deposit", "Additional capital", "Refund from previous trade"

6. **Submit**
   - Review your entries
   - Click **"Add Funding"** to complete the transaction
   - Or click **"Cancel"** to go back without adding funding

7. **Confirmation**
   - You will see a success message showing:
     - The amount added
     - Previous funding amount → New funding amount
     - Previous exchange balance → New exchange balance
   - You will be redirected back to the account detail page

---

## Funding Rules

### The FUNDING RULE

**When you add funding, BOTH funding and exchange_balance increase by the same amount simultaneously.**

This means:
- If you add ₹10,000 (1,000,000 paise):
  - Funding increases by ₹10,000
  - Exchange Balance increases by ₹10,000

### Why Both Increase?

- **Funding** tracks the total capital you've invested
- **Exchange Balance** tracks the money available for trading
- When you add money, it becomes both:
  - Part of your total investment (funding)
  - Available for trading (exchange balance)

---

## What Happens When You Add Funding

### Immediate Effects

1. **Funding Amount Increases**
   - Your total funding amount increases by the amount you added
   - This is tracked permanently in the system

2. **Exchange Balance Increases**
   - Your exchange balance increases by the same amount
   - This money is now available for trading

3. **Transaction Record Created**
   - A transaction record is automatically created
   - Type: `FUNDING_MANUAL`
   - Includes:
     - Date and time of funding
     - Amount added
     - Before and after values for both funding and exchange balance
     - Any notes you added

4. **Cycle Reset (if applicable)**
   - If you have an active profit/loss cycle, adding funding may reset the cycle
   - This ensures accurate tracking of your trading performance

### Example

**Before Adding Funding:**
- Funding: ₹50,000 (5,000,000 paise)
- Exchange Balance: ₹45,000 (4,500,000 paise)
- Profit/Loss: -₹5,000 (loss)

**After Adding ₹10,000:**
- Funding: ₹60,000 (6,000,000 paise) ← Increased by ₹10,000
- Exchange Balance: ₹55,000 (5,500,000 paise) ← Increased by ₹10,000
- Profit/Loss: -₹5,000 (same loss, but now with more capital)

---

## Viewing Your Account Status

### Account Detail Page

After adding funding, you can view your account status on the account detail page, which shows:

1. **Current Funding**
   - Total amount of money you've invested

2. **Current Exchange Balance**
   - Current balance available for trading

3. **Profit/Loss (PnL)**
   - Calculated as: Exchange Balance - Funding
   - Positive = Profit
   - Negative = Loss
   - Zero = Break-even

4. **Share Information**
   - Your share percentage
   - Computed share amount (if applicable)

5. **Settlement Status**
   - Remaining settlement amount (if any)
   - Settlement history

6. **Transaction History**
   - All funding transactions
   - All trading transactions
   - All settlement transactions

### Transaction History

You can view all your funding transactions in the transaction history:

- Go to **"Transactions"** in the main menu
- Filter by transaction type: `FUNDING_MANUAL`
- See all funding transactions with:
  - Date and time
  - Amount
  - Before/after balances
  - Notes

---

## Important Notes

### Currency Units

⚠️ **Important**: Always enter amounts in the **smallest currency unit**:

- **Indian Rupees**: Enter in paise (1 rupee = 100 paise)
  - Example: ₹10,000 = 1,000,000 paise
- **US Dollars**: Enter in cents (1 dollar = 100 cents)
  - Example: $1,000 = 100,000 cents
- **Other currencies**: Use the smallest unit accordingly

### Minimum Amount

- Minimum funding amount: **1 unit** (1 paise, 1 cent, etc.)
- There is no maximum limit, but ensure you have sufficient funds

### Accuracy

- Double-check the amount before submitting
- All transactions are permanent and cannot be undone
- Contact support if you make an error

### Timing

- Funding is added immediately upon submission
- The transaction is recorded with the current date and time
- Your exchange balance is updated instantly

### Security

- Only you can add funding to your own accounts
- All funding transactions are logged and auditable
- Review your transaction history regularly

---

## Troubleshooting

### Common Issues

#### 1. "Amount is required" Error
- **Problem**: You didn't enter an amount
- **Solution**: Enter a valid amount in the amount field

#### 2. "Amount must be greater than zero" Error
- **Problem**: You entered zero or a negative number
- **Solution**: Enter a positive amount (minimum 1 unit)

#### 3. "Invalid amount" Error
- **Problem**: You entered non-numeric characters
- **Solution**: Enter only numbers (no commas, currency symbols, or letters)

#### 4. Can't Find "Add Funding" Button
- **Problem**: You might not be viewing an exchange account detail page
- **Solution**: 
  - Navigate to Exchanges → Select your exchange account
  - The "Add Funding" button is on the account detail page

#### 5. Funding Not Reflected
- **Problem**: You don't see the funding reflected in your balance
- **Solution**:
  - Refresh the page
  - Check the transaction history to confirm the transaction was recorded
  - Contact support if the issue persists

### Getting Help

If you encounter any issues or have questions:

1. **Check Transaction History**: Verify if the transaction was recorded
2. **Review Account Details**: Check current balances and status
3. **Contact Support**: Reach out to your account manager or system administrator
4. **Check Documentation**: Review this guide and other system documentation

---

## Examples

### Example 1: Initial Funding

**Scenario**: You're setting up a new exchange account and want to add ₹25,000 as initial funding.

**Steps**:
1. Navigate to your exchange account
2. Click "Add Funding"
3. Enter amount: `2500000` (₹25,000 in paise)
4. Add note: "Initial deposit for trading account"
5. Click "Add Funding"

**Result**:
- Funding: ₹25,000
- Exchange Balance: ₹25,000
- Transaction recorded as `FUNDING_MANUAL`

### Example 2: Additional Funding

**Scenario**: You want to add ₹5,000 more to an existing account that has ₹20,000 funding and ₹18,000 balance.

**Steps**:
1. Navigate to your exchange account
2. Click "Add Funding"
3. Enter amount: `500000` (₹5,000 in paise)
4. Add note: "Additional capital for increased trading"
5. Click "Add Funding"

**Result**:
- Funding: ₹25,000 (was ₹20,000)
- Exchange Balance: ₹23,000 (was ₹18,000)
- Both increased by ₹5,000

### Example 3: Small Top-Up

**Scenario**: You want to add a small amount of ₹500 to cover trading fees.

**Steps**:
1. Navigate to your exchange account
2. Click "Add Funding"
3. Enter amount: `50000` (₹500 in paise)
4. Add note: "Top-up for trading fees"
5. Click "Add Funding"

**Result**:
- Funding and Exchange Balance both increase by ₹500
- Transaction recorded with your note

---

## Summary

- **Funding** adds money to both your total funding and exchange balance
- **Amounts** must be entered in smallest currency units (paise, cents, etc.)
- **Both values** increase by the same amount when you add funding
- **Transactions** are permanent and immediately reflected
- **Always verify** amounts before submitting
- **Review** your transaction history regularly

---

## Quick Reference

| Action | Description |
|--------|-------------|
| Navigate to Funding | Exchanges → Select Account → Add Funding |
| Minimum Amount | 1 unit (1 paise, 1 cent, etc.) |
| Currency Format | Smallest unit (paise for rupees, cents for dollars) |
| Both Values | Funding and Exchange Balance increase together |
| Transaction Type | FUNDING_MANUAL |
| View History | Transactions → Filter by FUNDING_MANUAL |

---

**Last Updated**: [Current Date]  
**Version**: 1.0  
**System**: Transaction Hub

