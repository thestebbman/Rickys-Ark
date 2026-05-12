"""
Memory Ark Desktop Interface

Standalone tkinter GUI — no web browser required.
Uses the same workspace, audit log, permissions, and mode files as app.py.

Run with:
    python desktop_app.py
"""

import hashlib
import json
import os
import tkinter as tk
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

# ── paths (same as app.py) ────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
WORKSPACE = BASE_DIR / "workspace"
SYSTEM_DIR = BASE_DIR / "system"
AUDIT_LOG = SYSTEM_DIR / "logs" / "audit.jsonl"
PERMISSIONS_FILE = SYSTEM_DIR / "permissions.json"
MODE_FILE = SYSTEM_DIR / "mode.json"

ZONES = ["human", "ai", "shared", "debate"]

MAX_SEARCH_RESULTS = 50
SNIPPET_CONTEXT_CHARS = 40

ZONE_LABELS = {
    "human":  "🔵 Human",
    "ai":     "🟣 AI",
    "shared": "🟢 Shared",
    "debate": "🟡 Debate",
}

MODE_LABELS = {
    "normal":   "✅ Normal",
    "test":     "🧪 Test",
    "acting":   "🎭 Acting",
    "baseline": "🔄 Reset Baseline",
}


# ── data helpers (identical logic to app.py) ──────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_audit(actor, action, zone, filename="", outcome="allowed", notes=""):
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": now_iso(),
        "actor": actor,
        "action": action,
        "zone": zone,
        "filename": filename,
        "outcome": outcome,
        "notes": notes,
        "annotation": "",
    }
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def read_audit():
    if not AUDIT_LOG.exists():
        return []
    entries = []
    with open(AUDIT_LOG, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return list(reversed(entries))  # newest first


def rewrite_audit(entries):
    """Rewrite the audit log — used only for annotation updates."""
    with open(AUDIT_LOG, "w", encoding="utf-8") as fh:
        for e in reversed(entries):
            fh.write(json.dumps(e) + "\n")


def load_permissions():
    defaults = {
        "zones": {
            z: {"ai_read": True, "ai_write": z == "ai", "ai_delete": z == "ai"}
            for z in ZONES
        },
        "devices": {
            "camera": False,
            "microphone": False,
            "clipboard": False,
            "network": False,
            "screen_reader": False,
        },
    }
    if PERMISSIONS_FILE.exists():
        try:
            return json.loads(PERMISSIONS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return defaults


def save_permissions(perms):
    PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERMISSIONS_FILE.write_text(json.dumps(perms, indent=2), encoding="utf-8")


def load_mode():
    default = {"current": "normal", "history": []}
    if MODE_FILE.exists():
        try:
            return json.loads(MODE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_mode(data):
    MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def zone_path(zone):
    if zone not in ZONES:
        raise ValueError(f"Unknown zone: {zone}")
    return WORKSPACE / zone


def safe_resolve(zone, rel):
    """Resolve a relative path inside a zone, preventing directory traversal."""
    base = zone_path(zone).resolve()
    raw_parts = Path(rel).parts
    clean_parts = []
    for part in raw_parts:
        if part in ("..", ".", "") or part.startswith("/") or part.startswith("\\"):
            raise ValueError(f"Unsafe path component '{part}' in '{rel}'")
        clean_parts.append(part)
    if not clean_parts:
        raise ValueError(f"Empty or invalid path '{rel}'")
    result = base.joinpath(*clean_parts)
    try:
        result.resolve().relative_to(base)
    except ValueError:
        raise ValueError(f"Path '{rel}' escapes zone '{zone}'")
    return result


def list_files_in_zone(zone):
    zp = zone_path(zone)
    files = []
    for p in sorted(zp.rglob("*")):
        if p.is_file():
            rel = p.relative_to(zp)
            files.append({"name": p.name, "path": str(rel), "zone": zone})
    return files


def bootstrap():
    """Ensure workspace and system dirs exist with seed files."""
    for zone in ZONES:
        zone_path(zone).mkdir(parents=True, exist_ok=True)

    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    (SYSTEM_DIR / "logs").mkdir(parents=True, exist_ok=True)

    if not PERMISSIONS_FILE.exists():
        save_permissions(load_permissions())
    if not MODE_FILE.exists():
        save_mode(load_mode())

    welcome = WORKSPACE / "human" / "notes" / "welcome.txt"
    if not welcome.exists():
        welcome.parent.mkdir(parents=True, exist_ok=True)
        welcome.write_text(
            "Welcome to the Memory Ark Interface.\n\n"
            "This is your Human zone — only you can delete files here.\n"
            "The AI can read (and copy) your files when permitted.\n\n"
            "Use the interface to:\n"
            "  • Create and organize notes, directives, character files\n"
            "  • Toggle what the AI is allowed to access\n"
            "  • Monitor and audit all access attempts\n"
            "  • Switch between Normal, Test, and Acting modes\n"
            "  • Reset to a safe baseline at any time\n",
            encoding="utf-8",
        )

    ai_note = WORKSPACE / "ai" / "notes.txt"
    if not ai_note.exists():
        ai_note.parent.mkdir(parents=True, exist_ok=True)
        ai_note.write_text(
            "AI Working Notes\n"
            "================\n\n"
            "This file belongs to the AI zone.\n"
            "The AI uses this space for working notes, questions, and checklists.\n\n"
            "Questions I have:\n"
            "- (none yet)\n\n"
            "Checklist:\n"
            "- [ ] Review welcome.txt in human/notes\n",
            encoding="utf-8",
        )


# ── main application ──────────────────────────────────────────────────────────

class ArkDesktop:
    def __init__(self, root):
        self.root = root
        self.root.title("🌊 Memory Ark — Desktop Interface")
        self.root.geometry("1150x760")
        self.root.minsize(820, 560)

        self._current_zone = None
        self._current_rel_path = None
        self._editing = False
        self._audit_filter = tk.StringVar(value="all")
        self._mode_var = tk.StringVar(value="normal")
        self._search_var = tk.StringVar()
        self._audit_entries = []

        self._build_ui()
        self._refresh_tree()
        self._refresh_mode_indicator()
        self._refresh_audit()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # top bar
        top = tk.Frame(self.root, bg="#1e2a3a", pady=6, padx=10)
        top.pack(side=tk.TOP, fill=tk.X)

        tk.Label(
            top, text="🌊 Memory Ark", bg="#1e2a3a", fg="white",
            font=("Helvetica", 14, "bold"),
        ).pack(side=tk.LEFT)

        self._mode_lbl = tk.Label(
            top, text="", bg="#1e2a3a", fg="#aaddff", font=("Helvetica", 11),
        )
        self._mode_lbl.pack(side=tk.LEFT, padx=16)

        # search (right side of top bar)
        tk.Button(
            top, text="🔍 Search", command=self._do_search,
            bg="#2a4060", fg="white", relief=tk.FLAT, padx=6,
        ).pack(side=tk.RIGHT)
        self._search_entry = tk.Entry(top, textvariable=self._search_var, width=22)
        self._search_entry.pack(side=tk.RIGHT, padx=(0, 4))
        self._search_entry.bind("<Return>", lambda _e: self._do_search())

        tk.Button(
            top, text="+ New File", command=self._new_file_dialog,
            bg="#2a6040", fg="white", relief=tk.FLAT, padx=8,
        ).pack(side=tk.RIGHT, padx=8)

        # main paned area
        main_pane = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL, sashwidth=6, bg="#c0c0c0",
        )
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # left: file tree
        left = tk.Frame(main_pane, bg="#f0f0f0", width=220)
        main_pane.add(left, minsize=160)
        tk.Label(
            left, text="Workspace Zones", bg="#f0f0f0",
            font=("Helvetica", 10, "bold"), pady=4,
        ).pack(fill=tk.X)

        tree_frame = tk.Frame(left)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self._tree = ttk.Treeview(tree_frame, selectmode="browse")
        self._tree.heading("#0", text="Files")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # right: notebook
        right = tk.Frame(main_pane)
        main_pane.add(right, minsize=420)
        self._notebook = ttk.Notebook(right)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        self._build_file_tab()
        self._build_permissions_tab()
        self._build_mode_tab()

        # bottom: audit log
        audit_frame = tk.LabelFrame(self.root, text="Audit Log", padx=4, pady=4)
        audit_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 4))

        audit_toolbar = tk.Frame(audit_frame)
        audit_toolbar.pack(fill=tk.X)
        tk.Label(audit_toolbar, text="Filter:").pack(side=tk.LEFT)
        for val, label in [("all", "All"), ("denied", "Denied only"), ("ai", "AI only")]:
            tk.Radiobutton(
                audit_toolbar, text=label, variable=self._audit_filter,
                value=val, command=self._refresh_audit,
            ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            audit_toolbar, text="↻ Refresh", command=self._refresh_audit,
        ).pack(side=tk.LEFT, padx=8)
        tk.Button(
            audit_toolbar, text="✏ Annotate selected", command=self._annotate_audit,
        ).pack(side=tk.LEFT)

        audit_tree_frame = tk.Frame(audit_frame)
        audit_tree_frame.pack(fill=tk.X)

        cols = ("time", "actor", "action", "zone", "file", "outcome", "notes", "annotation")
        self._audit_tree = ttk.Treeview(
            audit_tree_frame, columns=cols, show="headings", height=6,
        )
        col_widths = {
            "time": 130, "actor": 60, "action": 90, "zone": 70,
            "file": 160, "outcome": 70, "notes": 200, "annotation": 160,
        }
        for col in cols:
            self._audit_tree.heading(col, text=col.capitalize())
            self._audit_tree.column(col, width=col_widths.get(col, 80), stretch=False)

        asb = ttk.Scrollbar(audit_tree_frame, orient="vertical", command=self._audit_tree.yview)
        self._audit_tree.configure(yscrollcommand=asb.set)
        ahsb = ttk.Scrollbar(audit_tree_frame, orient="horizontal", command=self._audit_tree.xview)
        self._audit_tree.configure(xscrollcommand=ahsb.set)
        asb.pack(side=tk.RIGHT, fill=tk.Y)
        ahsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._audit_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_file_tab(self):
        tab = tk.Frame(self._notebook)
        self._notebook.add(tab, text="📄 File")

        header = tk.Frame(tab)
        header.pack(fill=tk.X, padx=6, pady=4)

        self._file_title = tk.Label(
            header, text="(no file selected)",
            font=("Helvetica", 10, "bold"), anchor="w",
        )
        self._file_title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._btn_delete = tk.Button(
            header, text="🗑 Delete", command=self._delete_file, state=tk.DISABLED,
        )
        self._btn_copy = tk.Button(
            header, text="📋 Copy to…", command=self._copy_file_dialog, state=tk.DISABLED,
        )
        self._btn_cancel = tk.Button(
            header, text="✖ Cancel", command=self._cancel_edit, state=tk.DISABLED,
        )
        self._btn_save = tk.Button(
            header, text="💾 Save", command=self._save_file, state=tk.DISABLED,
        )
        self._btn_edit = tk.Button(
            header, text="✏ Edit", command=self._start_edit, state=tk.DISABLED,
        )
        for btn in (self._btn_delete, self._btn_copy, self._btn_cancel,
                    self._btn_save, self._btn_edit):
            btn.pack(side=tk.RIGHT, padx=2)

        txt_frame = tk.Frame(tab)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._file_text = tk.Text(
            txt_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("Courier", 10), relief=tk.FLAT, bg="#fafafa", undo=True,
        )
        fvsb = ttk.Scrollbar(txt_frame, orient="vertical", command=self._file_text.yview)
        self._file_text.configure(yscrollcommand=fvsb.set)
        fvsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._file_text.pack(fill=tk.BOTH, expand=True)

    def _build_permissions_tab(self):
        tab = tk.Frame(self._notebook)
        self._notebook.add(tab, text="🔐 Permissions")

        canvas = tk.Canvas(tab, borderwidth=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        outer = tk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=outer, anchor="nw")

        def _on_frame_resize(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

        outer.bind("<Configure>", _on_frame_resize)

        tk.Label(
            outer, text="Zone Permissions (AI access)",
            font=("Helvetica", 10, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(8, 4))

        for col, heading in enumerate(("Zone", "AI Read", "AI Write", "AI Delete")):
            tk.Label(outer, text=heading, font=("Helvetica", 9, "bold")).grid(
                row=1, column=col, padx=8, pady=2,
            )

        self._perm_vars = {}
        for i, zone in enumerate(ZONES):
            row = i + 2
            tk.Label(outer, text=ZONE_LABELS[zone]).grid(
                row=row, column=0, sticky="w", padx=8, pady=3,
            )
            vars_ = {}
            for j, perm in enumerate(("ai_read", "ai_write", "ai_delete")):
                v = tk.BooleanVar()
                tk.Checkbutton(outer, variable=v).grid(row=row, column=j + 1, padx=8)
                vars_[perm] = v
            self._perm_vars[zone] = vars_

        sep_row = len(ZONES) + 3
        ttk.Separator(outer, orient="horizontal").grid(
            row=sep_row, column=0, columnspan=4, sticky="ew", pady=8,
        )
        tk.Label(
            outer, text="Device Permissions (AI access)",
            font=("Helvetica", 10, "bold"),
        ).grid(row=sep_row + 1, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 4))

        self._device_vars = {}
        devices = ["camera", "microphone", "clipboard", "network", "screen_reader"]
        for k, dev in enumerate(devices):
            v = tk.BooleanVar()
            tk.Checkbutton(
                outer, text=dev.replace("_", " ").title(), variable=v,
            ).grid(row=sep_row + 2 + k, column=0, columnspan=2, sticky="w", padx=8)
            self._device_vars[dev] = v

        btn_row = sep_row + 2 + len(devices) + 1
        tk.Button(
            outer, text="💾 Save Permissions", command=self._save_permissions,
        ).grid(row=btn_row, column=0, columnspan=2, sticky="w", padx=8, pady=10)
        tk.Button(
            outer, text="↻ Reload", command=self._load_permissions_into_ui,
        ).grid(row=btn_row, column=2, columnspan=2, sticky="e", padx=8, pady=10)

        self._load_permissions_into_ui()

    def _build_mode_tab(self):
        tab = tk.Frame(self._notebook)
        self._notebook.add(tab, text="⚙️ Mode")

        f = tk.Frame(tab)
        f.pack(padx=20, pady=16, anchor="nw")

        tk.Label(
            f, text="Current Mode", font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")

        for mode, label in MODE_LABELS.items():
            tk.Radiobutton(
                f, text=label, variable=self._mode_var, value=mode,
                font=("Helvetica", 10),
            ).pack(anchor="w", pady=2)

        tk.Button(
            f, text="Apply Mode", command=self._apply_mode,
            bg="#2a4060", fg="white", padx=10,
        ).pack(anchor="w", pady=10)

        tk.Label(tab, text="Recent mode changes:", font=("Helvetica", 9, "italic")).pack(
            anchor="w", padx=20,
        )
        self._mode_history_box = tk.Text(
            tab, height=8, state=tk.DISABLED, font=("Courier", 9), bg="#f8f8f8",
        )
        self._mode_history_box.pack(fill=tk.X, padx=10, pady=(0, 10))

    # ── tree ─────────────────────────────────────────────────────────────────

    def _refresh_tree(self, select_zone=None, select_path=None):
        self._tree.delete(*self._tree.get_children())
        for zone in ZONES:
            zone_id = self._tree.insert(
                "", "end", iid=f"zone:{zone}",
                text=ZONE_LABELS[zone], open=True,
            )
            for f in list_files_in_zone(zone):
                self._tree.insert(
                    zone_id, "end",
                    iid=f"file:{zone}:{f['path']}",
                    text=f"  {f['path']}",
                )
        if select_zone and select_path:
            iid = f"file:{select_zone}:{select_path}"
            try:
                self._tree.selection_set(iid)
                self._tree.see(iid)
            except tk.TclError:
                pass

    def _on_tree_select(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith("file:"):
            parts = iid.split(":", 2)  # ["file", zone, rel_path]
            if len(parts) == 3:
                _, zone, rel = parts
                self._load_file(zone, rel)

    # ── file tab ─────────────────────────────────────────────────────────────

    def _load_file(self, zone, rel_path):
        self._cancel_edit()
        self._current_zone = zone
        self._current_rel_path = rel_path
        try:
            fpath = safe_resolve(zone, rel_path)
            content = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = "[Binary file — cannot display as text]"
        except ValueError as exc:
            content = f"[Path error: {exc}]"
        except OSError as exc:
            content = f"[Error reading file: {exc}]"

        write_audit("human", "read", zone, rel_path, "allowed")
        self._file_title.config(text=f"[{ZONE_LABELS[zone]}]  {rel_path}")
        self._set_text(content)
        self._btn_edit.config(state=tk.NORMAL)
        self._btn_copy.config(state=tk.NORMAL)
        self._btn_delete.config(state=tk.NORMAL)
        self._btn_save.config(state=tk.DISABLED)
        self._btn_cancel.config(state=tk.DISABLED)
        self._notebook.select(0)
        self._refresh_audit()

    def _set_text(self, content):
        self._file_text.config(state=tk.NORMAL)
        self._file_text.delete("1.0", tk.END)
        self._file_text.insert("1.0", content)
        self._file_text.config(state=tk.DISABLED)

    def _start_edit(self):
        if not self._current_zone:
            return
        self._editing = True
        self._file_text.config(
            state=tk.NORMAL, bg="#fffef0",
            highlightbackground="#f0a000", highlightthickness=2,
        )
        self._btn_edit.config(state=tk.DISABLED)
        self._btn_save.config(state=tk.NORMAL)
        self._btn_cancel.config(state=tk.NORMAL)
        self._btn_copy.config(state=tk.DISABLED)
        self._btn_delete.config(state=tk.DISABLED)

    def _save_file(self):
        if not self._current_zone or not self._current_rel_path:
            return
        content = self._file_text.get("1.0", tk.END)
        # tk.Text always appends a trailing newline — strip exactly one
        if content.endswith("\n"):
            content = content[:-1]
        try:
            fpath = safe_resolve(self._current_zone, self._current_rel_path)
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
            write_audit("human", "write", self._current_zone, self._current_rel_path, "allowed")
            self._cancel_edit()
            self._refresh_tree(self._current_zone, self._current_rel_path)
            self._refresh_audit()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Save Error", str(exc))

    def _cancel_edit(self):
        self._editing = False
        self._file_text.config(
            state=tk.DISABLED, bg="#fafafa",
            highlightbackground="#d0d0d0", highlightthickness=1,
        )
        has_file = bool(self._current_zone)
        self._btn_edit.config(state=tk.NORMAL if has_file else tk.DISABLED)
        self._btn_save.config(state=tk.DISABLED)
        self._btn_cancel.config(state=tk.DISABLED)
        self._btn_copy.config(state=tk.NORMAL if has_file else tk.DISABLED)
        self._btn_delete.config(state=tk.NORMAL if has_file else tk.DISABLED)

    def _delete_file(self):
        if not self._current_zone or not self._current_rel_path:
            return
        if not messagebox.askyesno(
            "Delete File",
            f"Delete  {self._current_rel_path}  from  {self._current_zone}?\n"
            "A tombstone record will be created.",
        ):
            return
        try:
            fpath = safe_resolve(self._current_zone, self._current_rel_path)
            tombstone = {
                "original_path": self._current_rel_path,
                "zone": self._current_zone,
                "deleted_by": "human",
                "deleted_at": now_iso(),
            }
            ts_dir = WORKSPACE / "debate" / "tombstones"
            ts_dir.mkdir(parents=True, exist_ok=True)
            path_hash = hashlib.sha256(
                f"{self._current_zone}/{self._current_rel_path}".encode()
            ).hexdigest()[:12]
            ts_name = (
                f"tombstone-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                f"-{path_hash}.json"
            )
            (ts_dir / ts_name).write_text(json.dumps(tombstone, indent=2), encoding="utf-8")
            fpath.unlink()
            write_audit(
                "human", "delete", self._current_zone, self._current_rel_path,
                "allowed", "Tombstone created",
            )
            self._current_zone = None
            self._current_rel_path = None
            self._file_title.config(text="(no file selected)")
            self._set_text("")
            for btn in (self._btn_edit, self._btn_save, self._btn_cancel,
                        self._btn_copy, self._btn_delete):
                btn.config(state=tk.DISABLED)
            self._refresh_tree()
            self._refresh_audit()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Delete Error", str(exc))

    def _copy_file_dialog(self):
        if not self._current_zone or not self._current_rel_path:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Copy File To…")
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Destination zone:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        dst_zone_var = tk.StringVar(value="shared")
        ttk.Combobox(
            dlg, textvariable=dst_zone_var, values=ZONES, state="readonly", width=12,
        ).grid(row=0, column=1, padx=10, pady=6)

        tk.Label(dlg, text="Destination path:").grid(row=1, column=0, sticky="w", padx=10)
        dst_path_var = tk.StringVar(value=self._current_rel_path)
        tk.Entry(dlg, textvariable=dst_path_var, width=32).grid(row=1, column=1, padx=10, pady=4)

        def do_copy():
            dst_zone = dst_zone_var.get()
            dst_path = dst_path_var.get().strip()
            if not dst_path:
                messagebox.showerror("Error", "Destination path cannot be empty.", parent=dlg)
                return
            try:
                src_fpath = safe_resolve(self._current_zone, self._current_rel_path)
                dst_fpath = safe_resolve(dst_zone, dst_path)
                content = src_fpath.read_text(encoding="utf-8")
                provenance = (
                    f"[Copied from {self._current_zone}/{self._current_rel_path}"
                    f" by human at {now_iso()}]\n\n"
                )
                dst_fpath.parent.mkdir(parents=True, exist_ok=True)
                dst_fpath.write_text(provenance + content, encoding="utf-8")
                write_audit(
                    "human", "copy", dst_zone, dst_path, "allowed",
                    f"Copied from {self._current_zone}/{self._current_rel_path}",
                )
                dlg.destroy()
                self._refresh_tree()
                self._refresh_audit()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Copy Error", str(exc), parent=dlg)

        tk.Button(dlg, text="📋 Copy", command=do_copy).grid(row=2, column=0, pady=10, padx=10)
        tk.Button(dlg, text="Cancel", command=dlg.destroy).grid(row=2, column=1, pady=10)

    def _new_file_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("New File")
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Zone:").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        zone_var = tk.StringVar(value="human")
        ttk.Combobox(
            dlg, textvariable=zone_var, values=ZONES, state="readonly", width=12,
        ).grid(row=0, column=1, padx=10, pady=6)

        tk.Label(dlg, text="Path  (e.g. notes/myfile.txt):").grid(
            row=1, column=0, sticky="w", padx=10,
        )
        path_var = tk.StringVar()
        tk.Entry(dlg, textvariable=path_var, width=32).grid(row=1, column=1, padx=10, pady=4)

        tk.Label(dlg, text="Initial content:").grid(row=2, column=0, sticky="nw", padx=10, pady=4)
        content_txt = tk.Text(dlg, width=36, height=7, wrap=tk.WORD)
        content_txt.grid(row=2, column=1, padx=10, pady=4)

        def do_create():
            zone = zone_var.get()
            rel = path_var.get().strip()
            if not rel:
                messagebox.showerror("Error", "Path cannot be empty.", parent=dlg)
                return
            try:
                fpath = safe_resolve(zone, rel)
                if fpath.exists():
                    if not messagebox.askyesno(
                        "Overwrite?", f"{rel} already exists. Overwrite?", parent=dlg,
                    ):
                        return
                content = content_txt.get("1.0", tk.END)
                if content.endswith("\n"):
                    content = content[:-1]
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
                write_audit("human", "write", zone, rel, "allowed", "New file created")
                dlg.destroy()
                self._refresh_tree(zone, rel)
                self._load_file(zone, rel)
            except (ValueError, OSError) as exc:
                messagebox.showerror("Error", str(exc), parent=dlg)

        tk.Button(dlg, text="✅ Create", command=do_create).grid(
            row=3, column=0, pady=10, padx=10,
        )
        tk.Button(dlg, text="Cancel", command=dlg.destroy).grid(row=3, column=1, pady=10)

    # ── search ────────────────────────────────────────────────────────────────

    def _do_search(self):
        query = self._search_var.get().lower().strip()
        if not query:
            return
        results = []
        for zone in ZONES:
            zp = zone_path(zone)
            for fpath in sorted(zp.rglob("*")):
                if not fpath.is_file():
                    continue
                rel = str(fpath.relative_to(zp))
                if query in fpath.name.lower():
                    results.append((zone, rel, "filename match"))
                    continue
                try:
                    content = fpath.read_text(encoding="utf-8")
                    if query in content.lower():
                        idx = content.lower().find(query)
                        snippet = content[max(0, idx - SNIPPET_CONTEXT_CHARS):idx + SNIPPET_CONTEXT_CHARS].replace("\n", " ")
                        results.append((zone, rel, f"…{snippet}…"))
                except (UnicodeDecodeError, OSError):
                    pass
                if len(results) >= MAX_SEARCH_RESULTS:
                    break

        if not results:
            messagebox.showinfo("Search", f"No results for '{query}'.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f'Search: "{query}"')
        dlg.geometry("720x300")
        dlg.grab_set()

        tk.Label(
            dlg, text=f"{len(results)} result(s) for '{query}'",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=4)

        cols = ("zone", "path", "match")
        tv = ttk.Treeview(dlg, columns=cols, show="headings", height=10)
        tv.heading("zone", text="Zone");  tv.column("zone", width=90)
        tv.heading("path", text="Path");  tv.column("path", width=200)
        tv.heading("match", text="Match"); tv.column("match", width=380)
        for zone, rel, match in results:
            tv.insert("", "end", values=(ZONE_LABELS[zone], rel, match))

        sb = ttk.Scrollbar(dlg, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        tv.pack(fill=tk.BOTH, expand=True, padx=8)

        def open_result(_event=None):
            sel = tv.selection()
            if not sel:
                return
            vals = tv.item(sel[0])["values"]
            zone_label, rel, _ = vals[0], vals[1], vals[2]
            zone = next((z for z in ZONES if ZONE_LABELS[z] == zone_label), None)
            if zone:
                dlg.destroy()
                self._load_file(zone, rel)
                iid = f"file:{zone}:{rel}"
                try:
                    self._tree.selection_set(iid)
                    self._tree.see(iid)
                except tk.TclError:
                    pass

        tv.bind("<Double-1>", open_result)
        tk.Button(dlg, text="Open selected", command=open_result).pack(pady=4)

    # ── permissions ───────────────────────────────────────────────────────────

    def _load_permissions_into_ui(self):
        perms = load_permissions()
        for zone in ZONES:
            zp = perms["zones"].get(zone, {})
            self._perm_vars[zone]["ai_read"].set(zp.get("ai_read", False))
            self._perm_vars[zone]["ai_write"].set(zp.get("ai_write", False))
            self._perm_vars[zone]["ai_delete"].set(zp.get("ai_delete", False))
        for dev, v in self._device_vars.items():
            v.set(perms["devices"].get(dev, False))

    def _save_permissions(self):
        perms = load_permissions()
        for zone in ZONES:
            perms["zones"][zone]["ai_read"] = self._perm_vars[zone]["ai_read"].get()
            perms["zones"][zone]["ai_write"] = self._perm_vars[zone]["ai_write"].get()
            perms["zones"][zone]["ai_delete"] = self._perm_vars[zone]["ai_delete"].get()
        for dev in self._device_vars:
            old_val = perms["devices"].get(dev, False)
            new_val = self._device_vars[dev].get()
            perms["devices"][dev] = new_val
            if old_val != new_val:
                write_audit(
                    "human", "permission_change", "system", dev, "allowed",
                    f"Device {'enabled' if new_val else 'disabled'}",
                )
        save_permissions(perms)
        write_audit("human", "permission_update", "system", "", "allowed")
        self._refresh_audit()
        messagebox.showinfo("Permissions", "Permissions saved.")

    # ── mode ─────────────────────────────────────────────────────────────────

    def _refresh_mode_indicator(self):
        md = load_mode()
        current = md.get("current", "normal")
        self._mode_var.set(current)
        self._mode_lbl.config(text=f"Mode: {MODE_LABELS.get(current, current)}")
        history = md.get("history", [])[-10:]
        history_text = "\n".join(
            f"{h['at']}  {h['from']} → {h['to']}" for h in reversed(history)
        ) or "(no history)"
        self._mode_history_box.config(state=tk.NORMAL)
        self._mode_history_box.delete("1.0", tk.END)
        self._mode_history_box.insert("1.0", history_text)
        self._mode_history_box.config(state=tk.DISABLED)

    def _apply_mode(self):
        new_mode = self._mode_var.get()
        md = load_mode()
        old_mode = md["current"]

        if new_mode == "baseline":
            if not messagebox.askyesno(
                "Reset Baseline",
                "This will reset ALL permissions to safe defaults.\nContinue?",
            ):
                return
            default_perms = {
                "zones": {
                    z: {"ai_read": True, "ai_write": z == "ai", "ai_delete": z == "ai"}
                    for z in ZONES
                },
                "devices": {
                    "camera": False, "microphone": False, "clipboard": False,
                    "network": False, "screen_reader": False,
                },
            }
            save_permissions(default_perms)
            write_audit(
                "human", "baseline_reset", "system", "", "allowed",
                "All permissions restored to defaults",
            )
            md["current"] = "normal"
            self._load_permissions_into_ui()
        else:
            md["current"] = new_mode

        md["history"].append({"from": old_mode, "to": new_mode, "at": now_iso()})
        save_mode(md)
        write_audit(
            "human", "mode_change", "system", "", "allowed",
            f"Mode: {old_mode} → {new_mode}",
        )
        self._refresh_mode_indicator()
        self._refresh_audit()

    # ── audit log ─────────────────────────────────────────────────────────────

    def _refresh_audit(self):
        filt = self._audit_filter.get()
        entries = read_audit()[:200]
        if filt == "denied":
            entries = [e for e in entries if e.get("outcome") == "denied"]
        elif filt == "ai":
            entries = [e for e in entries if e.get("actor") == "ai"]
        self._audit_entries = entries
        self._audit_tree.delete(*self._audit_tree.get_children())
        for e in entries:
            outcome_icon = "✅" if e.get("outcome") == "allowed" else "❌"
            self._audit_tree.insert("", "end", iid=e["id"], values=(
                e.get("timestamp", ""),
                e.get("actor", ""),
                e.get("action", ""),
                e.get("zone", ""),
                e.get("filename", ""),
                f"{outcome_icon} {e.get('outcome', '')}",
                e.get("notes", ""),
                e.get("annotation", ""),
            ))

    def _annotate_audit(self):
        sel = self._audit_tree.selection()
        if not sel:
            messagebox.showinfo("Annotate", "Select an audit entry first.")
            return
        entry_id = sel[0]
        current_ann = next(
            (e.get("annotation", "") for e in self._audit_entries if e.get("id") == entry_id),
            "",
        )
        annotation = simpledialog.askstring(
            "Add Annotation",
            "Enter a note for this audit entry:",
            initialvalue=current_ann,
            parent=self.root,
        )
        if annotation is None:
            return
        entries = read_audit()
        found = False
        for e in entries:
            if e.get("id") == entry_id:
                e["annotation"] = annotation.strip()
                found = True
                break
        if found:
            rewrite_audit(entries)
            write_audit(
                "human", "annotation", "system", entry_id, "allowed",
                f"Annotated: {annotation[:80]}",
            )
            self._refresh_audit()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    bootstrap()
    root = tk.Tk()
    try:
        # high-DPI awareness on Windows
        root.tk.call("tk", "scaling", 1.5)
    except tk.TclError:
        pass
    ArkDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
