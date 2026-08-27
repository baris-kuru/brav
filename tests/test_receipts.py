import unittest

from backend.receipts import PageText, heuristic_receipt, normalize_text, pages_to_windows


class ReceiptTests(unittest.TestCase):
  def test_normalize_text_compacts_spacing(self) -> None:
    result = normalize_text("Cafe\n\n\nLatte   4,50\r\nTotal   4,50")
    self.assertIn("Latte 4,50", result)
    self.assertNotIn("\n\n\n", result)

  def test_pages_to_windows_respects_page_boundaries(self) -> None:
    pages = [
      PageText(page_number=1, text="A" * 30),
      PageText(page_number=2, text="B" * 30),
    ]
    windows = pages_to_windows(pages, max_chars=50)
    self.assertEqual(len(windows), 2)
    self.assertEqual(windows[0][1], [1])
    self.assertEqual(windows[1][1], [2])

  def test_heuristic_receipt_extracts_total_and_date(self) -> None:
    text = "Coffee House\n15.04.2026 13:42\nLatte  4,50\nToplam 4,50"
    receipt = heuristic_receipt(text, [1])
    self.assertEqual(receipt.merchant_name, "Coffee House")
    self.assertEqual(receipt.business_date, "2026-04-15")
    self.assertEqual(receipt.total, 4.50)


if __name__ == "__main__":
  unittest.main()
