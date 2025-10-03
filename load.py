import json
import os
import piecash
import pdfplumber
import re
import sys

from datetime import datetime
from decimal import Decimal, DecimalException, getcontext

def print_value(splits_groups, properties, value, desc, data):
    print(desc, value)

def earnings(splits_groups, properties, value, desc, data):
    splits = splits_groups["earnings"]

    fullname = properties["type"] + ":" + properties["account"]
    account = created_accounts.get(fullname)
    splits.append(piecash.Split(account=account, memo=properties["desc"], value=-value))

def outstanding_stock_tax(splits_groups, properties, value, desc, data):
    def deferred_outstanding_stock_tax():
        splits = splits_groups["earnings"]

        taxable_rsu_account = created_accounts.get("Income:Taxable:RSU")
        taxable_rsu = Decimal('0.00')
        for split in splits:
            if split.account == taxable_rsu_account:
                taxable_rsu += split.value

        aftertax_rsu_account = created_accounts.get("Asset:Stocks:RSU")
        #print("split", "aftertax rsu", value - taxable_rsu)
        splits.append(piecash.Split(account=aftertax_rsu_account, memo="aftertax rsu", value=value - taxable_rsu))

        stock_tax_account = created_accounts.get("Expense:Taxes:Stock")
        delta = Decimal('0.00')
        for split in splits:
            delta += split.value
        #print("split", "stock tax", delta)
        splits.append(piecash.Split(account=stock_tax_account, memo="stock tax", value=-delta))
        
    return deferred_outstanding_stock_tax


def drsu_vest(splits_groups, properties, value, desc, data):
    splits = splits_groups["earnings"]

    drsu_income_account = created_accounts.get("Income:Taxable:DRSU")
    # print(desc, value)
    splits.append(piecash.Split(account=drsu_income_account, memo=properties["desc"], value=-value))

    def deferred_drsu_vest():
        total = Decimal('0.00')
        for split in splits:
            total += split.value

        drsu_account = created_accounts.get("Asset:Stocks:DRSU")
        # print(desc, value)
        splits.append(piecash.Split(account=drsu_account, memo=properties["desc"], value=value))

        stock_tax_account = created_accounts.get("Expense:Taxes:Stock")
        splits.append(piecash.Split(account=stock_tax_account, memo="fica and medfica taxes", value=-value-total))

    return deferred_drsu_vest


def add_imputed_income(splits_groups, properties, value, desc, data):
    if "invisible" in splits_groups:
        splits = splits_groups["invisible"]
    else:
        splits = []
        splits_groups["invisible"] = splits

    invisible_equity_account = created_accounts.get("Equity:Invisible")
    splits.append(piecash.Split(account=invisible_equity_account, memo=properties["desc"], value=value))

    imputed_income_account = created_accounts.get("Income:Taxable:Imputed")
    splits.append(piecash.Split(account=imputed_income_account, memo=properties["desc"], value=-value))

def match_401k(splits_groups, properties, value, desc, data):
    if "match401k" in splits_groups:
        splits = splits_groups["match401k"]
    else:
        splits = []
        splits_groups["match401k"] = splits

    match_401k_account = created_accounts.get("Asset:401k:PreTax:Employer")
    splits.append(piecash.Split(account=match_401k_account, memo=properties["desc"], value=value))

    non_taxable_401k_account = created_accounts.get("Income:NonTaxable:401k")
    splits.append(piecash.Split(account=non_taxable_401k_account, memo=properties["desc"], value=-value))

def match_restor(splits_groups, properties, value, desc, data):
    if "matchrestor" in splits_groups:
        splits = splits_groups["matchrestor"]
    else:    
        splits = [] 
        splits_groups["matchrestor"] = splits

    match_restor_account = created_accounts.get("Asset:DCP:Restor")
    splits.append(piecash.Split(account=match_restor_account, memo=properties["desc"], value=value))

    non_taxable_restor_account = created_accounts.get("Income:NonTaxable:Misc")
    splits.append(piecash.Split(account=non_taxable_restor_account, memo=properties["desc"], value=-value))


def total_net_pay(splits_groups, properties, value, desc, data):
    return earnings(splits_groups, properties, -value, desc, data)

