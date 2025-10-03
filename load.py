import argparse
import json
import os
import piecash
import pdfplumber
import re
import sys

from datetime import datetime
from decimal import Decimal, DecimalException, getcontext


class AccountRegistry:
    """Registry for managing GnuCash account lookups"""

    def __init__(self):
        self._accounts = {}

    def load_from_book(self, book):
        """Load all accounts from a GnuCash book"""
        self._accounts.clear()
        for acc in book.accounts:
            self._accounts[acc.fullname] = acc

    def get(self, account_path):
        """Get an account by its full path"""
        account = self._accounts.get(account_path)
        if account is None:
            raise ValueError(f"Account not found: {account_path}")
        return account

    def get_safe(self, account_path):
        """Get an account by its full path, returns None if not found"""
        return self._accounts.get(account_path)

    def has(self, account_path):
        """Check if an account exists"""
        return account_path in self._accounts


def print_value(splits_groups, properties, value, desc, data, registry):
    print(desc, value)

def earnings(splits_groups, properties, value, desc, data, registry):
    splits = splits_groups["earnings"]

    account = registry.get(properties["account"])
    splits.append(piecash.Split(account=account, memo=properties["desc"], value=-value))

def outstanding_stock_tax(splits_groups, properties, value, desc, data, registry):
    def deferred_outstanding_stock_tax():
        splits = splits_groups["earnings"]

        taxable_rsu_account = registry.get(ACCOUNT_PATHS['INCOME_TAXABLE_RSU'])
        taxable_rsu = Decimal('0.00')
        for split in splits:
            if split.account == taxable_rsu_account:
                taxable_rsu += split.value

        aftertax_rsu_account = registry.get(ACCOUNT_PATHS['ASSET_STOCKS_RSU'])
        #print("split", "aftertax rsu", value - taxable_rsu)
        splits.append(piecash.Split(account=aftertax_rsu_account, memo="aftertax rsu", value=value - taxable_rsu))

        stock_tax_account = registry.get(ACCOUNT_PATHS['EXPENSE_TAXES_STOCK'])
        delta = Decimal('0.00')
        for split in splits:
            delta += split.value
        #print("split", "stock tax", delta)
        splits.append(piecash.Split(account=stock_tax_account, memo="stock tax", value=-delta))

    return deferred_outstanding_stock_tax


def drsu_vest(splits_groups, properties, value, desc, data, registry):
    splits = splits_groups["earnings"]

    drsu_income_account = registry.get(ACCOUNT_PATHS['INCOME_TAXABLE_DRSU'])
    # print(desc, value)
    splits.append(piecash.Split(account=drsu_income_account, memo=properties["desc"], value=-value))

    def deferred_drsu_vest():
        total = Decimal('0.00')
        for split in splits:
            total += split.value

        drsu_account = registry.get(ACCOUNT_PATHS['ASSET_STOCKS_DRSU'])
        # print(desc, value)
        splits.append(piecash.Split(account=drsu_account, memo=properties["desc"], value=value))

        stock_tax_account = registry.get(ACCOUNT_PATHS['EXPENSE_TAXES_STOCK'])
        splits.append(piecash.Split(account=stock_tax_account, memo="fica and medfica taxes", value=-value-total))

    return deferred_drsu_vest


def add_imputed_income(splits_groups, properties, value, desc, data, registry):
    if "invisible" in splits_groups:
        splits = splits_groups["invisible"]
    else:
        splits = []
        splits_groups["invisible"] = splits

    invisible_equity_account = registry.get(ACCOUNT_PATHS['EQUITY_INVISIBLE'])
    splits.append(piecash.Split(account=invisible_equity_account, memo=properties["desc"], value=value))

    imputed_income_account = registry.get(ACCOUNT_PATHS['INCOME_TAXABLE_IMPUTED'])
    splits.append(piecash.Split(account=imputed_income_account, memo=properties["desc"], value=-value))

def match_401k(splits_groups, properties, value, desc, data, registry):
    if "match401k" in splits_groups:
        splits = splits_groups["match401k"]
    else:
        splits = []
        splits_groups["match401k"] = splits

    match_401k_account = registry.get(ACCOUNT_PATHS['ASSET_401K_PRETAX_EMPLOYER'])
    splits.append(piecash.Split(account=match_401k_account, memo=properties["desc"], value=value))

    non_taxable_401k_account = registry.get(ACCOUNT_PATHS['INCOME_NONTAXABLE_401K'])
    splits.append(piecash.Split(account=non_taxable_401k_account, memo=properties["desc"], value=-value))

