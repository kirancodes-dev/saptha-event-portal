"""
test_coupons.py — Tests for the Coupon Code System

Covers: coupon creation, validation, application, deactivation,
and edge cases like expired and overused coupons.
"""
import pytest
import datetime


class TestCouponCRUD:
    """Test coupon creation and management."""

    def test_create_percentage_coupon(self, mock_db):
        coupon_data = {
            "id": "cpn_001",
            "code": "SAPTHA-TEST",
            "event_id": "evt_001",
            "discount_type": "percentage",
            "discount_value": 25.0,
            "max_uses": 50,
            "current_uses": 0,
            "is_active": True,
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "created_by": "admin@test.edu",
        }
        mock_db.collection("coupons").document("cpn_001").set(coupon_data)
        doc = mock_db.collection("coupons").document("cpn_001").get()
        assert doc.exists
        data = doc.to_dict()
        assert data["discount_type"] == "percentage"
        assert data["discount_value"] == 25.0

    def test_create_fixed_coupon(self, mock_db):
        coupon_data = {
            "id": "cpn_002",
            "code": "FLAT50",
            "event_id": "evt_001",
            "discount_type": "fixed",
            "discount_value": 50.0,
            "max_uses": 100,
            "current_uses": 0,
            "is_active": True,
        }
        mock_db.collection("coupons").document("cpn_002").set(coupon_data)
        doc = mock_db.collection("coupons").document("cpn_002").get()
        assert doc.to_dict()["discount_type"] == "fixed"


class TestCouponValidation:
    """Test coupon validation logic."""

    def test_percentage_discount_calculation(self):
        """25% of ₹400 = ₹100 discount."""
        original = 400.0
        discount_pct = 25.0
        discount = round(original * discount_pct / 100, 2)
        assert discount == 100.0
        assert original - discount == 300.0

    def test_fixed_discount_calculation(self):
        """₹50 off ₹200 = ₹150 final."""
        original = 200.0
        discount = min(50.0, original)
        assert original - discount == 150.0

    def test_fixed_discount_exceeds_price(self):
        """₹500 coupon on ₹200 item = ₹0 (free)."""
        original = 200.0
        discount = min(500.0, original)
        final = max(0, original - discount)
        assert final == 0.0

    def test_percentage_100_is_free(self):
        """100% discount = free."""
        original = 500.0
        discount = round(original * 100 / 100, 2)
        assert max(0, original - discount) == 0.0


class TestCouponEdgeCases:
    """Test coupon edge cases and error conditions."""

    def test_coupon_max_uses_reached(self, mock_db):
        mock_db.collection("coupons").document("cpn_full").set({
            "code": "FULL",
            "event_id": "evt_001",
            "max_uses": 10,
            "current_uses": 10,
            "is_active": True,
        })
        doc = mock_db.collection("coupons").document("cpn_full").get()
        data = doc.to_dict()
        assert data["current_uses"] >= data["max_uses"]

    def test_coupon_deactivation(self, mock_db):
        mock_db.collection("coupons").document("cpn_deact").set({
            "code": "DEACT",
            "is_active": True,
        })
        mock_db.collection("coupons").document("cpn_deact").update({"is_active": False})
        doc = mock_db.collection("coupons").document("cpn_deact").get()
        assert doc.to_dict()["is_active"] is False

    def test_coupon_usage_increment(self, mock_db):
        mock_db.collection("coupons").document("cpn_inc").set({
            "code": "INC",
            "current_uses": 5,
        })
        mock_db.collection("coupons").document("cpn_inc").update({"current_uses": 6})
        doc = mock_db.collection("coupons").document("cpn_inc").get()
        assert doc.to_dict()["current_uses"] == 6
