from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import Client, Exchange, ClientExchange, Transaction, CompanyShareRecord, SystemSettings, ClientDailyBalance


def dashboard(request):
    """Minimal dashboard view summarizing key metrics with filters."""

    today = date.today()

    # Filters
    client_id = request.GET.get("client")
    exchange_id = request.GET.get("exchange")
    search_query = request.GET.get("search", "")
    
    # Base queryset
    transactions_qs = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange")
    
    if client_id:
        transactions_qs = transactions_qs.filter(client_exchange__client_id=client_id)
    if exchange_id:
        transactions_qs = transactions_qs.filter(client_exchange__exchange_id=exchange_id)
    if search_query:
        transactions_qs = transactions_qs.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query)
        )

    total_turnover = transactions_qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        transactions_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))[
            "total"
        ]
        or 0
    )
    company_profit = (
        transactions_qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    )

    # Pending sections (all transactions, not filtered)
    pending_clients_owe = (
        Transaction.objects.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))[
            "total"
        ]
        or 0
    )
    pending_you_owe_clients = (
        Transaction.objects.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("client_share_amount"))[
            "total"
        ]
        or 0
    )

    context = {
        "today": today,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "active_clients_count": Client.objects.filter(is_active=True).count(),
        "total_exchanges_count": Exchange.objects.count(),
        "recent_transactions": transactions_qs[:10],
        "all_clients": Client.objects.filter(is_active=True).order_by("name"),
        "all_exchanges": Exchange.objects.filter(is_active=True).order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "search_query": search_query,
    }
    return render(request, "core/dashboard.html", context)


def client_list(request):
    search_query = request.GET.get("search", "")
    clients = Client.objects.all().order_by("name")
    
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) | Q(code__icontains=search_query)
        )
    
    return render(request, "core/clients/list.html", {
        "clients": clients,
        "search_query": search_query,
    })


def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    active_client_exchanges = client.client_exchanges.select_related("exchange").filter(is_active=True).all()
    inactive_client_exchanges = client.client_exchanges.select_related("exchange").filter(is_active=False).all()
    transactions = (
        Transaction.objects.filter(client_exchange__client=client)
        .select_related("client_exchange", "client_exchange__exchange")
        .order_by("-date", "-created_at")[:50]
    )
    return render(
        request,
        "core/clients/detail.html",
        {
            "client": client,
            "client_exchanges": active_client_exchanges,
            "inactive_client_exchanges": inactive_client_exchanges,
            "transactions": transactions,
        },
    )


def client_give_money(request, client_pk):
    """Give money to a client for a specific exchange (FUNDING transaction)."""
    client = get_object_or_404(Client, pk=client_pk)
    
    if request.method == "POST":
        client_exchange_id = request.POST.get("client_exchange")
        tx_date = request.POST.get("date")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and amount > 0:
            client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id, client=client)
            
            # For FUNDING: client gets the full amount, you get nothing
            transaction = Transaction.objects.create(
                client_exchange=client_exchange,
                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                transaction_type=Transaction.TYPE_FUNDING,
                amount=amount,
                client_share_amount=amount,
                your_share_amount=Decimal(0),
                company_share_amount=Decimal(0),
                note=note,
            )
            
            return redirect(reverse("clients:detail", args=[client.pk]))
    
    # If GET or validation fails, redirect back to client detail
    return redirect(reverse("clients:detail", args=[client.pk]))


def client_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code", "").strip()
        if name:
            client = Client.objects.create(
                name=name,
                code=code if code else None
            )
            return redirect(reverse("clients:detail", args=[client.pk]))
    return render(request, "core/clients/create.html")


def exchange_list(request):
    exchanges = Exchange.objects.all().order_by("name")
    return render(request, "core/exchanges/list.html", {"exchanges": exchanges})


def transaction_list(request):
    """Transaction list with filtering options."""
    client_id = request.GET.get("client")
    exchange_id = request.GET.get("exchange")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    tx_type = request.GET.get("type")
    search_query = request.GET.get("search", "")
    
    transactions = Transaction.objects.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").all()
    
    if client_id:
        transactions = transactions.filter(client_exchange__client_id=client_id)
    if exchange_id:
        transactions = transactions.filter(client_exchange__exchange_id=exchange_id)
    if start_date_str:
        transactions = transactions.filter(date__gte=date.fromisoformat(start_date_str))
    if end_date_str:
        transactions = transactions.filter(date__lte=date.fromisoformat(end_date_str))
    if tx_type:
        transactions = transactions.filter(transaction_type=tx_type)
    if search_query:
        transactions = transactions.filter(
            Q(client_exchange__client__name__icontains=search_query) |
            Q(client_exchange__client__code__icontains=search_query) |
            Q(client_exchange__exchange__name__icontains=search_query) |
            Q(note__icontains=search_query)
        )
    
    transactions = transactions.order_by("-date", "-created_at")[:200]
    
    return render(request, "core/transactions/list.html", {
        "transactions": transactions,
        "all_clients": Client.objects.filter(is_active=True).order_by("name"),
        "all_exchanges": Exchange.objects.filter(is_active=True).order_by("name"),
        "selected_client": int(client_id) if client_id else None,
        "selected_exchange": int(exchange_id) if exchange_id else None,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "selected_type": tx_type,
        "search_query": search_query,
    })