def match_restor(splits_groups, properties, value, desc, data, registry):
    if "matchrestor" in splits_groups:
        splits = splits_groups["matchrestor"]
    else:
        splits = []
        splits_groups["matchrestor"] = splits

    match_restor_account = registry.get(ACCOUNT_PATHS['ASSET_DCP_RESTOR'])
    splits.append(piecash.Split(account=match_restor_account, memo=properties["desc"], value=value))

    non_taxable_restor_account = registry.get(ACCOUNT_PATHS['INCOME_NONTAXABLE_MISC'])
    splits.append(piecash.Split(account=non_taxable_restor_account, memo=properties["desc"], value=-value))


def total_net_pay(splits_groups, properties, value, desc, data, registry):
    return earnings(splits_groups, properties, -value, desc, data, registry)

# Centralized registry of all account paths used in the system
ACCOUNT_PATHS = {
    # Asset accounts
    'ASSET_401K_PRETAX_ELECTIVE': 'Assets:401k:PreTax:Elective',
    'ASSET_401K_PRETAX_EMPLOYER': 'Assets:401k:PreTax:Employer',
    'ASSET_401K_AFTERTAX': 'Assets:401k:AfterTax',
    'ASSET_DCP_BONUS': 'Assets:DCP:Bonus',
    'ASSET_DCP_REGULAR': 'Assets:DCP:Regular',
    'ASSET_DCP_RESTOR': 'Assets:DCP:Restor',
    'ASSET_FSA_DC': 'Assets:FSA:DC',
    'ASSET_FSA_HEALTH': 'Assets:FSA:Health',
    'ASSET_STOCKS_ESPP': 'Assets:Stocks:ESPP',
    'ASSET_STOCKS_RSU': 'Assets:Stocks:RSU',
    'ASSET_STOCKS_DRSU': 'Assets:Stocks:DRSU',
    'ASSET_BANK_CHECKING': 'Assets:Bank:Checking',
    'ASSET_RECEIVABLES_PTO': 'Assets:Receivables:PTO',

    # Income accounts
    'INCOME_TAXABLE_REGULAR': 'Income:Taxable:Regular',
    'INCOME_TAXABLE_BONUS': 'Income:Taxable:Bonus',
    'INCOME_TAXABLE_RSU': 'Income:Taxable:RSU',
    'INCOME_TAXABLE_DRSU': 'Income:Taxable:DRSU',
    'INCOME_TAXABLE_ESPP': 'Income:Taxable:ESPP',
    'INCOME_TAXABLE_PTO': 'Income:Taxable:PTO',
    'INCOME_TAXABLE_FLOAT_HOL': 'Income:Taxable:FloatHol',
    'INCOME_TAXABLE_FLOATING_HOLIDAY': 'Income:Taxable:FloatingHoliday',
    'INCOME_TAXABLE_MISC': 'Income:Taxable:Misc',
    'INCOME_TAXABLE_IMPUTED': 'Income:Taxable:Imputed',
    'INCOME_NONTAXABLE_401K': 'Income:NonTaxable:401k',
    'INCOME_NONTAXABLE_DRSU': 'Income:NonTaxable:DRSU',
    'INCOME_NONTAXABLE_MISC': 'Income:NonTaxable:Misc',

    # Expense accounts
    'EXPENSE_PRETAX_DENTAL': 'Expenses:Pretax:Dental',
    'EXPENSE_PRETAX_MEDICAL': 'Expenses:Pretax:Medical',
    'EXPENSE_PRETAX_VISION': 'Expenses:Pretax:Vision',
    'EXPENSE_AFTERTAX_INSURANCE_LIFE': 'Expenses:Aftertax:Insurance:Life',
    'EXPENSE_AFTERTAX_INSURANCE_ILLNESS': 'Expenses:Aftertax:Insurance:Illness',
    'EXPENSE_AFTERTAX_INSURANCE_LEGAL': 'Expenses:Aftertax:Insurance:Legal',
    'EXPENSE_AFTERTAX_MISC': 'Expenses:Aftertax:Misc',
    'EXPENSE_TAXES_FEDERAL': 'Expenses:Taxes:Federal',
    'EXPENSE_TAXES_STATE': 'Expenses:Taxes:State',
    'EXPENSE_TAXES_CALIFORNIA': 'Expenses:Taxes:California',
    'EXPENSE_TAXES_FICA': 'Expenses:Taxes:FICA',
    'EXPENSE_TAXES_MEDICARE': 'Expenses:Taxes:Medicare',
    'EXPENSE_TAXES_STOCK': 'Expenses:Taxes:Stock',

    # Equity accounts
    'EQUITY_INVISIBLE': 'Equity:Invisible',
}

