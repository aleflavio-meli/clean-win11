#!/usr/bin/env python3
"""cleanpc - limpeza estilo CleanMyMac para Windows (somente stdlib).

Uso:
  python cleanpc.py scan                  # analisa e mostra o que pode ser liberado (nada é apagado)
  python cleanpc.py clean                 # simula a limpeza (dry-run)
  python cleanpc.py clean --apply         # apaga de verdade (pede confirmação)
  python cleanpc.py large --min-mb 500    # lista maiores arquivos do perfil do usuário
  python cleanpc.py memory                # libera working set dos processos (flush de RAM)
  python cleanpc.py all --apply           # clean + memory + dns + lixeira

Segurança: dry-run por padrão; arquivos grandes só são listados (nunca apagados
automaticamente); arquivos em uso são ignorados; só apaga arquivos com mais de
--days dias (padrão 2) nas pastas de lixo conhecidas.
"""
import argparse
import ctypes
import heapq
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ENV = os.environ
LOCAL = Path(ENV.get("LOCALAPPDATA", ""))
ROAMING = Path(ENV.get("APPDATA", ""))
WINDIR = Path(ENV.get("WINDIR", r"C:\Windows"))

# categoria -> (lista de pastas, precisa de admin)
TARGETS = {
    "Temp do usuário": ([Path(ENV.get("TEMP", LOCAL / "Temp"))], False),
    "Temp do Windows": ([WINDIR / "Temp"], True),
    "Cache de miniaturas": ([LOCAL / "Microsoft/Windows/Explorer"], False),
    "Relatórios de erro (WER)": ([LOCAL / "Microsoft/Windows/WER", Path(ENV.get("PROGRAMDATA", "")) / "Microsoft/Windows/WER"], False),
    "Windows Update (download)": ([WINDIR / "SoftwareDistribution/Download"], True),
    "Prefetch": ([WINDIR / "Prefetch"], True),
    "Logs do Windows": ([WINDIR / "Logs/CBS"], True),
    "Cache Chrome": ([LOCAL / "Google/Chrome/User Data/Default/Cache", LOCAL / "Google/Chrome/User Data/Default/Code Cache"], False),
    "Cache Edge": ([LOCAL / "Microsoft/Edge/User Data/Default/Cache", LOCAL / "Microsoft/Edge/User Data/Default/Code Cache"], False),
    "Cache Firefox": ([LOCAL / "Mozilla/Firefox/Profiles"], False),
    "Cache pip/npm": ([LOCAL / "pip/Cache", ROAMING / "npm-cache", LOCAL / "npm-cache"], False),
    "Cache Teams/Slack": ([ROAMING / "Microsoft/Teams/Cache", ROAMING / "Slack/Cache", ROAMING / "Slack/Code Cache"], False),
}

SKIP_DIRS = {"windows", "program files", "program files (x86)", "$recycle.bin",
             "system volume information", "appdata\\local\\packages"}


def fmt(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:,.1f} {u}"
        n /= 1024
    return f"{n:,.1f} PB"


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def iter_files(root, min_age_s=0):
    """Gera (path, size) de todos os arquivos sob root com idade >= min_age_s."""
    now = time.time()
    stack = [str(root)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            st = e.stat(follow_symlinks=False)
                            if now - st.st_mtime >= min_age_s:
                                yield e.path, st.st_size
                    except OSError:
                        pass
        except OSError:
            pass


def scan_junk(days):
    admin = is_admin()
    results = {}
    for name, (paths, need_admin) in TARGETS.items():
        files, total = [], 0
        if need_admin and not admin:
            results[name] = (files, -1)
            continue
        for p in paths:
            if not p.exists():
                continue
            for f, s in iter_files(p, days * 86400):
                files.append(f)
                total += s
        results[name] = (files, total)
    return results


def recycle_bin_size():
    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                    ("i64NumItems", ctypes.c_longlong)]
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(info)
    try:
        ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        return info.i64Size
    except Exception:
        return 0


def empty_recycle_bin():
    # 0x7 = sem confirmação, sem progresso, sem som
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)


