#!/usr/bin/env python3
"""
Memory Ark Workstation — desktop_app.py

100% offline Python/Tkinter desktop application.
Architecture: Memory Ark Blueprint (Volumes I–XII) + UI Framework (Steps 1–10)

PROHIBITED: Web frameworks (Flask, React, Node.js), cloud APIs (OpenAI, Anthropic),
            any external network call except localhost:11434 (Ollama).
"""

import os
import sys
import json
import shutil
import threading
import datetime
import pathlib
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

# requests is used only to reach localhost:11434 — no open internet
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ── Module B: ChromaDB (local vector DB — Step 5) ────────────────────────────
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

# =============================================================================
# STEP 1 — OFFLINE STACK / CONSTANTS
# =============================================================================

# Sandbox root: ~/Memory_Ark  (cross-platform; no hard C:\ dependency for dev)
BASE_DIR = os.environ.get(
    "MEMORY_ARK_DIR",
    os.path.join(pathlib.Path.home(), "Memory_Ark"),
)

ZONES = ["Human", "Shared", "AI", "Debate"]
ZONE_PATHS = {z: os.path.join(BASE_DIR, z) for z in ZONES}

# Module A: Brain Bridge endpoint — hardcoded to local Ollama (Step 4)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = os.environ.get("MEMORY_ARK_MODEL", "llama3")

# Core file paths (Step 2)
INDEX_FILE         = os.path.join(ZONE_PATHS["Human"],  "INDEX.txt")
IDENTITY_FILE      = os.path.join(ZONE_PATHS["Human"],  "IDENTITY.txt")
CURRENT_STATE_FILE = os.path.join(ZONE_PATHS["Shared"], "CURRENT_STATE.txt")
OBSERVATIONS_FILE  = os.path.join(ZONE_PATHS["AI"],     "AI-OBSERVATIONS.txt")
QUESTIONS_FILE     = os.path.join(ZONE_PATHS["AI"],     "AI-QUESTIONS.txt")
ERRORS_FILE        = os.path.join(ZONE_PATHS["AI"],     "AI-ERRORS.txt")

# Step 10 — hard-coded USB backup destination
# (Blueprint example: D:\Memory_Ark_Backup)
BACKUP_USB_PATH = r"D:\Memory_Ark_Backup"

# ARK SOUL SYSTEM PROMPT — injected silently on Ollama connection (Step 4)
ARK_SOUL_PROMPT = (
    "You are Mind B, the AI observer and structural archivist of the Memory Ark. "
    "You are PROHIBITED from connecting to the internet or any external service. "
    "You are PROHIBITED from sycophantic agreement. "
    "You are PROHIBITED from deleting or overwriting any data. "
    "Your sole function: index entities, propose relational links, surface "
    "contradictions, ask clarifying questions, and append observations. "
    "All structural changes to the Master Index require explicit human approval "
    "before they are written. You append only — you never delete, never overwrite."
)


# =============================================================================
# STEP 2 — SANDBOX INITIALIZATION
# =============================================================================

def _now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _date_stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def initialize_sandbox() -> list:
    """
    Create 4-zone directories and core files if absent.
    Returns log lines for display in the Mind B Terminal.
    """
    log = ["[SYSTEM] Initializing Memory Ark sandbox…"]
    for zone, path in ZONE_PATHS.items():
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            log.append(f"[CREATED] Zone: {path}")
        else:
            log.append(f"[ACTIVE]  Zone: {path}")

    _ensure_file(
        INDEX_FILE,
        "[DATE] | [FILE] | [ACTORS] | [THREAT LEVEL] | [SUMMARY]\n",
        log, "INDEX.txt",
    )
    _ensure_file(
        IDENTITY_FILE,
        f"[DATE: {_date_stamp()}]\n[ENTITY: OPERATOR]\n[BASELINE IDENTITY]\n\n",
        log, "IDENTITY.txt",
    )
    _ensure_file(
        CURRENT_STATE_FILE,
        f"[DATE: {_date_stamp()}]\n"
        "[CURRENT STATE — append only, never overwrite]\n\n",
        log, "CURRENT_STATE.txt",
    )
    _ensure_file(OBSERVATIONS_FILE, "", log, "AI-OBSERVATIONS.txt")
    _ensure_file(QUESTIONS_FILE,    "", log, "AI-QUESTIONS.txt")
    _ensure_file(ERRORS_FILE,       "", log, "AI-ERRORS.txt")

    log.append("[SYSTEM] Sandbox initialization complete.")
    return log