def pending_summary(request):
    """
    Simple derived view for:
    - Clients owe you
    - You owe clients

    Auto-shift behaviour is handled by aggregation over all history.
    
    Supports time-travel: filter by date to see pending payments as of that date.
    Supports report types: daily, weekly, monthly
    """
    from datetime import timedelta
    
    today = date.today()
    report_type = request.GET.get("report_type", "daily")  # daily, weekly, monthly
    
    # Calculate date range based on report type
    if report_type == "daily":
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    elif report_type == "weekly":
        # Weekly: from last same weekday to this same weekday (7 days)
        # If today is Monday, show from last Monday to this Monday
        # If today is Tuesday, show from last Tuesday to this Tuesday
        start_date = today - timedelta(days=7)
        end_date = today
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_weekday = today.weekday()
        date_range_label = f"Weekly ({weekday_names[today_weekday]} to {weekday_names[today_weekday]}): {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        # Get today's day of month
        day_of_month = today.day
        # Calculate start date (last month's same day)
        if today.month == 1:
            # If January, go to December of previous year
            start_date = date(today.year - 1, 12, min(day_of_month, 31))
        else:
            # Get last month
            last_month = today.month - 1
            # Handle edge case where day doesn't exist in last month (e.g., Jan 31 -> Dec 31)
            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day
            start_date = date(today.year, last_month, min(day_of_month, last_month_days))
        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        # Default to daily
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get date parameter for "as of" functionality (optional override)
    as_of_str = request.GET.get("date")
    if as_of_str:
        as_of = date.fromisoformat(as_of_str)
        end_date = as_of  # Use as_of as end date if provided
    else:
        as_of = end_date
    
    # Filter transactions within the date range
    base_qs = Transaction.objects.filter(date__gte=start_date, date__lte=end_date)
    
    # Clients owe you -> your share of losses not yet settled (simplified)
    clients_owe = (
        base_qs.filter(transaction_type=Transaction.TYPE_LOSS)
        .values("client_exchange__client__id", "client_exchange__client__name", "client_exchange__client__code")
        .annotate(total_owed=Sum("your_share_amount"))
        .order_by("-total_owed")
    )

    # You owe clients -> client share of profits not yet settled (simplified)
    you_owe = (
        base_qs.filter(transaction_type=Transaction.TYPE_PROFIT)
        .values("client_exchange__client__id", "client_exchange__client__name", "client_exchange__client__code")
        .annotate(total_owed=Sum("client_share_amount"))
        .order_by("-total_owed")
    )

    context = {
        "clients_owe": clients_owe,
        "you_owe": you_owe,
        "as_of": as_of,
        "today": today,
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
        "date_range_label": date_range_label,
    }
    return render(request, "core/pending/summary.html", context)