def print_scan(results):
    print(f"\n{'Categoria':<30}{'Arquivos':>10}{'Tamanho':>14}")
    print("-" * 54)
    total = 0
    for name, (files, size) in results.items():
        if size < 0:
            print(f"{name:<30}{'—':>10}{'(requer admin)':>14}")
            continue
        total += size
        print(f"{name:<30}{len(files):>10}{fmt(size):>14}")
    rb = recycle_bin_size()
    total += rb
    print(f"{'Lixeira':<30}{'':>10}{fmt(rb):>14}")
    print("-" * 54)
    print(f"{'TOTAL liberável':<40}{fmt(total):>14}")


def do_clean(results, apply):
    freed = 0
    for name, (files, size) in results.items():
        if size <= 0:
            continue
        if not apply:
            freed += size
            continue
        for f in files:
            try:
                s = os.path.getsize(f)
                os.remove(f)
                freed += s
            except OSError:
                pass  # em uso / sem permissão
    print(f"\n{'Liberado' if apply else 'Seria liberado'}: {fmt(freed)}")
    return freed


def find_large(min_mb, top, root=None):
    """Retorna [(size, path)] dos maiores arquivos sob root, do maior para o menor."""
    root = root or Path.home()
    heap = []
    min_b = min_mb * 1024 * 1024
    for f, s in iter_files(root):
        if "\\appdata\\local\\packages" in f.lower():
            continue
        if s >= min_b:
            heapq.heappush(heap, (s, f))
            if len(heap) > top:
                heapq.heappop(heap)
    return sorted(heap, reverse=True)


def cmd_large(min_mb, top):
    root = Path.home()
    heap = find_large(min_mb, top, root)
    print(f"\nMaiores arquivos (>= {min_mb} MB) em {root}:\n")
    for s, f in heap:
        print(f"{fmt(s):>12}  {f}")
    if not heap:
        print("Nenhum arquivo encontrado.")
    print("\nRevise manualmente — estes arquivos NÃO são apagados pelo script.")


def mem_status():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys, m.ullTotalPhys


def flush_memory():
    """Reduz o working set de todos os processos acessíveis (EmptyWorkingSet)."""
    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    before, total = mem_status()
    pids = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed))
    n_ok = 0
    for pid in pids[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if pid == 0:
            continue
        h = k32.OpenProcess(0x0100 | 0x0400, False, pid)  # SET_QUOTA | QUERY_INFORMATION
        if h:
            if psapi.EmptyWorkingSet(h):
                n_ok += 1
            k32.CloseHandle(h)
    time.sleep(1)
    after, _ = mem_status()
    print(f"\nRAM livre: {fmt(before)} -> {fmt(after)} de {fmt(total)} "
          f"({n_ok} processos ajustados{'' if is_admin() else '; rode como admin para mais'})")


def flush_dns():
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
    print("Cache DNS limpo.")


def confirm(msg):
    return input(f"{msg} [s/N] ").strip().lower() in ("s", "sim", "y", "yes")


def main():
    if sys.platform != "win32":
        sys.exit("Este script é para Windows.")
    ap = argparse.ArgumentParser(description="Limpeza estilo CleanMyMac para Windows")
    ap.add_argument("command", choices=["scan", "clean", "large", "memory", "all"])
    ap.add_argument("--apply", action="store_true", help="executa de verdade (sem isso é dry-run)")
    ap.add_argument("--days", type=int, default=2, help="só apaga arquivos mais velhos que N dias")
    ap.add_argument("--min-mb", type=int, default=500)
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()

    c = a.command
    if c == "large":
        return cmd_large(a.min_mb, a.top)
    if c == "memory":
        return flush_memory()

    results = scan_junk(a.days)
    print_scan(results)
    if c == "scan":
        return
    if a.apply and not confirm("\nApagar os arquivos acima?"):
        return print("Cancelado.")
    do_clean(results, a.apply)
    if c == "all":
        if a.apply:
            empty_recycle_bin()
            print("Lixeira esvaziada.")
        flush_dns()
        flush_memory()
    if not a.apply:
        print("Dry-run: nada foi apagado. Use --apply para executar.")


if __name__ == "__main__":
    main()
