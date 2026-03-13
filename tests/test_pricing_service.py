import unittest

from src.models import CartItem
from src.pricing import PricingService, PricingError


class TestPricingService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PricingService()

    def test_subtotal_single_item(self):
        items = [CartItem(sku="ABC", unit_price_cents=1000, qty=2)]
        self.assertEqual(self.service.subtotal_cents(items), 2000)

    def test_subtotal_multiple_items(self):
        items = [
            CartItem(sku="A", unit_price_cents=100, qty=1),
            CartItem(sku="B", unit_price_cents=250, qty=3),
        ]
        self.assertEqual(self.service.subtotal_cents(items), 850)

    def test_subtotal_empty_cart_returns_zero(self):
        self.assertEqual(self.service.subtotal_cents([]), 0)

    def test_subtotal_raises_on_non_positive_qty(self):
        items = [CartItem(sku="A", unit_price_cents=100, qty=0)]
        with self.assertRaises(PricingError) as ctx:
            self.service.subtotal_cents(items)
        self.assertIn("qty must be > 0", str(ctx.exception))

        items = [CartItem(sku="A", unit_price_cents=100, qty=-1)]
        with self.assertRaises(PricingError):
            self.service.subtotal_cents(items)

    def test_subtotal_raises_on_negative_unit_price(self):
        items = [CartItem(sku="A", unit_price_cents=-1, qty=1)]
        with self.assertRaises(PricingError) as ctx:
            self.service.subtotal_cents(items)
        self.assertIn("unit_price_cents must be >= 0", str(ctx.exception))

    def test_apply_coupon_none_or_empty_or_spaces_no_discount(self):
        self.assertEqual(self.service.apply_coupon(10000, None), 10000)
        self.assertEqual(self.service.apply_coupon(10000, ""), 10000)
        self.assertEqual(self.service.apply_coupon(10000, "   "), 10000)

    def test_apply_coupon_save10_percentage_discount_rounds_down(self):
        self.assertEqual(self.service.apply_coupon(105, "save10"), 95)
        self.assertEqual(self.service.apply_coupon(1000, "  SAVE10  "), 900)

    def test_apply_coupon_clp2000_fixed_discount_not_below_zero(self):
        self.assertEqual(self.service.apply_coupon(5000, "clp2000"), 3000)
        self.assertEqual(self.service.apply_coupon(1500, "CLP2000"), 0)

    def test_apply_coupon_invalid_raises_pricing_error(self):
        with self.assertRaises(PricingError) as ctx:
            self.service.apply_coupon(1000, "UNKNOWN")
        self.assertIn("invalid coupon", str(ctx.exception))


    def test_tax_cents_supported_countries(self):
        self.assertEqual(self.service.tax_cents(10000, "cl"), 1900)
        self.assertEqual(self.service.tax_cents(10000, "  EU  "), 2100)
        self.assertEqual(self.service.tax_cents(10000, "US"), 0)

    def test_tax_cents_unsupported_country_raises(self):
        with self.assertRaises(PricingError) as ctx:
            self.service.tax_cents(10000, "AR")
        self.assertIn("unsupported country", str(ctx.exception))


    def test_shipping_cl_free_over_threshold_else_fixed(self):
        self.assertEqual(self.service.shipping_cents(19999, "cl"), 2500)
        self.assertEqual(self.service.shipping_cents(20000, "CL"), 0)
        self.assertEqual(self.service.shipping_cents(30000, "  cl "), 0)

    def test_shipping_us_eu_fixed(self):
        self.assertEqual(self.service.shipping_cents(100, "US"), 5000)
        self.assertEqual(self.service.shipping_cents(999999, "eu"), 5000)

    def test_shipping_unsupported_country_raises(self):
        with self.assertRaises(PricingError) as ctx:
            self.service.shipping_cents(10000, "BR")
        self.assertIn("unsupported country", str(ctx.exception))


    def test_total_cents_integration_with_coupon_and_taxes_and_shipping(self):
        items = [CartItem(sku="ABC", unit_price_cents=1000, qty=2)]
        total = self.service.total_cents(items, "SAVE10", "CL")
        self.assertEqual(total, 4642)

    def test_total_cents_without_coupon_uses_all_components(self):
        items = [CartItem(sku="X", unit_price_cents=5000, qty=1)]
        self.assertEqual(self.service.total_cents(items, None, "US"), 10000)