ACCOUNTS = {
    '*401(k) PreTax Reg': {
        'account': ACCOUNT_PATHS['ASSET_401K_PRETAX_ELECTIVE'],
        'desc': 'Reg',
    },
    '*401k PT BC': {
        'account': ACCOUNT_PATHS['ASSET_401K_PRETAX_ELECTIVE'],
        'desc': 'BC',
    },
    '*Def Comp - Bonus': {
        'account': ACCOUNT_PATHS['ASSET_DCP_BONUS'],
        'desc': 'Bonus',
    },
    '*Def Comp - Regular': {
        'account': ACCOUNT_PATHS['ASSET_DCP_REGULAR'],
        'desc': 'Regular',
    },
    '*Dental Plan - Pre Tax': {
        'account': ACCOUNT_PATHS['EXPENSE_PRETAX_DENTAL'],
        'desc': 'Dental',
    },
    '*FSA - Dependent Care': {
        'account': ACCOUNT_PATHS['ASSET_FSA_DC'],
        'desc': 'DC',
    },
    '*Medical Plan - Pre tax': {
        'account': ACCOUNT_PATHS['EXPENSE_PRETAX_MEDICAL'],
        'desc': 'Medical',
    },
    '*Vision Plan - Pre Tax': {
        'account': ACCOUNT_PATHS['EXPENSE_PRETAX_VISION'],
        'desc': 'Vision',
    },
    '401k After-Tax Reg': {
        'account': ACCOUNT_PATHS['ASSET_401K_AFTERTAX'],
        'desc': 'Reg',
    },
    '401k Mat TUP PY': {
        'account': ACCOUNT_PATHS['ASSET_401K_PRETAX_EMPLOYER'],
        'desc': 'TUP PY',
        'function': match_401k,
    },
    '401k Match - ER': {
        'account': ACCOUNT_PATHS['ASSET_401K_PRETAX_EMPLOYER'],
        'desc': 'ER',
        'function': match_401k,
    },
    '401k Match -ERB': {
        'account': ACCOUNT_PATHS['ASSET_401K_PRETAX_EMPLOYER'],
        'desc': 'ERB',
        'function': match_401k,
    },
    'Bank Fees': {
        'account': ACCOUNT_PATHS['INCOME_NONTAXABLE_MISC'],
        'desc': 'Bank Fees',
    },
    'Bonus': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_BONUS'],
        'desc': 'Bonus',
    },
    'Child Life Insurance': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_INSURANCE_LIFE'],
        'desc': 'Child',
    },
    'Critical Illness -Spouse': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_INSURANCE_ILLNESS'],
        'desc': 'Spouse',
    },
    'Critical Illness Insur-EE': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_INSURANCE_ILLNESS'],
        'desc': 'EE',
    },
    'DRSU Vest': {
        'account': ACCOUNT_PATHS['INCOME_NONTAXABLE_DRSU'],
        'desc': 'Vest',
        'function' : drsu_vest
    },
    'Debt Forgiveness': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_MISC'],
        'desc': 'Debt Forgiveness',
        'function': add_imputed_income,
    },
    'EE Medicare Tax': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_MEDICARE'],
        'desc': 'EE',
    },
    'EE Social Security Tax': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_FICA'],
        'desc': 'EE',
    },
    'ESPP (Jan - June)': {
        'account': ACCOUNT_PATHS['ASSET_STOCKS_ESPP'],
        'desc': 'Jan - June',
    },
    'ESPP (Jul - Dec)': {
        'account': ACCOUNT_PATHS['ASSET_STOCKS_ESPP'],
        'desc': 'Jul - Dec',
    },
    'ESPP Disq Disp': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_ESPP'],
        'desc': 'Disq Disp',
        'function': add_imputed_income,
    },
    'ESPP Res REF 1H': {
        'account': ACCOUNT_PATHS['ASSET_STOCKS_ESPP'],
        'desc': 'Res REF 1H',
    },
    'ESPP Res REF 2H': {
        'account': ACCOUNT_PATHS['ASSET_STOCKS_ESPP'],
        'desc': 'Res REF 2H',
    },
    'Flexible Saving Acct': {
        'account': ACCOUNT_PATHS['ASSET_FSA_HEALTH'],
        'desc': 'FSA',
    },
    'FloatHol 0.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_FLOAT_HOL'],
        'desc': 'FloatHol',
    },
    'FloatHol 8.00': {},
    'Floating Holiday 136.93 8.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_FLOATING_HOLIDAY'],
        'desc': 'Floating Holiday 136.93 8.00',
    },
    'Gross Pay': {
        'function': print_value
    },
    'Imputed Income -': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_IMPUTED'],
        'desc': 'Imputed Income',
        'function': add_imputed_income
    },
    'InLieu of Notice': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_MISC'],
        'desc': 'InLieu of Notice',
    },
    'Life Insurance - EE': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_INSURANCE_LIFE'],
        'desc': 'EE',
    },
    'Life Insurance - Spouse': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_INSURANCE_LIFE'],
        'desc': 'Spouse',
    },
    'Misc Pymt GUP': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_MISC'],
        'desc': 'Misc Pymt GUP',
    },
    'Misc. Deduction': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_MISC'],
        'desc': 'Misc. Deduction',
    },
    'Non-EE Medicare Tax': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_MEDICARE'],
        'desc': 'Non-EE',
    },
    'PTO Payout 136.93 81.89': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'PTO Payout 136.93 81.89',
    },
    'Paid Time Off 136.93 24.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 24.00',
    },
    'Paid Time Off 136.93 32.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 32.00',
    },
    'Paid Time Off 136.93 40.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 40.00',
    },
    'Paid Time Off 136.93 64.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 64.00',
    },
    'Paid Time Off 136.93 8.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 8.00',
    },
    'Paid Time Off 136.93 80.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 80.00',
    },
    'Paid Time Off 136.93 88.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 88.00',
    },
    'Paid Time Off 136.93 96.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 96.00',
    },
    'Paid Time Off 136.93 9.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_PTO'],
        'desc': 'Paid Time Off 136.93 9.00',
    },
    'Prepaid Legal Plan': {
        'account': ACCOUNT_PATHS['EXPENSE_AFTERTAX_INSURANCE_LEGAL'],
        'desc': 'Prepaid',
    },
    'RSU/PSU Stock': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_RSU'],
        'desc': 'Stock',
    },
    'Regular Salary 16.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 16.00',
    },
    'Regular Salary 40.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 40.00',
    },
    'Regular Salary 48.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 48.00',
    },
    'Regular Salary 56.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 56.00',
    },
    'Regular Salary 64.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 64.00',
    },
    'Regular Salary 72.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 72.00',
    },
    'Regular Salary 80.00': {
        'account': ACCOUNT_PATHS['INCOME_TAXABLE_REGULAR'],
        'desc': 'Regular Salary 80.00',
    },
    'Restor Match': {
        'account': ACCOUNT_PATHS['ASSET_DCP_RESTOR'],
        'desc': 'Match',
        'function': match_restor
    },
    'Stock Tax True Up': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_STOCK'],
        'desc': 'Tax True Up',
    },
    'Tax Deductions: California': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_CALIFORNIA'],
        'desc': 'California',
    },
    'Tax Deductions: Federal': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_FEDERAL'],
        'desc': 'Federal',
    },
    'Tax Deductions: State': {
        'account': ACCOUNT_PATHS['EXPENSE_TAXES_STATE'],
        'desc': 'State',
    },
    'Total Net Pay': {
        'account': ACCOUNT_PATHS['ASSET_BANK_CHECKING'],
        'desc': 'Net Pay',
        'function': total_net_pay
    },
    'Your federal taxable wages': {
        'function': print_value,
    },
    'STK Tax OS RSU/P': {
        'function': outstanding_stock_tax,
    }
}

