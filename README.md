# Profit-Loss-Share-Settlement System

A Django-based system for managing client-exchange accounts, profit/loss calculations, and partner share settlements. Built according to PIN-TO-PIN master document specifications.

## 🎯 Core Philosophy

**Store only REAL money. Everything else must be DERIVED.**

The system follows these fundamental rules:
- Only `funding` and `exchange_balance` are stored (BIGINT)
- All percentages are stored as INT (0-100)
- Profit, loss, shares are **computed**, never stored
- Client always receives FULL profit and pays FULL loss
- Partner shares profit/loss with company
- Friend/Student shares are report-only (not used in settlements)

## 📋 Features

- ✅ Client management
- ✅ Exchange management
- ✅ Client-Exchange linking with percentage configuration
- ✅ Funding operations (follows FUNDING RULE: both funding and exchange_balance increase)
- ✅ Exchange balance updates (for trades, fees, profits, losses)
- ✅ Real-time PnL and share calculations (computed, not stored)
- ✅ Transaction audit trail
- ✅ Django admin interface
- ✅ Beautiful, modern UI

## 🗄️ Database Design

### Core Tables

1. **Client** - Client information
2. **Exchange** - Exchange/platform information
3. **ClientExchangeAccount** - Core system table storing:
   - `funding` (BIGINT) - Total real money given to client
   - `exchange_balance` (BIGINT) - Current balance on exchange
   - `my_percentage` (INT) - Partner's total percentage share

4. **ClientExchangeReportConfig** - Report configuration (isolated):
   - `friend_percentage` (INT) - Friend/Student % (report only)
   - `my_own_percentage` (INT) - Your own % (report only)

5. **Transaction** - Audit trail (never used to recompute balances)

## 🔢 Key Formulas

### Client PnL
```
Client_PnL = exchange_balance - funding
```

### Partner Share
```
My_Share = ABS(Client_PnL) × my_percentage / 100
```

### Friend Share (Report Only)
```
Friend_Share = ABS(Client_PnL) × friend_percentage / 100
```

## 🚀 Installation

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Run migrations:**
```bash
python manage.py migrate
```

3. **Create superuser (optional):**
```bash
python manage.py createsuperuser
```

4. **Run development server:**
```bash
python manage.py runserver
```

5. **Access the application:**
- Web interface: http://localhost:8000
- Admin panel: http://localhost:8000/admin
- Default superuser: `admin` / (set password with createsuperuser)

## 📖 Usage Guide

### 1. Create Clients
Navigate to **Clients → Add Client** and fill in:
- Client Name (required)
- Client Code (optional, unique)
- Referred By (optional)
- Company Client checkbox

### 2. Create Exchanges
Navigate to **Exchanges → Add Exchange** and fill in:
- Exchange Name (required)
- Exchange Code (optional, unique)

### 3. Link Client to Exchange
Navigate to **Exchanges → Link Client to Exchange**:
- Select Client and Exchange
- Enter **My Total %** (your total percentage share, 0-100)
- Optionally configure report percentages:
  - Friend % + My Own % must equal My Total %

### 4. Add Funding
When giving money to a client:
- Navigate to account detail page
- Click **Add Funding**
- Enter amount
- **FUNDING RULE**: Both funding and exchange_balance increase by the same amount

### 5. Update Exchange Balance
For trades, fees, profits, losses:
- Navigate to account detail page
- Click **Update Exchange Balance**
- Enter new balance
- Only exchange_balance changes, funding remains untouched

### 6. View Computed Values
All PnL and share values are computed in real-time:
- **Client PnL** = exchange_balance - funding
- **My Share** = ABS(Client_PnL) × my_percentage / 100
- If Client_PnL = 0, displays "N.A" (fully settled)

## 🔐 System Rules

### FUNDING RULE (Never Break)
When money is given to client:
```
funding = funding + X
exchange_balance = exchange_balance + X
```

### VALIDATION RULES
- `funding >= 0`
- `exchange_balance >= 0`
- `0 <= my_percentage <= 100`
- `friend_percentage >= 0`
- `friend_percentage <= my_percentage`
- `friend_percentage + my_own_percentage = my_percentage`

### SETTLEMENT LOGIC

**Client in PROFIT (Client_PnL > 0):**
- Client gets FULL profit
- Company pays (PnL - My_Share)
- You pay My_Share
- 📌 Client profit = your expense

**Client in LOSS (Client_PnL < 0):**
- Client pays FULL loss
- You keep My_Share
- You forward remaining to company
- 📌 Client loss = your profit

## 🎨 UI Features

- Modern, clean interface
- Real-time computed values
- Color-coded PnL (green for profit, red for loss)
- "N.A" display for settled accounts (PnL = 0)
- Transaction audit trail
- Responsive design

## 📊 Reports Module

Reports module is planned for future implementation. It will show:
- Client PnL breakdown
- My Total Share
- Friend Share (report only)
- My Own Share (report only)
- Student profit distribution
- Exchange-wise summary
- Date-wise summary

## 🛡️ Data Integrity

- **Stale Data Protection**: Always recompute from DB values before settlement
- **No History Replay**: Balances are never recomputed from transactions
- **No Auto-adjustments**: System follows exact formulas
- **No Derived Storage**: Only funding and exchange_balance stored

## 📝 Notes

- All money values are in smallest currency unit (e.g., paise for rupees)
- All percentages are integers (0-100)
- Transactions table is for audit only, never used for balance calculations
- Friend/Student shares are report-only and not used in settlements

## 🔧 Development

### Running Tests
```bash
python manage.py test
```

### Creating Migrations
```bash
python manage.py makemigrations
```

### Applying Migrations
```bash
python manage.py migrate
```

## 📄 License

This system is built according to the PIN-TO-PIN master document specifications.

---

**Built with Django 4.2+ and Python 3**

