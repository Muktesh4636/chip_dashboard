"""
Views for Profit-Loss-Share-Settlement System
"""
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Q
from django.contrib import messages
from django.http import JsonResponse
from .models import (
    Client, Exchange, ClientExchangeAccount, 
    ClientExchangeReportConfig, Transaction
)
from .forms import (
    ClientForm, ExchangeForm, ClientExchangeLinkForm,
    FundingForm, ExchangeBalanceUpdateForm, RecordPaymentForm
)


def login_view(request):
    """Login view."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            return render(request, "core/auth/login.html", {
                "error": "Invalid username or password."
            })
    return render(request, "core/auth/login.html")


def logout_view(request):
    """Logout view."""
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    """Dashboard view showing system overview."""
    accounts = ClientExchangeAccount.objects.select_related('client', 'exchange').all()
    
    # Compute totals
    total_funding = sum(acc.funding for acc in accounts)
    total_exchange_balance = sum(acc.exchange_balance for acc in accounts)
    total_client_pnl = sum(acc.compute_client_pnl() for acc in accounts)
    total_my_share = sum(acc.compute_my_share() for acc in accounts)
    
    # Counts
    total_clients = Client.objects.count()
    total_exchanges = Exchange.objects.count()
    total_accounts = accounts.count()
    
    # Recent accounts with PnL
    recent_accounts = accounts.order_by('-updated_at')[:10]
    
    context = {
        'total_clients': total_clients,
        'total_exchanges': total_exchanges,
        'total_accounts': total_accounts,
        'total_funding': total_funding,
        'total_exchange_balance': total_exchange_balance,
        'total_client_pnl': total_client_pnl,
        'total_my_share': total_my_share,
        'recent_accounts': recent_accounts,
    }
    return render(request, "core/dashboard.html", context)


# Client Views
@login_required
def client_list(request):
    """List all clients."""
    clients = Client.objects.all().order_by('name')
    return render(request, "core/clients/list.html", {'clients': clients})


@login_required
def client_create(request):
    """Create a new client."""
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Client created successfully.")
            return redirect("client_list")
    else:
        form = ClientForm()
    
    return render(request, "core/clients/create.html", {'form': form})


@login_required
def client_detail(request, pk):
    """View client details with all exchange accounts."""
    client = get_object_or_404(Client, pk=pk)
    accounts = client.exchange_accounts.select_related('exchange').all()
    
    # Compute totals for this client
    total_funding = sum(acc.funding for acc in accounts)
    total_exchange_balance = sum(acc.exchange_balance for acc in accounts)
    total_client_pnl = sum(acc.compute_client_pnl() for acc in accounts)
    
    context = {
        'client': client,
        'accounts': accounts,
        'total_funding': total_funding,
        'total_exchange_balance': total_exchange_balance,
        'total_client_pnl': total_client_pnl,
    }
    return render(request, "core/clients/detail.html", context)


# Exchange Views
@login_required
def exchange_list(request):
    """List all exchanges."""
    exchanges = Exchange.objects.all().order_by('name')
    return render(request, "core/exchanges/list.html", {'exchanges': exchanges})


@login_required
def exchange_create(request):
    """Create a new exchange."""
    if request.method == "POST":
        form = ExchangeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Exchange created successfully.")
            return redirect("exchange_list")
    else:
        form = ExchangeForm()
    
    return render(request, "core/exchanges/create.html", {'form': form})


# Client-Exchange Linking Views
@login_required
def link_client_to_exchange(request):
    """Link a client to an exchange with percentages (CONFIGURATION STEP)."""
    if request.method == "POST":
        form = ClientExchangeLinkForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(request, f"Client linked to exchange successfully.")
            return redirect("exchange_link")
    else:
        initial = {}
        client_id = request.GET.get('client')
        if client_id:
            try:
                initial['client'] = int(client_id)
            except (ValueError, TypeError):
                pass
        form = ClientExchangeLinkForm(initial=initial)
    
    return render(request, "core/exchanges/link_to_client.html", {'form': form})


@login_required
def exchange_account_detail(request, pk):
    """View detailed account information with computed values."""
    account = get_object_or_404(
        ClientExchangeAccount.objects.select_related('client', 'exchange'),
        pk=pk
    )
    
    # Compute values (never stored, always computed)
    client_pnl = account.compute_client_pnl()
    my_share = account.compute_my_share()
    is_settled = account.is_settled()
    
    # Get report config if exists
    try:
        report_config = account.report_config
        friend_share = report_config.compute_friend_share()
        my_own_share = report_config.compute_my_own_share()
    except ClientExchangeReportConfig.DoesNotExist:
        report_config = None
        friend_share = 0
        my_own_share = 0
    
    # Get transactions
    transactions = account.transactions.all()[:20]
    
    context = {
        'account': account,
        'client_pnl': client_pnl,
        'my_share': my_share,
        'is_settled': is_settled,
        'report_config': report_config,
        'friend_share': friend_share,
        'my_own_share': my_own_share,
        'transactions': transactions,
    }
    return render(request, "core/exchanges/edit.html", context)


# Funding Views
@login_required
def add_funding(request, account_id):
    """
    Add funding to account.
    Follows FUNDING RULE: funding += X, exchange_balance += X
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id)
    
    if request.method == "POST":
        form = FundingForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            notes = form.cleaned_data.get('notes', '')
            
            # FUNDING RULE: Both values increase together
            account.funding += amount
            account.exchange_balance += amount
            account.save()
            
            # Create transaction record (audit only)
            from django.utils import timezone
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type='FUNDING',
                amount=amount,
                exchange_balance_after=account.exchange_balance,
                notes=notes
            )
            
            messages.success(request, f"Funding of {amount:,} added successfully.")
            return redirect("exchange_account_detail", pk=account_id)
    else:
        form = FundingForm()
    
    return render(request, "core/exchanges/add_funding.html", {
        'form': form,
        'account': account
    })


