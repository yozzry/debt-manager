"""
upgrade_db.py - Add missing columns and tables to existing database.
Run once if you get 'no such column' or 'no such table' errors after updating.

For full migration management, use Alembic:
  python -m alembic upgrade head     # apply all migrations
  python -m alembic revision --autogenerate -m "description"  # create new migration
"""
import sqlite3
import os
import subprocess
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'debtors.db')

ALLOWED_TABLES = {'settings', 'clients', 'users', 'payments', 'invoices', 'activity_log',
                  'categories', 'products', 'stock_movements', 'purchase_orders', 'purchase_items',
                  'sales', 'sale_items', 'accounts', 'journal_entries', 'journal_entry_lines',
                  'ledger_entries'}


def col_exists(cursor, table, col):
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table}")
    cursor.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cursor.fetchall())


def table_exists(cursor, table):
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table}")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def upgrade():
    if not os.path.exists(DB_PATH):
        print("[!] Database not found. It will be created on first run.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    column_migrations = [
        ('settings', 'key', 'TEXT'),
        ('settings', 'value', 'TEXT'),
        ('settings', 'value_type', "TEXT DEFAULT 'string'"),
        ('clients', 'total_debt', 'NUMERIC DEFAULT 0'),
        ('clients', 'total_paid', 'NUMERIC DEFAULT 0'),
        ('clients', 'base_debt', 'NUMERIC DEFAULT 0'),
        ('clients', 'base_paid', 'NUMERIC DEFAULT 0'),
        ('clients', 'reminder_enabled', 'INTEGER DEFAULT 1'),
        ('clients', 'reminder_template', 'INTEGER DEFAULT 1'),
        ('clients', 'reminder_times', 'TEXT'),
        ('clients', 'reminder_frequency', "TEXT DEFAULT 'daily'"),
        ('clients', 'reminder_day', "TEXT DEFAULT 'sun'"),
        ('clients', 'reminder_dom', 'INTEGER DEFAULT 1'),
        ('clients', 'updated_at', 'TEXT'),
        ('clients', 'type', "TEXT DEFAULT 'customer'"),
        ('clients', 'company_name', 'TEXT'),
        ('clients', 'tax_id', 'TEXT'),
        ('users', 'is_active_flag', 'INTEGER DEFAULT 1'),
        ('users', 'role', "TEXT DEFAULT 'viewer'"),
        ('payments', 'payment_method', "TEXT"),
        ('invoices', 'sale_id', 'INTEGER'),
        ('journal_entries', 'source_type', 'TEXT'),
        ('journal_entries', 'source_id', 'INTEGER'),
    ]

    for table, col, col_def in column_migrations:
        try:
            if not table_exists(cur, table):
                continue
            if not col_exists(cur, table, col):
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
                print(f"[+] Added column: {table}.{col}")
            else:
                print(f"[=] Already exists: {table}.{col}")
        except Exception as e:
            print(f"[!] Error on {table}.{col}: {e}")

    if not table_exists(cur, 'activity_log'):
        cur.execute("""
            CREATE TABLE activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute("CREATE INDEX idx_activity_user ON activity_log(user_id)")
        cur.execute("CREATE INDEX idx_activity_entity ON activity_log(entity_type, entity_id)")
        cur.execute("CREATE INDEX idx_activity_created ON activity_log(created_at)")
        print("[+] Created table: activity_log")
    else:
        print("[=] Table activity_log already exists")

    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_status ON clients(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_name ON clients(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_phone ON clients(phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_updated ON clients(updated_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_client_type ON clients(type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoice_client ON invoices(client_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoices(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_client ON payments(client_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_payment_date ON payments(date)")
        print("[+] Indexes created/verified")
    except Exception as e:
        print(f"[!] Index error: {e}")

    if not table_exists(cur, 'categories'):
        cur.execute("""
            CREATE TABLE categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL
            )
        """)
        print("[+] Created table: categories")
    else:
        print("[=] Table categories already exists")

    if not table_exists(cur, 'products'):
        cur.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT,
                barcode TEXT,
                category_id INTEGER,
                unit TEXT DEFAULT 'قطعة',
                cost_price NUMERIC DEFAULT 0,
                selling_price NUMERIC DEFAULT 0,
                current_stock NUMERIC DEFAULT 0,
                min_stock NUMERIC DEFAULT 0,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)
        print("[+] Created table: products")
    else:
        print("[=] Table products already exists")

    if not table_exists(cur, 'stock_movements'):
        cur.execute("""
            CREATE TABLE stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                movement_type TEXT NOT NULL,
                quantity NUMERIC NOT NULL,
                balance_after NUMERIC DEFAULT 0,
                reference TEXT,
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[+] Created table: stock_movements")
    else:
        print("[=] Table stock_movements already exists")

    if not table_exists(cur, 'purchase_orders'):
        cur.execute("""
            CREATE TABLE purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                supplier_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT DEFAULT 'draft',
                total_amount NUMERIC DEFAULT 0,
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (supplier_id) REFERENCES clients(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[+] Created table: purchase_orders")
    else:
        print("[=] Table purchase_orders already exists")

    if not table_exists(cur, 'purchase_items'):
        cur.execute("""
            CREATE TABLE purchase_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity NUMERIC NOT NULL,
                unit_cost NUMERIC DEFAULT 0,
                FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        print("[+] Created table: purchase_items")
    else:
        print("[=] Table purchase_items already exists")

    if not table_exists(cur, 'sales'):
        cur.execute("""
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                client_id INTEGER,
                date TEXT NOT NULL,
                subtotal NUMERIC DEFAULT 0,
                discount NUMERIC DEFAULT 0,
                total NUMERIC DEFAULT 0,
                payment_method TEXT DEFAULT 'cash',
                status TEXT DEFAULT 'completed',
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[+] Created table: sales")
    else:
        print("[=] Table sales already exists")

    if not table_exists(cur, 'sale_items'):
        cur.execute("""
            CREATE TABLE sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity NUMERIC NOT NULL,
                unit_price NUMERIC DEFAULT 0,
                FOREIGN KEY (sale_id) REFERENCES sales(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        print("[+] Created table: sale_items")
    else:
        print("[=] Table sale_items already exists")

    if not table_exists(cur, 'accounts'):
        cur.execute("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                account_type TEXT NOT NULL,
                parent_id INTEGER,
                opening_balance NUMERIC DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES accounts(id)
            )
        """)
        print("[+] Created table: accounts")
    else:
        print("[=] Table accounts already exists")

    if not table_exists(cur, 'journal_entries'):
        cur.execute("""
            CREATE TABLE journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_number TEXT NOT NULL UNIQUE,
                date TEXT NOT NULL,
                description TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[+] Created table: journal_entries")
    else:
        print("[=] Table journal_entries already exists")

    if not table_exists(cur, 'journal_entry_lines'):
        cur.execute("""
            CREATE TABLE journal_entry_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                debit NUMERIC DEFAULT 0,
                credit NUMERIC DEFAULT 0,
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        """)
        print("[+] Created table: journal_entry_lines")
    else:
        print("[=] Table journal_entry_lines already exists")

    if not table_exists(cur, 'ledger_entries'):
        cur.execute("""
            CREATE TABLE ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                entry_id INTEGER NOT NULL,
                line_id INTEGER NOT NULL UNIQUE,
                date TEXT NOT NULL,
                debit NUMERIC DEFAULT 0,
                credit NUMERIC DEFAULT 0,
                running_balance NUMERIC DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id),
                FOREIGN KEY (line_id) REFERENCES journal_entry_lines(id)
            )
        """)
        print("[+] Created table: ledger_entries")
    else:
        print("[=] Table ledger_entries already exists")

    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_category_name ON categories(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_name ON products(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_sku ON products(sku)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_barcode ON products(barcode)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_product_category ON products(category_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_product ON stock_movements(product_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_type ON stock_movements(movement_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_reference ON stock_movements(reference)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_created ON stock_movements(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_supplier ON purchase_orders(supplier_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_status ON purchase_orders(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_date ON purchase_orders(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_number ON purchase_orders(order_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_item_order ON purchase_items(order_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_purchase_item_product ON purchase_items(product_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_client ON sales(client_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_date ON sales(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_status ON sales(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_number ON sales(invoice_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_item_sale ON sale_items(sale_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_item_product ON sale_items(product_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_account_code ON accounts(code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_account_type ON accounts(account_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_account_parent ON accounts(parent_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_date ON journal_entries(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_number ON journal_entries(entry_number)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_source ON journal_entries(source_type, source_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_line_entry ON journal_entry_lines(entry_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_line_account ON journal_entry_lines(account_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ledger_account_date ON ledger_entries(account_id, date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ledger_entry ON ledger_entries(entry_id)")
        print("[+] New tables indexes created/verified")
    except Exception as e:
        print(f"[!] Index error: {e}")

    # Backfill ledger_entries from journal_entry_lines for existing databases
    # (running balances computed in Python, ordered by entry date/id/line id).
    if table_exists(cur, 'ledger_entries') and table_exists(cur, 'journal_entry_lines'):
        try:
            cur.execute("SELECT COUNT(*) FROM ledger_entries")
            if cur.fetchone()[0] == 0:
                cur.execute("""
                    SELECT a.id, a.account_type, a.opening_balance
                      FROM accounts a
                     ORDER BY a.code
                """)
                accounts = cur.fetchall()
                backfilled = 0
                for account_id, atype, opening in accounts:
                    normal = 'credit' if atype in ('liability', 'equity', 'income') else 'debit'
                    cur.execute("""
                        SELECT jl.id, jl.entry_id, jl.account_id, jl.debit, jl.credit,
                               je.date, je.created_at
                          FROM journal_entry_lines jl
                          JOIN journal_entries je ON je.id = jl.entry_id
                         WHERE jl.account_id = ?
                         ORDER BY je.date, je.id, jl.id
                    """, (account_id,))
                    running = float(opening or 0)
                    for line_id, entry_id, _, debit, credit, ldate, created_at in cur.fetchall():
                        d, c = float(debit or 0), float(credit or 0)
                        running = running + d - c if normal == 'debit' else running + c - d
                        cur.execute("""
                            INSERT INTO ledger_entries
                                (account_id, entry_id, line_id, date, debit, credit,
                                 running_balance, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (account_id, entry_id, line_id, ldate, debit, credit,
                              round(running, 2), created_at))
                        backfilled += 1
                print(f"[+] Backfilled ledger_entries ({backfilled} rows)")
        except Exception as e:
            print(f"[!] Ledger backfill error: {e}")

    # Backfill base totals for existing clients that have no tracked invoices/payments
    # (i.e. previously imported standing totals) so recalc_client does not wipe them.
    try:
        cur.execute("""
            UPDATE clients
               SET base_debt = total_debt, base_paid = total_paid
             WHERE id NOT IN (SELECT DISTINCT client_id FROM invoices)
               AND id NOT IN (SELECT DISTINCT client_id FROM payments)
        """)
        print(f"[+] Backfilled base totals for imported clients ({cur.rowcount} rows)")
    except Exception as e:
        print(f"[!] Backfill error: {e}")

    conn.commit()
    conn.close()
    print("\nUpgrade complete.")


if __name__ == '__main__':
    upgrade()
