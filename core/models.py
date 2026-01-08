"""
Database models for Profit-Loss-Share-Settlement System
Following PIN-TO-PIN master document specifications.
"""
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class TimeStampedModel(models.Model):
    """Abstract base to track created/updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    """
    Client entity - trades on exchange, receives FULL profit, pays FULL loss.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    referred_by = models.CharField(max_length=200, blank=True, null=True)
    is_company_client = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Exchange(TimeStampedModel):
    """
    Exchange entity - trading platform.
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class ClientExchangeAccount(TimeStampedModel):
    """
    CORE SYSTEM TABLE - LOGIC SAFE
    
    Stores ONLY real money values:
    - funding: Total real money given to client
    - exchange_balance: Current balance on exchange
    
    All other values (profit, loss, shares) are DERIVED, never stored.
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='exchange_accounts')
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='client_accounts')
    
    # ONLY TWO MONEY VALUES STORED (BIGINT as per spec)
    funding = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    exchange_balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    
    # Partner percentage (INT as per spec)
    my_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Your total percentage share (0-100)"
    )
    
    class Meta:
        unique_together = [['client', 'exchange']]
        ordering = ['client__name', 'exchange__name']
    
    def __str__(self):
        return f"{self.client.name} - {self.exchange.name}"
    
    def compute_client_pnl(self):
        """
        MASTER PROFIT/LOSS FORMULA
        Client_PnL = exchange_balance - funding
        
        Returns: BIGINT (can be negative for loss)
        """
        return self.exchange_balance - self.funding
    
    def compute_my_share(self):
        """
        PARTNER SHARE FORMULA
        My_Share = ABS(Client_PnL) × my_percentage / 100
        
        Returns: BIGINT (always positive, integer division)
        """
        client_pnl = abs(self.compute_client_pnl())
        return (client_pnl * self.my_percentage) // 100
    
    def is_settled(self):
        """Check if client is fully settled (PnL = 0)"""
        return self.compute_client_pnl() == 0


class ClientExchangeReportConfig(TimeStampedModel):
    """
    REPORT CONFIG TABLE - ISOLATED
    
    Used ONLY for reports, NOT for system logic.
    Stores friend/student share percentages.
    """
    client_exchange = models.OneToOneField(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='report_config'
    )
    
    # Report-only percentages (INT as per spec)
    friend_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Friend/Student percentage (report only)"
    )
    my_own_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Your own percentage (report only)"
    )
    
    class Meta:
        verbose_name = "Report Configuration"
        verbose_name_plural = "Report Configurations"
    
    def __str__(self):
        return f"Report Config: {self.client_exchange}"
    
    def clean(self):
        """Validation: friend_percentage + my_own_percentage = my_percentage"""
        from django.core.exceptions import ValidationError
        
        if self.client_exchange:
            my_total = self.client_exchange.my_percentage
            friend_plus_own = self.friend_percentage + self.my_own_percentage
            
            if friend_plus_own != my_total:
                raise ValidationError(
                    f"Friend % ({self.friend_percentage}) + My Own % ({self.my_own_percentage}) "
                    f"must equal My Total % ({my_total})"
                )
    
    def compute_friend_share(self):
        """
        Friend share formula (report only)
        Friend_Share = ABS(Client_PnL) × friend_percentage / 100
        """
        client_pnl = abs(self.client_exchange.compute_client_pnl())
        return (client_pnl * self.friend_percentage) // 100
    
    def compute_my_own_share(self):
        """
        My own share formula (report only)
        My_Own_Share = ABS(Client_PnL) × my_own_percentage / 100
        """
        client_pnl = abs(self.client_exchange.compute_client_pnl())
        return (client_pnl * self.my_own_percentage) // 100


class Transaction(TimeStampedModel):
    """
    TRANSACTIONS TABLE - AUDIT ONLY
    
    Stores transaction history for audit purposes.
    NEVER used to recompute balances.
    """
    TRANSACTION_TYPES = [
        ('FUNDING', 'Funding'),
        ('TRADE', 'Trade'),
        ('FEE', 'Fee'),
        ('ADJUSTMENT', 'Adjustment'),
        ('RECORD_PAYMENT', 'Record Payment'),
    ]
    
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    date = models.DateTimeField()
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.BigIntegerField(help_text="Amount in smallest currency unit")
    exchange_balance_after = models.BigIntegerField(
        help_text="Exchange balance after this transaction (for audit)"
    )
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date', '-id']
    
    def __str__(self):
        return f"{self.type} - {self.client_exchange} - {self.date.strftime('%Y-%m-%d')}"