def report_overview(request):
    """High-level reporting screen with simple totals and graphs."""
    from datetime import timedelta
    from collections import defaultdict

    today = date.today()
    report_type = request.GET.get("report_type", "monthly")  # Default to monthly
    
    # Overall totals
    total_turnover = Transaction.objects.aggregate(total=Sum("amount"))["total"] or 0
    your_total_profit = (
        Transaction.objects.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))[
            "total"
        ]
        or 0
    )
    company_profit = (
        Transaction.objects.aggregate(total=Sum("company_share_amount"))["total"] or 0
    )

    # Daily trends for last 30 days
    start_date = today - timedelta(days=30)
    daily_data = defaultdict(lambda: {"profit": 0, "loss": 0, "turnover": 0})
    
    daily_transactions = Transaction.objects.filter(
        date__gte=start_date,
        date__lte=today
    ).values("date", "transaction_type").annotate(
        profit_sum=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        loss_sum=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_LOSS)),
        turnover_sum=Sum("amount")
    )
    
    for item in daily_transactions:
        tx_date = item["date"]
        daily_data[tx_date]["profit"] += float(item["profit_sum"] or 0)
        daily_data[tx_date]["loss"] += float(item["loss_sum"] or 0)
        daily_data[tx_date]["turnover"] += float(item["turnover_sum"] or 0)
    
    # Create sorted date list and data arrays
    date_labels = []
    profit_data = []
    loss_data = []
    turnover_data = []
    
    for i in range(30):
        current_date = start_date + timedelta(days=i)
        date_labels.append(current_date.strftime("%b %d"))
        profit_data.append(float(daily_data[current_date]["profit"]))
        loss_data.append(float(daily_data[current_date]["loss"]))
        turnover_data.append(float(daily_data[current_date]["turnover"]))
    
    # Transaction type breakdown
    type_breakdown = Transaction.objects.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_counts = []
    type_amounts = []
    type_colors = []
    
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#16a34a"),
        Transaction.TYPE_LOSS: ("Loss", "#dc2626"),
        Transaction.TYPE_FUNDING: ("Funding", "#2563eb"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#7c3aed"),
    }
    
    for item in type_breakdown:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_counts.append(item["count"])
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Monthly trends (last 6 months)
    monthly_labels = []
    monthly_profit = []
    monthly_loss = []
    monthly_turnover = []
    
    for i in range(6):
        # Calculate month start date
        month_date = today.replace(day=1)
        for _ in range(i):
            if month_date.month == 1:
                month_date = month_date.replace(year=month_date.year - 1, month=12)
            else:
                month_date = month_date.replace(month=month_date.month - 1)
        
        # Calculate month end date
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year + 1, month=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month + 1) - timedelta(days=1)
        
        monthly_labels.insert(0, month_date.strftime("%b %Y"))
        
        # Get transactions for this month
        month_transactions = Transaction.objects.filter(
            date__gte=month_date,
            date__lte=month_end
        )
        
        month_profit_val = month_transactions.filter(
            transaction_type=Transaction.TYPE_PROFIT
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        month_loss_val = month_transactions.filter(
            transaction_type=Transaction.TYPE_LOSS
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        month_turnover_val = month_transactions.aggregate(total=Sum("amount"))["total"] or 0
        
        monthly_profit.insert(0, float(month_profit_val))
        monthly_loss.insert(0, float(month_loss_val))
        monthly_turnover.insert(0, float(month_turnover_val))
    
    # Top clients by profit (last 30 days)
    top_clients = Transaction.objects.filter(
        date__gte=start_date,
        transaction_type=Transaction.TYPE_PROFIT
    ).values(
        "client_exchange__client__name"
    ).annotate(
        total_profit=Sum("your_share_amount")
    ).order_by("-total_profit")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in top_clients]
    client_profits = [float(item["total_profit"] or 0) for item in top_clients]

    # Weekly data (last 4 weeks)
    weekly_labels = []
    weekly_profit = []
    weekly_loss = []
    weekly_turnover = []
    
    for i in range(4):
        week_end = today - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=6)
        weekly_labels.insert(0, f"Week {4-i} ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d')})")
        
        week_transactions = Transaction.objects.filter(
            date__gte=week_start,
            date__lte=week_end
        )
        
        week_profit_val = week_transactions.filter(
            transaction_type=Transaction.TYPE_PROFIT
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        week_loss_val = week_transactions.filter(
            transaction_type=Transaction.TYPE_LOSS
        ).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        week_turnover_val = week_transactions.aggregate(total=Sum("amount"))["total"] or 0
        
        weekly_profit.insert(0, float(week_profit_val))
        weekly_loss.insert(0, float(week_loss_val))
        weekly_turnover.insert(0, float(week_turnover_val))

    context = {
        "report_type": report_type,
        "total_turnover": total_turnover,
        "your_total_profit": your_total_profit,
        "company_profit": company_profit,
        "daily_labels": json.dumps(date_labels),
        "daily_profit": json.dumps(profit_data),
        "daily_loss": json.dumps(loss_data),
        "daily_turnover": json.dumps(turnover_data),
        "weekly_labels": json.dumps(weekly_labels),
        "weekly_profit": json.dumps(weekly_profit),
        "weekly_loss": json.dumps(weekly_loss),
        "weekly_turnover": json.dumps(weekly_turnover),
        "type_labels": json.dumps(type_labels),
        "type_counts": json.dumps(type_counts),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "monthly_labels": json.dumps(monthly_labels),
        "monthly_profit": json.dumps(monthly_profit),
        "monthly_loss": json.dumps(monthly_loss),
        "monthly_turnover": json.dumps(monthly_turnover),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
    }
    return render(request, "core/reports/overview.html", context)


def time_travel_report(request):
    """
    Time‑travel reporting: filter transactions and aggregates by date range or up to a selected date.
    For now this uses live aggregation over `Transaction`; it can later leverage
    `DailyBalanceSnapshot` for faster queries.
    """
    # Get date parameters
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    as_of_str = request.GET.get("date")  # Legacy single date parameter
    
    # Determine date range
    if start_date_str and end_date_str:
        # Use date range
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        as_of = end_date  # For display purposes
        qs = Transaction.objects.filter(date__gte=start_date, date__lte=end_date)
        date_range_mode = True
    elif as_of_str:
        # Legacy: single date (up to that date)
        as_of = date.fromisoformat(as_of_str)
        qs = Transaction.objects.filter(date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None
    else:
        # Default: today
        as_of = date.today()
        qs = Transaction.objects.filter(date__lte=as_of)
        date_range_mode = False
        start_date = None
        end_date = None

    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0

    pending_clients_owe = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    pending_you_owe_clients = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("client_share_amount"))["total"] or 0
    )

    recent_transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")[:50]

    context = {
        "as_of": as_of,
        "start_date": start_date,
        "end_date": end_date,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
        "date_range_mode": date_range_mode,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "pending_clients_owe": pending_clients_owe,
        "pending_you_owe_clients": pending_you_owe_clients,
        "recent_transactions": recent_transactions,
    }
    return render(request, "core/reports/time_travel.html", context)


