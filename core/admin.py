"""
Django admin configuration
"""
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from .models import Client, Exchange, ClientExchangeAccount, ClientExchangeReportConfig, Transaction, Settlement


class ClientExchangeReportConfigInline(admin.StackedInline):
    """Inline admin for report config"""
    model = ClientExchangeReportConfig
    extra = 0
    fields = ('friend_percentage', 'my_own_percentage')
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        
        class ReportConfigForm(formset.form):
            def clean(self):
                cleaned_data = super().clean()
                if self.instance and self.instance.client_exchange:
                    friend_pct = cleaned_data.get('friend_percentage', 0)
                    my_own_pct = cleaned_data.get('my_own_percentage', 0)
                    my_total = self.instance.client_exchange.my_percentage
                    
                    if friend_pct + my_own_pct != my_total:
                        raise ValidationError(
                            f"Friend % ({friend_pct}) + My Own % ({my_own_pct}) "
                            f"must equal My Total % ({my_total})"
                        )
                return cleaned_data
        
        formset.form = ReportConfigForm
        return formset


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'referred_by', 'is_company_client', 'created_at']
    list_filter = ['is_company_client', 'created_at']
    search_fields = ['name', 'code', 'referred_by']


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'created_at']
    search_fields = ['name', 'code']


@admin.register(ClientExchangeAccount)
class ClientExchangeAccountAdmin(admin.ModelAdmin):
    list_display = ['client', 'exchange', 'funding', 'exchange_balance', 'loss_share_percentage', 'profit_share_percentage', 'computed_pnl', 'computed_share']
    list_filter = ['exchange', 'created_at']
    search_fields = ['client__name', 'exchange__name']
    readonly_fields = ['computed_pnl', 'computed_share', 'settlement_status_derived', 'remaining_settlement', 'created_at', 'updated_at']
    inlines = [ClientExchangeReportConfigInline]
    
    fieldsets = (
        ('Account Information', {
            'fields': ('client', 'exchange', 'my_percentage', 'loss_share_percentage', 'profit_share_percentage')
        }),
        ('Money Values (BIGINT)', {
            'fields': ('funding', 'exchange_balance'),
            'description': 'ONLY real money values stored here. All other values are DERIVED.'
        }),
        ('Computed Values (Read-Only)', {
            'fields': ('computed_pnl', 'computed_share', 'remaining_settlement', 'settlement_status_derived'),
            'description': 'These values are computed from funding and exchange_balance, never stored. Settlement status: PnL = 0 → Trading flat, Remaining = 0 → Settlement complete.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def computed_pnl(self, obj):
        """Display computed Client PnL"""
        pnl = obj.compute_client_pnl()
        if pnl == 0:
            return "N.A"
        color = "green" if pnl > 0 else "red"
        return f'<span style="color: {color};">{pnl:,}</span>'
    computed_pnl.short_description = "Client PnL (Computed)"
    computed_pnl.allow_tags = True
    
    def computed_share(self, obj):
        """Display computed My Share"""
        pnl = obj.compute_client_pnl()
        if pnl == 0:
            return "N.A"
        share = obj.compute_my_share()
        return f'{share:,}'
    computed_share.short_description = "My Share (Computed)"
    
    def remaining_settlement(self, obj):
        """Display remaining settlement amount"""
        remaining = obj.get_remaining_settlement_amount()
        final_share = obj.compute_my_share()
        if final_share == 0:
            return "N.A (Zero Share)"
        return f'{remaining:,} / {final_share:,}'
    remaining_settlement.short_description = "Remaining Settlement"
    
    def settlement_status_derived(self, obj):
        """
        DERIVED settlement status (NOT stored)
        
        Rule: if Client_PnL == 0 → Trading flat (PnL zero from trading/settlement)
        Rule: if Remaining = 0 → Settlement complete (all share paid)
              else → Action required
        """
        pnl = obj.compute_client_pnl()
        if pnl == 0:
            return '<span style="color: green; font-weight: bold;">✓ Trading Flat (PnL = 0)</span>'
        else:
            return '<span style="color: orange; font-weight: bold;">⚠ Action Required</span>'
    settlement_status_derived.short_description = "Settlement Status (Derived)"
    settlement_status_derived.help_text = "Derived from Client_PnL. NOT stored in database."
    settlement_status_derived.allow_tags = True


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ['date', 'client_exchange', 'amount', 'notes']
    list_filter = ['date']
    search_fields = ['client_exchange__client__name', 'client_exchange__exchange__name', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'


@admin.register(ClientExchangeReportConfig)
class ClientExchangeReportConfigAdmin(admin.ModelAdmin):
    list_display = ['client_exchange', 'friend_percentage', 'my_own_percentage', 'computed_friend_share', 'computed_my_own_share']
    readonly_fields = ['computed_friend_share', 'computed_my_own_share', 'created_at', 'updated_at']
    
    def computed_friend_share(self, obj):
        """Display computed friend share (report only)"""
        pnl = obj.client_exchange.compute_client_pnl()
        if pnl == 0:
            return "N.A"
        return f'{obj.compute_friend_share():,}'
    computed_friend_share.short_description = "Friend Share (Report)"
    
    def computed_my_own_share(self, obj):
        """Display computed my own share (report only)"""
        pnl = obj.client_exchange.compute_client_pnl()
        if pnl == 0:
            return "N.A"
        return f'{obj.compute_my_own_share():,}'
    computed_my_own_share.short_description = "My Own Share (Report)"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'client_exchange', 'type', 'amount', 'exchange_balance_after']
    list_filter = ['type', 'date']
    search_fields = ['client_exchange__client__name', 'client_exchange__exchange__name', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'
