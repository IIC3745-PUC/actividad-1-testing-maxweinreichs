import unittest
from unittest.mock import Mock, patch

from src.models import CartItem
from src.pricing import PricingService, PricingError
from src.checkout import CheckoutService, ChargeResult


class TestCheckoutService(unittest.TestCase):
    def setUp(self) -> None:
        self.payments = Mock()
        self.email = Mock()
        self.fraud = Mock()
        self.repo = Mock()

    def _make_service_with_real_pricing(self) -> CheckoutService:
        return CheckoutService(
            payments=self.payments,
            email=self.email,
            fraud=self.fraud,
            repo=self.repo,
        )

    def _make_service_with_mock_pricing(self) -> tuple[CheckoutService, Mock]:
        pricing = Mock(spec=PricingService)
        service = CheckoutService(
            payments=self.payments,
            email=self.email,
            fraud=self.fraud,
            repo=self.repo,
            pricing=pricing,
        )
        return service, pricing

    def test_checkout_invalid_user_returns_invalid_user(self):
        service = self._make_service_with_real_pricing()
        items = [CartItem("A", 1000, 1)]

        result = service.checkout(user_id="   ", items=items, payment_token="tok", country="CL")

        self.assertEqual(result, "INVALID_USER")
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_pricing_error_returns_invalid_cart(self):
        service, pricing = self._make_service_with_mock_pricing()
        pricing.total_cents.side_effect = PricingError("bad cart")
        items = [CartItem("A", 1000, 1)]

        result = service.checkout(user_id="user1", items=items, payment_token="tok", country="CL")

        self.assertEqual(result, "INVALID_CART:bad cart")
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_rejected_by_fraud(self):
        service, pricing = self._make_service_with_mock_pricing()
        pricing.total_cents.return_value = 10000
        self.fraud.score.return_value = 80
        items = [CartItem("A", 1000, 1)]

        result = service.checkout(user_id="user1", items=items, payment_token="tok", country="CL")

        self.assertEqual(result, "REJECTED_FRAUD")
        self.fraud.score.assert_called_once_with("user1", 10000)
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_payment_failure_returns_error(self):
        service, pricing = self._make_service_with_mock_pricing()
        pricing.total_cents.return_value = 5000
        self.fraud.score.return_value = 10 
        self.payments.charge.return_value = ChargeResult(ok=False, reason="DECLINED")

        items = [CartItem("A", 1000, 1)]

        result = service.checkout(user_id="user1", items=items, payment_token="tok", country="CL")

        self.assertEqual(result, "PAYMENT_FAILED:DECLINED")
        self.payments.charge.assert_called_once_with(
            user_id="user1", amount_cents=5000, payment_token="tok"
        )
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    @patch("src.checkout.uuid.uuid4", return_value="fixed-uuid")
    def test_checkout_success_flow_saves_order_and_sends_email(self, mock_uuid):
        service, pricing = self._make_service_with_mock_pricing()
        pricing.total_cents.return_value = 12345
        self.fraud.score.return_value = 0
        self.payments.charge.return_value = ChargeResult(ok=True, charge_id="charge-123")

        items = [CartItem("SKU1", 1000, 1)]

        result = service.checkout(
            user_id="u1",
            items=items,
            payment_token="tok",
            country=" cl ",
            coupon_code="SAVE10",
        )

        self.assertEqual(result, "OK:fixed-uuid")
        mock_uuid.assert_called_once()

        self.payments.charge.assert_called_once_with(
            user_id="u1", amount_cents=12345, payment_token="tok"
        )

        self.repo.save.assert_called_once()
        saved_order = self.repo.save.call_args.args[0]
        self.assertEqual(saved_order.order_id, "fixed-uuid")
        self.assertEqual(saved_order.user_id, "u1")
        self.assertEqual(saved_order.total_cents, 12345)
        self.assertEqual(saved_order.payment_charge_id, "charge-123")
        self.assertEqual(saved_order.coupon_code, "SAVE10")
        self.assertEqual(saved_order.country, "CL")

        self.email.send_receipt.assert_called_once_with("u1", "fixed-uuid", 12345)

    @patch("src.checkout.uuid.uuid4", return_value="fixed-uuid")
    def test_checkout_success_with_missing_charge_id_uses_unknown(self, mock_uuid):
        service, pricing = self._make_service_with_mock_pricing()
        pricing.total_cents.return_value = 2000
        self.fraud.score.return_value = 0
        self.payments.charge.return_value = ChargeResult(ok=True, charge_id=None)

        items = [CartItem("SKU1", 2000, 1)]

        result = service.checkout(
            user_id="u2",
            items=items,
            payment_token="tok",
            country="US",
        )

        self.assertEqual(result, "OK:fixed-uuid")
        self.repo.save.assert_called_once()
        saved_order = self.repo.save.call_args.args[0]
        self.assertEqual(saved_order.payment_charge_id, "UNKNOWN")

    def test_charge_result_simple_attributes(self):
        r = ChargeResult(ok=True, charge_id="id-1", reason=None)
        self.assertTrue(r.ok)
        self.assertEqual(r.charge_id, "id-1")
        self.assertIsNone(r.reason)