def company_share_summary(request):
    from .models import CompanyShareRecord

    # Get filter parameters
    client_id = request.GET.get("client")
    selected_client = None
    
    # Base queryset
    records_qs = CompanyShareRecord.objects.select_related(
        "client_exchange", 
        "client_exchange__client", 
        "client_exchange__exchange"
    )
    
    # Filter by client if selected
    if client_id:
        selected_client = get_object_or_404(Client, pk=client_id)
        records_qs = records_qs.filter(client_exchange__client=selected_client)

    total_company_profit = (
        records_qs.aggregate(total=Sum("company_amount"))["total"] or 0
    )

    per_client = (
        CompanyShareRecord.objects.values("client_exchange__client__id", "client_exchange__client__name")
        .annotate(total=Sum("company_amount"))
        .order_by("-total")
    )

    per_exchange = (
        records_qs.values(
            "client_exchange__exchange__id",
            "client_exchange__exchange__name",
            "client_exchange__client__name",
        )
        .annotate(total=Sum("company_amount"))
        .order_by("-total")
    )
    
    # Detailed breakdown for selected client (exchange-wise)
    client_exchange_details = None
    if selected_client:
        client_exchange_details = (
            records_qs.values(
                "client_exchange__exchange__name",
                "client_exchange__exchange__code",
            )
            .annotate(
                total=Sum("company_amount"),
                transaction_count=Count("id")
            )
            .order_by("-total")
        )

    # Get all clients for filter dropdown
    all_clients = Client.objects.filter(is_active=True).order_by("name")

    context = {
        "total_company_profit": total_company_profit,
        "per_client": per_client,
        "per_exchange": per_exchange,
        "selected_client": selected_client,
        "client_exchange_details": client_exchange_details,
        "all_clients": all_clients,
        "client_id": client_id,
    }
    return render(request, "core/company/share_summary.html", context)


# Exchange Management Views
def exchange_create(request):
    """Create a new standalone exchange (A, B, C, D, etc.)."""
    if request.method == "POST":
        name = request.POST.get("name")
        code = request.POST.get("code", "").strip()
        is_active = request.POST.get("is_active") == "on"
        
        if name:
            exchange = Exchange.objects.create(
                name=name,
                code=code if code else None,
                is_active=is_active,
            )
            return redirect(reverse("exchanges:list"))
    
    return render(request, "core/exchanges/create.html")


def exchange_edit(request, pk):
    """Edit an existing standalone exchange."""
    exchange = get_object_or_404(Exchange, pk=pk)
    if request.method == "POST":
        exchange.name = request.POST.get("name")
        exchange.code = request.POST.get("code", "").strip() or None
        exchange.is_active = request.POST.get("is_active") == "on"
        exchange.save()
        return redirect(reverse("exchanges:list"))
    
    return render(request, "core/exchanges/edit.html", {"exchange": exchange})


def client_exchange_create(request, client_pk):
    """Link a client to an exchange with specific percentages."""
    client = get_object_or_404(Client, pk=client_pk)
    exchanges = Exchange.objects.filter(is_active=True).order_by("name")
    
    if request.method == "POST":
        exchange_id = request.POST.get("exchange")
        my_share = request.POST.get("my_share_pct")
        company_share = request.POST.get("company_share_pct")
        is_active = request.POST.get("is_active") == "on"
        
        if exchange_id and my_share and company_share:
            exchange = get_object_or_404(Exchange, pk=exchange_id)
            my_share_decimal = Decimal(my_share)
            company_share_decimal = Decimal(company_share)
            
            # Validate company share is less than my share
            if company_share_decimal >= my_share_decimal:
                return render(request, "core/exchanges/link_to_client.html", {
                    "client": client,
                    "exchanges": exchanges,
                    "error": "Company share must be less than your share",
                })
            
            client_exchange = ClientExchange.objects.create(
                client=client,
                exchange=exchange,
                my_share_pct=my_share_decimal,
                company_share_pct=company_share_decimal,
                is_active=is_active,
            )
            return redirect(reverse("clients:detail", args=[client.pk]))
    
    return render(request, "core/exchanges/link_to_client.html", {
        "client": client,
        "exchanges": exchanges,
    })


def client_exchange_edit(request, pk):
    """Edit client-exchange link percentages. Exchange can be edited within 10 days of creation."""
    client_exchange = get_object_or_404(ClientExchange, pk=pk)
    
    # Check if exchange can be edited (within 10 days of creation)
    days_since_creation = (date.today() - client_exchange.created_at.date()).days
    can_edit_exchange = days_since_creation <= 10
    
    if request.method == "POST":
        my_share = Decimal(request.POST.get("my_share_pct"))
        company_share = Decimal(request.POST.get("company_share_pct"))
        
        # Validate company share is less than my share
        if company_share >= my_share:
            exchanges = Exchange.objects.filter(is_active=True).order_by("name")
            days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
            return render(request, "core/exchanges/edit_client_link.html", {
                "client_exchange": client_exchange,
                "exchanges": exchanges,
                "can_edit_exchange": can_edit_exchange,
                "days_since_creation": days_since_creation,
                "days_remaining": days_remaining,
                "error": "Company share must be less than your share",
            })
        
        # Update exchange if within 10 days and exchange was provided
        # Double-check can_edit_exchange to prevent manipulation
        if can_edit_exchange and request.POST.get("exchange"):
            new_exchange_id = request.POST.get("exchange")
            new_exchange = get_object_or_404(Exchange, pk=new_exchange_id)
            
            # Check if this exchange-client combination already exists (excluding current)
            existing = ClientExchange.objects.filter(
                client=client_exchange.client,
                exchange=new_exchange
            ).exclude(pk=client_exchange.pk).first()
            
            if existing:
                exchanges = Exchange.objects.filter(is_active=True).order_by("name")
                days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
                return render(request, "core/exchanges/edit_client_link.html", {
                    "client_exchange": client_exchange,
                    "exchanges": exchanges,
                    "can_edit_exchange": can_edit_exchange,
                    "days_since_creation": days_since_creation,
                    "days_remaining": days_remaining,
                    "error": f"This client already has a link to {new_exchange.name}. Please edit that link instead.",
                })
            
            client_exchange.exchange = new_exchange
        elif request.POST.get("exchange") and not can_edit_exchange:
            # Security check: prevent exchange update if beyond 10 days
            exchanges = Exchange.objects.filter(is_active=True).order_by("name")
            days_remaining = 0
            return render(request, "core/exchanges/edit_client_link.html", {
                "client_exchange": client_exchange,
                "exchanges": exchanges,
                "can_edit_exchange": can_edit_exchange,
                "days_since_creation": days_since_creation,
                "days_remaining": days_remaining,
                "error": "Exchange cannot be modified after 10 days from creation.",
            })
        
        client_exchange.my_share_pct = my_share
        client_exchange.company_share_pct = company_share
        client_exchange.is_active = request.POST.get("is_active") == "on"
        client_exchange.save()
        return redirect(reverse("clients:detail", args=[client_exchange.client.pk]))
    
    # GET request - prepare context
    exchanges = Exchange.objects.filter(is_active=True).order_by("name") if can_edit_exchange else None
    days_remaining = (10 - days_since_creation) if can_edit_exchange else 0
    
    return render(request, "core/exchanges/edit_client_link.html", {
        "client_exchange": client_exchange,
        "exchanges": exchanges,
        "can_edit_exchange": can_edit_exchange,
        "days_since_creation": days_since_creation,
        "days_remaining": days_remaining,
    })


