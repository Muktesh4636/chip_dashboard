from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base to track created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    """Represents an end client that receives funds via different exchanges."""

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        if self.code:
            return f"{self.name} ({self.code})"
        return self.name


class Exchange(TimeStampedModel):
    """
    Standalone exchange (A, B, C, D, etc.).
    Exchanges are created independently and then linked to clients with specific percentages.
    """

    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Optional exchange code")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ClientExchange(TimeStampedModel):
    """
    Links a Client to an Exchange with specific my share and company share percentages.
    This allows the same exchange to have different percentages for different clients.
    """

    client = models.ForeignKey(Client, related_name="client_exchanges", on_delete=models.CASCADE)
    exchange = models.ForeignKey(Exchange, related_name="client_exchanges", on_delete=models.CASCADE)

    my_share_pct = models.DecimalField(max_digits=5, decimal_places=2, help_text="Your share of profits (%)")
    company_share_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Company share from your profit (%) - must be less than your share",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("client", "exchange")
        ordering = ["client__name", "exchange__name"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.company_share_pct >= self.my_share_pct:
            raise ValidationError("Company share must be less than your share")

    def __str__(self) -> str:
        return f"{self.client.name} - {self.exchange.name}"


class Transaction(TimeStampedModel):
    """
    Atomic financial activity per client per exchange.

    This is the core source-of-truth used for:
    - Daily P&L
    - Pending payments (client owes you / you owe client)
    - Time‑travel reporting (snapshots are derived by date filtering)
    """

    TYPE_FUNDING = "FUNDING"
    TYPE_PROFIT = "PROFIT"
    TYPE_LOSS = "LOSS"
    TYPE_SETTLEMENT = "SETTLEMENT"

    TRANSACTION_TYPES = [
        (TYPE_FUNDING, "Funding (You give money to client)"),
        (TYPE_PROFIT, "Profit"),
        (TYPE_LOSS, "Loss"),
        (TYPE_SETTLEMENT, "Settlement / Payout"),
    ]

    client_exchange = models.ForeignKey("ClientExchange", related_name="transactions", on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)

    # Positive values; semantic meaning comes from transaction_type
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    # Computed shares at the time of transaction (denormalized for snapshot consistency)
    client_share_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    your_share_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    company_share_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.client_exchange} {self.transaction_type} {self.amount} on {self.date}"
    
    @property
    def exchange(self):
        """Backward compatibility property."""
        return self.client_exchange.exchange
    
    @property
    def client(self):
        """Backward compatibility property."""
        return self.client_exchange.client


class DailyBalanceSnapshot(TimeStampedModel):
    """
    Per client + exchange daily balance snapshot.

    This enables fast time‑travel reporting by date without recomputing
    aggregates across the full history every time.
    """

    client_exchange = models.ForeignKey("ClientExchange", related_name="daily_snapshots", on_delete=models.CASCADE)
    
    @property
    def client(self):
        return self.client_exchange.client
    
    @property
    def exchange(self):
        return self.client_exchange.exchange
    date = models.DateField()

    # Cumulative fields up to and including `date`
    total_funding = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    client_net_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    you_net_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    company_net_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    pending_client_owes_you = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pending_you_owe_client = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = ("client_exchange", "date")
        ordering = ["-date"]

    def __str__(self) -> str:
        code_part = f"{self.client_exchange.client.code} " if self.client_exchange.client.code else ""
        return f"Snapshot {code_part}{self.client_exchange.exchange.name} on {self.date}"


class CompanyShareRecord(TimeStampedModel):
    """
    Denormalized record of company share amounts for transparency and reporting.
    """

    client_exchange = models.ForeignKey("ClientExchange", related_name="company_shares", on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, related_name="company_shares", on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)

    company_amount = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.client_exchange} company share {self.company_amount} on {self.date}"


class ClientDailyBalance(TimeStampedModel):
    """
    Manual daily balance record for clients.
    Records the remaining balance in client's account for a specific date.
    """
    client = models.ForeignKey(Client, related_name="daily_balances", on_delete=models.CASCADE)
    date = models.DateField()
    remaining_balance = models.DecimalField(max_digits=14, decimal_places=2, help_text="Remaining balance in client's account")
    note = models.TextField(blank=True, help_text="Optional note about the balance")
    
    class Meta:
        unique_together = ("client", "date")
        ordering = ["-date"]
        verbose_name_plural = "Client Daily Balances"
    
    def __str__(self):
        return f"{self.client.name} - ₹{self.remaining_balance} on {self.date}"


class SystemSettings(models.Model):
    """
    System-wide settings for the broker portal.
    Singleton pattern - only one settings record should exist.
    """
    
    weekly_report_day = models.IntegerField(
        default=0,
        help_text="Day of week for auto weekly reports (0=Monday, 6=Sunday)",
        choices=[(0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"), (4, "Friday"), (5, "Saturday"), (6, "Sunday")]
    )
    auto_generate_weekly_reports = models.BooleanField(default=False, help_text="Automatically generate weekly reports")
    
    class Meta:
        verbose_name_plural = "System Settings"
    
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
    
    def __str__(self) -> str:
        return "System Settings"

