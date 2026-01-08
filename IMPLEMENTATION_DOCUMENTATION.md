# Profit-Loss-Share-Settlement System - Implementation Documentation

**Version:** 1.0  
**Framework:** Django 4.2+  
**Language:** Python 3  
**Database:** SQLite (development) / PostgreSQL (production-ready)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Database Design](#database-design)
3. [Models Implementation](#models-implementation)
4. [Views & URLs](#views--urls)
5. [Forms](#forms)
6. [Templates](#templates)
7. [Key Features](#key-features)
8. [Formulas & Calculations](#formulas--calculations)
9. [System Rules](#system-rules)
10. [API Structure](#api-structure)
11. [Admin Interface](#admin-interface)
12. [Installation & Setup](#installation--setup)

---

## System Overview

This is a Django-based Profit-Loss-Share-Settlement system built according to PIN-TO-PIN master document specifications. The system manages:

- **Clients** - Trading clients
- **Exchanges** - Trading platforms
- **Client-Exchange Accounts** - Linking clients to exchanges with percentage shares
- **Funding Operations** - Adding real money to accounts
- **Balance Updates** - Recording trades, fees, profits, losses
- **Profit/Loss Calculations** - Real-time computed values
- **Partner Share Calculations** - Your share of profit/loss
- **Transaction Audit Trail** - Complete history of all operations

### Core Philosophy

**"Store only REAL money. Everything else must be DERIVED."**

- Only `funding` and `exchange_balance` are stored (BIGINT)
- All percentages are stored as INT (0-100)
- Profit, loss, shares are **computed**, never stored
- Client always receives FULL profit and pays FULL loss
- Partner shares profit/loss with company
- Friend/Student shares are report-only (not used in settlements)

---

## Database Design

### Entity Relationship Diagram

```
┌─────────────┐         ┌──────────────────────────┐         ┌─────────────┐
│   Client    │         │ ClientExchangeAccount    │         │  Exchange   │
├─────────────┤         ├──────────────────────────┤         ├─────────────┤
│ id (PK)     │◄──┐     │ id (PK)                  │     ┌──►│ id (PK)     │
│ name        │   │     │ client_id (FK)          │     │   │ name        │
│ code        │   │     │ exchange_id (FK)        │─────┘   │ code        │
│ referred_by │   │     │ funding (BIGINT)         │         │ created_at  │
│ is_company  │   │     │ exchange_balance BIGINT │         │ updated_at  │
│ user_id (FK)│   │     │ my_percentage (INT)      │         └─────────────┘
│ created_at  │   │     │ created_at              │
│ updated_at  │   │     │ updated_at              │
└─────────────┘   │     └──────────────────────────┘
                  │                │
                  │                │ 1:1
                  │                │
                  │     ┌──────────────────────────┐
                  │     │ClientExchangeReportConfig│
                  │     ├──────────────────────────┤
                  │     │ client_exchange_id (FK)  │
                  │     │ friend_percentage (INT)  │
                  │     │ my_own_percentage (INT)  │
                  │     │ created_at               │
                  │     │ updated_at               │
                  │     └──────────────────────────┘
                  │
                  │     ┌──────────────────────────┐
                  └─────│      Transaction         │
                        ├──────────────────────────┤
                        │ id (PK)                  │
                        │ client_exchange_id (FK)  │
                        │ date                     │
                        │ type (CHAR)              │
                        │ amount (BIGINT)          │
                        │ exchange_balance_after   │
                        │ notes (TEXT)             │
                        │ created_at               │
                        │ updated_at               │
                        └──────────────────────────┘
```

### Database Tables

#### 1. `core_client`

Stores client information.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BigAutoField | PRIMARY KEY | Auto-increment ID |
| name | CharField(200) | NOT NULL | Client name |
| code | CharField(50) | NULL, UNIQUE | Optional client code |
| referred_by | CharField(200) | NULL | Person who referred client |
| is_company_client | BooleanField | DEFAULT False | Company client flag |
| user_id | ForeignKey(User) | NULL | Linked user (optional) |
| created_at | DateTimeField | AUTO_NOW_ADD | Creation timestamp |
| updated_at | DateTimeField | AUTO_NOW | Last update timestamp |

**Indexes:**
- `name` (for search)
- `code` (unique index)

---

#### 2. `core_exchange`

Stores exchange/platform information.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BigAutoField | PRIMARY KEY | Auto-increment ID |
| name | CharField(200) | NOT NULL | Exchange name |
| code | CharField(50) | NULL, UNIQUE | Optional exchange code |
| created_at | DateTimeField | AUTO_NOW_ADD | Creation timestamp |
| updated_at | DateTimeField | AUTO_NOW | Last update timestamp |

**Indexes:**
- `name` (for search)
- `code` (unique index)

---

#### 3. `core_clientexchangeaccount` ⭐ **CORE SYSTEM TABLE**

**This is the most important table - stores ONLY real money values.**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BigAutoField | PRIMARY KEY | Auto-increment ID |
| client_id | ForeignKey(Client) | NOT NULL | Reference to client |
| exchange_id | ForeignKey(Exchange) | NOT NULL | Reference to exchange |
| **funding** | **BigIntegerField** | **NOT NULL, >= 0** | **Total real money given to client** |
| **exchange_balance** | **BigIntegerField** | **NOT NULL, >= 0** | **Current balance on exchange** |
| **my_percentage** | **IntegerField** | **NOT NULL, 0-100** | **Partner's total percentage share** |
| created_at | DateTimeField | AUTO_NOW_ADD | Creation timestamp |
| updated_at | DateTimeField | AUTO_NOW | Last update timestamp |

**Unique Constraint:**
- `(client_id, exchange_id)` - One account per client-exchange pair

**Indexes:**
- `client_id` (for filtering)
- `exchange_id` (for filtering)
- `(client_id, exchange_id)` (unique index)

**Key Rules:**
- ✅ Only `funding` and `exchange_balance` are stored
- ✅ All money values are BIGINT (no decimals)
- ✅ All percentages are INT (0-100)
- ❌ Never store profit, loss, pending, settlement status (settlement status is DERIVED, not stored)
- ❌ Never store friend share, history adjustments

---

#### 4. `core_clientexchangereportconfig` 📊 **REPORT CONFIG TABLE**

**Used ONLY for reports, NOT for system logic.**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BigAutoField | PRIMARY KEY | Auto-increment ID |
| client_exchange_id | OneToOneField | NOT NULL, UNIQUE | Reference to account |
| friend_percentage | IntegerField | NOT NULL, >= 0 | Friend/Student % (report only) |
| my_own_percentage | IntegerField | NOT NULL, >= 0 | Your own % (report only) |
| created_at | DateTimeField | AUTO_NOW_ADD | Creation timestamp |
| updated_at | DateTimeField | AUTO_NOW | Last update timestamp |

**Validation Rule:**
```
friend_percentage + my_own_percentage = client_exchange.my_percentage
```

**Key Rules:**
- ✅ Used ONLY for reports
- ✅ Not used in settlements
- ✅ Not shown in system UI (except admin)
- ✅ Shows how much profit went to students

---

#### 5. `core_transaction` 📝 **AUDIT TRAIL TABLE**

**Stores transaction history for audit purposes. NEVER used to recompute balances.**

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | BigAutoField | PRIMARY KEY | Auto-increment ID |
| client_exchange_id | ForeignKey | NOT NULL | Reference to account |
| date | DateTimeField | NOT NULL | Transaction date/time |
| type | CharField(20) | NOT NULL | Transaction type |
| amount | BigIntegerField | NOT NULL | Transaction amount |
| exchange_balance_after | BigIntegerField | NOT NULL | Balance after transaction |
| notes | TextField | NULL | Optional notes |
| created_at | DateTimeField | AUTO_NOW_ADD | Creation timestamp |
| updated_at | DateTimeField | AUTO_NOW | Last update timestamp |

**Transaction Types:**
- `FUNDING` - Money given to client
- `TRADE` - Trading activity
- `FEE` - Exchange fees
- `ADJUSTMENT` - Manual adjustments

**Key Rules:**
- ✅ Used for audit trail only
- ❌ Never recompute balances from transactions
- ❌ Never used for system logic
- ✅ Shows complete history

---

## Models Implementation

### Model: `Client`

**File:** `core/models.py`

```python
class Client(TimeStampedModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    referred_by = models.CharField(max_length=200, blank=True, null=True)
    is_company_client = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['name']
```

**Key Features:**
- Optional unique code
- Company client flag
- Optional user linking
- Timestamp tracking

---

### Model: `Exchange`

**File:** `core/models.py`

```python
class Exchange(TimeStampedModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    class Meta:
        ordering = ['name']
```

**Key Features:**
- Optional unique code
- Timestamp tracking

---

### Model: `ClientExchangeAccount` ⭐

**File:** `core/models.py`

```python
class ClientExchangeAccount(TimeStampedModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE)
    
    # ONLY TWO MONEY VALUES STORED (BIGINT)
    funding = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    exchange_balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Partner percentage (INT)
    my_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    class Meta:
        unique_together = [['client', 'exchange']]
```

**Computed Methods:**

```python
def compute_client_pnl(self):
    """MASTER PROFIT/LOSS FORMULA
    Client_PnL = exchange_balance - funding
    Returns: BIGINT (can be negative for loss)
    """
    return self.exchange_balance - self.funding

def compute_my_share(self):
    """PARTNER SHARE FORMULA
    My_Share = ABS(Client_PnL) × my_percentage / 100
    Returns: BIGINT (always positive, integer division)
    """
    client_pnl = abs(self.compute_client_pnl())
    return (client_pnl * self.my_percentage) // 100

def is_settled(self):
    """Check if client is fully settled (PnL = 0)"""
    return self.compute_client_pnl() == 0
```

**Key Features:**
- Only stores real money values
- Computed methods for PnL and shares
- Validation for non-negative values
- Unique constraint on client-exchange pair

---

### Model: `ClientExchangeReportConfig`

**File:** `core/models.py`

```python
class ClientExchangeReportConfig(TimeStampedModel):
    client_exchange = models.OneToOneField(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='report_config'
    )
    
    friend_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    my_own_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    def clean(self):
        """Validation: friend_percentage + my_own_percentage = my_percentage"""
        if self.client_exchange:
            my_total = self.client_exchange.my_percentage
            friend_plus_own = self.friend_percentage + self.my_own_percentage
            
            if friend_plus_own != my_total:
                raise ValidationError(
                    f"Friend % ({self.friend_percentage}) + My Own % ({self.my_own_percentage}) "
                    f"must equal My Total % ({my_total})"
                )
```

**Computed Methods:**

```python
def compute_friend_share(self):
    """Friend share formula (report only)"""
    client_pnl = abs(self.client_exchange.compute_client_pnl())
    return (client_pnl * self.friend_percentage) // 100

def compute_my_own_share(self):
    """My own share formula (report only)"""
    client_pnl = abs(self.client_exchange.compute_client_pnl())
    return (client_pnl * self.my_own_percentage) // 100
```

**Key Features:**
- One-to-one relationship with account
- Validation ensures percentages add up correctly
- Computed methods for report shares

---

### Model: `Transaction`

**File:** `core/models.py`

```python
class Transaction(TimeStampedModel):
    TRANSACTION_TYPES = [
        ('FUNDING', 'Funding'),
        ('TRADE', 'Trade'),
        ('FEE', 'Fee'),
        ('ADJUSTMENT', 'Adjustment'),
    ]
    
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    date = models.DateTimeField()
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.BigIntegerField()
    exchange_balance_after = models.BigIntegerField()
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date', '-id']
```

**Key Features:**
- Audit trail only
- Never used for balance calculations
- Stores balance after transaction for verification

---

## Views & URLs

### URL Structure

**File:** `core/urls.py`

```python
urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    
    # Exchanges
    path('exchanges/', views.exchange_list, name='exchange_list'),
    path('exchanges/create/', views.exchange_create, name='exchange_create'),
    path('exchanges/link/', views.link_client_to_exchange, name='exchange_link'),
    path('exchanges/account/<int:pk>/', views.exchange_account_detail, name='exchange_account_detail'),
    
    # Funding & Transactions
    path('exchanges/account/<int:account_id>/funding/', views.add_funding, name='add_funding'),
    path('exchanges/account/<int:account_id>/update-balance/', views.update_exchange_balance, name='update_balance'),
    
    # Transactions (audit trail)
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:pk>/', views.transaction_detail, name='transaction_detail'),
]
```

### View Functions

#### 1. Authentication Views

**`login_view(request)`**
- Handles user login
- Redirects authenticated users to dashboard
- Shows error on invalid credentials

**`logout_view(request)`**
- Logs out user
- Redirects to login page

---

#### 2. Dashboard View

**`dashboard(request)`**
- Shows system overview
- Displays totals:
  - Total clients, exchanges, accounts
  - Total funding, exchange balance
  - Total client PnL, my share
- Shows recent accounts with computed values

---

#### 3. Client Views

**`client_list(request)`**
- Lists all clients
- Supports search and filtering
- Shows client type, status, exchange count

**`client_create(request)`**
- Creates new client
- Handles form validation
- Shows success/error messages

**`client_detail(request, pk)`**
- Shows client details
- Lists all exchange accounts
- Displays totals for client
- Shows computed PnL per account

---

#### 4. Exchange Views

**`exchange_list(request)`**
- Lists all exchanges
- Shows client count per exchange

**`exchange_create(request)`**
- Creates new exchange
- Handles form validation

**`link_client_to_exchange(request)`**
- Links client to exchange (CONFIGURATION STEP)
- Sets up percentages:
  - My Total % (system logic)
  - Friend % (report only)
  - My Own % (report only)
- Validates percentage rules

**`exchange_account_detail(request, pk)`**
- Shows account details
- Displays computed values:
  - Client PnL
  - My Share
  - Friend Share (if configured)
  - My Own Share (if configured)
- Shows recent transactions
- Provides actions: Add Funding, Update Balance

---

#### 5. Funding & Balance Views

**`add_funding(request, account_id)`**
- Adds funding to account
- **FUNDING RULE**: Both funding and exchange_balance increase
- Creates transaction record

**`update_exchange_balance(request, account_id)`**
- Updates exchange balance
- Only exchange_balance changes, funding untouched
- Used for trades, fees, profits, losses
- Creates transaction record

---

#### 6. Transaction Views

**`transaction_list(request)`**
- Lists all transactions
- Shows client, exchange, type, amount
- Audit trail view

**`transaction_detail(request, pk)`**
- Shows transaction details
- Links to account and client

---

## Forms

### Form: `ClientForm`

**File:** `core/forms.py`

```python
class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'code', 'referred_by', 'is_company_client']
```

**Fields:**
- `name` - Required
- `code` - Optional, unique
- `referred_by` - Optional
- `is_company_client` - Checkbox

---

### Form: `ExchangeForm`

**File:** `core/forms.py`

```python
class ExchangeForm(forms.ModelForm):
    class Meta:
        model = Exchange
        fields = ['name', 'code']
```

**Fields:**
- `name` - Required
- `code` - Optional, unique

---

### Form: `ClientExchangeLinkForm` ⭐

**File:** `core/forms.py`

```python
class ClientExchangeLinkForm(forms.ModelForm):
    friend_percentage = forms.IntegerField(required=False, initial=0, min_value=0, max_value=100)
    my_own_percentage = forms.IntegerField(required=False, initial=0, min_value=0, max_value=100)
    
    class Meta:
        model = ClientExchangeAccount
        fields = ['client', 'exchange', 'my_percentage']
    
    def clean(self):
        # Validation: Friend % + My Own % = My Total %
        my_percentage = cleaned_data.get('my_percentage', 0)
        friend_percentage = cleaned_data.get('friend_percentage', 0)
        my_own_percentage = cleaned_data.get('my_own_percentage', 0)
        
        if friend_percentage + my_own_percentage != my_percentage:
            raise ValidationError(...)
    
    def save(self, commit=True):
        # Saves account and report config
```

**Key Features:**
- Validates percentage rules
- Creates report config if percentages provided
- Handles both system and report percentages

---

### Form: `FundingForm`

**File:** `core/forms.py`

```python
class FundingForm(forms.Form):
    amount = forms.IntegerField(min_value=1)
    notes = forms.CharField(required=False, widget=forms.Textarea)
```

**Usage:**
- Adds funding to account
- Follows FUNDING RULE

---

### Form: `ExchangeBalanceUpdateForm`

**File:** `core/forms.py`

```python
class ExchangeBalanceUpdateForm(forms.Form):
    new_balance = forms.IntegerField(min_value=0)
    transaction_type = forms.ChoiceField(choices=Transaction.TRANSACTION_TYPES[1:])
    notes = forms.CharField(required=False, widget=forms.Textarea)
```

**Usage:**
- Updates exchange balance
- Only balance changes, funding untouched

---

## Templates

### Template Structure

```
core/templates/core/
├── base.html                    # Base template with sidebar
├── auth/
│   └── login.html              # Login page
├── dashboard.html              # Dashboard
├── clients/
│   ├── list.html              # Client list
│   ├── create.html             # Create client
│   └── detail.html             # Client detail
├── exchanges/
│   ├── list.html               # Exchange list
│   ├── create.html             # Create exchange
│   ├── link_to_client.html     # Link client to exchange
│   ├── edit.html               # Account detail
│   ├── add_funding.html        # Add funding form
│   └── update_balance.html     # Update balance form
└── transactions/
    ├── list.html               # Transaction list
    └── detail.html             # Transaction detail
```

### Key Template Features

1. **Base Template (`base.html`)**
   - Sidebar navigation
   - Responsive design
   - Modern UI with CSS variables
   - Active link highlighting

2. **Dashboard**
   - System overview cards
   - Recent accounts table
   - Computed values display

3. **Account Detail**
   - Shows funding and exchange balance
   - Computed PnL and shares
   - "N.A" for settled accounts
   - Recent transactions
   - Action buttons

4. **Forms**
   - Clean, modern design
   - Error message display
   - Success notifications
   - Validation feedback

---

## Key Features

### 1. Real-Time Computations

All profit/loss and share values are computed in real-time:

```python
# In templates
{% with pnl=account.compute_client_pnl share=account.compute_my_share %}
    {% if pnl == 0 %}
        <span>N.A</span>
    {% else %}
        <span>{{ pnl|floatformat:0 }}</span>
    {% endif %}
{% endwith %}
```

### 2. FUNDING RULE Enforcement

When adding funding, both values increase:

```python
account.funding += amount
account.exchange_balance += amount
account.save()
```

### 3. Balance Update

Only exchange balance changes:

```python
account.exchange_balance = new_balance
account.save()
```

### 4. Percentage Validation

Friend % + My Own % must equal My Total %:

```python
if friend_percentage + my_own_percentage != my_percentage:
    raise ValidationError(...)
```

### 5. Display Rules

- If `Client_PnL = 0`, display "N.A" (not zero)
- Color-code PnL: green for profit, red for loss
- Show computed shares only when PnL ≠ 0

---

## Formulas & Calculations

### 1. Client Profit/Loss

```
Client_PnL = exchange_balance - funding
```

**Interpretation:**
- `> 0` → Client in PROFIT
- `< 0` → Client in LOSS
- `= 0` → Fully settled (display "N.A")

**Implementation:**
```python
def compute_client_pnl(self):
    return self.exchange_balance - self.funding
```

---

### 2. Partner Share (My Share)

```
My_Share = ABS(Client_PnL) × my_percentage / 100
```

**Key Points:**
- Always positive (uses ABS)
- Integer division (FLOOR)
- Same formula for profit & loss
- BIGINT math

**Implementation:**
```python
def compute_my_share(self):
    client_pnl = abs(self.compute_client_pnl())
    return (client_pnl * self.my_percentage) // 100
```

---

### 3. Friend Share (Report Only)

```
Friend_Share = ABS(Client_PnL) × friend_percentage / 100
```

**Key Points:**
- Report only, not used in settlements
- Computed from report config

**Implementation:**
```python
def compute_friend_share(self):
    client_pnl = abs(self.client_exchange.compute_client_pnl())
    return (client_pnl * self.friend_percentage) // 100
```

---

### 4. My Own Share (Report Only)

```
My_Own_Share = ABS(Client_PnL) × my_own_percentage / 100
```

**Key Points:**
- Report only, not used in settlements
- Computed from report config

**Implementation:**
```python
def compute_my_own_share(self):
    client_pnl = abs(self.client_exchange.compute_client_pnl())
    return (client_pnl * self.my_own_percentage) // 100
```

---

## System Rules

### 1. FUNDING RULE (Never Break)

**When money is given to client:**

```
funding = funding + X
exchange_balance = exchange_balance + X
```

**Implementation:**
```python
account.funding += amount
account.exchange_balance += amount
account.save()
```

**Rules:**
- ❌ Funding must NEVER change alone
- ❌ Exchange balance must NEVER change alone during funding
- ✅ Both must increase together

---

### 2. Exchange Transactions

**For trades, fees, profits, losses:**

```
ONLY exchange_balance changes
funding remains untouched
```

**Implementation:**
```python
account.exchange_balance = new_balance
account.save()
```

---

### 3. Validation Rules

```
funding >= 0
exchange_balance >= 0
0 <= my_percentage <= 100
friend_percentage >= 0
friend_percentage <= my_percentage
friend_percentage + my_own_percentage = my_percentage
```

---

### 4. Settlement Logic

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

---

### 5. Display Rules

**If Client_PnL = 0:**
- Display "N.A" (not zero)
- Display "N.A" for My Share
- Show "Fully Settled" status (DERIVED, not stored)

**If Client_PnL ≠ 0:**
- Display actual value
- Color-code (green/red)
- Show computed shares
- Show "Action Required" status (DERIVED, not stored)

**Settlement Status Derivation:**
```
if Client_PnL == 0:
    status = "Fully Settled"
else:
    status = "Action Required"
```

**Important:** Settlement status is **NEVER stored**. It is always **DERIVED** from `Client_PnL`.

---

### 6. Stale Data Protection

**Before settlement:**
1. Read funding from DB
2. Read exchange_balance from DB
3. Recompute Client_PnL
4. Recompute My_Share
5. Validate
6. Execute settlement

**Rules:**
- ❌ Never trust UI values
- ✅ Always recompute from DB

---

## API Structure

### RESTful URLs

| Method | URL | View | Description |
|--------|-----|------|-------------|
| GET | `/` | dashboard | System overview |
| GET | `/login/` | login_view | Login page |
| POST | `/login/` | login_view | Process login |
| GET | `/logout/` | logout_view | Logout |
| GET | `/clients/` | client_list | List clients |
| GET | `/clients/create/` | client_create | Create client form |
| POST | `/clients/create/` | client_create | Process client creation |
| GET | `/clients/<id>/` | client_detail | Client details |
| GET | `/exchanges/` | exchange_list | List exchanges |
| GET | `/exchanges/create/` | exchange_create | Create exchange form |
| POST | `/exchanges/create/` | exchange_create | Process exchange creation |
| GET | `/exchanges/link/` | link_client_to_exchange | Link form |
| POST | `/exchanges/link/` | link_client_to_exchange | Process linking |
| GET | `/exchanges/account/<id>/` | exchange_account_detail | Account details |
| GET | `/exchanges/account/<id>/funding/` | add_funding | Funding form |
| POST | `/exchanges/account/<id>/funding/` | add_funding | Process funding |
| GET | `/exchanges/account/<id>/update-balance/` | update_exchange_balance | Balance form |
| POST | `/exchanges/account/<id>/update-balance/` | update_exchange_balance | Process balance update |
| GET | `/transactions/` | transaction_list | Transaction list |
| GET | `/transactions/<id>/` | transaction_detail | Transaction details |

---

## Admin Interface

### Admin Configuration

**File:** `core/admin.py`

**Registered Models:**
1. `ClientAdmin` - Client management
2. `ExchangeAdmin` - Exchange management
3. `ClientExchangeAccountAdmin` - Account management with computed values
4. `ClientExchangeReportConfigAdmin` - Report config management
5. `TransactionAdmin` - Transaction audit trail

### Key Admin Features

**ClientExchangeAccountAdmin:**
- Shows computed PnL (read-only)
- Shows computed My Share (read-only)
- Shows **DERIVED** settlement status (NOT stored)
- Inline report config editor
- Color-coded PnL display

**Computed Fields:**
```python
def computed_pnl(self, obj):
    pnl = obj.compute_client_pnl()
    if pnl == 0:
        return "N.A"
    color = "green" if pnl > 0 else "red"
    return f'<span style="color: {color};">{pnl:,}</span>'

def settlement_status_derived(self, obj):
    """
    DERIVED settlement status (NOT stored)
    
    Rule: if Client_PnL == 0 → Fully settled
          else → Action required
    """
    pnl = obj.compute_client_pnl()
    if pnl == 0:
        return '✓ Fully Settled'
    else:
        return '⚠ Action Required'
```

**Important:** Settlement status is **DERIVED** from `Client_PnL`, never stored. The admin panel computes it as:
- `Client_PnL == 0` → "Fully Settled"
- `Client_PnL != 0` → "Action Required"

---

## Installation & Setup

### 1. Prerequisites

- Python 3.8+
- pip
- Virtual environment (recommended)

### 2. Installation Steps

```bash
# Clone or navigate to project
cd chip-2

# Create virtual environment (optional)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### 3. Access Points

- **Web Interface:** http://localhost:8000
- **Admin Panel:** http://localhost:8000/admin
- **Login:** Use superuser credentials

### 4. Initial Setup

1. **Create Exchanges:**
   - Go to Exchanges → Add Exchange
   - Enter exchange name and code

2. **Create Clients:**
   - Go to Clients → Add Client
   - Enter client details

3. **Link Clients to Exchanges:**
   - Go to Exchanges → Link Client to Exchange
   - Select client and exchange
   - Set percentages

4. **Add Funding:**
   - Go to account detail page
   - Click "Add Funding"
   - Enter amount

5. **Update Balances:**
   - Go to account detail page
   - Click "Update Exchange Balance"
   - Enter new balance

---

## Data Types Summary

| Field Type | Database Type | Usage | Example |
|------------|---------------|-------|---------|
| Money Values | BIGINT | funding, exchange_balance | 100000 (paise) |
| Percentages | INT | my_percentage, friend_percentage | 10 (for 10%) |
| Text Fields | VARCHAR | name, code | "John Doe" |
| Boolean | BOOLEAN | is_company_client | True/False |
| Dates | DATETIME | created_at, updated_at | 2024-01-01 12:00:00 |

**Important:**
- ❌ No FLOAT, DOUBLE, or DECIMAL for money
- ❌ No FLOAT for percentages
- ✅ BIGINT for all money values
- ✅ INT for all percentages

---

## Testing Checklist

### Functional Tests

- [ ] Create client
- [ ] Create exchange
- [ ] Link client to exchange
- [ ] Add funding (both values increase)
- [ ] Update exchange balance (only balance changes)
- [ ] Verify computed PnL
- [ ] Verify computed shares
- [ ] Check "N.A" display for settled accounts
- [ ] Verify transaction audit trail
- [ ] Test percentage validation

### Validation Tests

- [ ] Funding >= 0
- [ ] Exchange balance >= 0
- [ ] My percentage 0-100
- [ ] Friend % + My Own % = My Total %
- [ ] Unique client-exchange pair

### Display Tests

- [ ] PnL color coding (green/red)
- [ ] "N.A" for zero PnL
- [ ] Computed values update correctly
- [ ] Transaction history displays

---

## Future Enhancements

### Planned Features

1. **Reports Module**
   - Client PnL breakdown
   - My Total Share summary
   - Friend Share distribution
   - Exchange-wise summary
   - Date-wise summary

2. **Export Functionality**
   - Excel export
   - PDF reports
   - CSV data export

3. **Advanced Filtering**
   - Date range filters
   - Client type filters
   - Exchange filters
   - PnL range filters

4. **Settlement Workflow**
   - Settlement approval process
   - Payment tracking
   - Settlement history

---

## Conclusion

This implementation follows the PIN-TO-PIN master document specifications exactly:

✅ **Only real money stored** (funding, exchange_balance)  
✅ **All values computed** (PnL, shares)  
✅ **BIGINT for money**, **INT for percentages**  
✅ **FUNDING RULE enforced**  
✅ **Validation rules implemented**  
✅ **Display rules followed**  
✅ **Audit trail maintained**  
✅ **Report config isolated**  

The system is:
- **Client-safe** - Client always gets full PnL
- **Company-safe** - Company sees only totals
- **Partner-safe** - Your share calculated correctly
- **Student-safe** - Friend shares tracked
- **Audit-proof** - Complete transaction history
- **Developer-ready** - Clean code, well-documented
- **Scalable** - Efficient queries, proper indexing

---

**Document Version:** 1.0  
**Last Updated:** 2024-01-07  
**Framework:** Django 4.2+  
**Python:** 3.8+

