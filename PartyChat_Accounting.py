#!/usr/bin/env python3
import csv, hashlib, secrets, shutil, sqlite3
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME='PartyChat Accounting'; VERSION='3.0'
BASE=Path.home()/'PartyChat Accounting'; DB=BASE/'partychat.db'; BACKUPS=BASE/'Backups'; EXPORTS=BASE/'Exports'
for p in (BASE,BACKUPS,EXPORTS): p.mkdir(parents=True,exist_ok=True)
ITER=250_000

def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def money(x): return f'₹{x:,.2f}'
def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init_db():
    c=connect(); c.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS parties(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'Customer',phone TEXT DEFAULT '',notes TEXT DEFAULT '',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,notes TEXT DEFAULT '',created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS project_members(project_id INTEGER NOT NULL,party_id INTEGER NOT NULL,PRIMARY KEY(project_id,party_id),FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,FOREIGN KEY(party_id) REFERENCES parties(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,party_id INTEGER NOT NULL,project_id INTEGER,txn_date TEXT NOT NULL,description TEXT NOT NULL,amount REAL NOT NULL,direction TEXT NOT NULL CHECK(direction IN ('RECEIVABLE','PAYABLE')),status TEXT NOT NULL DEFAULT 'DUE' CHECK(status IN ('DUE','SETTLED')),category TEXT NOT NULL DEFAULT 'General',created_at TEXT NOT NULL,FOREIGN KEY(party_id) REFERENCES parties(id) ON DELETE CASCADE,FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL);
    '''); c.commit(); c.close()

def password_value():
    c=connect(); r=c.execute("SELECT value FROM settings WHERE key='password_hash'").fetchone(); c.close(); return r['value'] if r else None

def set_password(pw):
    salt=secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac('sha256',pw.encode(),salt,ITER)
    c=connect(); c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('password_hash',?)",(salt.hex()+':'+digest.hex(),)); c.commit(); c.close()

def verify_password(pw):
    v=password_value()
    if not v:return False
    try:
        s,d=v.split(':',1); x=hashlib.pbkdf2_hmac('sha256',pw.encode(),bytes.fromhex(s),ITER); return secrets.compare_digest(x.hex(),d)
    except Exception:return False

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP_NAME); self.geometry('1250x800'); self.minsize(1050,680); self.selected_party=None; self.selected_project=None
        self.protocol('WM_DELETE_WINDOW',self.destroy); self.style=ttk.Style(self)
        try:self.style.theme_use('clam')
        except tk.TclError:pass
        self.style.configure('Treeview',rowheight=30); self.style.configure('TButton',padding=(10,6)); self.style.configure('TNotebook.Tab',padding=(14,7))
        self.bind('<Command-q>',lambda e:self.destroy()); self.bind('<Control-q>',lambda e:self.destroy())
        self.login() if password_value() else self.setup()
    def clear(self):
        for w in self.winfo_children():w.destroy()
    def setup(self):
        self.clear(); f=ttk.Frame(self,padding=40); f.place(relx=.5,rely=.5,anchor='center')
        ttk.Label(f,text='Welcome to PartyChat Accounting',font=('TkDefaultFont',22,'bold')).pack(pady=(0,8)); ttk.Label(f,text='Local-first accounting for parties and projects.').pack(pady=(0,22))
        ttk.Label(f,text='Create master password').pack(anchor='w'); a=ttk.Entry(f,show='*',width=36); a.pack(pady=(4,10)); ttk.Label(f,text='Confirm password').pack(anchor='w'); b=ttk.Entry(f,show='*',width=36); b.pack(pady=(4,18))
        def go():
            if len(a.get())<4:messagebox.showwarning('Password','Use at least 4 characters.',parent=self);return
            if a.get()!=b.get():messagebox.showerror('Password','Passwords do not match.',parent=self);return
            set_password(a.get()); self.main()
        ttk.Button(f,text='Create & Open',command=go).pack(fill='x'); a.focus(); b.bind('<Return>',lambda e:go())
    def login(self):
        self.clear(); f=ttk.Frame(self,padding=40); f.place(relx=.5,rely=.5,anchor='center'); ttk.Label(f,text=APP_NAME,font=('TkDefaultFont',22,'bold')).pack(pady=(0,8)); ttk.Label(f,text='Enter master password').pack(pady=(0,20)); p=ttk.Entry(f,show='*',width=36); p.pack(pady=(0,15))
        def go():
            if verify_password(p.get()):self.main()
            else:messagebox.showerror('Login failed','Incorrect password.',parent=self);p.delete(0,'end');p.focus()
        ttk.Button(f,text='Unlock',command=go).pack(fill='x'); p.focus(); p.bind('<Return>',lambda e:go())
    def main(self):
        self.clear(); self.selected_party=None; self.selected_project=None
        top=ttk.Frame(self,padding=(12,10));top.pack(fill='x');ttk.Label(top,text=APP_NAME,font=('TkDefaultFont',20,'bold')).pack(side='left');ttk.Label(top,text=f'  v{VERSION} • Local & Private').pack(side='left',padx=8)
        for label,cmd in [('Backup',self.backup),('Restore',self.restore),('Export CSV',self.export_csv),('Change Password',self.change_password)]:ttk.Button(top,text=label,command=cmd).pack(side='right',padx=3)
        pan=ttk.Panedwindow(self,orient='horizontal');pan.pack(fill='both',expand=True,padx=10,pady=(0,10));left=ttk.Frame(pan,width=330);self.right=ttk.Frame(pan);pan.add(left,weight=0);pan.add(self.right,weight=1)
        nb=ttk.Notebook(left);nb.pack(fill='both',expand=True);pt=ttk.Frame(nb);pr=ttk.Frame(nb);nb.add(pt,text=' Parties ');nb.add(pr,text=' Projects ')
        sf=ttk.Frame(pt,padding=7);sf.pack(fill='x');self.party_search=tk.StringVar();e=ttk.Entry(sf,textvariable=self.party_search);e.pack(side='left',fill='x',expand=True);ttk.Button(sf,text='+',width=3,command=self.add_party).pack(side='right',padx=(5,0));self.party_search.trace_add('write',lambda *_:self.refresh_parties())
        self.party_tree=ttk.Treeview(pt,show='tree');self.party_tree.pack(fill='both',expand=True,padx=7,pady=7);self.party_tree.bind('<<TreeviewSelect>>',self.party_selected);ttk.Button(pt,text='Edit Party',command=self.edit_party).pack(fill='x',padx=7,pady=3);ttk.Button(pt,text='Delete Party',command=self.delete_party).pack(fill='x',padx=7,pady=(0,7))
        ttk.Button(pr,text='+ New Project',command=self.add_project).pack(fill='x',padx=7,pady=7);self.project_tree=ttk.Treeview(pr,show='tree');self.project_tree.pack(fill='both',expand=True,padx=7,pady=7);self.project_tree.bind('<<TreeviewSelect>>',self.project_selected);ttk.Button(pr,text='Manage Members',command=self.manage_members).pack(fill='x',padx=7,pady=3);ttk.Button(pr,text='Delete Project',command=self.delete_project).pack(fill='x',padx=7,pady=(0,7))
        self.dashboard();self.refresh_lists()
    def clear_right(self):
        for w in self.right.winfo_children():w.destroy()
    def card(self,p,t,v):
        f=ttk.Frame(p,relief='ridge',padding=14);ttk.Label(f,text=t).pack();ttk.Label(f,text=v,font=('TkDefaultFont',15,'bold')).pack(pady=(3,0));return f
    def tree_columns(self,t,cols):
        for c,n,w in cols:t.heading(c,text=n);t.column(c,width=w,anchor='w')
    def dashboard(self):
        self.clear_right();c=connect();n=c.execute('SELECT COUNT(*) n FROM parties').fetchone()['n'];pr=c.execute('SELECT COUNT(*) n FROM projects').fetchone()['n'];d=c.execute("SELECT COALESCE(SUM(CASE WHEN direction='RECEIVABLE' AND status='DUE' THEN amount ELSE 0 END),0) rec,COALESCE(SUM(CASE WHEN direction='PAYABLE' AND status='DUE' THEN amount ELSE 0 END),0) pay FROM transactions").fetchone();recent=c.execute('SELECT t.*,p.name party FROM transactions t JOIN parties p ON p.id=t.party_id ORDER BY t.txn_date DESC,t.id DESC LIMIT 12').fetchall();c.close()
        ttk.Label(self.right,text='Dashboard',font=('TkDefaultFont',24,'bold')).pack(anchor='w',padx=20,pady=(20,4));ttk.Label(self.right,text='Your current receivables, payables and activity.').pack(anchor='w',padx=20,pady=(0,15));row=ttk.Frame(self.right,padding=10);row.pack(fill='x')
        for title,val in [('Receivable',d['rec']),('Payable',d['pay']),('Net Position',d['rec']-d['pay']),('Parties',n)]:self.card(row,title,money(val) if title!='Parties' else str(val)).pack(side='left',fill='x',expand=True,padx=5)
        ttk.Label(self.right,text=f'{pr} project(s) • latest transactions',font=('TkDefaultFont',14,'bold')).pack(anchor='w',padx=20,pady=(15,8));t=ttk.Treeview(self.right,columns=('date','party','desc','type','amount','status'),show='headings');self.tree_columns(t,[('date','Date',100),('party','Party',170),('desc','Description',330),('type','Type',110),('amount','Amount',130),('status','Status',100)]);t.pack(fill='both',expand=True,padx=20,pady=(0,20))
        for r in recent:t.insert('', 'end',values=(r['txn_date'],r['party'],r['description'],r['direction'].title(),money(r['amount']),r['status']))
    def refresh_lists(self):self.refresh_parties();self.refresh_projects()
    def refresh_parties(self):
        for x in self.party_tree.get_children():self.party_tree.delete(x)
        q=self.party_search.get().lower();c=connect();rows=c.execute('SELECT * FROM parties ORDER BY name COLLATE NOCASE').fetchall();c.close()
        for r in rows:
            if not q or q in f"{r['name']} {r['kind']} {r['phone']}".lower():self.party_tree.insert('', 'end',iid=str(r['id']),text=f"{r['name']}  ·  {r['kind']}")
    def refresh_projects(self):
        for x in self.project_tree.get_children():self.project_tree.delete(x)
        c=connect();rows=c.execute('SELECT * FROM projects ORDER BY name COLLATE NOCASE').fetchall();c.close()
        for r in rows:self.project_tree.insert('', 'end',iid=str(r['id']),text=r['name'])
    def party_selected(self,e=None):
        s=self.party_tree.selection()
        if s:self.selected_party=int(s[0]);self.selected_project=None;self.show_party(self.selected_party)
    def project_selected(self,e=None):
        s=self.project_tree.selection()
        if s:self.selected_project=int(s[0]);self.selected_party=None;self.show_project(self.selected_project)
    def show_party(self,pid):
        c=connect();p=c.execute('SELECT * FROM parties WHERE id=?',(pid,)).fetchone();tx=c.execute('SELECT t.*,pr.name project FROM transactions t LEFT JOIN projects pr ON pr.id=t.project_id WHERE t.party_id=? ORDER BY t.txn_date DESC,t.id DESC',(pid,)).fetchall();c.close()
        if not p:return
        self.clear_right();h=ttk.Frame(self.right,padding=(15,12));h.pack(fill='x');ttk.Label(h,text=p['name'],font=('TkDefaultFont',22,'bold')).pack(side='left');ttk.Label(h,text=f"  {p['kind']} {p['phone']}",foreground='#666').pack(side='left',padx=8);ttk.Button(h,text='Edit',command=self.edit_party).pack(side='right');s=ttk.Frame(self.right,padding=10);s.pack(fill='x');rec=sum(r['amount'] for r in tx if r['direction']=='RECEIVABLE' and r['status']=='DUE');pay=sum(r['amount'] for r in tx if r['direction']=='PAYABLE' and r['status']=='DUE')
        for a,b in [('Receivable',rec),('Payable',pay),('Net Position',rec-pay)]:self.card(s,a,money(b)).pack(side='left',fill='x',expand=True,padx=5)
        bar=ttk.Frame(self.right,padding=10);bar.pack(fill='x');ttk.Button(bar,text='+ Record Transaction',command=lambda:self.transaction_dialog(pid)).pack(side='left');ttk.Button(bar,text='Edit Selected',command=lambda:self.edit_transaction(pid)).pack(side='left',padx=5);ttk.Button(bar,text='Mark Settled',command=lambda:self.settle(pid)).pack(side='left');ttk.Button(bar,text='Delete Selected',command=lambda:self.delete_transaction(pid)).pack(side='left',padx=5)
        self.tx_tree=ttk.Treeview(self.right,columns=('date','desc','project','cat','type','amount','status'),show='headings');self.tree_columns(self.tx_tree,[('date','Date',100),('desc','Description',290),('project','Project',160),('cat','Category',120),('type','Type',110),('amount','Amount',130),('status','Status',100)]);self.tx_tree.pack(fill='both',expand=True,padx=15,pady=(0,15))
        for r in tx:self.tx_tree.insert('', 'end',iid=str(r['id']),values=(r['txn_date'],r['description'],r['project'] or '',r['category'],r['direction'].title(),money(r['amount']),r['status']))
    def party_dialog(self,party=None):
        w=tk.Toplevel(self);w.title('Edit Party' if party else 'New Party');w.transient(self);w.grab_set();f=ttk.Frame(w,padding=20);f.pack(fill='both',expand=True);fields=[('Name',party['name'] if party else ''),('Phone',party['phone'] if party else ''),('Notes',party['notes'] if party else '')];vs={}
        for i,(lab,val) in enumerate(fields):ttk.Label(f,text=lab).grid(row=i,column=0,sticky='w',pady=6);v=tk.StringVar(value=val);vs[lab]=v;ttk.Entry(f,textvariable=v,width=42).grid(row=i,column=1,pady=6)
        ttk.Label(f,text='Type').grid(row=3,column=0,sticky='w',pady=6);kind=tk.StringVar(value=party['kind'] if party else 'Customer');ttk.Combobox(f,textvariable=kind,values=['Customer','Supplier','Staff','Partner','Other'],state='readonly').grid(row=3,column=1,sticky='ew')
        def save():
            if not vs['Name'].get().strip():messagebox.showwarning('Required','Name is required.',parent=w);return
            c=connect();args=(vs['Name'].get().strip(),kind.get(),vs['Phone'].get().strip(),vs['Notes'].get().strip())
            if party:c.execute('UPDATE parties SET name=?,kind=?,phone=?,notes=? WHERE id=?',args+(party['id'],))
            else:c.execute('INSERT INTO parties(name,kind,phone,notes,created_at) VALUES(?,?,?,?,?)',args+(now(),))
            c.commit();c.close();w.destroy();self.refresh_lists();self.show_party(party['id']) if party else self.dashboard()
        ttk.Button(f,text='Save',command=save).grid(row=4,column=1,sticky='e',pady=14);w.wait_window()
    def add_party(self):self.party_dialog()
    def edit_party(self):
        if not self.selected_party:return
        c=connect();r=c.execute('SELECT * FROM parties WHERE id=?',(self.selected_party,)).fetchone();c.close()
        if r:self.party_dialog(r)
    def delete_party(self):
        if self.selected_party and messagebox.askyesno('Delete party','Delete this party and all its transactions?',parent=self):
            c=connect();c.execute('DELETE FROM parties WHERE id=?',(self.selected_party,));c.commit();c.close();self.selected_party=None;self.dashboard();self.refresh_lists()
    def transaction_dialog(self,pid,existing=None):
        c=connect();projects=c.execute('SELECT pr.* FROM projects pr JOIN project_members pm ON pm.project_id=pr.id WHERE pm.party_id=? ORDER BY pr.name',(pid,)).fetchall();c.close();w=tk.Toplevel(self);w.title('Edit Transaction' if existing else 'Record Transaction');w.transient(self);w.grab_set();f=ttk.Frame(w,padding=20);f.pack(fill='both',expand=True);dv=tk.StringVar(value=existing['txn_date'] if existing else date.today().isoformat());desc=tk.StringVar(value=existing['description'] if existing else '');amt=tk.StringVar(value=str(existing['amount']) if existing else '');direction=tk.StringVar(value=existing['direction'] if existing else 'RECEIVABLE');cat=tk.StringVar(value=existing['category'] if existing else 'General');project=tk.StringVar(value='No project')
        if existing and existing['project_id']:
            for r in projects:
                if r['id']==existing['project_id']:project.set(r['name'])
        for i,(lab,v) in enumerate([('Date (YYYY-MM-DD)',dv),('Description',desc),('Amount (₹)',amt)]):ttk.Label(f,text=lab).grid(row=i,column=0,sticky='w',pady=6);ttk.Entry(f,textvariable=v,width=42).grid(row=i,column=1,pady=6)
        for i,(lab,var,vals) in enumerate([('This transaction is',direction,['RECEIVABLE','PAYABLE']),('Category',cat,['General','Material','Labour','Advance','Payment','Expense','Income','Other'])],start=3):ttk.Label(f,text=lab).grid(row=i,column=0,sticky='w',pady=6);ttk.Combobox(f,textvariable=var,values=vals,state='readonly').grid(row=i,column=1,sticky='ew')
        ttk.Label(f,text='Project').grid(row=5,column=0,sticky='w',pady=6);ttk.Combobox(f,textvariable=project,values=['No project']+[r['name'] for r in projects],state='readonly').grid(row=5,column=1,sticky='ew')
        def save():
            try:a=float(amt.get().replace(',','').replace('₹','').strip())
            except:messagebox.showwarning('Amount','Enter a valid amount.',parent=w);return
            if a<=0 or not desc.get().strip():messagebox.showwarning('Missing information','Description and positive amount are required.',parent=w);return
            try:datetime.strptime(dv.get(),'%Y-%m-%d')
            except:messagebox.showwarning('Date','Use YYYY-MM-DD.',parent=w);return
            pr=next((r['id'] for r in projects if r['name']==project.get()),None);c=connect()
            if existing:c.execute('UPDATE transactions SET project_id=?,txn_date=?,description=?,amount=?,direction=?,category=? WHERE id=?',(pr,dv.get(),desc.get().strip(),a,direction.get(),cat.get(),existing['id']))
            else:c.execute('INSERT INTO transactions(party_id,project_id,txn_date,description,amount,direction,status,category,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(pid,pr,dv.get(),desc.get().strip(),a,direction.get(),'DUE',cat.get(),now()))
            c.commit();c.close();w.destroy();self.show_party(pid)
        ttk.Button(f,text='Save Transaction',command=save).grid(row=6,column=1,sticky='e',pady=14);w.wait_window()
    def edit_transaction(self,pid):
        if not hasattr(self,'tx_tree') or len(self.tx_tree.selection())!=1:return
        c=connect();r=c.execute('SELECT * FROM transactions WHERE id=?',(int(self.tx_tree.selection()[0]),)).fetchone();c.close()
        if r:self.transaction_dialog(pid,r)
    def settle(self,pid):
        ids=self.tx_tree.selection() if hasattr(self,'tx_tree') else []
        if not ids:return
        c=connect();c.executemany("UPDATE transactions SET status='SETTLED' WHERE id=?",[(int(x),) for x in ids]);c.commit();c.close();self.show_party(pid)
    def delete_transaction(self,pid):
        ids=self.tx_tree.selection() if hasattr(self,'tx_tree') else []
        if ids and messagebox.askyesno('Delete','Delete selected transaction(s)?',parent=self):
            c=connect();c.executemany('DELETE FROM transactions WHERE id=?',[(int(x),) for x in ids]);c.commit();c.close();self.show_party(pid)
    def add_project(self):
        w=tk.Toplevel(self);w.title('New Project');w.transient(self);w.grab_set();f=ttk.Frame(w,padding=20);f.pack(fill='both',expand=True);v=tk.StringVar();ttk.Label(f,text='Project name').pack(anchor='w');ttk.Entry(f,textvariable=v,width=42).pack(pady=8)
        def save():
            if not v.get().strip():return
            c=connect();c.execute('INSERT INTO projects(name,created_at) VALUES(?,?)',(v.get().strip(),now()));c.commit();c.close();w.destroy();self.refresh_projects()
        ttk.Button(f,text='Create Project',command=save).pack(anchor='e',pady=8);w.wait_window()
    def show_project(self,pid):
        c=connect();p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone();members=c.execute('SELECT pa.* FROM parties pa JOIN project_members pm ON pm.party_id=pa.id WHERE pm.project_id=? ORDER BY pa.name',(pid,)).fetchall();tx=c.execute('SELECT t.*,pa.name party FROM transactions t JOIN parties pa ON pa.id=t.party_id WHERE t.project_id=? ORDER BY t.txn_date DESC,t.id DESC',(pid,)).fetchall();c.close()
        if not p:return
        self.clear_right();ttk.Label(self.right,text=p['name'],font=('TkDefaultFont',23,'bold')).pack(anchor='w',padx=20,pady=(18,3));ttk.Label(self.right,text=f'{len(members)} member(s) • consolidated project ledger').pack(anchor='w',padx=20);s=ttk.Frame(self.right,padding=10);s.pack(fill='x');rec=sum(r['amount'] for r in tx if r['direction']=='RECEIVABLE' and r['status']=='DUE');pay=sum(r['amount'] for r in tx if r['direction']=='PAYABLE' and r['status']=='DUE')
        for a,b in [('Receivable',rec),('Payable',pay),('Net',rec-pay)]:self.card(s,a,money(b)).pack(side='left',fill='x',expand=True,padx=5)
        ttk.Button(self.right,text='Manage Members',command=self.manage_members).pack(anchor='w',padx=20,pady=8);ttk.Label(self.right,text='Transactions',font=('TkDefaultFont',13,'bold')).pack(anchor='w',padx=20,pady=(8,6));t=ttk.Treeview(self.right,columns=('date','party','desc','type','amount','status'),show='headings');self.tree_columns(t,[('date','Date',100),('party','Party',170),('desc','Description',330),('type','Type',110),('amount','Amount',130),('status','Status',100)]);t.pack(fill='both',expand=True,padx=15,pady=(0,15))
        for r in tx:t.insert('', 'end',values=(r['txn_date'],r['party'],r['description'],r['direction'].title(),money(r['amount']),r['status']))
    def manage_members(self):
        if not self.selected_project:return
        c=connect();ps=c.execute('SELECT * FROM parties ORDER BY name').fetchall();current={r['party_id'] for r in c.execute('SELECT party_id FROM project_members WHERE project_id=?',(self.selected_project,)).fetchall()};c.close();w=tk.Toplevel(self);w.title('Project Members');w.transient(self);w.grab_set();f=ttk.Frame(w,padding=18);f.pack(fill='both',expand=True);vs={}
        for r in ps:v=tk.BooleanVar(value=r['id'] in current);vs[r['id']]=v;ttk.Checkbutton(f,text=f"{r['name']} · {r['kind']}",variable=v).pack(anchor='w',pady=2)
        def save():
            c=connect();c.execute('DELETE FROM project_members WHERE project_id=?',(self.selected_project,));c.executemany('INSERT INTO project_members(project_id,party_id) VALUES(?,?)',[(self.selected_project,pid) for pid,v in vs.items() if v.get()]);c.commit();c.close();w.destroy();self.show_project(self.selected_project)
        ttk.Button(f,text='Save Members',command=save).pack(anchor='e',pady=10);w.wait_window()
    def delete_project(self):
        if self.selected_project and messagebox.askyesno('Delete Project','Delete this project? Its transactions remain unassigned.',parent=self):
            c=connect();c.execute('DELETE FROM projects WHERE id=?',(self.selected_project,));c.commit();c.close();self.selected_project=None;self.dashboard();self.refresh_projects()
    def backup(self):
        if DB.exists():
            target=BACKUPS/f'partychat_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db';shutil.copy2(DB,target);messagebox.showinfo('Backup complete',f'Saved to:\n{target}',parent=self)
    def restore(self):
        path=filedialog.askopenfilename(title='Choose PartyChat backup',initialdir=str(BACKUPS),filetypes=[('SQLite database','*.db')])
        if not path:return
        if messagebox.askyesno('Restore','Current data will be backed up first. Restore selected backup?',parent=self):
            self.backup();shutil.copy2(path,DB);messagebox.showinfo('Restored','Restore complete. Reopen the application.',parent=self);self.destroy()
    def export_csv(self):
        folder=EXPORTS/f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}';folder.mkdir(parents=True,exist_ok=True);c=connect()
        for fn,q in [('parties.csv','SELECT * FROM parties'),('projects.csv','SELECT * FROM projects'),('project_members.csv','SELECT * FROM project_members'),('transactions.csv','SELECT * FROM transactions')]:
            rows=c.execute(q).fetchall()
            with open(folder/fn,'w',newline='',encoding='utf-8') as f:
                w=csv.writer(f);w.writerow(rows[0].keys() if rows else []);w.writerows([tuple(r) for r in rows])
        c.close();messagebox.showinfo('Export complete',f'CSV files saved to:\n{folder}',parent=self)
    def change_password(self):
        w=tk.Toplevel(self);w.title('Change Password');w.transient(self);w.grab_set();f=ttk.Frame(w,padding=20);f.pack(fill='both',expand=True);old=ttk.Entry(f,show='*',width=34);new=ttk.Entry(f,show='*',width=34);conf=ttk.Entry(f,show='*',width=34)
        for i,(lab,e) in enumerate([('Current password',old),('New password',new),('Confirm new password',conf)]):ttk.Label(f,text=lab).grid(row=i,column=0,sticky='w',pady=6);e.grid(row=i,column=1,pady=6)
        def save():
            if not verify_password(old.get()):messagebox.showerror('Password','Current password is incorrect.',parent=w);return
            if len(new.get())<4 or new.get()!=conf.get():messagebox.showerror('Password','New passwords must match and contain at least 4 characters.',parent=w);return
            set_password(new.get());w.destroy();messagebox.showinfo('Password','Password changed.',parent=self)
        ttk.Button(f,text='Update Password',command=save).grid(row=3,column=1,sticky='e',pady=12);w.wait_window()

if __name__=='__main__':
    init_db()
    try: App().mainloop()
    except Exception as e:
        try: messagebox.showerror(APP_NAME,f'Application error:\n{e}')
        except Exception: pass
        raise