SEARCH_ACCOUNTS = [
    {
        'pattern': r"^PTO \d+\.\d+",
        'account': ACCOUNT_PATHS['ASSET_RECEIVABLES_PTO'],
        'desc': 'PTO 252.24',
        'function': print_value
    }
]
    


def parse_amount(text):
    if text is None:
        return None

    if text.endswith("-"):
        text = "-" + text[:-1]

    try:
        return Decimal(text.replace(",", ""))
    except (ValueError, DecimalException):
        return None



def is_amount(text):
    pattern = r"^\d+(,\d+)?(\.\d+)?-?$"
    return bool(re.match(pattern, text))

def parse_date_from_file_name(path):
    file_name = path.split("/")[-1]
    suffix = file_name.split("_")[1]
    prefix = suffix.split("(")[0]
    prefix = prefix.split(".")[0]
    try:
        return datetime.strptime(prefix, "%Y-%m-%d").date()
    except ValueError as e:
        print("unable to parse date", prefix, e)
        return None

def parse_cell(cell):
    if cell is None or len(cell) == 0 or not re.search(r"[a-zA-Z0-9,]", cell):
        return

    values = cell.split(" ")
    if len(values) > 1:
        ytd = values[-1] if is_amount(values[-1]) else None
        cur = values[-2] if is_amount(values[-2]) else None
        if ytd is None:
            return { "desc" : cell }
        if cur is None:
            return { "desc" : " ".join(values[:-1]), "ytd" : ytd }
        else:
            return { "desc" : " ".join(values[:-2]), "cur" : cur, "ytd" : ytd }
    else:
        return { "desc" : cell }