# Transaction Management Views
def transaction_create(request):
    """Create a new transaction with auto-calculation."""
    from datetime import date as date_today
    clients = Client.objects.filter(is_active=True).order_by("name")
    
    if request.method == "POST":
        client_exchange_id = request.POST.get("client_exchange")
        tx_date = request.POST.get("date")
        tx_type = request.POST.get("transaction_type")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if client_exchange_id and tx_date and tx_type and amount > 0:
            client_exchange = get_object_or_404(ClientExchange, pk=client_exchange_id)
            
            # Auto-calculate shares based on client-exchange percentages
            if tx_type == Transaction.TYPE_PROFIT:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                company_share = your_share * (client_exchange.company_share_pct / 100)
                your_share_after_company = your_share - company_share
            elif tx_type == Transaction.TYPE_LOSS:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                company_share = Decimal(0)  # No company share on losses
                your_share_after_company = your_share
            else:  # FUNDING or SETTLEMENT
                client_share = amount
                your_share = Decimal(0)
                company_share = Decimal(0)
                your_share_after_company = Decimal(0)
            
            transaction = Transaction.objects.create(
                client_exchange=client_exchange,
                date=datetime.strptime(tx_date, "%Y-%m-%d").date(),
                transaction_type=tx_type,
                amount=amount,
                client_share_amount=client_share,
                your_share_amount=your_share_after_company,
                company_share_amount=company_share,
                note=note,
            )
            
            # Create company share record if applicable
            if company_share > 0:
                CompanyShareRecord.objects.create(
                    client_exchange=client_exchange,
                    transaction=transaction,
                    date=transaction.date,
                    company_amount=company_share,
                )
            
            return redirect(reverse("transactions:list"))
    
    # Get client-exchanges for selected client (if provided)
    client_id = request.GET.get("client")
    client_exchanges = ClientExchange.objects.filter(is_active=True).select_related("client", "exchange")
    if client_id:
        client_exchanges = client_exchanges.filter(client_id=client_id)
    client_exchanges = client_exchanges.order_by("client__name", "exchange__name")
    
    return render(request, "core/transactions/create.html", {
        "clients": clients,
        "client_exchanges": client_exchanges,
        "selected_client": int(client_id) if client_id else None,
        "today": date_today.today(),
    })


def transaction_edit(request, pk):
    """Edit an existing transaction."""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    if request.method == "POST":
        tx_date = request.POST.get("date")
        tx_type = request.POST.get("transaction_type")
        amount = Decimal(request.POST.get("amount", 0))
        note = request.POST.get("note", "")
        
        if tx_date and tx_type and amount > 0:
            client_exchange = transaction.client_exchange
            
            # Recalculate shares
            if tx_type == Transaction.TYPE_PROFIT:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                company_share = your_share * (client_exchange.company_share_pct / 100)
                your_share_after_company = your_share - company_share
            elif tx_type == Transaction.TYPE_LOSS:
                your_share = amount * (client_exchange.my_share_pct / 100)
                client_share = amount - your_share
                company_share = Decimal(0)
                your_share_after_company = your_share
            else:
                client_share = amount
                your_share = Decimal(0)
                company_share = Decimal(0)
                your_share_after_company = Decimal(0)
            
            transaction.date = datetime.strptime(tx_date, "%Y-%m-%d").date()
            transaction.transaction_type = tx_type
            transaction.amount = amount
            transaction.client_share_amount = client_share
            transaction.your_share_amount = your_share_after_company
            transaction.company_share_amount = company_share
            transaction.note = note
            transaction.save()
            
            # Update company share record
            if company_share > 0:
                csr, _ = CompanyShareRecord.objects.get_or_create(
                    transaction=transaction,
                    defaults={"client_exchange": client_exchange, "date": transaction.date, "company_amount": company_share}
                )
                if csr.company_amount != company_share:
                    csr.company_amount = company_share
                    csr.save()
            else:
                CompanyShareRecord.objects.filter(transaction=transaction).delete()
            
            return redirect(reverse("transactions:list"))
    
    return render(request, "core/transactions/edit.html", {"transaction": transaction})


