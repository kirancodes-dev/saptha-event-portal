"""
services_finance.py — Universal Financial Management & Multi-Currency Engine

Features:
1. Multi-Currency Engine:
   - Supported: INR (₹), USD ($), EUR (€), GBP (£), AED (AED), SGD (S$), CAD (C$), AUD (A$).
   - Dynamic exchange conversion and localized currency formatting.
2. Checkout & Pricing Calculator:
   - Base tier price * quantity.
   - Dynamic early-bird & surge pricing adjustment.
   - Promotional coupon redemption with validation (percentage, fixed amount, min spend, max discount cap).
   - Tax engine: GST (18% with 9% CGST + 9% SGST breakdown) / VAT / configurable tax percentage.
   - Gateway convenience fee calculation.
3. Invoicing & Ledger:
   - Anti-counterfeit invoice reference generation (INV-YYYY-XXXXXXXX).
   - Itemized line items and tax breakdown.
   - Payout calculations and refund management.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "AED ",
    "SGD": "S$",
    "CAD": "C$",
    "AUD": "A$",
}

# Baseline exchange rates pegged to USD
DEFAULT_EXCHANGE_RATES_TO_USD = {
    "USD": 1.0,
    "INR": 86.5,
    "EUR": 0.92,
    "GBP": 0.78,
    "AED": 3.67,
    "SGD": 1.34,
    "CAD": 1.38,
    "AUD": 1.52,
}


class FinanceEngine:
    """
    Universal financial, multi-currency, tax, and invoicing calculation service.
    """

    @staticmethod
    def format_currency(amount: float, currency: str = "INR") -> str:
        """Format an amount with its currency symbol and 2 decimal places."""
        curr = currency.upper().strip()
        symbol = CURRENCY_SYMBOLS.get(curr, f"{curr} ")
        return f"{symbol}{amount:,.2f}"

    @classmethod
    def convert_currency(
        cls,
        amount: float,
        from_currency: str,
        to_currency: str,
        custom_rates: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Convert an amount between currencies using triangulated exchange rates.
        """
        from_curr = from_currency.upper().strip()
        to_curr = to_currency.upper().strip()

        if from_curr == to_curr:
            return round(amount, 2)

        rates = custom_rates or DEFAULT_EXCHANGE_RATES_TO_USD
        rate_from = rates.get(from_curr, 1.0)
        rate_to = rates.get(to_curr, 1.0)

        # Convert to base USD then to target currency
        # rate is units of currency per 1 USD
        usd_amount = amount / rate_from if rate_from > 0 else amount
        target_amount = usd_amount * rate_to
        return round(target_amount, 2)

    @classmethod
    def calculate_checkout(
        cls,
        *,
        unit_price: float,
        quantity: int = 1,
        currency: str = "INR",
        coupon_data: Optional[Dict[str, Any]] = None,
        tax_percentage: float = 18.0,
        convenience_fee_percentage: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Compute total payable breakdown including discounts, tax, and fees.
        """
        qty = max(1, int(quantity))
        subtotal = round(float(unit_price) * qty, 2)
        discount_amount = 0.0
        coupon_code = None

        if coupon_data:
            coupon_code = coupon_data.get("code")
            discount_type = coupon_data.get("type", "percentage")  # percentage | fixed
            discount_value = float(coupon_data.get("value", 0))
            min_spend = float(coupon_data.get("min_spend", 0))
            max_discount = float(coupon_data.get("max_discount", 999999))

            if subtotal >= min_spend:
                if discount_type == "percentage":
                    raw_discount = (subtotal * discount_value) / 100.0
                    discount_amount = round(min(raw_discount, max_discount), 2)
                elif discount_type == "fixed":
                    discount_amount = round(min(discount_value, subtotal), 2)

        taxable_amount = max(0.0, round(subtotal - discount_amount, 2))

        # Tax calculation
        tax_amount = round((taxable_amount * tax_percentage) / 100.0, 2) if tax_percentage > 0 else 0.0

        # Tax breakdown (CGST / SGST split for Indian GST)
        tax_breakdown = {}
        if currency.upper() == "INR" and tax_percentage > 0:
            half_tax = round(tax_amount / 2.0, 2)
            tax_breakdown["cgst"] = half_tax
            tax_breakdown["sgst"] = half_tax
            tax_breakdown["rate"] = tax_percentage
        else:
            tax_breakdown["tax"] = tax_amount
            tax_breakdown["rate"] = tax_percentage

        # Convenience fee
        fee_amount = round((taxable_amount * convenience_fee_percentage) / 100.0, 2) if convenience_fee_percentage > 0 else 0.0

        total_payable = round(taxable_amount + tax_amount + fee_amount, 2)

        return {
            "currency": currency.upper(),
            "quantity": qty,
            "unit_price": unit_price,
            "subtotal": subtotal,
            "discount_amount": discount_amount,
            "coupon_applied": coupon_code if discount_amount > 0 else None,
            "taxable_amount": taxable_amount,
            "tax_amount": tax_amount,
            "tax_percentage": tax_percentage,
            "tax_breakdown": tax_breakdown,
            "convenience_fee": fee_amount,
            "total_payable": total_payable,
            "formatted_total": cls.format_currency(total_payable, currency),
        }

    @classmethod
    def generate_invoice(
        cls,
        *,
        order_id: str,
        event_title: str,
        buyer_name: str,
        buyer_email: str,
        checkout_breakdown: Dict[str, Any],
        organization_name: str = "SapthaEvent Global",
        seller_gstin: Optional[str] = "29AABCS1429B1Z8",
    ) -> Dict[str, Any]:
        """
        Generate structured itemized invoice data.
        """
        now = datetime.now(timezone.utc)
        inv_num = f"INV-{now.year}-{uuid.uuid4().hex[:8].upper()}"

        return {
            "invoice_number": inv_num,
            "order_id": order_id,
            "invoice_date": now.isoformat(),
            "organization_name": organization_name,
            "seller_gstin": seller_gstin,
            "event_title": event_title,
            "buyer": {
                "name": buyer_name,
                "email": buyer_email,
            },
            "financials": checkout_breakdown,
            "status": "paid",
        }

    @classmethod
    def record_transaction(
        cls,
        db,
        *,
        transaction_id: str,
        order_id: str,
        event_id: str,
        amount: float,
        currency: str,
        buyer_email: str,
        gateway: str = "razorpay",
        payment_method: str = "upi",
        status: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Persist financial transaction record into the ledger.
        """
        now_str = _utcnow_iso()
        record = {
            "id": transaction_id,
            "transaction_id": transaction_id,
            "order_id": order_id,
            "event_id": event_id,
            "amount": amount,
            "currency": currency.upper(),
            "buyer_email": buyer_email.strip().lower(),
            "gateway": gateway,
            "payment_method": payment_method,
            "status": status,
            "metadata": metadata or {},
            "created_at": now_str,
            "updated_at": now_str,
        }
        db.collection("financial_transactions").document(transaction_id).set(record)
        return record

    @classmethod
    def calculate_event_payout_summary(cls, db, event_id: str) -> Dict[str, Any]:
        """
        Aggregate revenue, fees, and net payout for an event from transactions.
        """
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
        except ImportError:
            FieldFilter = None

        if FieldFilter:
            docs = db.collection("financial_transactions").where(filter=FieldFilter("event_id", "==", event_id)).stream()
        else:
            docs = db.collection("financial_transactions").where("event_id", "==", event_id).stream()

        gross_revenue = 0.0
        refunded_amount = 0.0
        success_count = 0
        refund_count = 0
        currency = "INR"

        for d in docs:
            t = d.to_dict()
            amt = float(t.get("amount", 0.0))
            currency = t.get("currency", "INR")
            stat = t.get("status", "")

            if stat == "success":
                gross_revenue += amt
                success_count += 1
            elif stat == "refunded":
                refunded_amount += amt
                refund_count += 1

        # Platform take rate: e.g. 3% platform fee
        platform_fee = round((gross_revenue * 0.03), 2)
        net_payout = round(gross_revenue - refunded_amount - platform_fee, 2)

        return {
            "event_id": event_id,
            "currency": currency,
            "transactions_count": success_count,
            "refunds_count": refund_count,
            "gross_revenue": round(gross_revenue, 2),
            "refunded_amount": round(refunded_amount, 2),
            "platform_fee": platform_fee,
            "net_payout": max(0.0, net_payout),
            "formatted_gross": cls.format_currency(gross_revenue, currency),
            "formatted_net": cls.format_currency(max(0.0, net_payout), currency),
        }