def parse_row(row):
    data = []
    for cell in row:
        cell_data = parse_cell(cell)
        if cell_data:
            data.append(cell_data)
    return data

def parse_table(table):
    data = []
    for row in table:
        row_data = parse_row(row)
        if len(row_data) == 0:
            continue

        if row_data[0]["desc"] == "Withholding Tax":
            row_data[0]["desc"] = data[-1][0]["desc"]
            data[-1][0] = row_data[0]
        else:
            data.append(row_data)

    return data

def is_earnings_table(table):
    """Check if table contains earnings data by examining header"""
    if not table or len(table) < 1:
        return False

    header_row = table[0]
    header_text = ' '.join(str(cell) if cell else '' for cell in header_row)

    # Earnings table should have these keywords in header
    return ('Earnings' in header_text or 'Deductions' in header_text or
            'Rate' in header_text or 'Hours/Units' in header_text)

def parse_file(file_path):
    all_data = []
    pdf = pdfplumber.open(file_path)
    for p in pdf.pages:
        tables = p.extract_tables({
            "vertical_strategy": "lines",
            "horizontal_strategy": "text"
        })
        if tables:
            for table in tables:
                if is_earnings_table(table):
                    all_data += parse_table(table)

    return all_data


def extract(filepath):
    data = parse_file(filepath)
    json_filepath = filepath[:-4] + ".json"
    with open(json_filepath, "w") as f:
        json.dump(data, f, indent=2)
    return json_filepath


def search_properties(desc):
    for account in SEARCH_ACCOUNTS:
        if re.search(account["pattern"], desc):
            return account

def process(file_path, book, registry):
    """Process a JSON file and create GnuCash transactions"""
    date = parse_date_from_file_name(file_path)
    with open(file_path, "r") as f:
        data = json.load(f)

    current = [item for sublist in data for item in sublist if "cur" in item]

    deferred_functions = []
    groups = { 'earnings': [] }
    for item in current:
        desc = item["desc"]

        properties = ACCOUNTS[item["desc"]] if item["desc"] in ACCOUNTS else search_properties(desc)
        if properties:
            # print(item, properties)
            func = properties["function"] if "function" in properties else earnings
            ret = func(groups, properties, parse_amount(item["cur"]), item["desc"], data, registry)
            if ret is not None:
                deferred_functions.append(ret)

    for func in deferred_functions:
        func()

    currency = book.commodities(mnemonic="USD")
    for id, splits in groups.items():
        if len(splits) == 0:
            continue
        # print("transaction", id)
        piecash.Transaction(post_date=date, splits=splits, currency=currency)