def get_exchanges_for_client(request):
    """AJAX endpoint to get client-exchanges for a client."""
    client_id = request.GET.get("client_id")
    if client_id:
        client_exchanges = ClientExchange.objects.filter(client_id=client_id, is_active=True).select_related("exchange").values("id", "exchange__name", "exchange__id")
        return JsonResponse(list(client_exchanges), safe=False)
    return JsonResponse([], safe=False)


# Period-based Reports
def report_daily(request):
    """Daily report for a specific date with graphs and analysis."""
    report_date_str = request.GET.get("date", date.today().isoformat())
    report_date = date.fromisoformat(report_date_str)
    
    qs = Transaction.objects.filter(date=report_date)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-created_at")
    
    # Chart data - transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#16a34a"),
        Transaction.TYPE_LOSS: ("Loss", "#dc2626"),
        Transaction.TYPE_FUNDING: ("Funding", "#2563eb"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#7c3aed"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Client-wise breakdown
    client_data = qs.values("client_exchange__client__name").annotate(
        profit=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        loss=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_LOSS)),
        turnover=Sum("amount")
    ).order_by("-turnover")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    
    context = {
        "report_date": report_date,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "company_profit": company_profit,
        "transactions": transactions,
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
    }
    return render(request, "core/reports/daily.html", context)


