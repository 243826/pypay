# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pypay is a Python-based payroll data processing tool that parses PDF paystubs and imports the financial transactions into GnuCash accounting software. It extracts structured data from payroll documents and creates double-entry bookkeeping transactions.

## Development Setup

### Environment Setup

The project uses pyenv for Python version management:

```bash
# Install Python 3.11.10 (note: .python-version specifies 3.12.9)
pyenv install 3.11.10

# Set local Python version
pyenv local 3.11.10

# Create virtual environment
pyenv exec python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pyenv exec pip install -r requirements.txt
```

### Running the Application

The application has four main commands:

**Initialize a new GnuCash file with all accounts:**

```bash
pyenv exec python load.py init my_finances.gnucash
```

**Preprocess PDF files to extract JSON data:**

```bash
pyenv exec python load.py preprocess data/paystubs           # Process all PDFs in directory
pyenv exec python load.py preprocess data/paystubs/file.pdf  # Process single PDF
```

**Load JSON transactions into GnuCash:**

```bash
pyenv exec python load.py load my_finances.gnucash data/paystubs  # Load all JSON files
pyenv exec python load.py load my_finances.gnucash file.json      # Load single JSON file
```

**Clean up JSON files generated during preprocessing:**

```bash
pyenv exec python load.py clean data/paystubs        # Delete all JSON files in directory (with confirmation)
pyenv exec python load.py clean file.json            # Delete single JSON file (with confirmation)
pyenv exec python load.py clean data/paystubs --force  # Delete without confirmation
```

## Architecture

### Main Components

**load.py** - Single-file application containing:

- PDF parsing logic using pdfplumber
- JSON data extraction and transformation
- GnuCash transaction creation using piecash library
- Account mapping and categorization

### Data Flow

1. **PDF Parsing** (`parse_file`, `parse_table`, `parse_row`, `parse_cell`)

   - Extracts tables from PDF paystubs (specifically Table 4 on each page)
   - Parses amounts (handling trailing minus signs), descriptions, and YTD values
   - Outputs structured JSON data

2. **Account Mapping** (`ACCOUNTS` dictionary)

   - Maps 80+ paystub line items to GnuCash account hierarchies
   - Defines account types: Asset, Income, Expense
   - Specifies custom processing functions for complex items

3. **Transaction Processing** (`process` function)

   - Groups splits by transaction type (earnings, invisible, match401k, matchrestor)
   - Applies deferred functions for complex multi-split transactions
   - Creates balanced double-entry transactions

4. **GnuCash Integration** (`piecash` library)
   - Creates accounts with hierarchy (create_gnucash_accounts)
   - Generates transactions with splits
   - Saves to GnuCash database

### Key Design Patterns

**Deferred Function Pattern**: Some account entries (DRSU, stock taxes, 401k matches) return functions that execute after initial splits are created. This allows calculating dependent values (e.g., stock taxes based on total taxable RSU).

**Split Groups**: Transactions are organized into logical groups:

- `earnings`: Main paycheck splits
- `invisible`: Imputed income that doesn't affect net pay
- `match401k`: Employer 401(k) contributions
- `matchrestor`: Employer restoration match contributions

**Regex Search**: `SEARCH_ACCOUNTS` provides pattern-based matching for variable account descriptions (e.g., PTO balances with amounts).

### Account Hierarchy

The system creates a three-tier structure:

- **Asset**: Bank accounts, retirement (401k, DCP), stocks (RSU, DRSU, ESPP), FSA
- **Income**: Taxable (salary, bonus, RSU, ESPP) and Non-Taxable (401k match, benefits)
- **Expense**: Taxes (federal, state, FICA, Medicare, stock), insurance, pretax deductions

### Important Functions

- `earnings()`: Standard split creation for most line items
- `outstanding_stock_tax()`: Calculates stock tax as difference between RSU value and taxable amount
- `drsu_vest()`: Handles DRSU vesting with deferred tax calculation
- `add_imputed_income()`: Records imputed income without affecting net pay
- `total_net_pay()`: Final check deposit, inverted sign

### Date Parsing

Dates are extracted from filenames with pattern: `*_YYYY-MM-DD*.pdf` → `parse_date_from_file_name()`

## Dependencies

- **pdfplumber**: PDF table extraction
- **piecash**: GnuCash file manipulation (SQLite-based)
- **regex**: Enhanced regular expression support

## Testing

No formal test suite exists. Manual testing workflow:

1. Parse PDF: `python load.py data/2024/example.pdf`
2. Verify JSON output
3. Check GnuCash database for correct transactions
4. Validate double-entry balance (sum of splits = 0)
- whenever you test the code, save the test code as automated tests which you can run anytime you alter the code.