# Exchange Balance Update Views
@login_required
def update_exchange_balance(request, account_id):
    """
    Update exchange balance (for trades, fees, etc.).
    Only exchange_balance changes, funding remains untouched.
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id)
    
    if request.method == "POST":
        form = ExchangeBalanceUpdateForm(request.POST)
        if form.is_valid():
            new_balance = form.cleaned_data['new_balance']
            transaction_type = form.cleaned_data['transaction_type']
            notes = form.cleaned_data.get('notes', '')
            
            # Calculate difference
            amount = new_balance - account.exchange_balance
            
            # Only exchange_balance changes
            account.exchange_balance = new_balance
            account.save()
            
            # Create transaction record (audit only)
            from django.utils import timezone
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type=transaction_type,
                amount=amount,
                exchange_balance_after=account.exchange_balance,
                notes=notes
            )
            
            messages.success(request, f"Exchange balance updated to {new_balance:,}.")
            return redirect("exchange_account_detail", pk=account_id)
    else:
        form = ExchangeBalanceUpdateForm()
    
    return render(request, "core/exchanges/update_balance.html", {
        'form': form,
        'account': account
    })


# Record Payment View
@login_required
def record_payment(request, account_id):
    """
    Record Payment - PIN-TO-PIN master document implementation.
    
    Rules:
    - If Client_PnL < 0 (LOSS): funding = funding - paid_amount
    - If Client_PnL > 0 (PROFIT): exchange_balance = exchange_balance - paid_amount
    - paid_amount must be > 0 and <= ABS(Client_PnL)
    """
    account = get_object_or_404(ClientExchangeAccount, pk=account_id)
    
    # Check if button should be visible (Client_PnL != 0)
    client_pnl = account.compute_client_pnl()
    if client_pnl == 0:
        messages.error(request, "Cannot record payment: Account is already settled (Client_PnL = 0).")
        return redirect("exchange_account_detail", pk=account_id)
    
    if request.method == "POST":
        form = RecordPaymentForm(request.POST, account=account)
        if form.is_valid():
            paid_amount = form.cleaned_data['paid_amount']
            notes = form.cleaned_data.get('notes', '')
            
            # Store old values for audit
            old_funding = account.funding
            old_exchange_balance = account.exchange_balance
            
            # RECORD PAYMENT LOGIC (PIN-TO-PIN)
            if client_pnl < 0:  # LOSS CASE
                # funding = funding - paid_amount
                account.funding -= paid_amount
            elif client_pnl > 0:  # PROFIT CASE
                # exchange_balance = exchange_balance - paid_amount
                account.exchange_balance -= paid_amount
            
            account.save()
            
            # Recompute Client_PnL after payment
            new_client_pnl = account.compute_client_pnl()
            
            # Create transaction record (audit only)
            from django.utils import timezone
            Transaction.objects.create(
                client_exchange=account,
                date=timezone.now(),
                type='RECORD_PAYMENT',
                amount=paid_amount,
                exchange_balance_after=account.exchange_balance,
                notes=f"Record Payment. Old Funding: {old_funding}, New Funding: {account.funding}. {notes}"
            )
            
            if new_client_pnl == 0:
                messages.success(request, f"Payment of {paid_amount:,} recorded. Account is now fully settled.")
            else:
                messages.success(request, f"Payment of {paid_amount:,} recorded. Remaining PnL: {new_client_pnl:,}.")
            
            # Redirect based on where user came from
            redirect_to = request.GET.get('redirect_to', 'exchange_account_detail')
            if redirect_to == 'pending_summary':
                return redirect("pending_summary")
            else:
                return redirect("exchange_account_detail", pk=account_id)
    else:
        form = RecordPaymentForm(account=account)
    
    return render(request, "core/exchanges/record_payment.html", {
        'form': form,
        'account': account,
        'client_pnl': client_pnl,
    })


# Pending Payments View
@login_required
def pending_summary(request):
    """
    Pending Payments Summary
    
    Shows two sections:
    1. Clients Owe You - When Client_PnL < 0 (client in loss)
    2. You Owe Clients - When Client_PnL > 0 (client in profit)
    
    All values are COMPUTED, not stored.
    """
    accounts = ClientExchangeAccount.objects.select_related('client', 'exchange').all()
    
    # Clients Owe You (Client_PnL < 0, meaning client is in loss)
    clients_owe_you = []
    for account in accounts:
        client_pnl = account.compute_client_pnl()
        if client_pnl < 0:  # Client in loss, they owe you
            my_share = account.compute_my_share()
            clients_owe_you.append({
                'account': account,
                'client': account.client,
                'exchange': account.exchange,
                'client_pnl': client_pnl,
                'my_share': my_share,
                'amount_owed': abs(client_pnl),  # Amount client owes (full loss)
                'my_share_amount': my_share,  # Your share of what they owe
            })
    
    # You Owe Clients (Client_PnL > 0, meaning client is in profit)
    you_owe_clients = []
    for account in accounts:
        client_pnl = account.compute_client_pnl()
        if client_pnl > 0:  # Client in profit, you owe them
            my_share = account.compute_my_share()
            you_owe_clients.append({
                'account': account,
                'client': account.client,
                'exchange': account.exchange,
                'client_pnl': client_pnl,
                'my_share': my_share,
                'amount_owed': client_pnl,  # Full profit client gets
                'my_share_amount': my_share,  # Your share (what you pay)
            })
    
    # Compute totals
    total_clients_owe = sum(item['amount_owed'] for item in clients_owe_you)
    total_my_share_clients_owe = sum(item['my_share_amount'] for item in clients_owe_you)
    total_you_owe = sum(item['amount_owed'] for item in you_owe_clients)
    total_my_share_you_owe = sum(item['my_share_amount'] for item in you_owe_clients)
    
    context = {
        'clients_owe_you': clients_owe_you,
        'you_owe_clients': you_owe_clients,
        'total_clients_owe': total_clients_owe,
        'total_my_share_clients_owe': total_my_share_clients_owe,
        'total_you_owe': total_you_owe,
        'total_my_share_you_owe': total_my_share_you_owe,
    }
    return render(request, "core/pending/summary.html", context)


# Transaction Views
@login_required
def transaction_list(request):
    """List all transactions (audit trail)."""
    transactions = Transaction.objects.select_related(
        'client_exchange__client',
        'client_exchange__exchange'
    ).order_by('-date', '-id')
    
    return render(request, "core/transactions/list.html", {
        'transactions': transactions
    })


@login_required
def transaction_detail(request, pk):
    """View transaction details."""
    transaction = get_object_or_404(
        Transaction.objects.select_related(
            'client_exchange__client',
            'client_exchange__exchange'
        ),
        pk=pk
    )
    
    return render(request, "core/transactions/detail.html", {
        'transaction': transaction
    })


# ============================================================================
# REPORT VIEWS
# ============================================================================

@login_required
def report_overview(request):
    """Main reports overview page."""
    report_type = request.GET.get('report_type', 'daily')
    client_type_filter = request.GET.get('client_type', '')
    selected_client_id = request.GET.get('client', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    selected_month = request.GET.get('month', '')
    
    # TODO: Add report calculation logic here
    context = {
        'report_type': report_type,
        'client_type_filter': client_type_filter,
        'selected_client_id': selected_client_id,
        'start_date_str': start_date_str,
        'end_date_str': end_date_str,
        'selected_month': selected_month,
        'total_turnover': 0,
        'your_total_profit': 0,
        'company_profit': 0,
    }
    
    return render(request, "core/reports/overview.html", context)


@login_required
def report_daily(request):
    """Daily report view."""
    # TODO: Add daily report calculation logic here
    context = {
        'report_type': 'daily',
    }
    return render(request, "core/reports/daily.html", context)


@login_required
def report_weekly(request):
    """Weekly report view."""
    # TODO: Add weekly report calculation logic here
    context = {
        'report_type': 'weekly',
    }
    return render(request, "core/reports/weekly.html", context)


@login_required
def report_monthly(request):
    """Monthly report view."""
    # TODO: Add monthly report calculation logic here
    context = {
        'report_type': 'monthly',
    }
    return render(request, "core/reports/monthly.html", context)


@login_required
def report_custom(request):
    """Custom date range report view."""
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # TODO: Add custom report calculation logic here
    context = {
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, "core/reports/custom.html", context)


@login_required
def report_client(request, pk):
    """Client-specific report view."""
    client = get_object_or_404(Client, pk=pk)
    report_type = request.GET.get('report_type', 'daily')
    
    # TODO: Add client report calculation logic here
    context = {
        'client': client,
        'report_type': report_type,
    }
    return render(request, "core/reports/client.html", context)


@login_required
def report_exchange(request, pk):
    """Exchange-specific report view."""
    exchange = get_object_or_404(Exchange, pk=pk)
    report_type = request.GET.get('report_type', 'daily')
    
    # TODO: Add exchange report calculation logic here
    context = {
        'exchange': exchange,
        'report_type': report_type,
    }
    return render(request, "core/reports/exchange.html", context)


@login_required
def report_time_travel(request):
    """Time travel report view."""
    date = request.GET.get('date', '')
    
    # TODO: Add time travel report calculation logic here
    context = {
        'date': date,
    }
    return render(request, "core/reports/time_travel.html", context)
