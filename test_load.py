#!/usr/bin/env python3
"""
Automated tests for pypay load.py

Tests verify:
1. Single transaction is created per paycheck
2. Transaction balances to zero
3. All splits are included in the transaction
"""

import os
import sys
import tempfile
import piecash
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))
from load import process, create_gnucash_accounts
from load import AccountRegistry


def test_single_transaction_per_paycheck():
    """Test that exactly one transaction is created per paycheck"""
    with tempfile.NamedTemporaryFile(suffix='.gnucash', delete=False) as tmp:
        gnucash_file = tmp.name

    try:
        # Create GnuCash file with accounts
        create_gnucash_accounts(gnucash_file)

        # Load a test paycheck
        test_json = "data/2021/Statement for Jan 08, 2021.json"
        if not os.path.exists(test_json):
            print(f"SKIP: Test file {test_json} not found")
            return

        book = piecash.open_book(gnucash_file, readonly=False, do_backup=False, open_if_lock=True)
        registry = AccountRegistry()
        registry.load_from_book(book)

        process(test_json, book, registry)
        book.save()

        # Verify exactly one transaction
        transactions = list(book.transactions)
        assert len(transactions) == 1, f"Expected 1 transaction, got {len(transactions)}"

        print("✓ test_single_transaction_per_paycheck PASSED")
        book.close()

    finally:
        os.unlink(gnucash_file)


def test_transaction_balances():
    """Test that the transaction balances to zero"""
    with tempfile.NamedTemporaryFile(suffix='.gnucash', delete=False) as tmp:
        gnucash_file = tmp.name

    try:
        # Create GnuCash file with accounts
        create_gnucash_accounts(gnucash_file)

        # Load a test paycheck
        test_json = "data/2021/Statement for Jan 08, 2021.json"
        if not os.path.exists(test_json):
            print(f"SKIP: Test file {test_json} not found")
            return

        book = piecash.open_book(gnucash_file, readonly=False, do_backup=False, open_if_lock=True)
        registry = AccountRegistry()
        registry.load_from_book(book)

        process(test_json, book, registry)
        book.save()

        # Verify transaction balances
        transactions = list(book.transactions)
        for txn in transactions:
            total = sum(split.value for split in txn.splits)
            assert total == Decimal('0.00'), f"Transaction does not balance: {total}"

        print("✓ test_transaction_balances PASSED")
        book.close()

    finally:
        os.unlink(gnucash_file)


def test_transaction_has_description():
    """Test that the transaction has a description"""
    with tempfile.NamedTemporaryFile(suffix='.gnucash', delete=False) as tmp:
        gnucash_file = tmp.name

    try:
        # Create GnuCash file with accounts
        create_gnucash_accounts(gnucash_file)

        # Load a test paycheck
        test_json = "data/2021/Statement for Jan 08, 2021.json"
        if not os.path.exists(test_json):
            print(f"SKIP: Test file {test_json} not found")
            return

        book = piecash.open_book(gnucash_file, readonly=False, do_backup=False, open_if_lock=True)
        registry = AccountRegistry()
        registry.load_from_book(book)

        process(test_json, book, registry)
        book.save()

        # Verify transaction has description
        transactions = list(book.transactions)
        assert len(transactions) > 0, "No transactions found"
        assert transactions[0].description == "Paycheck", f"Expected description 'Paycheck', got '{transactions[0].description}'"

        print("✓ test_transaction_has_description PASSED")
        book.close()

    finally:
        os.unlink(gnucash_file)


def test_all_splits_included():
    """Test that all expected splits are included in the transaction"""
    with tempfile.NamedTemporaryFile(suffix='.gnucash', delete=False) as tmp:
        gnucash_file = tmp.name

    try:
        # Create GnuCash file with accounts
        create_gnucash_accounts(gnucash_file)

        # Load a test paycheck
        test_json = "data/2021/Statement for Jan 08, 2021.json"
        if not os.path.exists(test_json):
            print(f"SKIP: Test file {test_json} not found")
            return

        book = piecash.open_book(gnucash_file, readonly=False, do_backup=False, open_if_lock=True)
        registry = AccountRegistry()
        registry.load_from_book(book)

        process(test_json, book, registry)
        book.save()

        # Verify transaction has splits
        transactions = list(book.transactions)
        assert len(transactions) > 0, "No transactions found"
        assert len(transactions[0].splits) > 0, "Transaction has no splits"

        # For Jan 08, 2021, we expect at least 20 splits (income, taxes, deductions, etc.)
        assert len(transactions[0].splits) >= 20, f"Expected at least 20 splits, got {len(transactions[0].splits)}"

        print(f"✓ test_all_splits_included PASSED ({len(transactions[0].splits)} splits)")
        book.close()

    finally:
        os.unlink(gnucash_file)


def test_multiple_paychecks():
    """Test that multiple paychecks create multiple transactions"""
    with tempfile.NamedTemporaryFile(suffix='.gnucash', delete=False) as tmp:
        gnucash_file = tmp.name

    try:
        # Create GnuCash file with accounts
        create_gnucash_accounts(gnucash_file)

        # Load two test paychecks
        test_files = [
            "data/2021/Statement for Jan 08, 2021.json",
            "data/2021/Statement for Feb 05, 2021.json"
        ]

        available_files = [f for f in test_files if os.path.exists(f)]
        if len(available_files) < 2:
            print(f"SKIP: Need at least 2 test files, found {len(available_files)}")
            return

        book = piecash.open_book(gnucash_file, readonly=False, do_backup=False, open_if_lock=True)
        registry = AccountRegistry()
        registry.load_from_book(book)

        for test_json in available_files:
            process(test_json, book, registry)

        book.save()

        # Verify we have 2 transactions
        transactions = list(book.transactions)
        assert len(transactions) == len(available_files), \
            f"Expected {len(available_files)} transactions, got {len(transactions)}"

        # Verify each transaction balances
        for txn in transactions:
            total = sum(split.value for split in txn.splits)
            assert total == Decimal('0.00'), f"Transaction does not balance: {total}"

        print(f"✓ test_multiple_paychecks PASSED ({len(transactions)} transactions)")
        book.close()

    finally:
        os.unlink(gnucash_file)


if __name__ == "__main__":
    print("Running pypay automated tests...\n")

    try:
        test_single_transaction_per_paycheck()
        test_transaction_balances()
        test_transaction_has_description()
        test_all_splits_included()
        test_multiple_paychecks()

        print("\n✓ All tests PASSED")
        sys.exit(0)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
