#!/usr/bin/env python3
import sqlite3, hashlib, secrets, shutil, csv
from datetime import datetime, date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "PartyChat Accounting V2"
BASE = Path.home() / "PartyChat Accounting"
DB = BASE / "partychat_v2.db"
BACKUPS = BASE / "Backups"
EXPORTS = BASE / "Exports"
PBKDF2_ITERS = 200_000
BASE.mkdir(exist_ok=True); BACKUPS.mkdir(exist_ok=True); EXPORTS.mkdir(exist_ok=True)

def now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    c = connect()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS parties(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'Customer', phone TEXT DEFAULT '', notes TEXT DEFAULT '', is_group INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS project_members(project_id INTEGER NOT NULL, party_id INTEGER NOT NULL, PRIMARY KEY(project_id, party_id), FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE, FOREIGN KEY(party_id) REFERENCES parties(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, party_id INTEGER NOT NULL, project_id INTEGER, txn_date TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('RECEIVABLE','PAYABLE')), status TEXT NOT NULL DEFAULT 'DUE' CHECK(status IN ('DUE','SETTLED')), category TEXT DEFAULT 'General', created_at TEXT NOT NULL, FOREIGN KEY(party_id) REFERENCES parties(id) ON DELETE CASCADE, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL);
    ''')
    c.commit()
    c.close()

def has_password():
    c = connect()
    r = c.execute("SELECT value FROM settings WHERE key='password_hash'").fetchone()
    c.close()
    return bool(r)

def set_password(pw):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, PBKDF2_ITERS)
    c = connect()
    c.execute("INSERT OR REPLACE INTO settings VALUES('password_hash', ?)", (salt.hex() + ':' + digest.hex(),))
    c.commit()
    c.close()

def verify_password(pw):
    c = connect()
    r = c.execute("SELECT value FROM settings WHERE key='password_hash'").fetchone()
    c.close()
    if not r:
        return False
    s, d = r['value'].split(':')
    x = hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(s), PBKDF2_ITERS)
    return secrets.compare_digest(x.hex(), d)

def money(x): return f"₹{x:,.2f}"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry('1180x760')
        self.minsize(980, 650)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        
        # Consistent styling for dark and light modes
        self.style = ttk.Style(self)
        try:
            self.style.theme_use('clam')
        except:
            pass
        self.style.configure('TEntry', fieldbackground='white', foreground='black')
        self.style.configure('TCombobox', fieldbackground='white', foreground='black')

        self.selected_party = None
        self.selected_project = None

        if not has_password():
            self.show_setup_password()
        else:
            self.show_login()

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

    # --- Authentication Views ---
    def show_setup_password(self):
        self.clear_screen()
        frame = ttk.Frame(self, padding=30)
        frame.place(relx=0.5, rely=0.5, anchor='center')

        ttk.Label(frame, text='Create Master Password', font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 15))
        ttk.Label(frame, text='Set a password to secure your accounting data:').pack(pady=(0, 10))

        ttk.Label(frame, text='New Password:').pack(anchor='w')
        p1 = ttk.Entry(frame, show='*', width=30)
        p1.pack(pady=(0, 10))
        p1.focus()

        ttk.Label(frame, text='Confirm Password:').pack(anchor='w')
        p2 = ttk.Entry(frame, show='*', width=30)
        p2.pack(pady=(0, 15))

        def on_submit():
            v1, v2 = p1.get(), p2.get()
            if not v1.strip():
                messagebox.showwarning('Required', 'Password cannot be blank.', parent=self)
                return
            if v1 != v2:
                messagebox.showerror('Mismatch', 'Passwords do not match.', parent=self)
                return
            set_password(v1)
            self.build()

        ttk.Button(frame, text='Save & Open App', command=on_submit).pack(fill='x')
        self.bind('<Return>', lambda _: on_submit())

    def show_login(self):
        self.clear_screen()
        frame = ttk.Frame(self, padding=30)
        frame.place(relx=0.5, rely=0.5, anchor='center')

        ttk.Label(frame, text=APP_NAME, font=('TkDefaultFont', 18, 'bold')).pack(pady=(0, 5))
        ttk.Label(frame, text='Enter password to continue:', foreground='#666').pack(pady=(0, 15))

        pw_entry = ttk.Entry(frame, show='*', width=30)
        pw_entry.pack(pady=(0, 15))
        pw_entry.focus()

        def attempt_login():
            val = pw_entry.get()
            if verify_password(val):
                self.unbind('<Return>')
                self.build()
            else:
                messagebox.showerror('Error', 'Incorrect password.', parent=self)
                pw_entry.delete(0, 'end')

        ttk.Button(frame, text='Log In', command=attempt_login).pack(fill='x')
        self.bind('<Return>', lambda _: attempt_login())

    # --- Main Application View ---
    def build(self):
        self.clear_screen()
        top = ttk.Frame(self, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='PartyChat Accounting', font=('TkDefaultFont', 20, 'bold')).pack(side='left')
        ttk.Label(top, text='  V2 • Local & Private', foreground='#666').pack(side='left')
        for text, cmd in [('Backup', self.backup), ('Restore', self.restore), ('Export CSV', self.export_csv), ('Change Password', self.change_password)]:
            ttk.Button(top, text=text, command=cmd).pack(side='right', padx=3)

        pan = ttk.Panedwindow(self, orient='horizontal')
        pan.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(pan, width=320)
        right = ttk.Frame(pan)
        pan.add(left, weight=0)
        pan.add(right, weight=1)
        self.right = right

        nb = ttk.Notebook(left)
        nb.pack(fill='both', expand=True)
        pt = ttk.Frame(nb)
        pr = ttk.Frame(nb)
        nb.add(pt, text=' Parties ')
        nb.add(pr, text=' Projects ')

        self.party_search = tk.StringVar()
        sf = ttk.Frame(pt, padding=6)
        sf.pack(fill='x')
        ttk.Entry(sf, textvariable=self.party_search).pack(side='left', fill='x', expand=True)
        self.party_search.trace_add('write', lambda *_: self.refresh_parties())
        ttk.Button(sf, text='+', width=3, command=self.add_party).pack(side='right', padx=(5, 0))

        self.party_tree = ttk.Treeview(pt, show='tree', selectmode='browse')
        self.party_tree.pack(fill='both', expand=True, padx=6, pady=6)
        self.party_tree.bind('<<TreeviewSelect>>', self.party_selected)
        ttk.Button(pt, text='Edit selected', command=self.edit_party).pack(fill='x', padx=6, pady=3)
        ttk.Button(pt, text='Delete selected', command=self.delete_party).pack(fill='x', padx=6, pady=(0, 6))

        ttk.Button(pr, text='+ New Project', command=self.add_project).pack(fill='x', padx=6, pady=6)
        self.project_tree = ttk.Treeview(pr, show='tree', selectmode='browse')
        self.project_tree.pack(fill='both', expand=True, padx=6, pady=6)
        self.project_tree.bind('<<TreeviewSelect>>', self.project_selected)
        ttk.Button(pr, text='Manage Members', command=self.manage_members).pack(fill='x', padx=6, pady=3)
        ttk.Button(pr, text='Delete Project', command=self.delete_project).pack(fill='x', padx=6, pady=(0, 6))

        self.build_empty()
        self.refresh_all()

    def clear_right(self):
        for w in self.right.winfo_children():
            w.destroy()

    def build_empty(self):
        self.clear_right()
        ttk.Label(self.right, text='Select a party or project', font=('TkDefaultFont', 18, 'bold')).pack(pady=80)
        ttk.Label(self.right, text='Use + to create a party, or create a project from Projects.', foreground='#666').pack()

    def refresh_all(self):
        self.refresh_parties()
        self.refresh_projects()
        if self.selected_party:
            self.show_party(self.selected_party)
        elif self.selected_project:
            self.show_project(self.selected_project)

    def refresh_parties(self):
        for x in self.party_tree.get_children():
            self.party_tree.delete(x)
        q = self.party_search.get().lower()
        c = connect()
        rows = c.execute('SELECT * FROM parties WHERE is_group=0 ORDER BY name').fetchall()
        c.close()
        for r in rows:
            if not q or q in (r['name'] + ' ' + r['kind'] + ' ' + r['phone']).lower():
                self.party_tree.insert('', 'end', iid=str(r['id']), text=f"{r['name']}  ·  {r['kind']}")

    def refresh_projects(self):
        for x in self.project_tree.get_children():
            self.project_tree.delete(x)
        c = connect()
        rows = c.execute('SELECT * FROM projects ORDER BY name').fetchall()
        c.close()
        for r in rows:
            self.project_tree.insert('', 'end', iid=str(r['id']), text=r['name'])

    def party_selected(self, _=None):
        s = self.party_tree.selection()
        if s:
            self.selected_party = int(s[0])
            self.selected_project = None
            self.show_party(self.selected_party)

    def project_selected(self, _=None):
        s = self.project_tree.selection()
        if s:
            self.selected_project = int(s[0])
            self.selected_party = None
            self.show_project(self.selected_project)

    def add_party(self):
        self.party_dialog()

    def party_dialog(self, party=None):
        w = tk.Toplevel(self)
        w.title('Edit Party' if party else 'New Party')
        w.transient(self)
        w.grab_set()
        f = ttk.Frame(w, padding=18)
        f.pack(fill='both', expand=True)
        vars = {}
        for i, (lab, val) in enumerate([('Name', party['name'] if party else ''), ('Phone', party['phone'] if party else ''), ('Notes', party['notes'] if party else '')]):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky='w', pady=5)
            v = tk.StringVar(value=val)
            vars[lab] = v
            ttk.Entry(f, textvariable=v, width=42).grid(row=i, column=1, pady=5)
        ttk.Label(f, text='Type').grid(row=3, column=0, sticky='w', pady=5)
        kind = tk.StringVar(value=party['kind'] if party else 'Customer')
        ttk.Combobox(f, textvariable=kind, values=['Customer', 'Supplier', 'Staff', 'Partner', 'Other'], state='readonly').grid(row=3, column=1, sticky='ew')

        def save():
            if not vars['Name'].get().strip():
                messagebox.showwarning('Required', 'Name is required', parent=w)
                return
            c = connect()
            if party:
                c.execute('UPDATE parties SET name=?, kind=?, phone=?, notes=? WHERE id=?',
                          (vars['Name'].get().strip(), kind.get(), vars['Phone'].get(), vars['Notes'].get(), party['id']))
            else:
                c.execute('INSERT INTO parties(name, kind, phone, notes, created_at) VALUES(?,?,?,?,?)',
                          (vars['Name'].get().strip(), kind.get(), vars['Phone'].get(), vars['Notes'].get(), now()))
            c.commit()
            c.close()
            w.destroy()
            self.refresh_all()

        ttk.Button(f, text='Save', command=save).grid(row=4, column=1, sticky='e', pady=12)
        w.wait_window()

    def edit_party(self):
        if not self.selected_party:
            return
        c = connect()
        r = c.execute('SELECT * FROM parties WHERE id=?', (self.selected_party,)).fetchone()
        c.close()
        if r:
            self.party_dialog(r)

    def delete_party(self):
        if self.selected_party and messagebox.askyesno('Delete', 'Delete this party and its transactions?'):
            c = connect()
            c.execute('DELETE FROM parties WHERE id=?', (self.selected_party,))
            c.commit()
            c.close()
            self.selected_party = None
            self.build_empty()
            self.refresh_all()

    def show_party(self, pid):
        c = connect()
        p = c.execute('SELECT * FROM parties WHERE id=?', (pid,)).fetchone()
        tx = c.execute('SELECT t.*, pr.name project FROM transactions t LEFT JOIN projects pr ON pr.id=t.project_id WHERE t.party_id=? ORDER BY t.txn_date DESC, t.id DESC', (pid,)).fetchall()
        c.close()
        if not p:
            return
        self.clear_right()
        h = ttk.Frame(self.right, padding=(15, 12))
        h.pack(fill='x')
        ttk.Label(h, text=p['name'], font=('TkDefaultFont', 22, 'bold')).pack(side='left')
        ttk.Label(h, text=f"  {p['kind']}", foreground='#666').pack(side='left')
        ttk.Button(h, text='Edit', command=self.edit_party).pack(side='right')
        s = ttk.Frame(self.right, padding=12)
        s.pack(fill='x')
        rec = sum(r['amount'] for r in tx if r['direction'] == 'RECEIVABLE' and r['status'] == 'DUE')
        pay = sum(r['amount'] for r in tx if r['direction'] == 'PAYABLE' and r['status'] == 'DUE')
        self.card(s, 'Receivable', money(rec)).pack(side='left', fill='x', expand=True, padx=4)
        self.card(s, 'Payable', money(pay)).pack(side='left', fill='x', expand=True, padx=4)
        self.card(s, 'Net Position', money(rec - pay)).pack(side='left', fill='x', expand=True, padx=4)
        tb = ttk.Frame(self.right, padding=10)
        tb.pack(fill='x')
        ttk.Button(tb, text='+ Record Transaction', command=lambda: self.add_transaction(pid)).pack(side='left')
        ttk.Button(tb, text='Mark Selected Settled', command=lambda: self.settle_transaction(pid)).pack(side='left', padx=5)
        tree = ttk.Treeview(self.right, columns=('date', 'description', 'project', 'category', 'direction', 'amount', 'status'), show='headings')
        self.tx_tree = tree
        for col, title, width in [('date', 'Date', 95), ('description', 'Description', 260), ('project', 'Project', 150), ('category', 'Category', 120), ('direction', 'Type', 105), ('amount', 'Amount', 110), ('status', 'Status', 90)]:
            tree.heading(col, text=title)
            tree.column(col, width=width)
        tree.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        for r in tx:
            tree.insert('', 'end', iid=str(r['id']), values=(r['txn_date'], r['description'], r['project'] or '', r['category'], 'Receivable' if r['direction'] == 'RECEIVABLE' else 'Payable', money(r['amount']), r['status']))

    def card(self, parent, title, value):
        f = ttk.Frame(parent, relief='ridge', padding=10)
        ttk.Label(f, text=title, foreground='#666').pack()
        ttk.Label(f, text=value, font=('TkDefaultFont', 15, 'bold')).pack()
        return f

    def add_transaction(self, pid):
        c = connect()
        projects = c.execute('SELECT pr.* FROM projects pr JOIN project_members pm ON pm.project_id=pr.id WHERE pm.party_id=? ORDER BY pr.name', (pid,)).fetchall()
        c.close()
        w = tk.Toplevel(self)
        w.title('Record Transaction')
        w.transient(self)
        w.grab_set()
        f = ttk.Frame(w, padding=18)
        f.pack(fill='both', expand=True)
        datev = tk.StringVar(value=date.today().isoformat())
        desc = tk.StringVar()
        amount = tk.StringVar()
        direction = tk.StringVar(value='RECEIVABLE')
        category = tk.StringVar(value='General')
        project = tk.StringVar(value='No project')
        for i, (lab, var) in enumerate([('Date (YYYY-MM-DD)', datev), ('Description', desc), ('Amount', amount)]):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky='w', pady=5)
            ttk.Entry(f, textvariable=var, width=42).grid(row=i, column=1, pady=5)
        ttk.Label(f, text='Transaction means').grid(row=3, column=0, sticky='w', pady=5)
        ttk.Combobox(f, textvariable=direction, values=['RECEIVABLE', 'PAYABLE'], state='readonly').grid(row=3, column=1, sticky='ew')
        ttk.Label(f, text='Category').grid(row=4, column=0, sticky='w', pady=5)
        ttk.Combobox(f, textvariable=category, values=['General', 'Material', 'Labour', 'Advance', 'Payment', 'Expense', 'Income', 'Other']).grid(row=4, column=1, sticky='ew')
        ttk.Label(f, text='Project').grid(row=5, column=0, sticky='w', pady=5)
        ttk.Combobox(f, textvariable=project, values=['No project'] + [r['name'] for r in projects], state='readonly').grid(row=5, column=1, sticky='ew')

        def save():
            try:
                a = float(amount.get().replace(',', '').replace('₹', '').strip())
            except:
                messagebox.showwarning('Invalid amount', 'Enter a valid amount.', parent=w)
                return
            if a <= 0 or not desc.get().strip():
                messagebox.showwarning('Missing information', 'Description and positive amount are required.', parent=w)
                return
            pr = next((r['id'] for r in projects if r['name'] == project.get()), None)
            c = connect()
            c.execute('INSERT INTO transactions(party_id, project_id, txn_date, description, amount, direction, status, category, created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                      (pid, pr, datev.get(), desc.get().strip(), a, direction.get(), 'DUE', category.get(), now()))
            c.commit()
            c.close()
            w.destroy()
            self.show_party(pid)

        ttk.Button(f, text='Save Transaction', command=save).grid(row=6, column=1, sticky='e', pady=12)
        w.wait_window()

    def settle_transaction(self, pid):
        if not hasattr(self, 'tx_tree') or not self.tx_tree.selection():
            return
        c = connect()
        c.executemany("UPDATE transactions SET status='SETTLED' WHERE id=?", [(int(x),) for x in self.tx_tree.selection()])
        c.commit()
        c.close()
        self.show_party(pid)

    def add_project(self):
        w = tk.Toplevel(self)
        w.title('New Project')
        w.transient(self)
        w.grab_set()
        f = ttk.Frame(w, padding=18)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text='Project Name:').grid(row=0, column=0, sticky='w', pady=5)
        name_var = tk.StringVar()
        ttk.Entry(f, textvariable=name_var, width=30).grid(row=0, column=1, pady=5)
        
        def save():
            name = name_var.get().strip()
            if name:
                c = connect()
                c.execute('INSERT INTO projects(name, created_at) VALUES(?,?)', (name, now()))
                c.commit()
                c.close()
                w.destroy()
                self.refresh_all()

        ttk.Button(f, text='Add', command=save).grid(row=1, column=1, sticky='e', pady=10)
        w.wait_window()

    def show_project(self, pid):
        c = connect()
        p = c.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
        members = c.execute('SELECT pa.* FROM parties pa JOIN project_members pm ON pm.party_id=pa.id WHERE pm.project_id=? ORDER BY pa.name', (pid,)).fetchall()
        tx = c.execute('SELECT t.*, pa.name party FROM transactions t JOIN parties pa ON pa.id=t.party_id WHERE t.project_id=? ORDER BY t.txn_date DESC, t.id DESC', (pid,)).fetchall()
        c.close()
        self.clear_right()
        ttk.Label(self.right, text=p['name'], font=('TkDefaultFont', 22, 'bold')).pack(anchor='w', padx=15, pady=(15, 3))
        ttk.Label(self.right, text=f'{len(members)} parties • consolidated project ledger', foreground='#666').pack(anchor='w', padx=15)
        rec = sum(r['amount'] for r in tx if r['direction'] == 'RECEIVABLE' and r['status'] == 'DUE')
        pay = sum(r['amount'] for r in tx if r['direction'] == 'PAYABLE' and r['status'] == 'DUE')
        s = ttk.Frame(self.right, padding=12)
        s.pack(fill='x')
        self.card(s, 'Project Receivable', money(rec)).pack(side='left', fill='x', expand=True, padx=4)
        self.card(s, 'Project Payable', money(pay)).pack(side='left', fill='x', expand=True, padx=4)
        self.card(s, 'Project Net', money(rec - pay)).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Label(self.right, text='Project transactions', font=('TkDefaultFont', 13, 'bold')).pack(anchor='w', padx=15, pady=5)
        tree = ttk.Treeview(self.right, columns=('date', 'party', 'desc', 'type', 'amount', 'status'), show='headings')
        for col, title, w in [('date', 'Date', 95), ('party', 'Party', 150), ('desc', 'Description', 300), ('type', 'Type', 110), ('amount', 'Amount', 120), ('status', 'Status', 90)]:
            tree.heading(col, text=title)
            tree.column(col, width=w)
        tree.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        for r in tx:
            tree.insert('', 'end', values=(r['txn_date'], r['party'], r['description'], 'Receivable' if r['direction'] == 'RECEIVABLE' else 'Payable', money(r['amount']), r['status']))

    def manage_members(self):
        if not self.selected_project:
            return
        c = connect()
        ps = c.execute('SELECT * FROM parties ORDER BY name').fetchall()
        current = {r['party_id'] for r in c.execute('SELECT party_id FROM project_members WHERE project_id=?', (self.selected_project,)).fetchall()}
        c.close()
        w = tk.Toplevel(self)
        w.title('Project Members')
        w.transient(self)
        w.grab_set()
        f = ttk.Frame(w, padding=15)
        f.pack(fill='both', expand=True)
        vars = {}
        for r in ps:
            v = tk.BooleanVar(value=r['id'] in current)
            vars[r['id']] = v
            ttk.Checkbutton(f, text=f"{r['name']} · {r['kind']}", variable=v).pack(anchor='w')

        def save():
            c = connect()
            c.execute('DELETE FROM project_members WHERE project_id=?', (self.selected_project,))
            c.executemany('INSERT INTO project_members(project_id, party_id) VALUES(?,?)', [(self.selected_project, pid) for pid, v in vars.items() if v.get()])
            c.commit()
            c.close()
            w.destroy()
            self.refresh_projects()
            self.show_project(self.selected_project)

        ttk.Button(f, text='Save Members', command=save).pack(anchor='e', pady=10)
        w.wait_window()

    def delete_project(self):
        if self.selected_project and messagebox.askyesno('Delete Project', 'Delete project? Transactions remain but lose their project link.'):
            c = connect()
            c.execute('DELETE FROM projects WHERE id=?', (self.selected_project,))
            c.commit()
            c.close()
            self.selected_project = None
            self.build_empty()
            self.refresh_all()

    def backup(self):
        if DB.exists():
            target = BACKUPS / f"partychat_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(DB, target)
            messagebox.showinfo('Backup created', f'Backup saved to:\n{target}')

    def restore(self):
        path = filedialog.askopenfilename(title='Choose SQLite backup', initialdir=str(BACKUPS), filetypes=[('SQLite DB', '*.db'), ('All files', '*.*')])
        if path and messagebox.askyesno('Restore', 'Restore this backup? Current data will first be backed up.'):
            self.backup()
            shutil.copy2(path, DB)
            messagebox.showinfo('Restored', 'Data restored. The app will now close; reopen it.')
            self.destroy()

    def export_csv(self):
        c = connect()
        folder = EXPORTS / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        folder.mkdir()
        for fn, q in [('parties.csv', 'SELECT * FROM parties'), ('projects.csv', 'SELECT * FROM projects'), ('project_members.csv', 'SELECT * FROM project_members'), ('transactions.csv', 'SELECT * FROM transactions')]:
            rows = c.execute(q).fetchall()
            with open(folder / fn, 'w', newline='', encoding='utf-8') as f:
                wr = csv.writer(f)
                wr.writerow(rows[0].keys() if rows else [])
                wr.writerows([tuple(r) for r in rows])
        c.close()
        messagebox.showinfo('Export complete', f'CSV files saved to:\n{folder}')

    def change_password(self):
        w = tk.Toplevel(self)
        w.title('Change Password')
        w.transient(self)
        w.grab_set()
        f = ttk.Frame(w, padding=18)
        f.pack(fill='both', expand=True)

        ttk.Label(f, text='Current Password:').grid(row=0, column=0, sticky='w', pady=5)
        old_v = ttk.Entry(f, show='*', width=30)
        old_v.grid(row=0, column=1, pady=5)

        ttk.Label(f, text='New Password:').grid(row=1, column=0, sticky='w', pady=5)
        new_v = ttk.Entry(f, show='*', width=30)
        new_v.grid(row=1, column=1, pady=5)

        ttk.Label(f, text='Confirm New:').grid(row=2, column=0, sticky='w', pady=5)
        conf_v = ttk.Entry(f, show='*', width=30)
        conf_v.grid(row=2, column=1, pady=5)

        def save():
            if not verify_password(old_v.get()):
                messagebox.showerror('Error', 'Current password incorrect.', parent=w)
                return
            if not new_v.get():
                messagebox.showwarning('Required', 'New password cannot be empty.', parent=w)
                return
            if new_v.get() != conf_v.get():
                messagebox.showerror('Error', 'New passwords do not match.', parent=w)
                return
            set_password(new_v.get())
            messagebox.showinfo('Done', 'Password changed successfully.', parent=w)
            w.destroy()

        ttk.Button(f, text='Update Password', command=save).grid(row=3, column=1, sticky='e', pady=10)
        w.wait_window()

if __name__ == '__main__':
    init_db()
    app = App()
    app.mainloop()
