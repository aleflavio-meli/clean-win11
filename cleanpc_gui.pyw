"""cleanpc GUI - interface tkinter para o cleanpc.py (dê dois cliques para abrir)."""
import ctypes
import io
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from contextlib import redirect_stdout
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleanpc as cp  # noqa: E402

BG, PANEL, ACCENT, TEXT, MUTED = "#1e1f29", "#2a2c3a", "#7c5cff", "#f2f2f7", "#9a9cb0"


def send_to_recycle_bin(path):
    """Move um arquivo para a Lixeira (recuperável)."""
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = path + "\0"
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CleanPC")
        self.geometry("980x640")
        self.minsize(820, 520)
        self.configure(bg=BG)
        self.q = queue.Queue()
        self.results = {}
        self.busy = False
        self._style()
        self._layout()
        self.after(100, self._poll)
        self.show("junk")
        self.update_mem()

    # ---------- visual ----------
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, font=("Segoe UI", 10))
        s.configure("Side.TButton", background=PANEL, foreground=TEXT, borderwidth=0,
                    padding=(16, 12), anchor="w", font=("Segoe UI", 11))
        s.map("Side.TButton", background=[("active", "#3a3d52")])
        s.configure("Sel.TButton", background=ACCENT, foreground="white", borderwidth=0,
                    padding=(16, 12), anchor="w", font=("Segoe UI", 11, "bold"))
        s.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0,
                    padding=(18, 9), font=("Segoe UI", 10, "bold"))
        s.map("Accent.TButton", background=[("active", "#6a4cf0"), ("disabled", "#4a4a5a")])
        s.configure("Ghost.TButton", background=PANEL, foreground=TEXT, borderwidth=0, padding=(14, 9))
        s.map("Ghost.TButton", background=[("active", "#3a3d52")])
        s.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL,
                    rowheight=28, borderwidth=0)
        s.configure("Treeview.Heading", background=BG, foreground=MUTED, borderwidth=0,
                    font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", "#4b3fa0")])
        s.configure("Big.TLabel", font=("Segoe UI", 22, "bold"))
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL, borderwidth=0)
        s.configure("TCheckbutton", background=BG, foreground=TEXT)
        s.configure("TSpinbox", arrowsize=12)

    def _layout(self):
        side = tk.Frame(self, bg=PANEL, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="✦ CleanPC", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=18, pady=(20, 18))
        self.nav = {}
        for key, label in [("junk", "🧹  Lixo do sistema"), ("large", "📦  Arquivos grandes"),
                           ("mem", "⚡  Memória e DNS")]:
            b = ttk.Button(side, text=label, style="Side.TButton", command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=10, pady=2)
            self.nav[key] = b
        adm = "Executando como admin ✓" if cp.is_admin() else "Sem privilégios de admin"
        tk.Label(side, text=adm, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="bottom", pady=(0, 14))
        if not cp.is_admin():
            ttk.Button(side, text="Reabrir como admin", style="Ghost.TButton",
                       command=self.relaunch_admin).pack(side="bottom", fill="x", padx=10, pady=6)

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=22, pady=18)
        self.pages = {"junk": self._page_junk(main), "large": self._page_large(main),
                      "mem": self._page_mem(main)}

        bottom = tk.Frame(main, bg=BG)
        bottom.pack(side="bottom", fill="x", pady=(10, 0))
        self.status = ttk.Label(bottom, text="Pronto.", style="Muted.TLabel")
        self.status.pack(side="left")
        self.prog = ttk.Progressbar(bottom, mode="indeterminate", length=180)
        self.prog.pack(side="right")

    def _header(self, parent, title, subtitle):
        ttk.Label(parent, text=title, style="Big.TLabel").pack(anchor="w")
        ttk.Label(parent, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(2, 12))

    def _page_junk(self, parent):
        f = tk.Frame(parent, bg=BG)
        self._header(f, "Lixo do sistema",
                     "Caches, temporários e logs antigos. Selecione as categorias e clique em Limpar.")
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        self.btn_scan = ttk.Button(bar, text="Analisar", style="Accent.TButton", command=self.scan)
        self.btn_scan.pack(side="left")
        self.btn_clean = ttk.Button(bar, text="Limpar selecionados", style="Ghost.TButton",
                                    command=self.clean, state="disabled")
        self.btn_clean.pack(side="left", padx=8)
        self.rb_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Esvaziar Lixeira", variable=self.rb_var,
                        command=self._update_total).pack(side="left", padx=8)
        ttk.Label(bar, text="Mais antigos que (dias):", style="Muted.TLabel").pack(side="left", padx=(12, 4))
        self.days = tk.IntVar(value=2)
        ttk.Spinbox(bar, from_=0, to=90, width=4, textvariable=self.days).pack(side="left")
        self.total_lbl = ttk.Label(bar, text="", font=("Segoe UI", 13, "bold"), foreground=ACCENT)
        self.total_lbl.pack(side="right")

        self.tree = ttk.Treeview(f, columns=("files", "size"), selectmode="extended")
        self.tree.heading("#0", text="CATEGORIA", anchor="w")
        self.tree.heading("files", text="ARQUIVOS", anchor="e")
        self.tree.heading("size", text="TAMANHO", anchor="e")
        self.tree.column("#0", width=360)
        self.tree.column("files", width=110, anchor="e")
        self.tree.column("size", width=140, anchor="e")
        self.tree.tag_configure("off", foreground=MUTED)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_total())
        return f

    def _page_large(self, parent):
        f = tk.Frame(parent, bg=BG)
        self._header(f, "Arquivos grandes",
                     f"Maiores arquivos em {Path.home()}. Revise antes de remover — vão para a Lixeira.")
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Mínimo (MB):", style="Muted.TLabel").pack(side="left")
        self.min_mb = tk.IntVar(value=500)
        ttk.Spinbox(bar, from_=50, to=50000, increment=50, width=7,
                    textvariable=self.min_mb).pack(side="left", padx=(4, 12))
        self.btn_large = ttk.Button(bar, text="Buscar", style="Accent.TButton", command=self.scan_large)
        self.btn_large.pack(side="left")
        ttk.Button(bar, text="Mostrar no Explorer", style="Ghost.TButton",
                   command=self.reveal).pack(side="left", padx=8)
        ttk.Button(bar, text="Mover para Lixeira", style="Ghost.TButton",
                   command=self.trash_large).pack(side="left")

        self.ltree = ttk.Treeview(f, columns=("size", "path"), show="headings", selectmode="extended")
        self.ltree.heading("size", text="TAMANHO", anchor="e")
        self.ltree.heading("path", text="CAMINHO", anchor="w")
        self.ltree.column("size", width=110, anchor="e", stretch=False)
        self.ltree.column("path", width=600)
        self.ltree.pack(fill="both", expand=True)
        self.ltree.bind("<Double-1>", lambda e: self.reveal())
        return f

    def _page_mem(self, parent):
        f = tk.Frame(parent, bg=BG)
        self._header(f, "Memória e DNS",
                     "Libera o working set dos processos e limpa o cache DNS. O ganho de RAM é temporário.")
        card = tk.Frame(f, bg=PANEL)
        card.pack(fill="x", pady=(0, 14))
        self.mem_lbl = tk.Label(card, text="", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold"))
        self.mem_lbl.pack(anchor="w", padx=18, pady=(16, 6))
        self.mem_bar = ttk.Progressbar(card, mode="determinate", maximum=100)
        self.mem_bar.pack(fill="x", padx=18, pady=(0, 16))
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x")
        self.btn_mem = ttk.Button(bar, text="Liberar memória", style="Accent.TButton", command=self.flush_mem)
        self.btn_mem.pack(side="left")
        ttk.Button(bar, text="Limpar cache DNS", style="Ghost.TButton",
                   command=self.flush_dns).pack(side="left", padx=8)
        self.log = tk.Text(f, bg=PANEL, fg=TEXT, relief="flat", height=10, font=("Consolas", 10),
                           insertbackground=TEXT, padx=10, pady=8)
        self.log.pack(fill="both", expand=True, pady=(14, 0))
        return f

    # ---------- navegação / util ----------
    def show(self, key):
        for k, p in self.pages.items():
            p.pack_forget()
            self.nav[k].configure(style="Side.TButton")
        self.pages[key].pack(fill="both", expand=True)
        self.nav[key].configure(style="Sel.TButton")

    def update_mem(self):
        avail, total = cp.mem_status()
        used = total - avail
        self.mem_lbl.config(text=f"RAM em uso: {cp.fmt(used)} de {cp.fmt(total)}  ·  livre {cp.fmt(avail)}")
        self.mem_bar["value"] = used / total * 100 if total else 0

    def write_log(self, text):
        self.log.insert("end", text.strip() + "\n")
        self.log.see("end")

    def run_bg(self, label, fn, done):
        if self.busy:
            return
        self.busy = True
        self.status.config(text=label)
        self.prog.start(12)

        def worker():
            try:
                self.q.put((done, fn(), None))
            except Exception as e:  # noqa: BLE001
                self.q.put((done, None, e))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, res, err = self.q.get_nowait()
                self.busy = False
                self.prog.stop()
                if err:
                    self.status.config(text="Erro.")
                    messagebox.showerror("CleanPC", str(err))
                else:
                    done(res)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def relaunch_admin(self):
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, f'"{Path(__file__).resolve()}"', None, 1)
        self.destroy()

    # ---------- lixo ----------
    def scan(self):
        self.btn_clean.config(state="disabled")
        days = self.days.get()
        self.run_bg("Analisando…", lambda: (cp.scan_junk(days), cp.recycle_bin_size()), self._scan_done)

    def _scan_done(self, res):
        self.results, rb = res
        self.rb_size = rb
        self.tree.delete(*self.tree.get_children())
        for name, (files, size) in sorted(self.results.items(), key=lambda kv: -kv[1][1]):
            if size < 0:
                self.tree.insert("", "end", iid=name, text=name, values=("—", "requer admin"), tags=("off",))
            else:
                self.tree.insert("", "end", iid=name, text=name, values=(f"{len(files):,}", cp.fmt(size)))
        selectable = [n for n, (_, s) in self.results.items() if s > 0]
        self.tree.selection_set(selectable)
        self.btn_clean.config(state="normal")
        self.status.config(text=f"Análise concluída. Lixeira: {cp.fmt(rb)}.")
        self._update_total()

    def _selected(self):
        return {n: self.results[n] for n in self.tree.selection() if self.results.get(n, ([], -1))[1] > 0}

    def _update_total(self):
        if not self.results:
            return
        total = sum(s for _, s in self._selected().values())
        if self.rb_var.get():
            total += getattr(self, "rb_size", 0)
        self.total_lbl.config(text=f"{cp.fmt(total)} liberáveis")

    def clean(self):
        sel = self._selected()
        if not sel and not self.rb_var.get():
            return
        n = sum(len(f) for f, _ in sel.values())
        if not messagebox.askyesno("CleanPC", f"Apagar {n:,} arquivos de {len(sel)} categorias"
                                   f"{' e esvaziar a Lixeira' if self.rb_var.get() else ''}?"):
            return
        empty_rb = self.rb_var.get()

        def work():
            buf = io.StringIO()
            with redirect_stdout(buf):
                freed = cp.do_clean(sel, apply=True)
            if empty_rb:
                freed += cp.recycle_bin_size()
                cp.empty_recycle_bin()
            return freed
        self.run_bg("Limpando…", work, self._clean_done)

    def _clean_done(self, freed):
        messagebox.showinfo("CleanPC", f"Pronto! {cp.fmt(freed)} liberados.\n"
                                       "Arquivos em uso foram ignorados.")
        self.scan()

    # ---------- arquivos grandes ----------
    def scan_large(self):
        mb = self.min_mb.get()
        self.run_bg("Procurando arquivos grandes…", lambda: cp.find_large(mb, 200), self._large_done)

    def _large_done(self, items):
        self.ltree.delete(*self.ltree.get_children())
        for s, p in items:
            self.ltree.insert("", "end", values=(cp.fmt(s), p))
        total = sum(s for s, _ in items)
        self.status.config(text=f"{len(items)} arquivos encontrados · {cp.fmt(total)} no total.")

    def _sel_paths(self):
        return [self.ltree.item(i, "values")[1] for i in self.ltree.selection()]

    def reveal(self):
        paths = self._sel_paths()
        if paths:
            subprocess.Popen(["explorer", "/select,", paths[0]])

    def trash_large(self):
        paths = self._sel_paths()
        if not paths:
            return
        if not messagebox.askyesno("CleanPC", f"Mover {len(paths)} arquivo(s) para a Lixeira?\n\n"
                                   + "\n".join(paths[:8]) + ("\n…" if len(paths) > 8 else "")):
            return
        failed = [p for p in paths if not send_to_recycle_bin(p)]
        for i in list(self.ltree.selection()):
            if self.ltree.item(i, "values")[1] not in failed:
                self.ltree.delete(i)
        if failed:
            messagebox.showwarning("CleanPC", "Não foi possível mover:\n" + "\n".join(failed))
        self.status.config(text=f"{len(paths) - len(failed)} arquivo(s) movidos para a Lixeira.")

    # ---------- memória ----------
    def flush_mem(self):
        def work():
            buf = io.StringIO()
            with redirect_stdout(buf):
                cp.flush_memory()
            return buf.getvalue()
        self.run_bg("Liberando memória…", work, self._mem_done)

    def _mem_done(self, out):
        self.write_log(out)
        self.update_mem()
        self.status.config(text="Memória liberada.")

    def flush_dns(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cp.flush_dns()
        self.write_log(buf.getvalue())


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido em telas HiDPI
    except Exception:
        pass
    App().mainloop()
