# PartyChat Accounting

PartyChat Accounting is a local-first desktop accounting application for macOS.

## Rebuilt in v3
- Password-protected local SQLite database
- Parties: Customer, Supplier, Staff, Partner and Other
- Search, add, edit and delete parties
- Party ledger with receivable/payable, due/settled and project information
- Add, edit, settle and delete transactions
- Projects containing multiple parties
- Consolidated project ledger
- Dashboard showing receivables, payables and net position
- SQLite backup and restore
- CSV export
- No internet required during normal use

## Build the Mac application

On the Mac, open Terminal in this repository and run:

```bash
chmod +x build_mac.command
./build_mac.command
```

The script builds `PartyChat Accounting.app` and places it on the Desktop.

**Important:** the native macOS application must be built on macOS. This repository contains the source and build script; it is not necessary to run the Python file every time after the `.app` is built.

## Run from source

```bash
python3 PartyChat_Accounting.py
```

## Data location

All application data is stored locally in:

`~/PartyChat Accounting/`

Backups are stored in `~/PartyChat Accounting/Backups/` and CSV exports in `~/PartyChat Accounting/Exports/`.