def create_gnucash_accounts(gnucash_file):
    """Create a new GnuCash file with all accounts but no transactions"""
    with piecash.create_book(gnucash_file, currency="USD", overwrite=True) as book:
        USD = book.commodities.get(mnemonic="USD")

        # Add GnuCash features metadata (required for GnuCash GUI to recognize the file)
        book['features'] = {
            'ISO-8601 formatted date strings in SQLite3 databases.': 'Use ISO formatted date-time strings in SQLite3 databases (requires at least GnuCash 2.6.20)',
            'Register sort and filter settings stored in .gcm file': 'Store the register sort and filter settings in .gcm metadata file (requires at least GnuCash 3.3)',
            "Use a dedicated opening balance account identified by an 'equity-type' slot": "Use a dedicated opening balance account identified by an 'equity-type' slot (requires at least Gnucash 4.3)"
        }
        book['remove-color-not-set-slots'] = True

        # Root accounts are automatically created, just fetch them
        created_accounts_map = {}

        # Use all accounts from ACCOUNT_PATHS registry
        account_paths = set(ACCOUNT_PATHS.values())

        # Sort to ensure parent accounts are created first
        account_paths = sorted(account_paths)

        types_map = {
            "Assets": "ASSET",
            "Income": "INCOME",
            "Expenses": "EXPENSE",
            "Equity": "EQUITY",
            "Bank": "BANK"
        }

        for full_path in account_paths:
            elements = full_path.split(":")
            account_type = types_map.get(elements[0], "ASSET")

            # Build hierarchy
            for i in range(len(elements)):
                partial_path = ":".join(elements[:i+1])
                if partial_path not in created_accounts_map:
                    name = elements[i]
                    if i == 0:
                        # Top-level account
                        parent = book.root_account
                    else:
                        parent_path = ":".join(elements[:i])
                        parent = created_accounts_map[parent_path]

                    is_placeholder = (i < len(elements) - 1)
                    print(f"Creating account: {name} ({parent} -> {partial_path})")
                    created_accounts_map[partial_path] = piecash.Account(
                        name=name,
                        type=account_type,
                        parent=parent,
                        commodity=USD,
                        placeholder=is_placeholder
                    )

        book.flush()
        book.save()
        print(f"Created GnuCash file: {gnucash_file}")

def main():
    parser = argparse.ArgumentParser(description='Process payroll PDFs and load into GnuCash')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Preprocess command
    preprocess_parser = subparsers.add_parser('preprocess', help='Extract JSON from PDF file(s)')
    preprocess_parser.add_argument('path', help='Path to PDF file or directory containing PDFs')

    # Init command
    init_parser = subparsers.add_parser('init', help='Create new GnuCash file with accounts')
    init_parser.add_argument('gnucash_file', help='Path to new GnuCash file to create')

    # Load command
    load_parser = subparsers.add_parser('load', help='Load JSON data into GnuCash')
    load_parser.add_argument('gnucash_file', help='Path to GnuCash file')
    load_parser.add_argument('path', help='Path to JSON file or directory containing JSON files')

    args = parser.parse_args()

    if args.command == 'preprocess':
        if os.path.isdir(args.path):
            for file in sorted(os.listdir(args.path)):
                if file.endswith(".pdf"):
                    file_path = os.path.join(args.path, file)
                    print(f"Processing {file_path}...")
                    json_filepath = extract(file_path)
                    print(f"Created {json_filepath}")
        elif os.path.isfile(args.path):
            if args.path.endswith(".pdf"):
                print(f"Processing {args.path}...")
                json_filepath = extract(args.path)
                print(f"Created {json_filepath}")
            else:
                print(f"Error: {args.path} is not a PDF file")
        else:
            print(f"Error: {args.path} is not a valid path")

    elif args.command == 'init':
        if os.path.exists(args.gnucash_file):
            response = input(f"File {args.gnucash_file} already exists. Overwrite? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                return
        create_gnucash_accounts(args.gnucash_file)

    elif args.command == 'load':
        book = piecash.open_book(args.gnucash_file, readonly=False, do_backup=False, open_if_lock=True)
        registry = AccountRegistry()
        try:
            registry.load_from_book(book)

            if os.path.isdir(args.path):
                json_filepaths = []
                for file in sorted(os.listdir(args.path)):
                    if file.endswith(".json"):
                        file_path = os.path.join(args.path, file)
                        print(f"Loading {file_path}...")
                        process(file_path, book, registry)
            elif os.path.isfile(args.path):
                if args.path.endswith(".json"):
                    print(f"Loading {args.path}...")
                    process(args.path, book, registry)
                else:
                    print(f"Error: {args.path} is not a JSON file")
            else:
                raise ValueError(f"The path '{args.path}' is not valid")

            book.save()
            print("Successfully saved to GnuCash")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            book.close()

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
