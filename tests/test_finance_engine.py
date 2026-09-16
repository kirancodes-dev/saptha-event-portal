"""
tests/test_finance_engine.py — Unit & Integration Tests for Phase 8

Verifies:
1. Multi-currency conversion across supported pairs (INR, USD, EUR, GBP).
2. Localized currency formatting.
3. Itemized checkout calculations (discounts, GST/VAT, convenience fee).
4. Invoice record generation.
5. Transaction ledger persistence and payout summary aggregation.
6. REST API v1 endpoints for checkout preview, currency conversion, and event payout summary.
"""

import pytest
import uuid
from auth_jwt import create_tokens
from services_finance import FinanceEngine


@pytest.fixture
def admin_token():
    tokens = create_tokens(user_email="admin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


class TestCurrencyConversionAndFormatting:
    """Verify multi-currency arithmetic and formatting."""

    def test_format_currency(self):
        assert FinanceEngine.format_currency(1500, "INR") == "₹1,500.00"
        assert FinanceEngine.format_currency(49.99, "USD") == "$49.99"
        assert FinanceEngine.format_currency(120.50, "EUR") == "€120.50"
        assert FinanceEngine.format_currency(75, "GBP") == "£75.00"

    def test_convert_currency(self):
        # 100 USD to INR @ 86.5 = 8650.0
        inr_val = FinanceEngine.convert_currency(100.0, "USD", "INR")
        assert inr_val == 8650.0

        # Same currency conversion
        same_val = FinanceEngine.convert_currency(500.0, "INR", "INR")
        assert same_val == 500.0


class TestCheckoutPricingCalculator:
    """Verify itemized calculations, coupon discounts, and tax engine."""

    def test_standard_checkout_with_gst(self):
        # 2 tickets @ 1000 each = 2000 subtotal
        # GST 18% = 360 (CGST 180, SGST 180)
        # Convenience fee 2% = 40
        # Total = 2400
        res = FinanceEngine.calculate_checkout(
            unit_price=1000.0,
            quantity=2,
            currency="INR",
            tax_percentage=18.0,
            convenience_fee_percentage=2.0,
        )
        assert res["subtotal"] == 2000.0
        assert res["tax_amount"] == 360.0
        assert res["tax_breakdown"]["cgst"] == 180.0
        assert res["tax_breakdown"]["sgst"] == 180.0
        assert res["convenience_fee"] == 40.0
        assert res["total_payable"] == 2400.0
        assert "₹2,400.00" in res["formatted_total"]

    def test_checkout_with_percentage_coupon(self):
        # Unit price = 1000, qty = 1
        # Coupon 20% off with max discount 150
        # Subtotal = 1000, raw discount = 200, capped discount = 150
        # Taxable = 850
        # Tax 10% = 85, Fee 0% = 0
        # Total = 935
        coupon = {"code": "SAVE20", "type": "percentage", "value": 20, "max_discount": 150}
        res = FinanceEngine.calculate_checkout(
            unit_price=1000.0,
            quantity=1,
            coupon_data=coupon,
            tax_percentage=10.0,
            convenience_fee_percentage=0.0,
        )
        assert res["discount_amount"] == 150.0
        assert res["taxable_amount"] == 850.0
        assert res["tax_amount"] == 85.0
        assert res["total_payable"] == 935.0
        assert res["coupon_applied"] == "SAVE20"

    def test_invoice_generation(self):
        checkout = FinanceEngine.calculate_checkout(unit_price=500, quantity=1)
        invoice = FinanceEngine.generate_invoice(
            order_id="ord_12345",
            event_title="Hackathon Pro",
            buyer_name="Aditi Sharma",
            buyer_email="aditi@saptha.org",
            checkout_breakdown=checkout,
        )
        assert invoice["invoice_number"].startswith("INV-")
        assert invoice["status"] == "paid"
        assert invoice["buyer"]["name"] == "Aditi Sharma"


class TestLedgerAndPayoutSummary:
    """Verify transaction recording and organizer payout calculations."""

    def test_record_transactions_and_calculate_payout(self, mock_db):
        event_id = f"ev_fin_{uuid.uuid4().hex[:6]}"

        # 1. Record 2 successful ticket payments: 2000 + 3000 = 5000
        FinanceEngine.record_transaction(
            mock_db,
            transaction_id="tx_1",
            order_id="ord_1",
            event_id=event_id,
            amount=2000.0,
            currency="INR",
            buyer_email="user1@saptha.org",
            status="success",
        )
        FinanceEngine.record_transaction(
            mock_db,
            transaction_id="tx_2",
            order_id="ord_2",
            event_id=event_id,
            amount=3000.0,
            currency="INR",
            buyer_email="user2@saptha.org",
            status="success",
        )

        # 2. Record 1 refund: 500
        FinanceEngine.record_transaction(
            mock_db,
            transaction_id="tx_3",
            order_id="ord_3",
            event_id=event_id,
            amount=500.0,
            currency="INR",
            buyer_email="user3@saptha.org",
            status="refunded",
        )

        summary = FinanceEngine.calculate_event_payout_summary(mock_db, event_id)
        assert summary["gross_revenue"] == 5000.0
        assert summary["refunded_amount"] == 500.0
        # Platform fee 3% of 5000 = 150.0
        assert summary["platform_fee"] == 150.0
        # Net payout = 5000 - 500 - 150 = 4350.0
        assert summary["net_payout"] == 4350.0
        assert summary["transactions_count"] == 2
        assert summary["refunds_count"] == 1


class TestFinancialAPIEndpoints:
    """Verify REST API v1 endpoints for Phase 8."""

    def test_checkout_preview_api(self, client):
        resp = client.post(
            "/api/v1/finance/checkout-preview",
            json={
                "unit_price": 500.0,
                "quantity": 2,
                "currency": "INR",
                "tax_percentage": 18.0,
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["subtotal"] == 1000.0
        assert data["tax_amount"] == 180.0
        assert data["total_payable"] == 1200.0  # 1000 + 180 tax + 20 fee

    def test_currency_convert_api(self, client):
        resp = client.post(
            "/api/v1/finance/convert",
            json={
                "amount": 100.0,
                "from_currency": "USD",
                "to_currency": "EUR",
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["from_currency"] == "USD"
        assert data["to_currency"] == "EUR"
        assert data["converted_amount"] == 92.0

    def test_payout_summary_api(self, client, admin_token, mock_db):
        event_id = f"ev_payout_api_{uuid.uuid4().hex[:6]}"
        FinanceEngine.record_transaction(
            mock_db,
            transaction_id="tx_api_1",
            order_id="ord_api_1",
            event_id=event_id,
            amount=1000.0,
            currency="INR",
            buyer_email="buyer@saptha.org",
            status="success",
        )

        resp = client.get(
            f"/api/v1/events/{event_id}/payout-summary",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["gross_revenue"] == 1000.0
        assert data["platform_fee"] == 30.0
        assert data["net_payout"] == 970.0