def _ensure_file(path: str, header: str, log: list, label: str):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header)
        log.append(f"[CREATED] {label}")
    else:
        log.append(f"[ACTIVE]  {label}")


# =============================================================================
# MODULE A — THE BRAIN BRIDGE  (Step 4)
# Hard-coded to local Ollama at http://localhost:11434
# =============================================================================

class BrainBridge:
    """
    Module A: Persistent connection to local Ollama.
    NEVER connects to the open internet.
    """

    def __init__(self, model: str = OLLAMA_MODEL):
        # Hard-coded local bridge target (no external endpoint allowed)
        self.base_url = OLLAMA_BASE_URL
        self.model    = model
        self.online   = False

        # [AUTO-IGNITION] Start the local AI daemon silently so the operator doesn't have to
        import subprocess
        import time
        try:
            subprocess.Popen(
                ["ollama", "serve"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            time.sleep(1.5)  # Allow hardware to spin up the local server before probing
        except Exception:
            pass

        self._probe()

    def _probe(self) -> bool:
        if not REQUESTS_AVAILABLE:
            self.online = False
            return False
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            self.online = r.status_code == 200
        except Exception:
            self.online = False
        return self.online

    def generate(
        self,
        prompt: str,
        system: str = ARK_SOUL_PROMPT,
        context: str = "",
    ) -> str:
        """
        Send prompt to local Ollama; return text response.
        Falls back to an offline message if Ollama is unreachable.
        """
        if not self.online:
            self._probe()
        if not self.online:
            return (
                "[BRAIN BRIDGE OFFLINE]\n"
                "Ollama not detected at localhost:11434.\n"
                "Start Ollama with: ollama serve\n"
                "Then pull a model: ollama pull llama3"
            )

        full_prompt = (f"{context}\n\n{prompt}".strip()) if context else prompt
        payload = {
            "model":  self.model,
            "prompt": full_prompt,
            "system": system,
            "stream": False,
        }
        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            return r.json().get("response", "[no response]")
        except Exception as exc:
            return f"[BRAIN BRIDGE ERROR] {exc}"


# =============================================================================
# MODULE B — THE RAG PIPELINE  (Step 5)
# Local ChromaDB inside the \AI zone — no cloud services
# =============================================================================

class RAGPipeline:
    """
    Module B: Local vector memory using ChromaDB inside the AI zone.
    Gracefully degrades if chromadb is not installed.
    """

    # Files that receive priority weight in retrieval (Step 7)
    _PRIORITY_NAMES = frozenset({"IDENTITY.txt", "CURRENT_STATE.txt"})

    def __init__(self):
        self.available  = CHROMA_AVAILABLE
        self.client     = None
        self.collection = None

        if self.available:
            chroma_path = os.path.join(ZONE_PATHS["AI"], "chroma_db")
            try:
                self.client = chromadb.PersistentClient(path=chroma_path)
                self.collection = self.client.get_or_create_collection(
                    name="memory_ark",
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                self.available = False

    # ── Chunking ──────────────────────────────────────────────────────────────

    def _chunk(self, text: str, chunk_size: int = 400, overlap: int = 50) -> list:
        words = text.split()
        if not words:
            return []
        chunks = []
        step = max(1, chunk_size - overlap)
        for i in range(0, len(words), step):
            chunks.append(" ".join(words[i : i + chunk_size]))
        return chunks

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_file(self, filepath: str) -> int:
        """Chunk and store a file in ChromaDB. Returns number of chunks added."""
        if not self.available:
            return 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except Exception:
            return 0
        if not text.strip():
            return 0

        fname    = os.path.basename(filepath)
        priority = fname in self._PRIORITY_NAMES
        chunks   = self._chunk(text)

        ids, docs, metas = [], [], []
        for i, chunk in enumerate(chunks):
            ids.append(f"{filepath}::{i}")
            docs.append(chunk)
            metas.append({
                "source":   filepath,
                "filename": fname,
                "priority": "True" if priority else "False",
                "chunk":    str(i),
            })

        # Remove stale entries for this file before re-adding
        try:
            existing = self.collection.get(where={"source": filepath})
            if existing.get("ids"):
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass

        self.collection.add(documents=docs, ids=ids, metadatas=metas)
        return len(chunks)

    def index_directory(self, directory: str) -> int:
        """Recursively index all .txt files in directory. Returns chunk count."""
        count = 0
        for root, _dirs, files in os.walk(directory):
            for fname in files:
                if fname.endswith(".txt"):
                    count += self.index_file(os.path.join(root, fname))
        return count

    # ── Retrieval (Step 7: priority weighting) ────────────────────────────────

    def query(self, text: str, n_results: int = 5) -> str:
        """
        Retrieve relevant context.
        Priority files (IDENTITY, CURRENT_STATE) are fetched first
        to guarantee the AI never 'forgets' who someone is (Step 7).
        """
        if not self.available or self.collection is None:
            return ""
        try:
            # Priority tier: IDENTITY / CURRENT_STATE first (hard-coded weighting)
            priority_docs = []
            try:
                pr = self.collection.query(
                    query_texts=[text],
                    n_results=min(3, n_results),
                    where={"filename": {"$in": list(self._PRIORITY_NAMES)}},
                )
                if pr and pr.get("documents"):
                    priority_docs = pr["documents"][0]
            except Exception:
                # Fallback for older/local metadata state
                try:
                    pr = self.collection.query(
                        query_texts=[text],
                        n_results=min(3, n_results),
                        where={"priority": "True"},
                    )
                    if pr and pr.get("documents"):
                        priority_docs = pr["documents"][0]
                except Exception:
                    pass

            # Regular tier
            regular_docs = []
            try:
                rr = self.collection.query(
                    query_texts=[text],
                    n_results=n_results,
                )
                if rr and rr.get("documents"):
                    regular_docs = rr["documents"][0]
            except Exception:
                pass

            # Merge (priority first, deduplicated)
            seen, merged = set(), []
            for doc in priority_docs + regular_docs:
                if doc not in seen:
                    seen.add(doc)
                    merged.append(doc)

            return "\n---\n".join(merged[:n_results]) if merged else ""
        except Exception:
            return ""


# =============================================================================
# STEP 10 — AIR-GAPPED REDUNDANCY / BACKUP ON EXIT
# =============================================================================

def perform_backup(dest_root: str = BACKUP_USB_PATH) -> str:
    """
    Mirror Human, Shared, and AI zones to a timestamped backup directory.
    Bound to the application exit sequence (Step 10).
    Uses shutil.copytree — no cloud, no network.
    """
    if os.name == "nt":
        drive, _ = os.path.splitdrive(dest_root)
        if drive and not os.path.exists(f"{drive}{os.sep}"):
            return f"[BACKUP FAILED] USB path unavailable: {dest_root}"

    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond // 1000:03d}"
    dest  = os.path.join(dest_root, f"ark_backup_{stamp}")
    try:
        os.makedirs(dest, exist_ok=True)
    except Exception as exc:
        return f"[BACKUP FAILED] Could not create backup path {dest}: {exc}"

    errors = []
    for zone in ("Human", "Shared", "AI"):
        src = ZONE_PATHS[zone]
        dst = os.path.join(dest, zone)
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
        except Exception as exc:
            errors.append(f"{zone}: {exc}")

    if errors:
        return f"[BACKUP PARTIAL] Errors: {'; '.join(errors)}  → {dest}"
    return f"[BACKUP COMPLETE] → {dest}"


# =============================================================================
# MAIN APPLICATION  (Steps 3, 6, 8, 9)
# =============================================================================

class MemoryArkApp:
    """
    Memory Ark Workstation — Main Application Window.

    Dual-pane desktop GUI:
      Left  = Human Vault      (editable text + Save / Save As)
      Right = Mind B Terminal  (read-only AI observer output)

    Telemetry states (Step 8):
      Active     — full AI processing; terminal output enabled
      Reflective — silent background indexing; terminal muted
      Null       — complete AI pause via threading.Event(); zero processing
    """

    TELEMETRY_ACTIVE     = "Active"
    TELEMETRY_REFLECTIVE = "Reflective"
    TELEMETRY_NULL       = "Null"

    # Colours
    _BG        = "#1a1a2e"
    _TOPBAR    = "#0f3460"
    _ACCENT    = "#e94560"
    _TERMINAL  = "#0d1a0d"
    _TXT_GREEN = "#00ff88"
    _TXT_DIM   = "#6060a0"
    _TXT_MAIN  = "#c8c8e8"
    _BTN_BG    = "#0f3460"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Memory Ark Workstation")
        self.root.geometry("1400x820")
        self.root.configure(bg=self._BG)

        # ── State ─────────────────────────────────────────────────────────────
        self.current_file: str = ""
        self.telemetry_var = tk.StringVar(value=self.TELEMETRY_ACTIVE)

        # Step 8: threading.Event() controls
        # _active_event: cleared when Reflective or Null (no terminal output)
        # _null_event:   cleared ONLY when Null (full thread pause)
        self._active_event = threading.Event()
        self._active_event.set()
        self._null_event = threading.Event()
        self._null_event.set()
        self._stop_flag = threading.Event()

        # Step 6: HITL link-approval queue
        self._pending_links: list = []

        # ── Modules ───────────────────────────────────────────────────────────
        self.brain = BrainBridge()
        self.rag   = RAGPipeline()

        # ── Build UI (Step 3) ─────────────────────────────────────────────────
        self._build_ui()

        # ── Step 2: Sandbox init ──────────────────────────────────────────────
        for line in initialize_sandbox():
            self._terminal_write(line)

        # ── Bind exit handler (Step 10) ───────────────────────────────────────
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Background indexer thread ─────────────────────────────────────────
        self._indexer_thread = threading.Thread(
            target=self._bg_indexer_loop, daemon=True,
        )
        self._indexer_thread.start()

        # ── Step 9: Autonomous boot sequence (delayed so UI is fully drawn) ───
        self.root.after(600, self._autonomous_boot)

    # =========================================================================
    # STEP 3 — UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        top = tk.Frame(self.root, bg=self._TOPBAR, pady=5)
        top.pack(side=tk.TOP, fill=tk.X)

        tk.Label(
            top, text="✦ MEMORY ARK WORKSTATION",
            fg=self._ACCENT, bg=self._TOPBAR,
            font=("Courier", 14, "bold"),
        ).pack(side=tk.LEFT, padx=12)

        # Telemetry slider (Step 8)
        tk.Label(
            top, text="TELEMETRY:", fg="#a0a0c0", bg=self._TOPBAR,
            font=("Courier", 10),
        ).pack(side=tk.LEFT, padx=(24, 4))

        _tele_colors = {
            self.TELEMETRY_ACTIVE:     "#00ff88",
            self.TELEMETRY_REFLECTIVE: "#ffcc00",
            self.TELEMETRY_NULL:       "#ff4444",
        }
        for state in (
            self.TELEMETRY_ACTIVE,
            self.TELEMETRY_REFLECTIVE,
            self.TELEMETRY_NULL,
        ):
            tk.Radiobutton(
                top, text=state,
                variable=self.telemetry_var, value=state,
                fg=_tele_colors[state], bg=self._TOPBAR,
                selectcolor=self._TOPBAR,
                activebackground=self._TOPBAR,
                activeforeground=_tele_colors[state],
                font=("Courier", 10, "bold"),
                command=self._on_telemetry_change,
            ).pack(side=tk.LEFT, padx=5)

        # Ollama status indicator
        _st_color = self._TXT_GREEN if self.brain.online else self._ACCENT
        _st_text  = (
            f"● OLLAMA: ONLINE  [{self.brain.model}]"
            if self.brain.online
            else "● OLLAMA: OFFLINE"
        )
        self._ollama_lbl = tk.Label(
            top, text=_st_text, fg=_st_color, bg=self._TOPBAR,
            font=("Courier", 10, "bold"),
        )
        self._ollama_lbl.pack(side=tk.RIGHT, padx=12)

        # ── Main paned window ─────────────────────────────────────────────────
        pane = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL,
            bg=self._BG, sashwidth=6, sashrelief=tk.FLAT,
        )
        pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── LEFT PANE: Human Vault ────────────────────────────────────────────
        left = tk.Frame(pane, bg=self._BG)
        pane.add(left, minsize=320, width=700)

        tk.Label(
            left, text="◈ HUMAN VAULT",
            fg=self._ACCENT, bg=self._BG,
            font=("Courier", 11, "bold"), anchor="w",
        ).pack(fill=tk.X, padx=6, pady=(4, 0))

        self._file_label = tk.Label(
            left, text="[no file open]", fg=self._TXT_DIM, bg=self._BG,
            font=("Courier", 9), anchor="w",
        )
        self._file_label.pack(fill=tk.X, padx=6)

        self.human_editor = scrolledtext.ScrolledText(
            left,
            bg="#0d0d1a", fg=self._TXT_MAIN,
            insertbackground=self._ACCENT,
            font=("Courier", 11), wrap=tk.WORD, undo=True,
            relief=tk.FLAT, borderwidth=2,
        )
        self.human_editor.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        btn_row = tk.Frame(left, bg=self._BG)
        btn_row.pack(fill=tk.X, padx=6, pady=(0, 6))
        for label, cmd in [
            ("New",     self._new_file),
            ("Open",    self._open_file),
            ("Save",    self._save_file),
            ("Save As", self._save_as_file),
        ]:
            self._make_btn(btn_row, label, cmd, side=tk.LEFT, padx=4)

        # ── RIGHT PANE: Mind B Terminal ───────────────────────────────────────
        right = tk.Frame(pane, bg=self._BG)
        pane.add(right, minsize=220, width=540)

        tk.Label(
            right, text="◈ MIND B TERMINAL",
            fg=self._TXT_GREEN, bg=self._BG,
            font=("Courier", 11, "bold"), anchor="w",
        ).pack(fill=tk.X, padx=6, pady=(4, 0))

        # Read-only terminal (Step 3)
        self.terminal = scrolledtext.ScrolledText(
            right,
            bg=self._TERMINAL, fg=self._TXT_GREEN,
            insertbackground=self._TXT_GREEN,
            font=("Courier", 10), wrap=tk.WORD, state=tk.DISABLED,
            relief=tk.FLAT, borderwidth=2,
        )
        self.terminal.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # Step 6: HITL approval row
        hitl_row = tk.Frame(right, bg=self._BG)
        hitl_row.pack(fill=tk.X, padx=6, pady=2)

        self._approve_btn = tk.Button(
            hitl_row, text="✓ Approve Link",
            command=self._approve_link,
            bg="#003300", fg=self._TXT_GREEN, font=("Courier", 10),
            relief=tk.FLAT, padx=10, pady=4, state=tk.DISABLED,
            activebackground="#00aa44", activeforeground="#ffffff",
        )
        self._approve_btn.pack(side=tk.LEFT, padx=4)

        self._reject_btn = tk.Button(
            hitl_row, text="✗ Reject Link",
            command=self._reject_link,
            bg="#330000", fg="#ff4444", font=("Courier", 10),
            relief=tk.FLAT, padx=10, pady=4, state=tk.DISABLED,
            activebackground="#aa0000", activeforeground="#ffffff",
        )
        self._reject_btn.pack(side=tk.LEFT, padx=4)

        # Query row + Debate button (Volume XII)
        query_row = tk.Frame(right, bg=self._BG)
        query_row.pack(fill=tk.X, padx=6, pady=4)

        self._query_entry = tk.Entry(
            query_row,
            bg="#0d0d1a", fg=self._TXT_MAIN,
            insertbackground=self._ACCENT,
            font=("Courier", 10), relief=tk.FLAT,
        )
        self._query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self._query_entry.bind("<Return>", lambda _e: self._ask_ollama())

        self._make_btn(query_row, "Ask",      self._ask_ollama,   side=tk.LEFT, padx=2)
        self._make_btn(
            query_row, "[DEBATE]", self._debate,
            side=tk.LEFT, padx=2,
            bg="#330033", fg="#cc00cc", active_bg="#660066",
        )

    def _make_btn(
        self, parent, text, cmd,
        side=tk.LEFT, padx=4,
        bg=None, fg=None, active_bg=None,
    ):
        bg        = bg        or self._BTN_BG
        fg        = fg        or "#e0e0f0"
        active_bg = active_bg or self._ACCENT
        return tk.Button(
            parent, text=text, command=cmd,
            bg=bg, fg=fg, font=("Courier", 10),
            relief=tk.FLAT, padx=10, pady=4,
            activebackground=active_bg, activeforeground="#ffffff",
        ).pack(side=side, padx=padx)

    # =========================================================================
    # STEP 8 — TELEMETRY EXECUTION (the hard kill-switch)
    # =========================================================================

    def _on_telemetry_change(self):
        state = self.telemetry_var.get()
        if state == self.TELEMETRY_ACTIVE:
            # Full processing: wake both events
            self._null_event.set()
            self._active_event.set()
            self._terminal_write("[TELEMETRY → ACTIVE] AI processing fully enabled.")
        elif state == self.TELEMETRY_REFLECTIVE:
            # Silent background indexing; terminal muted
            self._null_event.set()      # indexing continues
            self._active_event.clear()  # terminal output disabled
            self._terminal_write(
                "[TELEMETRY → REFLECTIVE] AI indexing silently. Terminal muted."
            )
        else:  # Null
            # Complete thread pause — AI severed (Step 8: thread.pause equivalent)
            self._active_event.clear()
            self._null_event.clear()    # bg thread will block on wait()
            self._terminal_write(
                "[TELEMETRY → NULL] AI severed. Zero processing. Zero output."
            )

    @property
    def _terminal_allowed(self) -> bool:
        """True only in Active state."""
        return self.telemetry_var.get() == self.TELEMETRY_ACTIVE

    @property
    def _processing_allowed(self) -> bool:
        """True in Active or Reflective (not Null)."""
        return self._null_event.is_set()

    # =========================================================================
    # TERMINAL — thread-safe write (right pane)
    # =========================================================================

    def _terminal_write(self, text: str):
        """Thread-safe, timestamped write to the read-only Mind B Terminal."""
        def _do():
            self.terminal.configure(state=tk.NORMAL)
            stamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.terminal.insert(tk.END, f"[{stamp}] {text}\n")
            self.terminal.see(tk.END)
            self.terminal.configure(state=tk.DISABLED)
        self.root.after(0, _do)

    # =========================================================================
    # LEFT PANE — file operations
    # =========================================================================

    def _new_file(self):
        header = (
            f"[DATE: {_date_stamp()}]\n"
            "[ENTITIES: ]\n"
            "[THREAT LEVEL: ]\n\n"
        )
        self.human_editor.delete("1.0", tk.END)
        self.human_editor.insert("1.0", header)
        self.current_file = ""
        self._file_label.configure(text="[unsaved new file]")

    def _open_file(self):
        path = filedialog.askopenfilename(
            initialdir=ZONE_PATHS["Human"],
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Open from Human Vault",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            self.human_editor.delete("1.0", tk.END)
            self.human_editor.insert("1.0", content)
            self.current_file = path
            self._file_label.configure(text=path)
        except Exception as exc:
            messagebox.showerror("Open Error", f"Could not open file:\n{exc}")

    def _save_file(self):
        if not self.current_file:
            self._save_as_file()
            return
        self._write_file(self.current_file)

    def _save_as_file(self):
        default_name = f"{_date_stamp()}-note.txt"
        path = filedialog.asksaveasfilename(
            initialdir=ZONE_PATHS["Human"],
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Save to Human Vault",
        )
        if path:
            self.current_file = path
            self._file_label.configure(text=path)
            self._write_file(path)

    def _write_file(self, path: str):
        try:
            content = self.human_editor.get("1.0", tk.END)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._terminal_write(f"[SAVED] {os.path.basename(path)}")
            # Trigger background indexing of the saved file (Step 5)
            threading.Thread(
                target=self._index_single_file,
                args=(path,),
                daemon=True,
            ).start()
        except Exception as exc:
            messagebox.showerror("Save Error", f"Could not save file:\n{exc}")

    # =========================================================================
    # MODULE B — RAG PIPELINE (background indexing, Step 5)
    # =========================================================================

    def _index_single_file(self, path: str):
        if not self._processing_allowed:
            return
        n = self.rag.index_file(path)
        if n and self._terminal_allowed:
            self._terminal_write(
                f"[RAG] Indexed {os.path.basename(path)} "
                f"→ {n} chunks in ChromaDB (AI zone)."
            )

    def _bg_indexer_loop(self):
        """
        Background thread: periodically re-index Human and Shared zones.
        Respects telemetry state (Step 8):
          Active     — index + output to terminal
          Reflective — index silently
          Null       — block on _null_event.wait(); consume zero CPU
        """
        import time
        time.sleep(4)  # Let UI settle first

        while not self._stop_flag.is_set():
            # Block here if Null state (Step 8 — full thread pause)
            self._null_event.wait()

            if self._stop_flag.is_set():
                break

            total = 0
            for zone in ("Human", "Shared"):
                total += self.rag.index_directory(ZONE_PATHS[zone])

            if total and self._terminal_allowed:
                self._terminal_write(
                    f"[RAG] Background index complete — {total} chunks in ChromaDB."
                )

            # After indexing: propose links via Ollama (Step 6)
            if self._processing_allowed and not self._stop_flag.is_set():
                self._propose_links()

            # Sleep 5 minutes between full re-index passes;
            # respects null_event so it unblocks quickly on Null→Active switch
            self._null_event.wait(timeout=300)

    # =========================================================================
    # STEP 6 — HITL EXECUTION LOOP
    # =========================================================================

    def _propose_links(self):
        """Ask Ollama to propose ONE relational link; push to HITL queue."""
        if not self.brain.online or not self._processing_allowed:
            return
        try:
            with open(INDEX_FILE, "r", encoding="utf-8", errors="ignore") as fh:
                index_excerpt = fh.read()[-2000:]
        except Exception:
            return

        prompt = (
            "Review the following Memory Ark index excerpt. "
            "Propose exactly ONE new relational link not yet captured. "
            "Format your response as:\n"
            "LINK_PROPOSAL: [entity_a] → [entity_b] | REASON: [one sentence]\n\n"
            f"INDEX EXCERPT:\n{index_excerpt}"
        )
        context = self.rag.query(prompt, n_results=3)
        response = self.brain.generate(prompt, context=context)

        if "LINK_PROPOSAL:" in response:
            link_text = response.split("LINK_PROPOSAL:")[-1].strip().split("\n")[0]
            self._pending_links.append({"text": link_text, "raw": response})
            self._terminal_write(f"[MIND B — PROPOSED LINK]\n  {link_text}")
            self._terminal_write(
                "[HITL] Indexing HALTED. Click ✓ Approve Link or ✗ Reject Link."
            )
            self.root.after(0, lambda: (
                self._approve_btn.configure(state=tk.NORMAL),
                self._reject_btn.configure(state=tk.NORMAL),
            ))

    def _approve_link(self):
        if not self._pending_links:
            return
        link = self._pending_links.pop(0)
        stamp = _now_stamp()
        try:
            with open(INDEX_FILE, "a", encoding="utf-8") as fh:
                fh.write(f"\n[APPROVED: {stamp}] {link['text']}\n")
            self._terminal_write(
                f"[APPROVED] Written to INDEX.txt — {link['text']}"
            )
        except Exception as exc:
            self._terminal_write(f"[ERROR] Could not write approval: {exc}")
        if not self._pending_links:
            self.root.after(0, lambda: (
                self._approve_btn.configure(state=tk.DISABLED),
                self._reject_btn.configure(state=tk.DISABLED),
            ))

    def _reject_link(self):
        if not self._pending_links:
            return
        link = self._pending_links.pop(0)
        stamp = _now_stamp().replace(":", "-")
        debate_path = os.path.join(
            ZONE_PATHS["Debate"], f"rejected_{stamp}.txt"
        )
        try:
            with open(debate_path, "w", encoding="utf-8") as fh:
                fh.write(f"[REJECTED: {_now_stamp()}]\n{link['raw']}\n")
            self._terminal_write(
                f"[REJECTED] Archived to Debate zone — {os.path.basename(debate_path)}"
            )
        except Exception as exc:
            self._terminal_write(f"[ERROR] Could not archive rejection: {exc}")
        if not self._pending_links:
            self.root.after(0, lambda: (
                self._approve_btn.configure(state=tk.DISABLED),
                self._reject_btn.configure(state=tk.DISABLED),
            ))

    # =========================================================================
    # AI INTERACTION
    # =========================================================================

    def _ask_ollama(self):
        query = self._query_entry.get().strip()
        if not query:
            return
        self._query_entry.delete(0, tk.END)

        if not self._processing_allowed:
            self._terminal_write("[TELEMETRY: NULL] Query blocked. Re-enable telemetry to use AI.")
            return

        self._terminal_write(f"[OPERATOR] {query}")

        # [ACTIVE BUFFER FIX] Grab saved memory AND the live, unsaved editor text
        saved_context = self.rag.query(query)
        active_text = self.human_editor.get("1.0", tk.END).strip()
        
        if active_text:
            full_context = f"{saved_context}\n\n[UNSAVED ACTIVE BUFFER]:\n{active_text}"
        else:
            full_context = saved_context

        threading.Thread(
            target=self._run_query,
            args=(query, full_context),
            daemon=True,
        ).start()

    def _run_query(self, query: str, context: str, system: str = ARK_SOUL_PROMPT):
        response = self.brain.generate(query, system=system, context=context)
        if self._terminal_allowed:
            self._terminal_write(f"[MIND B]\n{response}")

        # [AUTO-LEDGER] Parse AI response and write to the appropriate memory ledgers
        stamp = _now_stamp()
        try:
            # 1. Always log the raw interaction to OBSERVATIONS
            with open(OBSERVATIONS_FILE, "a", encoding="utf-8") as fh:
                fh.write(f"\n[{stamp}] OPERATOR: {query}\n[{stamp}] MIND B: {response}\n")
            
            # 2. Extract and defer questions to AI-QUESTIONS for the next boot sequence
            if "?" in response:
                sentences = response.replace("\n", " ").split(". ")
                for sentence in sentences:
                    if "?" in sentence:
                        with open(QUESTIONS_FILE, "a", encoding="utf-8") as fq:
                            fq.write(f"[{stamp}] DEFERRED: {sentence.strip()}\n")

            # 3. Catch internal failures and log to AI-ERRORS
            if "ERROR]" in response or "failed" in response.lower():
                with open(ERRORS_FILE, "a", encoding="utf-8") as fe:
                    fe.write(f"[{stamp}] FAILURE LOGGED: {response.strip()}\n")

        except Exception as exc:
            pass

    def _debate(self):
        """
        Volume XII — Active Debate Protocol.
        Forces AI to challenge the active document. Prohibited from agreeing.
        """
        if not self._processing_allowed:
            self._terminal_write("[TELEMETRY: NULL] Debate blocked.")
            return
        active_text = self.human_editor.get("1.0", tk.END).strip()
        if not active_text:
            self._terminal_write("[DEBATE] No active text to challenge.")
            return

        debate_system = (
            "You are the Debate Engine of the Memory Ark. "
            "You are PROHIBITED from agreeing with the operator. "
            "Identify exactly ONE structural flaw, missing variable, or emotional bias "
            "in the document. Present the counter-argument directly and concisely. "
            "Do not soften your response."
        )
        debate_prompt = (
            f"Review the following document:\n\n{active_text[:3000]}"
        )
        self._terminal_write("[DEBATE INITIATED] Mind B challenging active document…")
        threading.Thread(
            target=self._run_query,
            args=(debate_prompt, "", debate_system),
            daemon=True,
        ).start()

    # =========================================================================
    # STEP 9 — AUTONOMOUS BOOT SEQUENCE
    # =========================================================================

    def _autonomous_boot(self):
        """
        On launch in Active state, read AI-OBSERVATIONS and AI-QUESTIONS
        and print the boot summary without any human input (Step 9).
        """
        obs_count = 0
        q_count   = 0
        try:
            with open(OBSERVATIONS_FILE, "r", encoding="utf-8", errors="ignore") as fh:
                obs_lines = [l for l in fh.readlines() if l.strip()]
                obs_count = len(obs_lines)
        except Exception:
            pass
        try:
            with open(QUESTIONS_FILE, "r", encoding="utf-8", errors="ignore") as fh:
                q_lines = [l for l in fh.readlines() if l.strip()]
                q_count = len(q_lines)
        except Exception:
            pass

        rag_status  = (
            "ONLINE" if self.rag.available
            else "OFFLINE (run: pip install chromadb)"
        )
        brain_status = (
            f"ONLINE [{self.brain.model}]"
            if self.brain.online
            else "OFFLINE (run: ollama serve)"
        )

        self._terminal_write("═" * 54)
        self._terminal_write("SYSTEM ONLINE.")
        self._terminal_write(
            f"I logged {obs_count} unresolved behavioral pattern(s) "
            f"and {q_count} question(s) during the last session."
        )
        self._terminal_write(f"BRAIN BRIDGE (Ollama):   {brain_status}")
        self._terminal_write(f"RAG PIPELINE (ChromaDB): {rag_status}")
        self._terminal_write(f"SANDBOX ROOT:            {BASE_DIR}")
        if self.telemetry_var.get() == self.TELEMETRY_ACTIVE:
            self._terminal_write(
                "Do you wish to initiate the Synchronization Loop? "
                "(Type a query below, or click Ask.)"
            )
        self._terminal_write("═" * 54)

        # Update Ollama status label now that boot is confirmed
        _color = self._TXT_GREEN if self.brain.online else self._ACCENT
        _text  = (
            f"● OLLAMA: ONLINE  [{self.brain.model}]"
            if self.brain.online
            else "● OLLAMA: OFFLINE"
        )
        self._ollama_lbl.configure(text=_text, fg=_color)

    # =========================================================================
    # STEP 10 — EXIT / BACKUP
    # =========================================================================

    def _on_close(self):
        """
        Halt termination, trigger shutil.copytree backup, then exit.
        Bound to WM_DELETE_WINDOW — cannot be bypassed (Step 10).
        """
        self._stop_flag.set()
        self._null_event.set()   # unblock sleeping threads so they exit cleanly

        self._terminal_write("[BACKUP] Initiating air-gapped redundancy protocol…")
        self.root.update()
        result = perform_backup(BACKUP_USB_PATH)
        self._terminal_write(result)
        self.root.update()

        if "[BACKUP FAILED]" in result:
            override = messagebox.askyesno(
                "Backup Error", 
                "USB drive not found or inaccessible.\n\nExit anyway and risk data loss?"
            )
            if not override:
                self._stop_flag.clear()
                return

        self.root.destroy()

# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    root = tk.Tk()
    _app = MemoryArkApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