ACCOUNTS = {
    '*401(k) PreTax Reg': {
        'account': '401k:PreTax:Elective',
        'type': 'Asset',
        'desc': 'Reg',
    },
    '*401k PT BC': {
        'account': '401k:PreTax:Elective',
        'type': 'Asset',
        'desc': 'BC',
    },
    '*Def Comp - Bonus': {
        'account': 'DCP:Bonus',
        'type': 'Asset',
        'desc': 'Bonus',
    },
    '*Def Comp - Regular': {
        'account': 'DCP:Regular',
        'type': 'Asset',
        'desc': 'Regular',
    },
    '*Dental Plan - Pre Tax': {
        'account': 'Pretax:Dental',
        'type': 'Expense',
        'desc': 'Dental',
    },
    '*FSA - Dependent Care': {
        'account': 'FSA:DC',
        'type': 'Asset',
        'desc': 'DC',
    },
    '*Medical Plan - Pre tax': {
        'account': 'Pretax:Medical',
        'type': 'Expense',
        'desc': 'Medical',
    },
    '*Vision Plan - Pre Tax': {
        'account': 'Pretax:Vision',
        'type': 'Expense',
        'desc': 'Vision',
    },
    '401k After-Tax Reg': {
        'account': '401k:AfterTax',
        'type': 'Asset',
        'desc': 'Reg',
    },
    '401k Mat TUP PY': {
        'account': '401k:PreTax:Employer',
        'type': 'Asset',
        'desc': 'TUP PY',
        'function': match_401k,
    },
    '401k Match - ER': {
        'account': '401k:PreTax:Employer',
        'type': 'Asset',
        'desc': 'ER',
        'function': match_401k,
    },
    '401k Match -ERB': {
        'account': '401k:PreTax:Employer',
        'type': 'Asset',
        'desc': 'ERB',
        'function': match_401k,
    },
    'Bank Fees': {
        'account': 'NonTaxable:Misc',
        'type': 'Income',
        'desc': 'Bank Fees',
    },
    'Bonus': {
        'account': 'Taxable:Bonus',
        'type': 'Income',
        'desc': 'Bonus',
    },
    'Child Life Insurance': {
        'account': 'Aftertax:Insurance:Life',
        'type': 'Expense',
        'desc': 'Child',
    },
    'Critical Illness -Spouse': {
        'account': 'Aftertax:Insurance:Illness',
        'type': 'Expense',
        'desc': 'Spouse',
    },
    'Critical Illness Insur-EE': {
        'account': 'Aftertax:Insurance:Illness',
        'type': 'Expense',
        'desc': 'EE',
    },
    'DRSU Vest': {
        'account': 'NonTaxable:DRSU',
        'type': 'Income',
        'desc': 'Vest',
        'function' : drsu_vest
    },
    'Debt Forgiveness': {
        'account': 'Taxable:Misc',
        'type': 'Income',
        'desc': 'Debt Forgiveness',
        'function': add_imputed_income,
    },
    'EE Medicare Tax': {
        'account': 'Taxes:Medicare',
        'type': 'Expense',
        'desc': 'EE',
    },
    'EE Social Security Tax': {
        'account': 'Taxes:FICA',
        'type': 'Expense',
        'desc': 'EE',
    },
    'ESPP (Jan - June)': {
        'account': 'Stocks:ESPP',
        'type': 'Asset',
        'desc': 'Jan - June',
    },
    'ESPP (Jul - Dec)': {
        'account': 'Stocks:ESPP',
        'type': 'Asset',
        'desc': 'Jul - Dec',
    },
    'ESPP Disq Disp': {
        'account': 'Taxable:ESPP',
        'type': 'Income',
        'desc': 'Disq Disp',
        'function': add_imputed_income,
    },
    'ESPP Res REF 1H': {
        'account': 'Stocks:ESPP',
        'type': 'Asset',
        'desc': 'Res REF 1H',
    },
    'ESPP Res REF 2H': {
        'account': 'Stocks:ESPP',
        'type': 'Asset',
        'desc': 'Res REF 2H',
    },
    'Flexible Saving Acct': {
        'account': 'FSA:Health',
        'type': 'Asset',
        'desc': 'FSA',
    },
    'FloatHol 0.00': {
        'account': 'Taxable:FloatHol',
        'type': 'Income',
        'desc': 'FloatHol',
    },
    'FloatHol 8.00': {},
    'Floating Holiday 136.93 8.00': {
        'account': 'Taxable:FloatingHoliday',
        'type': 'Income',
        'desc': 'Floating Holiday 136.93 8.00',
    },
    'Gross Pay': {
        'function': print_value
    },
    'Imputed Income -': {
        'account': 'Taxable:Imputed',
        'type': 'Income',
        'desc': 'Imputed Income',
        'function': add_imputed_income
    },
    'InLieu of Notice': {
        'account': 'Taxable:Misc',
        'type': 'Income',
        'desc': 'InLieu of Notice',
    },
    'Life Insurance - EE': {
        'account': 'Aftertax:Insurance:Life',
        'type': 'Expense',
        'desc': 'EE',
    },
    'Life Insurance - Spouse': {
        'account': 'Aftertax:Insurance:Life',
        'type': 'Expense',
        'desc': 'Spouse',
    },
    'Misc Pymt GUP': {
        'account': 'Taxable:Misc',
        'type': 'Income',
        'desc': 'Misc Pymt GUP',
    },
    'Misc. Deduction': {
        'account': 'Aftertax:Misc',
        'type': 'Expense',
        'desc': 'Misc. Deduction',
    },
    'Non-EE Medicare Tax': {
        'account': 'Taxes:Medicare',
        'type': 'Expense',
        'desc': 'Non-EE',
    },
    'PTO Payout 136.93 81.89': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'PTO Payout 136.93 81.89',
    },
    'Paid Time Off 136.93 24.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 24.00',
    },
    'Paid Time Off 136.93 32.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 32.00',
    },
    'Paid Time Off 136.93 40.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 40.00',
    },
    'Paid Time Off 136.93 64.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 64.00',
    },
    'Paid Time Off 136.93 8.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 8.00',
    },
    'Paid Time Off 136.93 80.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 80.00',
    },
    'Paid Time Off 136.93 88.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 88.00',
    },
    'Paid Time Off 136.93 96.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 96.00',
    },
    'Paid Time Off 136.93 9.00': {
        'account': 'Taxable:PTO',
        'type': 'Income',
        'desc': 'Paid Time Off 136.93 9.00',
    },
    'Prepaid Legal Plan': {
        'account': 'Aftertax:Insurance:Legal',
        'type': 'Expense',
        'desc': 'Prepaid',
    },
    'RSU/PSU Stock': {
        'account': 'Taxable:RSU',
        'type': 'Income',
        'desc': 'Stock',
    },
    'Regular Salary 16.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 16.00',
    },
    'Regular Salary 40.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 40.00',
    },
    'Regular Salary 48.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 48.00',
    },
    'Regular Salary 56.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 56.00',
    },
    'Regular Salary 64.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 64.00',
    },
    'Regular Salary 72.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 72.00',
    },
    'Regular Salary 80.00': {
        'account': 'Taxable:Regular',
        'type': 'Income',
        'desc': 'Regular Salary 80.00',
    },
    'Restor Match': {
        'account': 'DCP:Restor',
        'type': 'Asset',
        'desc': 'Match',
        'function': match_restor
    },
    'Stock Tax True Up': {
        'account': 'Taxes:Stock',
        'type': 'Expense',
        'desc': 'Tax True Up',
    },
    'Tax Deductions: California': {
        'account': 'Taxes:California',
        'type': 'Expense',
        'desc': 'California',
    },
    'Tax Deductions: Federal': {
        'account': 'Taxes:Federal',
        'type': 'Expense',
        'desc': 'Federal',
    },
    'Tax Deductions: State': {
        'account': 'Taxes:State',
        'type': 'Expense',
        'desc': 'State',
    },
    'Total Net Pay': {
        'account': 'Bank:Checking',
        'type': 'Asset',
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
        'account': 'Receivables:PTO',
        'type': 'Asset',
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
                table_num = tables.index(table) + 1
                if table_num == 4:
                    # print(f"File: {file_path}, Page: {p.page_number}, Table number: {table_num}")
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
        
def process(file_path, book):
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
            ret = func(groups, properties, parse_amount(item["cur"]), item["desc"], data)
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




created_accounts = {}

if len(sys.argv) > 1:
    path = sys.argv[1]

    book = piecash.open_book("example.gnucash", readonly=False, do_backup=False, open_if_lock=True)
    try:
        for acc in book.accounts:
            created_accounts[acc.fullname] = acc
        if os.path.isdir(path):
            json_filepaths = []
            for file in sorted(os.listdir(path)):
                if file.endswith(".json"):
                    file_path = os.path.join(path, file)
                    process(file_path, book)
        elif os.path.isfile(path):
            process(path, book)
        else:
            raise ValueError(f"The passed argument '{path}' is not a valid path")

        book.save()
    except Exception as e:
        print(e)
    finally:
        book.close()
else:
    print("usage: python load.py <path>")            


def create_gnucash_accounts():

    book = piecash.create_book("example.gnucash", currency="USD", overwrite=True)

    USD = book.commodities.get(namespace="CURRENCY", mnemonic="USD")

    asset = piecash.Account(name="Asset", type="ASSET", parent=book.root_account, commodity=USD, placeholder=True)
    income = piecash.Account(name="Income", type="INCOME", parent=book.root_account, commodity=USD, placeholder=True)
    expense = piecash.Account(name="Expense", type="EXPENSE", parent=book.root_account, commodity=USD, placeholder=True)


    created_accounts = {
        "Asset": asset,
        "Income": income,
        "Expense": expense
    }

    types = {
        "Asset": "ASSET",
        "Income": "INCOME",
        "Expense": "EXPENSE"
    }

    for account in ACCOUNTS.values():
        if len(account) > 0:
            parent = created_accounts[account["type"]]
            mapped = account["type"]
            type = types[mapped]

            elements = account["account"].split(":")
            for i in range(len(elements) - 1):
                name = elements[i]
                mapped = mapped + ":" + name
                if mapped in created_accounts:
                    parent = created_accounts[mapped]
                else:
                    parent = piecash.Account(name=name, type=type, parent=parent, commodity=USD, placeholder=True)
                    created_accounts[mapped] = parent

            name = elements[-1]
            mapped = mapped + ":" + name
            if mapped not in created_accounts:
                created_accounts[mapped] = piecash.Account(name=name, type=type, parent=parent, commodity=USD, placeholder=False)

    book.save()
