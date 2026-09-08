import csv
import tempfile
import unittest
from pathlib import Path

from balance_log import FIELDS, append_world_balance_log


class BalanceLogTests(unittest.TestCase):
    def test_append_world_log_writes_header_once_and_keeps_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world_dps.csv"
            first = {field: f"first-{field}" for field in FIELDS}
            second = {field: f"second-{field}" for field in FIELDS}
            append_world_balance_log(first, path)
            append_world_balance_log(second, path)

            with path.open("r", encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["run_id"], "first-run_id")
            self.assertEqual(rows[1]["run_id"], "second-run_id")


if __name__ == "__main__":
    unittest.main()