def report_weekly(request):
    """Weekly report for a specific week with graphs and analysis."""
    week_start_str = request.GET.get("week_start", None)
    if week_start_str:
        week_start = date.fromisoformat(week_start_str)
    else:
        # Default to current week (Monday)
        today = date.today()
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
    
    week_end = week_start + timedelta(days=6)
    
    qs = Transaction.objects.filter(date__gte=week_start, date__lte=week_end)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Daily breakdown for the week
    daily_labels = []
    daily_profit = []
    daily_loss = []
    daily_turnover = []
    
    for i in range(7):
        current_date = week_start + timedelta(days=i)
        daily_labels.append(current_date.strftime("%a %d"))
        
        day_qs = qs.filter(date=current_date)
        day_profit = day_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
        day_loss = day_qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
        day_turnover = day_qs.aggregate(total=Sum("amount"))["total"] or 0
        
        daily_profit.append(float(day_profit))
        daily_loss.append(float(day_loss))
        daily_turnover.append(float(day_turnover))
    
    # Transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#16a34a"),
        Transaction.TYPE_LOSS: ("Loss", "#dc2626"),
        Transaction.TYPE_FUNDING: ("Funding", "#2563eb"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#7c3aed"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    avg_daily_turnover = float(total_turnover) / 7
    
    context = {
        "week_start": week_start,
        "week_end": week_end,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_daily_turnover": avg_daily_turnover,
        "company_profit": company_profit,
        "transactions": transactions,
        "daily_labels": json.dumps(daily_labels),
        "daily_profit": json.dumps(daily_profit),
        "daily_loss": json.dumps(daily_loss),
        "daily_turnover": json.dumps(daily_turnover),
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
    }
    return render(request, "core/reports/weekly.html", context)


def report_monthly(request):
    """Monthly report for a specific month with graphs and analysis."""
    month_str = request.GET.get("month", date.today().strftime("%Y-%m"))
    year, month = map(int, month_str.split("-"))
    
    month_start = date(year, month, 1)
    if month == 12:
        month_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(year, month + 1, 1) - timedelta(days=1)
    
    qs = Transaction.objects.filter(date__gte=month_start, date__lte=month_end)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    # Weekly breakdown for the month
    weekly_labels = []
    weekly_profit = []
    weekly_loss = []
    weekly_turnover = []
    
    current_date = month_start
    week_num = 1
    while current_date <= month_end:
        week_end_date = min(current_date + timedelta(days=6), month_end)
        weekly_labels.append(f"Week {week_num} ({current_date.strftime('%d')}-{week_end_date.strftime('%d %b')})")
        
        week_qs = qs.filter(date__gte=current_date, date__lte=week_end_date)
        week_profit = week_qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
        week_loss = week_qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
        week_turnover = week_qs.aggregate(total=Sum("amount"))["total"] or 0
        
        weekly_profit.append(float(week_profit))
        weekly_loss.append(float(week_loss))
        weekly_turnover.append(float(week_turnover))
        
        current_date = week_end_date + timedelta(days=1)
        week_num += 1
    
    # Transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#16a34a"),
        Transaction.TYPE_LOSS: ("Loss", "#dc2626"),
        Transaction.TYPE_FUNDING: ("Funding", "#2563eb"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#7c3aed"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Top clients
    client_data = qs.values("client_exchange__client__name").annotate(
        profit=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        turnover=Sum("amount")
    ).order_by("-profit")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    days_in_month = (month_end - month_start).days + 1
    avg_daily_turnover = float(total_turnover) / days_in_month if days_in_month > 0 else 0
    
    context = {
        "month_start": month_start,
        "month_end": month_end,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_daily_turnover": avg_daily_turnover,
        "company_profit": company_profit,
        "transactions": transactions,
        "weekly_labels": json.dumps(weekly_labels),
        "weekly_profit": json.dumps(weekly_profit),
        "weekly_loss": json.dumps(weekly_loss),
        "weekly_turnover": json.dumps(weekly_turnover),
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
    }
    return render(request, "core/reports/monthly.html", context)


def report_custom(request):
    """Custom period report."""
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    else:
        # Default to last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    
    qs = Transaction.objects.filter(date__gte=start_date, date__lte=end_date)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    
    transactions = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    context = {
        "start_date": start_date,
        "end_date": end_date,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "transactions": transactions,
    }
    return render(request, "core/reports/custom.html", context)


# Export Views
def export_report_csv(request):
    """Export report as CSV."""
    import csv
    
    report_type = request.GET.get("type", "all")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(date__gte=start_date, date__lte=end_date)
    else:
        qs = Transaction.objects.all()
    
    if report_type == "profit":
        qs = qs.filter(transaction_type=Transaction.TYPE_PROFIT)
    elif report_type == "loss":
        qs = qs.filter(transaction_type=Transaction.TYPE_LOSS)
    
    qs = qs.select_related("client_exchange", "client_exchange__client", "client_exchange__exchange").order_by("-date", "-created_at")
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="report_{date.today()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(["Date", "Client", "Exchange", "Type", "Amount", "Your Share", "Client Share", "Company Share", "Note"])
    
    for tx in qs:
        writer.writerow([
            tx.date,
            tx.client_exchange.client.name,
            tx.client_exchange.exchange.name,
            tx.get_transaction_type_display(),
            tx.amount,
            tx.your_share_amount,
            tx.client_share_amount,
            tx.company_share_amount,
            tx.note,
        ])
    
    return response


# Client-specific and Exchange-specific Reports
def report_client(request, client_pk):
    """Report for a specific client."""
    client = get_object_or_404(Client, pk=client_pk)
    
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        qs = Transaction.objects.filter(client_exchange__client=client, date__gte=start_date, date__lte=end_date)
    else:
        qs = Transaction.objects.filter(client_exchange__client=client)
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    
    transactions = qs.select_related("client_exchange", "client_exchange__exchange", "client_exchange__client").order_by("-date", "-created_at")
    
    context = {
        "client": client,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "company_profit": company_profit,
        "transactions": transactions,
    }
    return render(request, "core/reports/client.html", context)


def report_exchange(request, exchange_pk):
    """Report for a specific exchange with graphs and analysis."""
    from datetime import timedelta
    
    exchange = get_object_or_404(Exchange, pk=exchange_pk)
    today = date.today()
    report_type = request.GET.get("report_type", "weekly")  # daily, weekly, monthly
    
    # Calculate date range based on report type
    if report_type == "daily":
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    elif report_type == "weekly":
        # Weekly: from last same weekday to this same weekday (7 days)
        start_date = today - timedelta(days=7)
        end_date = today
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_weekday = today.weekday()
        date_range_label = f"Weekly ({weekday_names[today_weekday]} to {weekday_names[today_weekday]}): {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    elif report_type == "monthly":
        # Monthly: from last month's same day to today
        day_of_month = today.day
        if today.month == 1:
            start_date = date(today.year - 1, 12, min(day_of_month, 31))
        else:
            last_month = today.month - 1
            last_month_days = (date(today.year, today.month, 1) - timedelta(days=1)).day
            start_date = date(today.year, last_month, min(day_of_month, last_month_days))
        end_date = today
        date_range_label = f"Monthly ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')})"
    else:
        # Default to daily
        start_date = today
        end_date = today
        date_range_label = f"Today ({today.strftime('%B %d, %Y')})"
    
    # Get date parameter for custom date range (optional override)
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    
    if start_date_str and end_date_str:
        # Custom date range overrides report type
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        date_range_label = f"Custom: {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"
    
    qs = Transaction.objects.filter(
        client_exchange__exchange=exchange, 
        date__gte=start_date, 
        date__lte=end_date
    )
    
    total_turnover = qs.aggregate(total=Sum("amount"))["total"] or 0
    your_profit = (
        qs.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    company_profit = qs.aggregate(total=Sum("company_share_amount"))["total"] or 0
    your_loss = (
        qs.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
    )
    
    transactions = qs.select_related(
        "client_exchange", 
        "client_exchange__client", 
        "client_exchange__exchange"
    ).order_by("-date", "-created_at")
    
    # Transaction type breakdown
    type_data = qs.values("transaction_type").annotate(
        count=Count("id"),
        total_amount=Sum("amount")
    )
    type_labels = []
    type_amounts = []
    type_colors = []
    type_map = {
        Transaction.TYPE_PROFIT: ("Profit", "#16a34a"),
        Transaction.TYPE_LOSS: ("Loss", "#dc2626"),
        Transaction.TYPE_FUNDING: ("Funding", "#2563eb"),
        Transaction.TYPE_SETTLEMENT: ("Settlement", "#7c3aed"),
    }
    for item in type_data:
        tx_type = item["transaction_type"]
        if tx_type in type_map:
            label, color = type_map[tx_type]
            type_labels.append(label)
            type_amounts.append(float(item["total_amount"] or 0))
            type_colors.append(color)
    
    # Client-wise breakdown
    client_data = qs.values("client_exchange__client__name").annotate(
        profit=Sum("your_share_amount", filter=Q(transaction_type=Transaction.TYPE_PROFIT)),
        turnover=Sum("amount")
    ).order_by("-profit")[:10]
    
    client_labels = [item["client_exchange__client__name"] for item in client_data]
    client_profits = [float(item["profit"] or 0) for item in client_data]
    
    # Analysis
    net_profit = float(your_profit) - float(your_loss)
    profit_margin = (float(your_profit) / float(total_turnover) * 100) if total_turnover > 0 else 0
    
    # Check if we have data for charts
    has_type_data = len(type_labels) > 0
    has_client_data = len(client_labels) > 0
    
    context = {
        "exchange": exchange,
        "start_date": start_date_str if start_date_str else start_date.strftime('%Y-%m-%d'),
        "end_date": end_date_str if end_date_str else end_date.strftime('%Y-%m-%d'),
        "report_type": report_type,
        "date_range_label": date_range_label,
        "total_turnover": total_turnover,
        "your_profit": your_profit,
        "your_loss": your_loss,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "company_profit": company_profit,
        "transactions": transactions,
        "type_labels": json.dumps(type_labels),
        "type_amounts": json.dumps(type_amounts),
        "type_colors": json.dumps(type_colors),
        "client_labels": json.dumps(client_labels),
        "client_profits": json.dumps(client_profits),
        "has_type_data": has_type_data,
        "has_client_data": has_client_data,
    }
    return render(request, "core/reports/exchange.html", context)


# Settings View
def settings_view(request):
    """System settings page for configuring weekly reports and other options."""
    settings = SystemSettings.load()
    
    if request.method == "POST":
        settings.weekly_report_day = int(request.POST.get("weekly_report_day", 0))
        settings.auto_generate_weekly_reports = request.POST.get("auto_generate_weekly_reports") == "on"
        settings.save()
        return redirect(reverse("settings"))
    
    return render(request, "core/settings.html", {"settings": settings})


# Balance Tracking
def client_balance(request, client_pk):
    """Show balance summary for a specific client."""
    client = get_object_or_404(Client, pk=client_pk)
    
    # Handle daily balance recording/editing
    if request.method == "POST" and request.POST.get("action") == "record_balance":
        balance_date = request.POST.get("date")
        remaining_balance = Decimal(request.POST.get("remaining_balance", 0))
        note = request.POST.get("note", "")
        balance_id = request.POST.get("balance_id")
        
        if balance_date and remaining_balance >= 0:
            if balance_id:
                # Edit existing balance
                balance = get_object_or_404(ClientDailyBalance, pk=balance_id, client=client)
                balance.date = date.fromisoformat(balance_date)
                balance.remaining_balance = remaining_balance
                balance.note = note
                balance.save()
            else:
                # Create new balance
                ClientDailyBalance.objects.update_or_create(
                    client=client,
                    date=date.fromisoformat(balance_date),
                    defaults={
                        "remaining_balance": remaining_balance,
                        "note": note,
                    }
                )
            return redirect(reverse("clients:balance", args=[client.pk]))
    
    # Check if editing a balance
    edit_balance_id = request.GET.get("edit_balance")
    edit_balance = None
    if edit_balance_id:
        try:
            edit_balance = ClientDailyBalance.objects.get(pk=edit_balance_id, client=client)
        except ClientDailyBalance.DoesNotExist:
            pass
    
    # Calculate balances per client-exchange
    client_exchanges = client.client_exchanges.select_related("exchange").all()
    exchange_balances = []
    
    for client_exchange in client_exchanges:
        transactions = Transaction.objects.filter(client_exchange=client_exchange)
        
        total_funding = transactions.filter(transaction_type=Transaction.TYPE_FUNDING).aggregate(total=Sum("amount"))["total"] or 0
        total_profit = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("amount"))["total"] or 0
        total_loss = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("amount"))["total"] or 0
        
        client_profit_share = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("client_share_amount"))["total"] or 0
        client_loss_share = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("client_share_amount"))["total"] or 0
        
        your_profit_share = transactions.filter(transaction_type=Transaction.TYPE_PROFIT).aggregate(total=Sum("your_share_amount"))["total"] or 0
        your_loss_share = transactions.filter(transaction_type=Transaction.TYPE_LOSS).aggregate(total=Sum("your_share_amount"))["total"] or 0
        
        client_net = total_funding + client_profit_share - client_loss_share
        you_net = your_profit_share - your_loss_share
        
        exchange_balances.append({
            "client_exchange": client_exchange,
            "exchange": client_exchange.exchange,
            "total_funding": total_funding,
            "total_profit": total_profit,
            "total_loss": total_loss,
            "client_net": client_net,
            "you_net": you_net,
            "pending_client_owes": your_loss_share,
            "pending_you_owe": client_profit_share,
        })
    
    # Get daily balance records
    daily_balances = ClientDailyBalance.objects.filter(client=client).order_by("-date")[:30]
    
    context = {
        "client": client,
        "exchange_balances": exchange_balances,
        "daily_balances": daily_balances,
        "today": date.today(),
        "edit_balance": edit_balance,
    }
    return render(request, "core/clients/balance.html", context)


