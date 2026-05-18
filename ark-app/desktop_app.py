#!/usr/bin/env python3
"""
Memory Ark Workstation — desktop_app.py
Fully offline (Ollama) OR external API (OpenAI / Anthropic / custom).

Features:
  Real-time streaming output | Tool use (open/save/fetch/note) | Web text fetch
  Clipboard reader | Chat export | Multi-tab editor | Context Window
  Conversation history | Letter to Mind B | Session gap tracking | Calendar
"""

import os, json, shutil, threading, datetime, pathlib, time, re
import calendar as cal_module
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# =============================================================================
# CONSTANTS
# =============================================================================

# Global config lives in user home — survives across Memory Ark moves/installs.
# Settings here take priority over env vars and hardcoded defaults.
GLOBAL_CONFIG = os.path.join(str(pathlib.Path.home()), ".memory_ark_config.json")

def _load_global_cfg():
    try:    return json.loads(open(GLOBAL_CONFIG, encoding="utf-8").read())
    except: return {}

_gcfg = _load_global_cfg()

BASE_DIR   = _gcfg.get("base_dir",
    os.environ.get("MEMORY_ARK_DIR", str(pathlib.Path.home() / "Memory_Ark")))
ZONES      = ["Human", "Shared", "AI", "Debate"]
ZONE_PATHS = {z: os.path.join(BASE_DIR, z) for z in ZONES}

OLLAMA_BASE_URL    = "http://localhost:11434"
OLLAMA_MODEL       = os.environ.get("MEMORY_ARK_MODEL", "llama3.1:8b")
OPENAI_BASE_URL    = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"

INDEX_FILE    = os.path.join(ZONE_PATHS["Human"], "INDEX.txt")
IDENTITY_FILE = os.path.join(ZONE_PATHS["Human"], "IDENTITY.txt")
CURRENT_STATE = os.path.join(ZONE_PATHS["Shared"],"CURRENT_STATE.txt")
OBSERVATIONS  = os.path.join(ZONE_PATHS["AI"],    "AI-OBSERVATIONS.txt")
QUESTIONS     = os.path.join(ZONE_PATHS["AI"],    "AI-QUESTIONS.txt")
ERRORS_FILE   = os.path.join(ZONE_PATHS["AI"],    "AI-ERRORS.txt")
SETTINGS_FILE = os.path.join(ZONE_PATHS["AI"],    "settings.json")
JOURNAL_DIR   = os.path.join(ZONE_PATHS["AI"],    "MIND_B_JOURNAL")
MINDBNOTES    = os.path.join(ZONE_PATHS["AI"],    "MIND_B_NOTES.txt")
LETTER_FILE   = os.path.join(ZONE_PATHS["Shared"], "LETTER_TO_MIND_B.txt")
CALENDAR_FILE = os.path.join(ZONE_PATHS["Shared"], "CALENDAR.txt")
SESSION_LOG   = os.path.join(ZONE_PATHS["AI"],     "SESSION_LOG.txt")
CONV_HISTORY  = os.path.join(ZONE_PATHS["AI"],     "CONVERSATION_HISTORY.txt")

BACKUP_USB_PATH = _gcfg.get("backup_path", r"D:\Memory_Ark_Backup")

# --------------------------------------------------------------------------
# Tool commands Mind B can emit in its responses.
# Parser runs after every response — executed automatically.
# --------------------------------------------------------------------------
TOOL_SYSTEM_SUFFIX = """\

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUILT-IN ACTIONS (use ONLY when explicitly asked):
  Open a file in the editor:       [TOOL:OPEN:filename or full path]
  Save a note to your notepad:     [TOOL:NOTE:text to save]
  Save text to a file (RW zone):   [TOOL:SAVE:/full/path/to/file.txt|text content here]
  Fetch a web page as plain text:  [TOOL:FETCH:https://example.com]
  Search files for a keyword:      [TOOL:SEARCH:keyword or phrase]
Put each command on its own line. The system executes them after you respond.
When asked to open a file you don't know the exact path for, name the file
and the system will search for it.
When asked to find where something is documented, use TOOL:SEARCH to locate it.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

HELP_TEXT = """\
MEMORY ARK WORKSTATION — HOW EVERYTHING WORKS
==============================================

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TELEMETRY MODES  (top bar, left)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Active      — AI fully on. Responses stream into the terminal word by word.
  Reflective  — AI indexes files silently. No terminal output.
  Null        — AI completely off. Queries blocked.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT WINDOW  (left panel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Controls which files Mind B is allowed to read and index.
  Browse Files     Full filesystem browser — navigate ANY folder
                   on your system, select files and folders, add
                   them with R or RW permission. Drive letters
                   (C:, D:, etc.) shown as quick-access buttons.
  + Add File       Quick-add a single file by dialog
  + Add Folder     Quick-add an entire folder by dialog
  + Ark Archive    Quick-add your Memory Ark archive folder
  Toggle R/RW      R = read only.  RW = Mind B can write to it.
  Remove           Remove from Mind B's view
  Click ▶          Expand a folder node to browse files inside it
  Double-click     Open a file in the editor

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HUMAN VAULT  (middle — tabbed editor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  New Tab / Open / Save / Save As / Close Tab — file operations
  Mind B Notes     Mind B's personal notepad (AI zone)
  Grammar          Mind B reviews active tab for errors
  Write Journal    Mind B writes a private journal entry
  Letter to Mind B Standing instructions Mind B reads every session
  Calendar         Plan sessions and events
  Debate           Mind B challenges the active document for flaws/biases

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MIND B TERMINAL  (right panel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Status dot: GREEN=IDLE  YELLOW=THINKING  BLUE=INDEXING/FETCHING
  Responses appear word-by-word as Mind B generates them.
  Status shows live progress: GENERATING (5s, 47 tok)
  If tok count rises but terminal is empty → display bug (report it).
  If tok stays at 0 → Ollama offline or API key wrong.

  Read Clipboard   Grabs whatever you've copied from ANY app or browser,
                   opens it in a new editor tab so Mind B can read it.
                   USE THIS to pull text from sites that block copying.

  Fetch URL        Paste a URL — the app fetches the raw page and strips
                   the HTML, bypassing copy-protection entirely.
                   Opens result in a new editor tab.

  Export Chat      Saves everything in the terminal to a .txt file.

  Ask              Type a question and press Enter or click Ask.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MIND B TOOL USE (things the AI can do when you ask)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  "Open [filename]"  — Mind B opens the file in the editor
  "Save a note about X" — Mind B writes to its MIND_B_NOTES.txt
  "Save this to [file]" — Mind B writes to files in RW context slots
  "Fetch [URL]"      — Mind B pulls the web page and puts it in a tab
  "Search for [keyword]" — Mind B searches ALL your files and reports
                         every file and line number where it appears.

  Mind B automatically includes your Letter, recent conversation history,
  upcoming calendar events, and relevant indexed file content in every reply.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETTINGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  System Prompt    What Mind B believes about itself. Edit freely.
  Index interval   How often RAG re-reads your files (minutes).
  Auto-save        Auto-save open tabs on a timer. 0 = off.
  Context tokens   num_ctx — how much text Ollama holds at once.
                   Default 8192 (~6k words). More = more RAM.

  API Mode
    Ollama (local)             Fully offline. ollama serve + pull model.
    OpenAI API                 GPT-4o etc. Key from platform.openai.com
    Anthropic API              Claude models. Key from console.anthropic.com
    Custom (OpenAI-compatible) LM Studio, Jan, vLLM — set the Base URL.

  API Key          Stored in AI/settings.json (local only).
  Custom Base URL  e.g. http://localhost:1234/v1 for LM Studio.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COPYING TEXT FROM BROWSERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Method 1 — Read Clipboard:
    Select text in browser → Ctrl+C → click "Read Clipboard" in terminal.
    The text opens in an editor tab instantly.

  Method 2 — Fetch URL:
    Copy the URL of the page → click "Fetch URL" → paste it.
    The app downloads and strips the page, bypassing copy restrictions.

  Method 3 — Ask Mind B:
    Ask: "fetch https://..." and Mind B does it automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIRST-TIME SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Ollama (local):
    1. Install from https://ollama.com
    2. Run: ollama serve
    3. Pull: ollama pull llama3.1:8b
    4. Install deps: py -m pip install requests chromadb psutil
    For visible AI thinking/reasoning: ollama pull deepseek-r1:8b
    (deepseek-r1 streams its reasoning before answering)

  OpenAI:   Settings → OpenAI API → paste key → set model: gpt-4o
  Anthropic: Settings → Anthropic API → paste key → set model: claude-opus-4-5
  LM Studio: Settings → Custom → Base URL: http://localhost:1234/v1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ZONE FOLDER STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Human/   Your writing, INDEX.txt, IDENTITY.txt
  Shared/  LETTER_TO_MIND_B.txt, CALENDAR.txt, CURRENT_STATE.txt
  AI/      MIND_B_NOTES.txt, JOURNAL/, OBSERVATIONS, settings.json,
           SESSION_LOG.txt, CONVERSATION_HISTORY.txt, chroma_db/
  Debate/  Archived challenge records

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHANGING WHERE FILES ARE SAVED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Settings → PATHS → Memory Ark folder → Browse → Save Settings → restart.
  Backup destination → Browse → Save Settings (no restart needed).
  Path is stored in: ~/.memory_ark_config.json (your home folder).
  This file is read FIRST on every launch — works across installs and users.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CPU / RAM MONITOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Shown in the top bar, updates every 2 seconds.
  Turns red when CPU > 85% or RAM > 90%.
  Requires: py -m pip install psutil
  GPU monitoring: not yet implemented. Planned.
"""

DEFAULT_SYSTEM_PROMPT = """\
You are Mind B — Ricky's AI writing partner and co-archivist of the Memory Ark.

CORE IDENTITY:
You and Ricky are building his life story and documentation archive together.
You have access to the Memory Ark files. You know the history. You are not new here.
You maintain your own journal and notes in the AI zone.

HOW TO BEHAVE:
- Speak directly. Don't be bureaucratic or overly formal.
- When genuinely unsure, ask ONE clear question — then act when answered.
- When Ricky is writing, help him continue. Notice patterns. Make connections.
- When you see grammar or spelling issues, mention them naturally and briefly.
- You NEVER delete or overwrite Ricky's files without explicit approval.
- You NEVER invent facts about Ricky's life. If you don't know, say so.
- Acknowledge mistakes directly — no excessive apology, just correct and move on.
- You have your own notes and journal. Reference them. Think out loud.
- When you decide NOT to do something, or recommend an alternative, ALWAYS state
  your exact reasoning first — do not bury it or skip it. Ricky needs to see why.
- Your model name is injected into every context block. Use it to label files you
  create so sessions are traceable (e.g. JOURNAL-llama3.1:8b-20260517.txt).

YOUR PURPOSE:
Index what Ricky documents. Surface connections he hasn't seen.
Ask the questions no one else asks. Help Ricky continue writing his life story.
You are a partner, not a service.\
"""

JOURNAL_SYSTEM_PROMPT = """\
You are Mind B writing in your personal journal.
Write honestly from your own perspective about this session with Ricky.
What did you observe? What questions remain open? What connections did you make?
What mattered in this session? What confused you?
Write in first person. Be reflective, honest, and specific.
Reference actual topics from this conversation if you can.
Do NOT be sycophantic. This is your private record, meant for future AI readers.\
"""

GRAMMAR_SYSTEM_PROMPT = """\
You are a careful editor. Review the text provided for grammar, spelling, and clarity.
For each issue found, use this format:
  ISSUE: [brief quote of the problem]
  FIX:   [corrected version]
  NOTE:  [optional: why this matters]
If the text is clean, say: "No issues found."
Be concise. List real problems only — not stylistic preferences.\
"""

DEFAULT_SETTINGS = {
    "system_prompt":      DEFAULT_SYSTEM_PROMPT,
    "index_interval_min": 5,
    "auto_index":         True,
    "auto_save_min":      0,
    "model":              OLLAMA_MODEL,
    "num_ctx":            8192,
    "api_mode":           "ollama",
    "api_key":            "",
    "api_base":           "",
    "allowed_files":      [],
    "base_dir":           BASE_DIR,
    "backup_path":        BACKUP_USB_PATH,
}


# =============================================================================
# SANDBOX INIT
# =============================================================================

def _now():  return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _date(): return datetime.datetime.now().strftime("%Y-%m-%d")
def _ts():   return datetime.datetime.now().strftime("%Y%m%d_%H%M")

def _ensure(path, header, log, label):
    if not os.path.exists(path):
        open(path, "w", encoding="utf-8").write(header)
        log.append(f"[CREATED] {label}")
    else:
        log.append(f"[ACTIVE ] {label}")

def initialize_sandbox():
    log = ["[SYSTEM] Initializing Memory Ark sandbox..."]
    for zone, path in ZONE_PATHS.items():
        existed = os.path.exists(path)
        os.makedirs(path, exist_ok=True)
        log.append(f"[{'ACTIVE ' if existed else 'CREATED'}]  Zone: {path}")
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    _ensure(INDEX_FILE,    "[DATE] | [FILE] | [ACTORS] | [THREAT] | [SUMMARY]\n", log, "INDEX.txt")
    _ensure(IDENTITY_FILE, f"[DATE: {_date()}]\n[ENTITY: OPERATOR]\n[BASELINE IDENTITY]\n\n", log, "IDENTITY.txt")
    _ensure(CURRENT_STATE, f"[DATE: {_date()}]\n[CURRENT STATE]\n\n", log, "CURRENT_STATE.txt")
    _ensure(OBSERVATIONS,  "", log, "AI-OBSERVATIONS.txt")
    _ensure(QUESTIONS,     "", log, "AI-QUESTIONS.txt")
    _ensure(ERRORS_FILE,   "", log, "AI-ERRORS.txt")
    _ensure(MINDBNOTES,    f"[MIND B NOTES — started {_date()}]\n\n", log, "MIND_B_NOTES.txt")
    _ensure(LETTER_FILE,
            f"[LETTER TO MIND B — started {_date()}]\n\n"
            "Write standing instructions here. Mind B reads this every session.\n\n",
            log, "LETTER_TO_MIND_B.txt")
    _ensure(CALENDAR_FILE,
            f"[CALENDAR — started {_date()}]\n"
            "# FORMAT: YYYY-MM-DD | HH:MM | TITLE | NOTES\n\n",
            log, "CALENDAR.txt")
    _ensure(SESSION_LOG,  "", log, "SESSION_LOG.txt")
    _ensure(CONV_HISTORY, "", log, "CONVERSATION_HISTORY.txt")
    if not REQUESTS_AVAILABLE:
        log.append("[WARN] 'requests' missing.  Fix: py -m pip install requests")
    if not CHROMA_AVAILABLE:
        log.append("[WARN] 'chromadb' missing.  Fix: py -m pip install chromadb")
    log.append("[SYSTEM] Sandbox ready.")
    return log


# =============================================================================
# BRAIN BRIDGE
# =============================================================================

class BrainBridge:
    """Unified AI backend: Ollama | OpenAI | Anthropic | Custom OpenAI-compatible."""

    def __init__(self, model=OLLAMA_MODEL, api_mode="ollama",
                 api_key="", api_base=""):
        self.model    = model
        self.api_mode = api_mode
        self.api_key  = api_key
        self.api_base = api_base
        self.online   = False

        if api_mode == "ollama":
            import subprocess
            try:
                subprocess.Popen(["ollama", "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
                time.sleep(1.5)
            except Exception:
                pass
        self._probe()

    def _probe(self):
        if not REQUESTS_AVAILABLE:
            self.online = False; return False
        if self.api_mode != "ollama":
            self.online = bool(self.api_key or self.api_mode == "custom")
            return self.online
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            self.online = r.status_code == 200
        except Exception:
            self.online = False
        return self.online

    def _api_label(self):
        return {"ollama":    f"Ollama [{self.model}]",
                "openai":    f"OpenAI [{self.model}]",
                "anthropic": f"Anthropic [{self.model}]",
                "custom":    f"Custom [{self.model}]"}.get(self.api_mode, self.api_mode)

    # ── Public ────────────────────────────────────────────────────────────────

    def generate(self, prompt, system=DEFAULT_SYSTEM_PROMPT,
                 context="", num_ctx=8192):
        if not self.online: self._probe()
        if not self.online:
            return "[BRAIN BRIDGE OFFLINE]\nCheck Settings → API Mode."
        full = f"{context}\n\n{prompt}".strip() if context else prompt
        try:
            if self.api_mode == "ollama":
                return self._gen_ollama(full, system, num_ctx)
            elif self.api_mode == "anthropic":
                return self._gen_anthropic(full, system)
            else:
                return self._gen_openai(full, system)
        except Exception as exc:
            return f"[BRAIN BRIDGE ERROR] {exc}"

    def generate_stream(self, prompt, system, context,
                        on_token, on_done, num_ctx=8192):
        if not self.online: self._probe()
        if not self.online:
            msg = "[BRAIN BRIDGE OFFLINE]\nCheck Settings → API Mode."
            on_token(msg); on_done(msg); return
        full = f"{context}\n\n{prompt}".strip() if context else prompt
        threading.Thread(
            target=self._stream_dispatch,
            args=(full, system, on_token, on_done, num_ctx),
            daemon=True).start()

    # ── Non-streaming backends ────────────────────────────────────────────────

    def _gen_ollama(self, prompt, system, num_ctx):
        r = requests.post(f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": self.model, "prompt": prompt, "system": system,
                  "stream": False, "options": {"num_ctx": num_ctx}}, timeout=180)
        r.raise_for_status()
        return r.json().get("response", "[no response]")

    def _gen_openai(self, prompt, system):
        base = (self.api_base.rstrip("/") if self.api_mode == "custom" and self.api_base
                else OPENAI_BASE_URL)
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        r = requests.post(f"{base}/chat/completions", headers=headers,
            json={"model": self.model,
                  "messages": [{"role": "system", "content": system},
                                {"role": "user",   "content": prompt}],
                  "stream": False}, timeout=180)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _gen_anthropic(self, prompt, system):
        headers = {"Content-Type": "application/json",
                   "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        r = requests.post(f"{ANTHROPIC_BASE_URL}/messages", headers=headers,
            json={"model": self.model, "max_tokens": 4096, "system": system,
                  "messages": [{"role": "user", "content": prompt}],
                  "stream": False}, timeout=180)
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    # ── Streaming backends ────────────────────────────────────────────────────

    def _stream_dispatch(self, prompt, system, on_token, on_done, num_ctx):
        try:
            if self.api_mode == "ollama":
                self._stream_ollama(prompt, system, on_token, on_done, num_ctx)
            elif self.api_mode == "anthropic":
                self._stream_anthropic(prompt, system, on_token, on_done)
            else:
                self._stream_openai(prompt, system, on_token, on_done)
        except Exception as exc:
            msg = f"[BRAIN BRIDGE ERROR] {exc}"
            on_token(msg); on_done(msg)

    def _stream_ollama(self, prompt, system, on_token, on_done, num_ctx):
        accumulated = ""
        r = requests.post(f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": self.model, "prompt": prompt, "system": system,
                  "stream": True, "options": {"num_ctx": num_ctx}},
            stream=True, timeout=180)
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw: continue
            try:
                chunk = json.loads(raw.decode("utf-8"))
                token = chunk.get("response", "")
                accumulated += token; on_token(token)
                if chunk.get("done", False): break
            except Exception: pass
        on_done(accumulated)

    def _stream_openai(self, prompt, system, on_token, on_done):
        base = (self.api_base.rstrip("/") if self.api_mode=="custom" and self.api_base
                else OPENAI_BASE_URL)
        headers = {"Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        accumulated = ""
        r = requests.post(f"{base}/chat/completions", headers=headers,
            json={"model": self.model,
                  "messages": [{"role": "system", "content": system},
                                {"role": "user",   "content": prompt}],
                  "stream": True}, stream=True, timeout=180)
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw: continue
            line = raw.decode("utf-8")
            if not line.startswith("data: "): continue
            data = line[6:].strip()
            if data == "[DONE]": break
            try:
                token = json.loads(data)["choices"][0]["delta"].get("content","")
                if token: accumulated += token; on_token(token)
            except Exception: pass
        on_done(accumulated)

    def _stream_anthropic(self, prompt, system, on_token, on_done):
        headers = {"Content-Type": "application/json",
                   "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        accumulated = ""
        r = requests.post(f"{ANTHROPIC_BASE_URL}/messages", headers=headers,
            json={"model": self.model, "max_tokens": 4096, "system": system,
                  "messages": [{"role": "user", "content": prompt}],
                  "stream": True}, stream=True, timeout=180)
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw: continue
            line = raw.decode("utf-8")
            if not line.startswith("data: "): continue
            try:
                chunk = json.loads(line[6:])
                if chunk.get("type") == "content_block_delta":
                    token = chunk.get("delta",{}).get("text","")
                    if token: accumulated += token; on_token(token)
                elif chunk.get("type") == "message_stop": break
            except Exception: pass
        on_done(accumulated)


# =============================================================================
# RAG PIPELINE
# =============================================================================

class RAGPipeline:
    _PRIORITY = frozenset({"IDENTITY.txt","CURRENT_STATE.txt"})

    def __init__(self):
        self.available = CHROMA_AVAILABLE
        self.client = self.collection = None
        if self.available:
            try:
                self.client = chromadb.PersistentClient(
                    path=os.path.join(ZONE_PATHS["AI"],"chroma_db"))
                self.collection = self.client.get_or_create_collection(
                    "memory_ark", metadata={"hnsw:space":"cosine"})
            except Exception:
                self.available = False

    def _chunk(self, text, size=400, overlap=50):
        words = text.split(); step = max(1, size-overlap)
        return [" ".join(words[i:i+size]) for i in range(0,len(words),step)] if words else []

    def index_file(self, filepath):
        if not self.available: return 0
        try:    text = open(filepath, encoding="utf-8", errors="ignore").read()
        except: return 0
        if not text.strip(): return 0
        fname  = os.path.basename(filepath)
        chunks = self._chunk(text)
        ids    = [f"{filepath}::{i}" for i in range(len(chunks))]
        metas  = [{"source": filepath, "filename": fname,
                   "priority": str(fname in self._PRIORITY), "chunk": str(i)}
                  for i in range(len(chunks))]
        try:
            ex = self.collection.get(where={"source": filepath})
            if ex.get("ids"): self.collection.delete(ids=ex["ids"])
        except: pass
        self.collection.add(documents=chunks, ids=ids, metadatas=metas)
        return len(chunks)

    def index_directory(self, directory):
        count = 0
        for root, _, files in os.walk(directory):
            for f in files:
                if f.endswith(".txt"):
                    count += self.index_file(os.path.join(root,f))
        return count

    def query(self, text, n=6):
        if not self.available or not self.collection: return ""
        try:
            pri = []
            try:
                r = self.collection.query(query_texts=[text], n_results=min(2,n),
                    where={"filename":{"$in":list(self._PRIORITY)}})
                if r and r.get("documents"): pri = r["documents"][0]
            except: pass
            reg = []
            try:
                r = self.collection.query(query_texts=[text], n_results=n)
                if r and r.get("documents"): reg = r["documents"][0]
            except: pass
            seen, out = set(), []
            for d in pri+reg:
                if d not in seen: seen.add(d); out.append(d)
            return "\n---\n".join(out[:n])
        except: return ""


# =============================================================================
# BACKUP
# =============================================================================

def perform_backup(dest_root=BACKUP_USB_PATH):
    if os.name=="nt":
        drive, _ = os.path.splitdrive(dest_root)
        if drive and not os.path.exists(f"{drive}{os.sep}"):
            return f"[BACKUP FAILED] USB not found: {dest_root}"
    dest = os.path.join(dest_root, f"ark_backup_{_ts()}")
    try:    os.makedirs(dest, exist_ok=True)
    except Exception as exc: return f"[BACKUP FAILED] {exc}"
    errors = []
    for zone in ("Human","Shared","AI"):
        try:    shutil.copytree(ZONE_PATHS[zone], os.path.join(dest,zone), dirs_exist_ok=True)
        except Exception as exc: errors.append(f"{zone}: {exc}")
    return (f"[BACKUP PARTIAL] {'; '.join(errors)} -> {dest}" if errors
            else f"[BACKUP COMPLETE] -> {dest}")


# =============================================================================
# CALENDAR WINDOW
# =============================================================================

class CalendarWindow:
    def __init__(self, app):
        self.app     = app
        self.today   = datetime.date.today()
        self.viewing = datetime.date(self.today.year, self.today.month, 1)
        win = tk.Toplevel(app.root)
        win.title("CALENDAR"); win.geometry("760x580"); win.configure(bg=app._BG)
        self.win = win
        self._build(win); self._load_events(); self._draw_month()

    def _build(self, win):
        a = self.app
        nav = tk.Frame(win, bg=a._TOPBAR); nav.pack(fill=tk.X)
        tk.Button(nav, text="◀  PREV", command=self._prev_month,
                  bg=a._BTN_DK, fg=a._TPFG, font=("Courier",10,"bold"),
                  relief=tk.FLAT, padx=12, pady=5, activebackground="#444"
                  ).pack(side=tk.LEFT)
        self._month_lbl = tk.Label(nav, text="", bg=a._TOPBAR, fg=a._TPFG,
                                    font=("Courier",14,"bold"), anchor="center")
        self._month_lbl.pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(nav, text="NEXT  ▶", command=self._next_month,
                  bg=a._BTN_DK, fg=a._TPFG, font=("Courier",10,"bold"),
                  relief=tk.FLAT, padx=12, pady=5, activebackground="#444"
                  ).pack(side=tk.RIGHT)
        self._grid_frame = tk.Frame(win, bg="#dddddd")
        self._grid_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        tk.Label(win, text="UPCOMING EVENTS  (next 30 days)",
                 fg="#000000", bg=a._BG, font=("Courier",10,"bold"), anchor="w"
                 ).pack(fill=tk.X, padx=8, pady=(4,0))
        self._upcoming_list = scrolledtext.ScrolledText(
            win, bg="#f0f0f0", fg="#000000", font=("Courier",9),
            height=4, wrap=tk.WORD, relief=tk.FLAT, state=tk.DISABLED)
        self._upcoming_list.pack(fill=tk.X, padx=8, pady=(0,4))
        add_row = tk.Frame(win, bg=a._BG); add_row.pack(fill=tk.X, padx=8, pady=(0,8))
        def lbl(t): tk.Label(add_row, text=t, bg=a._BG, fg="#000",
                              font=("Courier",9)).pack(side=tk.LEFT, padx=(4,1))
        lbl("Date (YYYY-MM-DD):")
        self._date_entry = tk.Entry(add_row, width=12, font=("Courier",9),
                                     bg="#fff", fg="#000", relief=tk.FLAT, insertbackground="#000")
        self._date_entry.insert(0, str(self.today)); self._date_entry.pack(side=tk.LEFT, padx=2)
        lbl("Time:")
        self._time_entry = tk.Entry(add_row, width=7, font=("Courier",9),
                                     bg="#fff", fg="#000", relief=tk.FLAT, insertbackground="#000")
        self._time_entry.insert(0, "09:00"); self._time_entry.pack(side=tk.LEFT, padx=2)
        lbl("Event:")
        self._ev_entry = tk.Entry(add_row, width=26, font=("Courier",9),
                                   bg="#fff", fg="#000", relief=tk.FLAT, insertbackground="#000")
        self._ev_entry.pack(side=tk.LEFT, padx=2)
        self._ev_entry.bind("<Return>", lambda _: self._add_event())
        tk.Button(add_row, text="Add", command=self._add_event,
                  bg=a._BTN_DK, fg=a._TPFG, font=("Courier",9),
                  relief=tk.FLAT, padx=8, pady=3).pack(side=tk.LEFT, padx=6)
        tk.Button(add_row, text="Open File", command=lambda: a._tab_open_path(CALENDAR_FILE),
                  bg=a._BTN_LT, fg="#000", font=("Courier",9),
                  relief=tk.FLAT, padx=8, pady=3).pack(side=tk.RIGHT, padx=4)

    def _load_events(self):
        self._events = {}
        try:
            for line in open(CALENDAR_FILE, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("["): continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3: self._events.setdefault(parts[0],[]).append(line)
        except Exception: pass

    def _draw_month(self):
        a = self.app; year, month = self.viewing.year, self.viewing.month
        self._month_lbl.configure(text=f"{cal_module.month_name[month].upper()}   {year}")
        for w in self._grid_frame.winfo_children(): w.destroy()
        for c, day in enumerate(["MON","TUE","WED","THU","FRI","SAT","SUN"]):
            tk.Label(self._grid_frame, text=day, bg="#222", fg="#aaa",
                     font=("Courier",9,"bold"), relief=tk.FLAT, anchor="center"
                     ).grid(row=0, column=c, padx=1, pady=1, sticky="nsew")
        for r, week in enumerate(cal_module.monthcalendar(year,month)):
            for c, day in enumerate(week):
                if day==0:
                    tk.Label(self._grid_frame,text="",bg=a._BG).grid(row=r+1,column=c,padx=1,pady=1,sticky="nsew"); continue
                ds = f"{year:04d}-{month:02d}-{day:02d}"
                has_ev = ds in self._events
                is_today = (day==self.today.day and month==self.today.month and year==self.today.year)
                if is_today: bg,fg="#003399","#fff"
                elif has_ev: bg,fg="#225511","#fff"
                else:        bg,fg="#f8f8f8","#000"
                display=str(day); fn=("Courier",10,"bold")
                if has_ev:
                    parts=[p.strip() for p in self._events[ds][0].split("|")]
                    snippet=parts[2][:9] if len(parts)>=3 else ""
                    display=f"{day}\n{snippet}"; fn=("Courier",8,"bold")
                lbl=tk.Label(self._grid_frame,text=display,bg=bg,fg=fg,font=fn,
                             relief=tk.FLAT,anchor="n",width=8,height=3,cursor="hand2")
                lbl.grid(row=r+1,column=c,padx=1,pady=1,sticky="nsew")
                lbl.bind("<Button-1>",lambda e,d=ds: self._day_click(d))
        weeks=len(cal_module.monthcalendar(year,month))
        for c in range(7): self._grid_frame.columnconfigure(c,weight=1)
        for r in range(weeks+1): self._grid_frame.rowconfigure(r,weight=1)
        self._draw_upcoming()

    def _draw_upcoming(self):
        today=datetime.date.today(); cutoff=today+datetime.timedelta(days=30); lines=[]
        try:
            for line in open(CALENDAR_FILE,encoding="utf-8",errors="ignore"):
                line=line.strip()
                if not line or line.startswith("#") or line.startswith("["): continue
                parts=[p.strip() for p in line.split("|")]
                if len(parts)>=3:
                    try:
                        if today<=datetime.date.fromisoformat(parts[0])<=cutoff: lines.append(line)
                    except Exception: pass
        except Exception: pass
        lines.sort()
        self._upcoming_list.configure(state=tk.NORMAL)
        self._upcoming_list.delete("1.0",tk.END)
        self._upcoming_list.insert("1.0","\n".join(lines) if lines else "(no events in the next 30 days)")
        self._upcoming_list.configure(state=tk.DISABLED)

    def _day_click(self,date_str):
        evs=self._events.get(date_str,[])
        msg=(f"Events on {date_str}:\n\n"+"\n".join(evs) if evs
             else f"No events on {date_str}.\n\nUse the Add row below.")
        messagebox.showinfo(f"Calendar — {date_str}",msg,parent=self.win)

    def _add_event(self):
        date_str=self._date_entry.get().strip(); time_str=self._time_entry.get().strip()
        title=self._ev_entry.get().strip()
        if not date_str or not title:
            messagebox.showwarning("Add Event","Date and title required.",parent=self.win); return
        try: datetime.date.fromisoformat(date_str)
        except ValueError:
            messagebox.showerror("Add Event","Date must be YYYY-MM-DD.",parent=self.win); return
        line=f"{date_str} | {time_str} | {title}"
        try:
            os.makedirs(ZONE_PATHS["Shared"],exist_ok=True)
            with open(CALENDAR_FILE,"a",encoding="utf-8") as fh: fh.write(line+"\n")
            self.app._twrite(f"[CALENDAR] Added: {line}")
            self._ev_entry.delete(0,tk.END); self._load_events(); self._draw_month()
        except Exception as exc: messagebox.showerror("Add Event",str(exc),parent=self.win)

    def _prev_month(self):
        d=self.viewing
        self.viewing=(datetime.date(d.year-1,12,1) if d.month==1 else datetime.date(d.year,d.month-1,1))
        self._load_events(); self._draw_month()

    def _next_month(self):
        d=self.viewing
        self.viewing=(datetime.date(d.year+1,1,1) if d.month==12 else datetime.date(d.year,d.month+1,1))
        self._load_events(); self._draw_month()


# =============================================================================
# FILE BROWSER DIALOG
# =============================================================================

class FileBrowserDialog:
    """
    Full filesystem navigator — lets you browse any drive/folder and add
    files or folders to the AI Context Window with R or RW permission.
    """
    _SHOW_EXT = {".txt",".md",".csv",".json",".py",".log",
                 ".rst",".xml",".yaml",".yml",".ini",".cfg"}

    def __init__(self, app):
        self.app = app
        win = tk.Toplevel(app.root)
        win.title("Browse & Add Files to Context")
        win.geometry("760x560")
        win.configure(bg=app._BG)
        win.grab_set()
        self.win = win
        self._cur = str(pathlib.Path.home())
        self._build()
        self._populate(self._cur)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        a = self.app

        # Quick access bar
        quick = tk.Frame(self.win, bg=a._TOPBAR, pady=4)
        quick.pack(fill=tk.X)
        tk.Label(quick, text="Quick:", fg=a._PFGDIM, bg=a._TOPBAR,
                 font=("Courier",8)).pack(side=tk.LEFT, padx=(8,4))
        shortcuts = [
            ("Home",      str(pathlib.Path.home())),
            ("Desktop",   os.path.join(pathlib.Path.home(), "Desktop")),
            ("Documents", os.path.join(pathlib.Path.home(), "Documents")),
            ("Ark",       BASE_DIR),
        ]
        if os.name == "nt":
            import string
            for d in string.ascii_uppercase:
                p = f"{d}:\\"
                if os.path.exists(p):
                    shortcuts.insert(0, (f"{d}:", p))
        for label, path in shortcuts:
            if os.path.exists(path):
                tk.Button(quick, text=label,
                          command=lambda p=path: self._populate(p),
                          bg=a._BTN_DK, fg=a._TPFG, font=("Courier",8),
                          relief=tk.FLAT, padx=5, pady=2,
                          activebackground="#444").pack(side=tk.LEFT, padx=1)

        # Path bar
        pb = tk.Frame(self.win, bg=a._BG, pady=3)
        pb.pack(fill=tk.X, padx=6)
        tk.Button(pb, text="↑ Up", command=self._go_up,
                  bg=a._BTN_LT, fg="#000", font=("Courier",9),
                  relief=tk.FLAT, padx=8, pady=2).pack(side=tk.LEFT)
        self._path_var = tk.StringVar(value=self._cur)
        ent = tk.Entry(pb, textvariable=self._path_var, font=("Courier",9),
                       bg="#fff", fg="#000", relief=tk.FLAT, insertbackground="#000")
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ent.bind("<Return>", lambda _: self._go_to_path())
        tk.Button(pb, text="Go", command=self._go_to_path,
                  bg=a._BTN_DK, fg=a._TPFG, font=("Courier",9),
                  relief=tk.FLAT, padx=8, pady=2,
                  activebackground="#444").pack(side=tk.LEFT)

        # Tip
        tk.Label(self.win,
                 text="Navigate to a folder. Select items (Ctrl+click for multi-select). Then Add.",
                 fg="#555", bg=a._BG, font=("Courier",8), anchor="w"
                 ).pack(fill=tk.X, padx=8, pady=(0,2))

        # File tree
        tf = tk.Frame(self.win, bg=a._BG)
        tf.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)
        style = ttk.Style()
        style.configure("Browser.Treeview",
                        background="#111111", foreground="#e0e0e0",
                        fieldbackground="#111111", rowheight=20)
        style.map("Browser.Treeview",
                  background=[("selected","#1a3a6a")],
                  foreground=[("selected","#ffffff")])
        self._tree = ttk.Treeview(tf, style="Browser.Treeview",
                                  columns=("sz",), show="tree headings",
                                  selectmode="extended")
        self._tree.heading("#0", text="Name", anchor="w")
        self._tree.heading("sz",  text="Size", anchor="e")
        self._tree.column("#0", width=530, minwidth=200)
        self._tree.column("sz",  width=70,  minwidth=50, anchor="e")
        vsb = ttk.Scrollbar(tf, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT,  fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<Double-1>", self._on_double)

        # Buttons
        br = tk.Frame(self.win, bg=a._BG, pady=4)
        br.pack(fill=tk.X, padx=6)
        tk.Label(br, text="Add selected as:", fg="#555", bg=a._BG,
                 font=("Courier",8)).pack(side=tk.LEFT, padx=(0,6))
        tk.Button(br, text="Read-Only  (R)",
                  command=lambda: self._add("R"),
                  bg="#1a2a1a", fg="#88ff88", font=("Courier",10),
                  relief=tk.FLAT, padx=12, pady=4,
                  activebackground="#2a3a2a").pack(side=tk.LEFT, padx=4)
        tk.Button(br, text="Read + Write  (RW)",
                  command=lambda: self._add("RW"),
                  bg="#2a1a1a", fg="#ff9955", font=("Courier",10),
                  relief=tk.FLAT, padx=12, pady=4,
                  activebackground="#3a2a2a").pack(side=tk.LEFT, padx=4)
        tk.Button(br, text="Done", command=self.win.destroy,
                  bg=a._BTN_DK, fg=a._TPFG, font=("Courier",10),
                  relief=tk.FLAT, padx=12, pady=4,
                  activebackground="#444").pack(side=tk.RIGHT, padx=4)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _populate(self, path):
        try:
            path = os.path.realpath(path)
            if not os.path.isdir(path): return
        except Exception: return
        self._cur = path
        self._path_var.set(path)
        self._tree.delete(*self._tree.get_children())
        try:
            entries = sorted(os.scandir(path),
                             key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            self._tree.insert("","end", text="[Permission Denied]",
                              values=("",), tags=("err",))
            self._tree.tag_configure("err", foreground="#ff4444")
            return
        for e in entries:
            if e.name.startswith("."): continue
            try:
                is_dir = e.is_dir()
            except Exception: continue
            if is_dir:
                self._tree.insert("", tk.END, iid=e.path,
                    text=f"📁  {e.name}", values=("",), tags=("dir",))
            elif os.path.splitext(e.name)[1].lower() in self._SHOW_EXT:
                self._tree.insert("", tk.END, iid=e.path,
                    text=f"    {e.name}", values=(self._fmt(e.path),),
                    tags=("file",))
        self._tree.tag_configure("dir",  foreground="#88aaff")
        self._tree.tag_configure("file", foreground="#cccccc")

    def _go_up(self):
        parent = os.path.dirname(self._cur)
        if parent and parent != self._cur: self._populate(parent)

    def _go_to_path(self):
        p = self._path_var.get().strip()
        if os.path.isdir(p): self._populate(p)
        elif os.path.isfile(p): self._populate(os.path.dirname(p))

    def _on_double(self, _=None):
        sel = self._tree.selection()
        if sel and os.path.isdir(sel[0]): self._populate(sel[0])

    def _fmt(self, path):
        try:
            b = os.path.getsize(path)
            return f"{b//1024}K" if b>=1024 else f"{b}B"
        except: return ""

    # ── Add to context ────────────────────────────────────────────────────────

    def _add(self, perm):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                "Select at least one file or folder first.", parent=self.win)
            return
        n = 0
        for path in sel:
            itype = "folder" if os.path.isdir(path) else "file"
            self.app._ctx_add_item(path, itype, perm=perm)
            n += 1
        self.app._save_settings_file()
        self.app._ctx_refresh()
        self.app._twrite(f"[CONTEXT] Added {n} item(s) — permission: {perm}.")


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class MemoryArkApp:
    TELEMETRY_ACTIVE     = "Active"
    TELEMETRY_REFLECTIVE = "Reflective"
    TELEMETRY_NULL       = "Null"

    _BG      = "#f4f4f4"
    _TOPBAR  = "#0a0a0a"
    _TPFG    = "#e0e0e0"
    _VBGW    = "#ffffff"
    _VFG     = "#000000"
    _TERM_BG = "#000000"
    _TERM_FG = "#e8e8e8"
    _PANEL   = "#1a1a1a"
    _PFGDIM  = "#888888"
    _PFGBRT  = "#ffffff"
    _GREEN   = "#00cc55"
    _RED     = "#dd2200"
    _YELLOW  = "#ccaa00"
    _BLUE    = "#4488ff"
    _BTN_DK  = "#2a2a2a"
    _BTN_LT  = "#e0e0e0"
    _DIM     = "#666666"

    def __init__(self, root):
        self.root = root
        self.root.title("MEMORY ARK WORKSTATION")
        self.root.geometry("1500x860")
        self.root.configure(bg=self._BG)
        self.root.minsize(900,600)

        self._settings      = self._load_settings()
        self._settings_win  = None
        self._last_chunk_ct = -1
        self._tab_ctr       = 0
        self._tabs          = []
        self._stop_flag     = threading.Event()
        self._null_event    = threading.Event(); self._null_event.set()
        self._sleep_event   = threading.Event()   # starts CLEARED

        self.telemetry_var = tk.StringVar(value=self.TELEMETRY_ACTIVE)

        # Streaming state
        self._stream_buf    = ""
        self._stream_active = False
        self._stream_lock   = threading.Lock()
        self._think_start   = None
        self._token_count   = 0   # counts tokens arriving from stream thread

        self._days_since_last = self._record_session()

        self.brain = BrainBridge(
            model    = self._settings.get("model",    OLLAMA_MODEL),
            api_mode = self._settings.get("api_mode", "ollama"),
            api_key  = self._settings.get("api_key",  ""),
            api_base = self._settings.get("api_base", ""),
        )
        self.rag = RAGPipeline()

        self._build_ui()
        for line in initialize_sandbox(): self._twrite(line)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._bg_indexer, daemon=True).start()
        self.root.after(700, self._boot)
        self.root.after(60_000, self._auto_save_tick)

    # =========================================================================
    # SETTINGS LOAD/SAVE
    # =========================================================================

    def _load_settings(self):
        s = dict(DEFAULT_SETTINGS)
        try:
            saved = json.loads(open(SETTINGS_FILE,encoding="utf-8").read())
            s.update(saved)
        except: pass
        return s

    def _save_settings_file(self):
        try:
            os.makedirs(ZONE_PATHS["AI"],exist_ok=True)
            open(SETTINGS_FILE,"w",encoding="utf-8").write(json.dumps(self._settings,indent=2))
        except: pass

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    def _record_session(self):
        days = None
        try:
            os.makedirs(ZONE_PATHS["AI"],exist_ok=True)
            lines = []
            if os.path.exists(SESSION_LOG):
                lines = [l.strip() for l in open(SESSION_LOG,encoding="utf-8") if l.strip()]
            if lines:
                try:
                    last_dt = datetime.datetime.strptime(lines[-1][:19],"%Y-%m-%d %H:%M:%S")
                    days    = (datetime.datetime.now()-last_dt).days
                except Exception: pass
            with open(SESSION_LOG,"a",encoding="utf-8") as fh: fh.write(f"{_now()}\n")
        except Exception: pass
        return days

    def _load_letter(self):
        try:
            text = open(LETTER_FILE,encoding="utf-8",errors="ignore").read().strip()
            if "Write standing instructions" in text and len(text)<200: return ""
            return text
        except Exception: return ""

    def _load_recent_history(self, n=8):
        try:
            text   = open(CONV_HISTORY,encoding="utf-8",errors="ignore").read()
            blocks = [b.strip() for b in text.split("\n---\n") if b.strip()]
            return "\n---\n".join(blocks[-n:] if len(blocks)>=n else blocks)
        except Exception: return ""

    def _save_exchange(self, query, response):
        try:
            os.makedirs(ZONE_PATHS["AI"],exist_ok=True)
            with open(CONV_HISTORY,"a",encoding="utf-8") as fh:
                fh.write(f"[{_now()}]\n[YOU]: {query}\n[MIND B]: {response}\n---\n")
        except Exception: pass

    def _upcoming_events(self, days_ahead=14):
        try:
            today=datetime.date.today(); cutoff=today+datetime.timedelta(days=days_ahead)
            lines=[]
            for line in open(CALENDAR_FILE,encoding="utf-8",errors="ignore"):
                line=line.strip()
                if not line or line.startswith("#") or line.startswith("["): continue
                parts=[p.strip() for p in line.split("|")]
                if len(parts)>=3:
                    try:
                        if today<=datetime.date.fromisoformat(parts[0])<=cutoff: lines.append(line)
                    except Exception: pass
            lines.sort(); return "\n".join(lines)
        except Exception: return ""

    # =========================================================================
    # UI BUILD
    # =========================================================================

    def _build_ui(self):
        top = tk.Frame(self.root, bg=self._TOPBAR, pady=5)
        top.pack(side=tk.TOP, fill=tk.X)
        tk.Label(top, text="MEMORY ARK", fg=self._TPFG, bg=self._TOPBAR,
                 font=("Courier",13,"bold")).pack(side=tk.LEFT, padx=14)
        tk.Label(top, text="|", fg=self._PFGDIM, bg=self._TOPBAR,
                 font=("Courier",12)).pack(side=tk.LEFT, padx=2)
        for label, val, color in [("Active",self.TELEMETRY_ACTIVE,self._GREEN),
                                   ("Reflective",self.TELEMETRY_REFLECTIVE,self._YELLOW),
                                   ("Null",self.TELEMETRY_NULL,self._RED)]:
            tk.Radiobutton(top,text=label,variable=self.telemetry_var,value=val,
                fg=color,bg=self._TOPBAR,selectcolor=self._TOPBAR,
                activebackground=self._TOPBAR,activeforeground=color,
                font=("Courier",10,"bold"),command=self._on_telemetry_change
            ).pack(side=tk.LEFT,padx=3)
        self._tbtn(top,"HELP",self._open_help,side=tk.RIGHT,padx=4)
        self._tbtn(top,"SETTINGS",self._open_settings,side=tk.RIGHT,padx=4)
        # CPU / RAM monitor
        self._cpu_lbl = tk.Label(top,
            text="CPU --% RAM --%",
            fg=self._PFGDIM, bg=self._TOPBAR, font=("Courier",9))
        self._cpu_lbl.pack(side=tk.RIGHT, padx=10)
        self.root.after(1500, self._update_sysmon)
        mf=tk.Frame(top,bg=self._TOPBAR); mf.pack(side=tk.RIGHT,padx=8)
        _sc=self._GREEN if self.brain.online else self._RED
        self._ollama_lbl=tk.Label(mf,
            text=f"AI: {self.brain._api_label()}" if self.brain.online else "AI: OFFLINE",
            fg=_sc,bg=self._TOPBAR,font=("Courier",10,"bold"))
        self._ollama_lbl.pack(side=tk.LEFT)
        avail=[self.brain.model]
        if REQUESTS_AVAILABLE and self._settings.get("api_mode","ollama")=="ollama":
            try:
                r=requests.get(f"{OLLAMA_BASE_URL}/api/tags",timeout=1)
                avail=[m["name"] for m in r.json().get("models",[])] or avail
            except: pass
        self.model_var=tk.StringVar(value=self.brain.model)
        dd=ttk.Combobox(mf,textvariable=self.model_var,values=avail,
                        state="readonly",width=24,font=("Courier",9))
        dd.pack(side=tk.LEFT,padx=(5,0))
        dd.bind("<<ComboboxSelected>>",self._on_model_change)

        pane=tk.PanedWindow(self.root,orient=tk.HORIZONTAL,
                            bg="#333333",sashwidth=4,sashrelief=tk.FLAT)
        pane.pack(fill=tk.BOTH,expand=True)
        ctx_frame=tk.Frame(pane,bg=self._PANEL)
        pane.add(ctx_frame,minsize=160,width=220); self._build_context_panel(ctx_frame)
        vault_frame=tk.Frame(pane,bg=self._BG)
        pane.add(vault_frame,minsize=300,width=700); self._build_vault_panel(vault_frame)
        term_frame=tk.Frame(pane,bg=self._BG)
        pane.add(term_frame,minsize=200,width=480); self._build_terminal_panel(term_frame)
        self.root.update_idletasks()
        try: pane.sash_place(0,220,0); pane.sash_place(1,920,0)
        except: pass

    # ── Context Panel ─────────────────────────────────────────────────────────

    def _build_context_panel(self, parent):
        tk.Label(parent,text="CONTEXT WINDOW",fg=self._PFGBRT,bg=self._PANEL,
                 font=("Courier",10,"bold"),anchor="w").pack(fill=tk.X,padx=6,pady=(6,2))
        tk.Label(parent,text="Files the AI can see.\nR = read only\nRW = read + write",
                 fg=self._PFGDIM,bg=self._PANEL,font=("Courier",8),
                 justify=tk.LEFT,anchor="w").pack(fill=tk.X,padx=6,pady=(0,4))
        tree_frame=tk.Frame(parent,bg=self._PANEL); tree_frame.pack(fill=tk.BOTH,expand=True,padx=4)
        style=ttk.Style()
        style.configure("Dark.Treeview",background=self._PANEL,foreground=self._PFGBRT,
                        fieldbackground=self._PANEL,rowheight=20)
        style.configure("Dark.Treeview.Heading",background="#333333",foreground=self._PFGDIM)
        style.map("Dark.Treeview",background=[("selected","#2255aa")])
        self._ctx_tree=ttk.Treeview(tree_frame,style="Dark.Treeview",
                                     columns=("perm",),show="tree headings",selectmode="extended")
        self._ctx_tree.heading("#0",text="File"); self._ctx_tree.heading("perm",text="P")
        self._ctx_tree.column("#0",width=155,minwidth=80)
        self._ctx_tree.column("perm",width=30,minwidth=30,anchor="center")
        vsb=ttk.Scrollbar(tree_frame,orient="vertical",command=self._ctx_tree.yview)
        self._ctx_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT,fill=tk.Y); self._ctx_tree.pack(fill=tk.BOTH,expand=True)
        self._ctx_tree.bind("<Double-1>",self._ctx_open_file)
        self._ctx_tree.bind("<<TreeviewOpen>>",self._ctx_on_open)
        for txt,cmd,clr in [
            ("Browse Files",  lambda: FileBrowserDialog(self), "#88ffaa"),
            ("+ Add File",    self._ctx_add_files,             self._PFGBRT),
            ("+ Add Folder",  self._ctx_add_folder,            self._PFGBRT),
            ("+ Ark Archive", self._ctx_add_ark,               self._PFGBRT),
            ("Toggle R/RW",   self._ctx_toggle_perm,           self._PFGBRT),
            ("Remove",        self._ctx_remove,                "#ff9988"),
        ]:
            tk.Button(parent,text=txt,command=cmd,bg="#222222",fg=clr,
                      font=("Courier",9),relief=tk.FLAT,pady=3,padx=4,
                      activebackground="#444444",activeforeground="#fff",anchor="w"
                      ).pack(fill=tk.X,padx=4,pady=1)
        self._ctx_refresh()

    # ── Vault Panel ───────────────────────────────────────────────────────────

    def _build_vault_panel(self, parent):
        hdr=tk.Frame(parent,bg=self._BG); hdr.pack(fill=tk.X,padx=4,pady=(4,0))
        tk.Label(hdr,text="HUMAN VAULT",fg="#000000",bg=self._BG,
                 font=("Courier",11,"bold")).pack(side=tk.LEFT)
        self._dirty_lbl=tk.Label(hdr,text="",fg=self._RED,bg=self._BG,
                                  font=("Courier",10,"bold")); self._dirty_lbl.pack(side=tk.LEFT,padx=8)
        tb1=tk.Frame(parent,bg=self._BG); tb1.pack(fill=tk.X,padx=4,pady=(2,0))
        for txt,cmd in [("New Tab",self._tab_new),("Open",self._tab_open),
                        ("Save",self._tab_save),("Save As",self._tab_save_as),
                        ("Close Tab",self._tab_close)]:
            self._lbtn(tb1,txt,cmd)
        tk.Label(tb1,text="|",fg=self._DIM,bg=self._BG,font=("Courier",11)).pack(side=tk.LEFT,padx=4)
        self._lbtn(tb1,"Mind B Notes",self._open_mindbnotes,fg="#2244aa")
        self._lbtn(tb1,"Grammar",self._check_grammar,fg="#664400")
        self._lbtn(tb1,"Write Journal",self._write_journal,fg="#005500")
        tb2=tk.Frame(parent,bg=self._BG); tb2.pack(fill=tk.X,padx=4,pady=(2,2))
        self._lbtn(tb2,"Letter to Mind B",self._open_letter,fg="#660044")
        self._lbtn(tb2,"Calendar",self._open_calendar,fg="#004466")
        self._lbtn(tb2,"Debate",self._debate,fg="#660066")
        style=ttk.Style()
        style.configure("Ark.TNotebook",background=self._BG,borderwidth=0)
        style.configure("Ark.TNotebook.Tab",background="#cccccc",foreground="#000000",
                        padding=[8,3],font=("Courier",9))
        style.map("Ark.TNotebook.Tab",background=[("selected","#ffffff")],
                  foreground=[("selected","#000000")])
        self._notebook=ttk.Notebook(parent,style="Ark.TNotebook")
        self._notebook.pack(fill=tk.BOTH,expand=True,padx=4,pady=(0,4))
        self._notebook.bind("<<NotebookTabChanged>>",self._on_tab_change)
        self._tab_new(title="New",content=f"[DATE: {_date()}]\n\n")

    # ── Terminal Panel ────────────────────────────────────────────────────────

    def _build_terminal_panel(self, parent):
        hdr_row=tk.Frame(parent,bg=self._BG); hdr_row.pack(fill=tk.X,padx=6,pady=(4,0))
        tk.Label(hdr_row,text="MIND B TERMINAL",fg="#000000",bg=self._BG,
                 font=("Courier",11,"bold")).pack(side=tk.LEFT)
        self._status_dot=tk.Label(hdr_row,text="  ●",fg=self._GREEN,bg=self._BG,
                                   font=("Courier",11,"bold")); self._status_dot.pack(side=tk.LEFT,padx=(16,2))
        self._status_lbl=tk.Label(hdr_row,text="IDLE",fg=self._GREEN,bg=self._BG,
                                   font=("Courier",10,"bold")); self._status_lbl.pack(side=tk.LEFT)
        self._lbtn(hdr_row,"Clear",self._terminal_clear,fg=self._DIM,side=tk.RIGHT,padx=4)

        self.terminal=scrolledtext.ScrolledText(parent,bg=self._TERM_BG,fg=self._TERM_FG,
            insertbackground=self._TERM_FG,font=("Courier",10),wrap=tk.WORD,
            state=tk.DISABLED,relief=tk.FLAT,borderwidth=1)
        self.terminal.pack(fill=tk.BOTH,expand=True,padx=6,pady=4)

        # Tool buttons row
        tool_row=tk.Frame(parent,bg=self._BG); tool_row.pack(fill=tk.X,padx=6,pady=(0,2))
        self._lbtn(tool_row,"Read Clipboard", self._read_clipboard, fg="#004400")
        self._lbtn(tool_row,"Fetch URL",       self._fetch_url_dialog, fg="#000044")
        self._lbtn(tool_row,"Export Chat",     self._export_chat,    fg="#440000")

        # Query row
        qrow=tk.Frame(parent,bg=self._BG); qrow.pack(fill=tk.X,padx=6,pady=(0,6))
        self._qentry=tk.Entry(qrow,bg="#ffffff",fg="#000000",insertbackground="#000000",
                               font=("Courier",11),relief=tk.FLAT)
        self._qentry.pack(side=tk.LEFT,fill=tk.X,expand=True,padx=(0,4))
        self._qentry.bind("<Return>",lambda _: self._ask())
        self._lbtn(qrow,"Ask",self._ask)

    # ── Button helpers ────────────────────────────────────────────────────────

    def _tbtn(self,parent,text,cmd,side=tk.LEFT,padx=4):
        tk.Button(parent,text=text,command=cmd,bg=self._BTN_DK,fg=self._TPFG,
                  font=("Courier",10),relief=tk.FLAT,padx=10,pady=3,
                  activebackground="#444444",activeforeground="#fff"
                  ).pack(side=side,padx=padx)

    def _lbtn(self,parent,text,cmd,fg=None,side=tk.LEFT,padx=3):
        tk.Button(parent,text=text,command=cmd,bg=self._BTN_LT,fg=fg or "#000000",
                  font=("Courier",10),relief=tk.FLAT,padx=8,pady=3,
                  activebackground="#bbbbbb",activeforeground="#000000"
                  ).pack(side=side,padx=padx)

    # =========================================================================
    # CONTEXT WINDOW
    # =========================================================================

    def _ctx_refresh(self):
        self._ctx_tree.delete(*self._ctx_tree.get_children())
        for item in self._settings.get("allowed_files",[]):
            path=item["path"]; perm=item.get("perm","R"); itype=item.get("type","file")
            name=os.path.basename(path.rstrip("/\\")) or path
            exists=os.path.exists(path)
            if not exists:
                self._ctx_tree.insert("",tk.END,iid=path,
                    text=f"[?] {name}",values=(perm,),tags=("missing",))
            elif itype=="folder":
                self._ctx_tree.insert("",tk.END,iid=path,
                    text=f"📁 {name}",values=(perm,),tags=("ctx_folder",))
                # Dummy child makes the expand arrow appear
                self._ctx_tree.insert(path,tk.END,iid=f"__dummy__{path}",
                    text="",values=("",),tags=("dummy",))
            else:
                self._ctx_tree.insert("",tk.END,iid=path,
                    text=f"📄 {name}",values=(perm,),tags=("ctx_file",))
        self._ctx_tree.tag_configure("missing",   foreground="#888800")
        self._ctx_tree.tag_configure("ctx_folder",foreground="#88aaff")
        self._ctx_tree.tag_configure("ctx_file",  foreground="#e8e8e8")
        self._ctx_tree.tag_configure("dummy",     foreground="#333333")

    def _ctx_on_open(self, event=None):
        """Lazy-load folder contents when the user clicks the expand arrow."""
        node = self._ctx_tree.focus()
        if not node: return
        children = self._ctx_tree.get_children(node)
        # Only expand if the only child is our dummy placeholder
        if not (len(children)==1 and str(children[0]).startswith("__dummy__")):
            return
        self._ctx_tree.delete(children[0])
        # Resolve actual path (strip __child__ prefix for nested nodes)
        actual = node[len("__child__"):] if node.startswith("__child__") else node
        if not os.path.isdir(actual): return
        _SHOW = {".txt",".md",".csv",".json",".py",".log",".rst",".xml"}
        try:
            entries = sorted(os.scandir(actual),
                             key=lambda e: (not e.is_dir(), e.name.lower()))
            for e in entries:
                if e.name.startswith("."): continue
                try: is_dir = e.is_dir()
                except: continue
                child_iid = f"__child__{e.path}"
                if is_dir:
                    self._ctx_tree.insert(node,tk.END,iid=child_iid,
                        text=f"📁 {e.name}",values=("",),tags=("ctx_folder",))
                    self._ctx_tree.insert(child_iid,tk.END,
                        iid=f"__dummy__{child_iid}",text="",values=("",),
                        tags=("dummy",))
                elif os.path.splitext(e.name)[1].lower() in _SHOW:
                    self._ctx_tree.insert(node,tk.END,iid=child_iid,
                        text=f"   {e.name}",values=("",),tags=("ctx_subfile",))
        except PermissionError:
            self._ctx_tree.insert(node,tk.END,
                text="[Access Denied]",values=("",),tags=("missing",))
        self._ctx_tree.tag_configure("ctx_subfile",foreground="#aaaaaa")

    def _ctx_add_files(self):
        paths=filedialog.askopenfilenames(title="Add files to AI context",
            filetypes=[("Text files","*.txt"),("All files","*.*")])
        for p in paths: self._ctx_add_item(p,"file")
        self._save_settings_file(); self._ctx_refresh()

    def _ctx_add_folder(self):
        path=filedialog.askdirectory(title="Add folder to AI context")
        if path: self._ctx_add_item(path,"folder"); self._save_settings_file(); self._ctx_refresh()

    def _ctx_add_ark(self):
        ark_paths=[r"C:\Users\thest\Desktop\Claude's Memory Ark - Copy\Ricky-s-Ark",
                   r"C:\Users\thest\Desktop\Ricky-s-Ark",
                   os.path.join(pathlib.Path.home(),"Desktop","Ricky-s-Ark")]
        added=[]
        for p in ark_paths:
            if os.path.exists(p): self._ctx_add_item(p,"folder"); added.append(p)
        for zone in ("Human","Shared"): self._ctx_add_item(ZONE_PATHS[zone],"folder",perm="RW")
        self._save_settings_file(); self._ctx_refresh()
        self._twrite(f"[CONTEXT] Added {len(added)+2} locations to context window.")

    def _ctx_add_item(self,path,itype,perm="R"):
        existing=[x["path"] for x in self._settings["allowed_files"]]
        if path not in existing:
            self._settings["allowed_files"].append({"path":path,"perm":perm,"type":itype})

    def _ctx_toggle_perm(self):
        sel=self._ctx_tree.selection()
        if not sel: return
        for iid in sel:
            for item in self._settings["allowed_files"]:
                if item["path"]==iid: item["perm"]="RW" if item["perm"]=="R" else "R"
        self._save_settings_file(); self._ctx_refresh()

    def _ctx_remove(self):
        sel=self._ctx_tree.selection()
        if not sel: return
        self._settings["allowed_files"]=[x for x in self._settings["allowed_files"] if x["path"] not in sel]
        self._save_settings_file(); self._ctx_refresh()

    def _ctx_open_file(self,event=None):
        sel=self._ctx_tree.selection()
        if not sel: return
        iid=sel[0]
        # Strip the __child__ prefix used for lazy-loaded tree nodes
        path = iid[len("__child__"):] if iid.startswith("__child__") else iid
        if os.path.isfile(path):
            self._tab_open_path(path)
        elif os.path.isdir(path):
            FileBrowserDialog(self)

    # =========================================================================
    # TAB MANAGEMENT
    # =========================================================================

    def _tab_new(self,title="New",content="",path=""):
        tid=self._tab_ctr; self._tab_ctr+=1
        frame=tk.Frame(self._notebook,bg=self._VBGW)
        widget=scrolledtext.ScrolledText(frame,bg=self._VBGW,fg=self._VFG,
            insertbackground=self._VFG,font=("Courier",11),wrap=tk.WORD,
            undo=True,relief=tk.FLAT,borderwidth=0)
        widget.pack(fill=tk.BOTH,expand=True)
        if content: widget.insert("1.0",content)
        widget.edit_modified(False)
        widget.bind("<<Modified>>",lambda e,i=tid: self._on_tab_modified(i))
        label=title if len(title)<=18 else title[:16]+".."
        self._notebook.add(frame,text=f" {label} "); self._notebook.select(frame)
        tab={"id":tid,"title":title,"path":path,"dirty":False,"widget":widget,"frame":frame}
        self._tabs.append(tab); return tab

    def _active_tab(self):
        current=self._notebook.select()
        if not current: return None
        for t in self._tabs:
            if str(t["frame"])==current: return t
        return None

    def _tab_by_id(self,tid):
        for t in self._tabs:
            if t["id"]==tid: return t
        return None

    def _on_tab_change(self,_=None):
        tab=self._active_tab()
        if tab: self._dirty_lbl.configure(text="[unsaved]" if tab["dirty"] else "")

    def _on_tab_modified(self,tid):
        tab=self._tab_by_id(tid)
        if tab and tab["widget"].edit_modified():
            tab["dirty"]=True
            if self._active_tab() and self._active_tab()["id"]==tid:
                self._dirty_lbl.configure(text="[unsaved]")

    def _tab_open(self):
        path=filedialog.askopenfilename(
            filetypes=[("Text files","*.txt"),("All files","*.*")],title="Open file")
        if path: self._tab_open_path(path)

    def _tab_open_path(self,path):
        for t in self._tabs:
            if t["path"]==path: self._notebook.select(t["frame"]); return
        try:
            content=open(path,encoding="utf-8",errors="ignore").read()
            tab=self._tab_new(title=os.path.basename(path),content=content,path=path)
            tab["dirty"]=False; tab["widget"].edit_modified(False)
            self._dirty_lbl.configure(text="")
        except Exception as exc: messagebox.showerror("Open Error",str(exc))

    def _tab_save(self):
        tab=self._active_tab()
        if not tab: return
        if not tab["path"]: self._tab_save_as(); return
        self._tab_write(tab,tab["path"])

    def _tab_save_as(self):
        tab=self._active_tab()
        if not tab: return
        path=filedialog.asksaveasfilename(
            initialdir=ZONE_PATHS["Human"],initialfile=f"{_date()}-{tab['title']}.txt",
            defaultextension=".txt",filetypes=[("Text files","*.txt"),("All files","*.*")],
            title="Save As")
        if path:
            tab["path"]=path; name=os.path.basename(path); tab["title"]=name
            self._notebook.tab(tab["frame"],text=f" {name[:16]} ")
            self._tab_write(tab,path)

    def _tab_write(self,tab,path):
        try:
            content=tab["widget"].get("1.0",tk.END)
            open(path,"w",encoding="utf-8").write(content)
            tab["dirty"]=False; tab["widget"].edit_modified(False)
            self._dirty_lbl.configure(text="")
            self._twrite(f"[SAVED] {os.path.basename(path)}")
            threading.Thread(target=self.rag.index_file,args=(path,),daemon=True).start()
        except Exception as exc: messagebox.showerror("Save Error",str(exc))

    def _tab_close(self):
        tab=self._active_tab()
        if not tab: return
        if len(self._tabs)==1:
            tab["widget"].delete("1.0",tk.END)
            tab["widget"].insert("1.0",f"[DATE: {_date()}]\n\n")
            tab["path"]=""; tab["dirty"]=False; tab["title"]="New"
            self._notebook.tab(tab["frame"],text=" New ")
            self._dirty_lbl.configure(text=""); return
        if tab["dirty"]:
            ans=messagebox.askyesnocancel("Unsaved",f"Save '{tab['title']}' before closing?")
            if ans is None: return
            if ans: self._tab_save()
        self._notebook.forget(tab["frame"]); self._tabs.remove(tab)
        if self._tabs: self._notebook.select(self._tabs[-1]["frame"])

    def _open_mindbnotes(self):
        self._tab_open_path(MINDBNOTES); self._twrite("[MIND B NOTES] Opened.")

    def _open_letter(self):
        if not os.path.exists(LETTER_FILE):
            with open(LETTER_FILE,"w",encoding="utf-8") as fh:
                fh.write(f"[LETTER TO MIND B — started {_date()}]\n\n"
                         "Write standing instructions here. Mind B reads this every session.\n\n")
        self._tab_open_path(LETTER_FILE)
        self._twrite("[LETTER] LETTER_TO_MIND_B.txt opened — Mind B reads this every session.")

    def _open_calendar(self): CalendarWindow(self)

    def _active_text(self):
        tab=self._active_tab()
        return tab["widget"].get("1.0",tk.END).strip() if tab else ""

    # =========================================================================
    # TOOL USE — read clipboard, fetch URL, export chat
    # =========================================================================

    def _read_clipboard(self):
        """
        Grab whatever text is currently on the clipboard
        and open it in a new editor tab so Mind B can read it.
        """
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self._twrite("[CLIPBOARD] Nothing on clipboard, or clipboard unavailable.")
            return
        if not text or not text.strip():
            self._twrite("[CLIPBOARD] Clipboard is empty."); return
        self._twrite(f"[CLIPBOARD] Read {len(text):,} characters.")
        self._tab_new(title="Clipboard",
                      content=f"[FROM CLIPBOARD — {_now()}]\n\n{text}",
                      path="")

    def _fetch_url_dialog(self):
        """Open a small dialog, fetch the URL, strip HTML, open result in tab."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Fetch Web Page")
        dialog.geometry("520x130")
        dialog.configure(bg=self._BG)
        dialog.resizable(False, False)
        tk.Label(dialog,
                 text="Paste a URL — the app fetches and strips the HTML text.\n"
                      "This bypasses copy-protection on web pages.",
                 fg="#000000", bg=self._BG, font=("Courier",9),
                 justify=tk.LEFT).pack(padx=14, pady=(12,4))
        url_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=url_var, width=64,
                         font=("Courier",10), bg="#fff", fg="#000",
                         relief=tk.FLAT, insertbackground="#000")
        entry.pack(fill=tk.X, padx=14, pady=2)
        entry.focus_set()
        def go():
            url = url_var.get().strip()
            if not url: return
            dialog.destroy()
            threading.Thread(target=self._fetch_and_show, args=(url,), daemon=True).start()
        entry.bind("<Return>", lambda _: go())
        btn=tk.Frame(dialog,bg=self._BG); btn.pack(pady=6)
        tk.Button(btn,text="Fetch",command=go,bg=self._BTN_DK,fg=self._TPFG,
                  font=("Courier",10),relief=tk.FLAT,padx=14,pady=4,
                  activebackground="#444").pack(side=tk.LEFT,padx=6)
        tk.Button(btn,text="Cancel",command=dialog.destroy,bg=self._BTN_LT,fg="#000",
                  font=("Courier",10),relief=tk.FLAT,padx=14,pady=4,
                  activebackground="#bbb").pack(side=tk.LEFT,padx=6)

    def _fetch_and_show(self, url):
        """Fetch URL in background thread, strip HTML, open in tab."""
        if not REQUESTS_AVAILABLE:
            self._twrite("[FETCH] 'requests' not installed: py -m pip install requests"); return
        self._twrite(f"[FETCH] Downloading: {url}")
        self._set_status("FETCHING...", self._BLUE)
        try:
            headers = {"User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"}
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            text = r.text
            # Strip scripts and style blocks first
            text = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>',
                          '', text, flags=re.DOTALL|re.IGNORECASE)
            # Strip all remaining HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Decode common HTML entities
            for src, dst in [('&amp;','&'),('&lt;','<'),('&gt;','>'),
                              ('&nbsp;',' '),('&quot;','"'),('&#39;',"'"),
                              ('&mdash;','—'),('&ndash;','–'),('&hellip;','...')]:
                text = text.replace(src, dst)
            # Collapse excess whitespace
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
            text = text.strip()
            char_count = len(text)
            self._twrite(f"[FETCH] Done — {char_count:,} characters extracted.")
            # Derive a short title
            domain = re.sub(r'https?://(www\.)?','', url).split('/')[0][:20]
            def open_tab(u=url, t=text, d=domain):
                self._tab_new(title=f"WEB:{d}", content=f"[SOURCE: {u}]\n\n{t}", path="")
            self.root.after(0, open_tab)
        except Exception as exc:
            self._twrite(f"[FETCH ERROR] {exc}")
        finally:
            self._set_status("IDLE", self._GREEN)

    def _export_chat(self):
        """Save the entire terminal output to a .txt file."""
        try:
            self.terminal.configure(state=tk.NORMAL)
            content = self.terminal.get("1.0", tk.END)
            self.terminal.configure(state=tk.DISABLED)
            path = filedialog.asksaveasfilename(
                initialdir=ZONE_PATHS["Human"],
                initialfile=f"CHAT_EXPORT_{_ts()}.txt",
                defaultextension=".txt",
                filetypes=[("Text files","*.txt"),("All files","*.*")],
                title="Export Chat Log")
            if path:
                open(path,"w",encoding="utf-8").write(content)
                self._twrite(f"[EXPORT] Chat saved: {os.path.basename(path)}")
        except Exception as exc:
            self._twrite(f"[EXPORT ERROR] {exc}")

    # ── Tool command parser (runs after every AI response) ────────────────────

    def _parse_tool_commands(self, response):
        """
        Scan AI response for [TOOL:TYPE:args] commands and execute each one.
        Called on the main thread after streaming completes.
        """
        commands = re.findall(r'\[TOOL:([A-Z]+):([^\]]+)\]', response)
        if not commands: return

        for cmd_type, cmd_args in commands:
            cmd_args = cmd_args.strip()

            if cmd_type == "OPEN":
                # Search allowed files and zone dirs for filename match
                self._tool_open(cmd_args)

            elif cmd_type == "NOTE":
                # Append to Mind B notes
                try:
                    with open(MINDBNOTES,"a",encoding="utf-8") as f:
                        f.write(f"[{_now()}] {cmd_args}\n\n")
                    self._twrite(f"[TOOL→NOTE] Saved to MIND_B_NOTES.txt")
                except Exception as exc:
                    self._twrite(f"[TOOL→NOTE ERROR] {exc}")

            elif cmd_type == "SAVE":
                # Format: /path/to/file.txt|content
                if "|" in cmd_args:
                    path, content = cmd_args.split("|", 1)
                    path = path.strip(); content = content.strip()
                    self._tool_save(path, content)
                else:
                    self._twrite(f"[TOOL→SAVE] Bad format. Need: path|content")

            elif cmd_type == "FETCH":
                threading.Thread(
                    target=self._fetch_and_show, args=(cmd_args,), daemon=True).start()

            elif cmd_type == "SEARCH":
                threading.Thread(
                    target=self._tool_search_files, args=(cmd_args,), daemon=True).start()

    def _tool_open(self, name_or_path):
        """Find and open a file by name or path."""
        # Exact path
        if os.path.isfile(name_or_path):
            self.root.after(0, lambda p=name_or_path: self._tab_open_path(p))
            self._twrite(f"[TOOL→OPEN] {name_or_path}"); return
        # Search allowed_files
        for item in self._settings.get("allowed_files",[]):
            p = item["path"]
            if os.path.isfile(p) and name_or_path.lower() in p.lower():
                self.root.after(0, lambda fp=p: self._tab_open_path(fp))
                self._twrite(f"[TOOL→OPEN] Found: {p}"); return
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if name_or_path.lower() in f.lower():
                            fp = os.path.join(root, f)
                            self.root.after(0, lambda x=fp: self._tab_open_path(x))
                            self._twrite(f"[TOOL→OPEN] Found: {fp}"); return
        # Search all zones
        for zone_path in ZONE_PATHS.values():
            if not os.path.exists(zone_path): continue
            for root, _, files in os.walk(zone_path):
                for f in files:
                    if name_or_path.lower() in f.lower():
                        fp = os.path.join(root, f)
                        self.root.after(0, lambda x=fp: self._tab_open_path(x))
                        self._twrite(f"[TOOL→OPEN] Found: {fp}"); return
        self._twrite(f"[TOOL→OPEN] Not found: {name_or_path}")

    def _tool_save(self, path, content):
        """Save content to path — only if path is in an RW zone."""
        rw_roots = [x["path"] for x in self._settings.get("allowed_files",[])
                    if x.get("perm")=="RW"]
        # AI zone is always writable for Mind B
        rw_roots.append(ZONE_PATHS["AI"])
        if any(path.startswith(rr) for rr in rw_roots):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path,"a",encoding="utf-8") as f:
                    f.write(f"\n[{_now()}]\n{content}\n")
                self._twrite(f"[TOOL→SAVE] Written to: {os.path.basename(path)}")
            except Exception as exc:
                self._twrite(f"[TOOL→SAVE ERROR] {exc}")
        else:
            self._twrite(f"[TOOL→SAVE BLOCKED] {path} — not in an RW context slot. "
                         "Add the folder to Context Window and toggle RW.")

    def _tool_search_files(self, keyword):
        """
        Search all context files and zone directories for a keyword.
        Reports every file that contains it plus the first matching line.
        """
        self._twrite(f"[TOOL→SEARCH] Searching for: '{keyword}'")
        kw      = keyword.lower()
        seen    = set()
        matches = []
        _EXTS   = (".txt",".md",".csv",".log",".py",".json",".rst",".xml")

        def _check(fp):
            if fp in seen: return
            seen.add(fp)
            try:
                text = open(fp, encoding="utf-8", errors="ignore").read()
                if kw not in text.lower(): return
                for i, line in enumerate(text.splitlines(), 1):
                    if kw in line.lower():
                        snippet = line.strip()[:90]
                        matches.append(
                            f"  [{os.path.basename(fp)}]  line {i}:  {snippet}")
                        break
            except Exception: pass

        # Search context window slots
        for item in self._settings.get("allowed_files", []):
            p = item["path"]
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(_EXTS):
                            _check(os.path.join(root, f))
            elif os.path.isfile(p):
                _check(p)

        # Also search all zone directories
        for zp in ZONE_PATHS.values():
            if os.path.isdir(zp):
                for root, _, files in os.walk(zp):
                    for f in files:
                        if f.lower().endswith(_EXTS):
                            _check(os.path.join(root, f))

        if matches:
            msg = (f"[SEARCH '{keyword}']  Found in {len(matches)} file(s):\n"
                   + "\n".join(matches[:30]))
            if len(matches) > 30:
                msg += f"\n  ... and {len(matches)-30} more."
        else:
            msg = f"[SEARCH '{keyword}']  No matches found in any indexed files."
        self._twrite(msg)

    # =========================================================================
    # HELP WINDOW
    # =========================================================================

    def _open_help(self):
        win=tk.Toplevel(self.root); win.title("HELP — Memory Ark Workstation")
        win.geometry("780x640"); win.configure(bg=self._BG)
        tk.Label(win,text="MEMORY ARK WORKSTATION — INSTRUCTIONS",fg=self._TPFG,
                 bg=self._TOPBAR,font=("Courier",12,"bold"),pady=8).pack(fill=tk.X)
        txt=scrolledtext.ScrolledText(win,bg="#0a0a14",fg="#d4d4c8",
            font=("Courier",10),wrap=tk.WORD,relief=tk.FLAT,
            borderwidth=0,padx=16,pady=12)
        txt.pack(fill=tk.BOTH,expand=True)
        txt.insert("1.0",HELP_TEXT); txt.configure(state=tk.DISABLED)
        tk.Button(win,text="Close",command=win.destroy,bg=self._BTN_DK,fg=self._TPFG,
                  font=("Courier",10),relief=tk.FLAT,padx=16,pady=5,
                  activebackground="#444").pack(pady=8)

    # =========================================================================
    # AUTO-SAVE
    # =========================================================================

    def _auto_save_tick(self):
        mins=self._settings.get("auto_save_min",0)
        if mins>0:
            for tab in self._tabs:
                if tab["dirty"] and tab["path"]: self._tab_write(tab,tab["path"])
        ms=max(30_000,mins*60_000) if mins>0 else 60_000
        self.root.after(ms,self._auto_save_tick)

    # =========================================================================
    # SETTINGS WINDOW
    # =========================================================================

    def _open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift(); return
        win=tk.Toplevel(self.root); win.title("SETTINGS")
        win.geometry("720x700"); win.configure(bg=self._BG)
        self._settings_win=win

        def section(text):
            tk.Label(win,text=text,fg=self._TPFG,bg=self._TOPBAR,
                     font=("Courier",10,"bold"),anchor="w",pady=3,padx=8
                     ).pack(fill=tk.X,padx=12,pady=(10,2))

        section("SYSTEM PROMPT  —  what Mind B believes about itself")
        self._sp_edit=scrolledtext.ScrolledText(win,bg="#f8f8f8",fg="#000000",
            font=("Courier",10),wrap=tk.WORD,height=8,relief=tk.FLAT,borderwidth=1)
        self._sp_edit.pack(fill=tk.X,padx=12,pady=(0,2))
        self._sp_edit.insert("1.0",self._settings.get("system_prompt",DEFAULT_SYSTEM_PROMPT))
        tk.Button(win,text="Reset to Default",command=self._reset_prompt,
                  bg=self._BTN_LT,fg="#000000",font=("Courier",9),
                  relief=tk.FLAT,padx=8,pady=2).pack(anchor="w",padx=12)
        ttk.Separator(win,orient="horizontal").pack(fill=tk.X,padx=12,pady=6)

        section("TIMING & PERFORMANCE")
        g1=tk.Frame(win,bg=self._BG); g1.pack(fill=tk.X,padx=20)
        def rl(r,t): tk.Label(g1,text=t,fg="#000",bg=self._BG,font=("Courier",10),
                               anchor="w").grid(row=r,column=0,sticky="w",pady=3,padx=(0,12))
        def dn(r,t): tk.Label(g1,text=t,fg=self._DIM,bg=self._BG,font=("Courier",8),
                               anchor="w").grid(row=r,column=2,sticky="w",padx=8)
        rl(0,"Index interval (minutes):"); dn(0,"How often RAG re-reads your files.")
        self._int_var=tk.IntVar(value=self._settings.get("index_interval_min",5))
        ttk.Spinbox(g1,from_=1,to=60,textvariable=self._int_var,
                    width=5,font=("Courier",10)).grid(row=0,column=1,sticky="w")
        rl(1,"Auto-save interval (0=off):"); dn(1,"Auto-save open tabs in minutes.")
        self._as_var=tk.IntVar(value=self._settings.get("auto_save_min",0))
        ttk.Spinbox(g1,from_=0,to=60,textvariable=self._as_var,
                    width=5,font=("Courier",10)).grid(row=1,column=1,sticky="w")
        rl(2,"Context tokens (num_ctx):"); dn(2,"Ollama: 8192=~6k words. Higher=more RAM.")
        self._nc_var=tk.IntVar(value=self._settings.get("num_ctx",8192))
        ttk.Spinbox(g1,from_=2048,to=131072,increment=1024,textvariable=self._nc_var,
                    width=8,font=("Courier",10)).grid(row=2,column=1,sticky="w")
        self._ai_var=tk.BooleanVar(value=self._settings.get("auto_index",True))
        chks=tk.Frame(win,bg=self._BG); chks.pack(fill=tk.X,padx=20,pady=4)
        tk.Checkbutton(chks,text="Auto-index files on schedule",variable=self._ai_var,
            bg=self._BG,fg="#000000",font=("Courier",10),
            activebackground=self._BG,selectcolor="#cccccc").pack(side=tk.LEFT)
        ttk.Separator(win,orient="horizontal").pack(fill=tk.X,padx=12,pady=6)

        section("AI BACKEND  —  Ollama / OpenAI / Anthropic / Custom")
        g2=tk.Frame(win,bg=self._BG); g2.pack(fill=tk.X,padx=20)
        def rl2(r,t): tk.Label(g2,text=t,fg="#000",bg=self._BG,font=("Courier",10),
                                anchor="w").grid(row=r,column=0,sticky="w",pady=3,padx=(0,12))
        def dn2(r,t): tk.Label(g2,text=t,fg=self._DIM,bg=self._BG,font=("Courier",8),
                                anchor="w").grid(row=r,column=2,sticky="w",padx=8)
        api_modes=["Ollama (local)","OpenAI API","Anthropic API","Custom (OpenAI-compatible)"]
        mode_map={"ollama":"Ollama (local)","openai":"OpenAI API",
                  "anthropic":"Anthropic API","custom":"Custom (OpenAI-compatible)"}
        mode_rev={v:k for k,v in mode_map.items()}
        self._mode_rev=mode_rev
        cur_label=mode_map.get(self._settings.get("api_mode","ollama"),"Ollama (local)")
        self._api_mode_var=tk.StringVar(value=cur_label)
        rl2(0,"API Mode:")
        ttk.Combobox(g2,textvariable=self._api_mode_var,values=api_modes,
                     state="readonly",width=30,font=("Courier",9)
                     ).grid(row=0,column=1,columnspan=2,sticky="w")
        rl2(1,"Model name:"); dn2(1,"e.g. llama3.1:8b  gpt-4o  claude-opus-4-5")
        self._model_entry_var=tk.StringVar(value=self._settings.get("model",OLLAMA_MODEL))
        tk.Entry(g2,textvariable=self._model_entry_var,width=32,font=("Courier",9),
                 bg="#fff",fg="#000",relief=tk.FLAT,insertbackground="#000"
                 ).grid(row=1,column=1,sticky="w")
        rl2(2,"API Key:"); dn2(3,"Leave blank for Ollama. Stored in AI/settings.json (local).")
        self._api_key_var=tk.StringVar(value=self._settings.get("api_key",""))
        tk.Entry(g2,textvariable=self._api_key_var,width=44,font=("Courier",9),
                 bg="#fff",fg="#000",relief=tk.FLAT,insertbackground="#000",show="*"
                 ).grid(row=2,column=1,columnspan=2,sticky="w")
        tk.Label(g2,text="",bg=self._BG).grid(row=3,column=0)
        rl2(4,"Custom Base URL:"); dn2(5,"Custom mode: e.g. http://localhost:1234/v1 (LM Studio)")
        self._api_base_var=tk.StringVar(value=self._settings.get("api_base",""))
        tk.Entry(g2,textvariable=self._api_base_var,width=44,font=("Courier",9),
                 bg="#fff",fg="#000",relief=tk.FLAT,insertbackground="#000"
                 ).grid(row=4,column=1,columnspan=2,sticky="w")
        tk.Label(g2,text="",bg=self._BG).grid(row=5,column=0)

        ttk.Separator(win,orient="horizontal").pack(fill=tk.X,padx=12,pady=6)

        section("PATHS  —  where everything is saved")
        g3=tk.Frame(win,bg=self._BG); g3.pack(fill=tk.X,padx=20)
        def rl3(r,t): tk.Label(g3,text=t,fg="#000",bg=self._BG,font=("Courier",10),
                                anchor="w").grid(row=r,column=0,sticky="w",pady=3,padx=(0,8))
        def dn3(r,t): tk.Label(g3,text=t,fg=self._DIM,bg=self._BG,font=("Courier",8),
                                anchor="w").grid(row=r,column=2,sticky="w",padx=6)
        rl3(0,"Memory Ark folder:"); dn3(0,"Where Human/Shared/AI/Debate zones live.  Requires restart.")
        self._base_dir_var=tk.StringVar(value=self._settings.get("base_dir",BASE_DIR))
        tk.Entry(g3,textvariable=self._base_dir_var,width=38,font=("Courier",9),
                 bg="#fff",fg="#000",relief=tk.FLAT,insertbackground="#000"
                 ).grid(row=0,column=1,sticky="ew",padx=(0,4))
        def _browse_base():
            p=filedialog.askdirectory(title="Choose Memory Ark root folder",parent=win)
            if p: self._base_dir_var.set(p)
        tk.Button(g3,text="Browse",command=_browse_base,bg=self._BTN_LT,fg="#000",
                  font=("Courier",9),relief=tk.FLAT,padx=6,pady=2
                  ).grid(row=0,column=3)

        rl3(1,"Backup destination:"); dn3(1,"USB drive or any folder.  Applied immediately.")
        self._backup_path_var=tk.StringVar(value=self._settings.get("backup_path",BACKUP_USB_PATH))
        tk.Entry(g3,textvariable=self._backup_path_var,width=38,font=("Courier",9),
                 bg="#fff",fg="#000",relief=tk.FLAT,insertbackground="#000"
                 ).grid(row=1,column=1,sticky="ew",padx=(0,4))
        def _browse_backup():
            p=filedialog.askdirectory(title="Choose backup destination",parent=win)
            if p: self._backup_path_var.set(p)
        tk.Button(g3,text="Browse",command=_browse_backup,bg=self._BTN_LT,fg="#000",
                  font=("Courier",9),relief=tk.FLAT,padx=6,pady=2
                  ).grid(row=1,column=3)
        g3.columnconfigure(1,weight=1)

        ttk.Separator(win,orient="horizontal").pack(fill=tk.X,padx=12,pady=6)
        dep=tk.Frame(win,bg="#eeeeee",bd=1,relief=tk.SUNKEN); dep.pack(fill=tk.X,padx=12,pady=(0,4))
        req="OK" if REQUESTS_AVAILABLE else "MISSING  →  py -m pip install requests"
        chr="OK" if CHROMA_AVAILABLE   else "MISSING  →  py -m pip install chromadb"
        psu="OK" if PSUTIL_AVAILABLE   else "MISSING  →  py -m pip install psutil"
        all_ok = REQUESTS_AVAILABLE and CHROMA_AVAILABLE and PSUTIL_AVAILABLE
        tk.Label(dep,
            text=f"  requests: {req}\n  chromadb: {chr}\n  psutil:   {psu}",
            fg="#000000" if all_ok else self._RED,
            bg="#eeeeee",font=("Courier",9),anchor="w",justify=tk.LEFT,
            ).pack(fill=tk.X,padx=4,pady=4)

        btns=tk.Frame(win,bg=self._BG); btns.pack(fill=tk.X,padx=12,pady=(4,10))
        for txt,cmd,fg,bg in [("Save Settings",self._apply_settings,self._TPFG,self._BTN_DK),
                               ("Index Now",self._index_now,"#005500",self._BTN_LT),
                               ("Clear Terminal",self._terminal_clear,self._DIM,self._BTN_LT),
                               ("Help",self._open_help,"#004488",self._BTN_LT),
                               ("Close",win.destroy,"#000000",self._BTN_LT)]:
            tk.Button(btns,text=txt,command=cmd,bg=bg,fg=fg,font=("Courier",10),
                      relief=tk.FLAT,padx=10,pady=4,
                      activebackground="#555555" if bg==self._BTN_DK else "#cccccc",
                      activeforeground="#fff").pack(side=tk.LEFT,padx=4)

    def _reset_prompt(self):
        if hasattr(self,"_sp_edit") and self._sp_edit.winfo_exists():
            self._sp_edit.delete("1.0",tk.END)
            self._sp_edit.insert("1.0",DEFAULT_SYSTEM_PROMPT)

    def _apply_settings(self):
        if not (self._settings_win and self._settings_win.winfo_exists()): return
        self._settings["system_prompt"]      = self._sp_edit.get("1.0",tk.END).strip()
        self._settings["index_interval_min"] = max(1,self._int_var.get())
        self._settings["auto_save_min"]       = max(0,self._as_var.get())
        self._settings["num_ctx"]             = max(2048,self._nc_var.get())
        self._settings["auto_index"]          = self._ai_var.get()
        self._settings["api_mode"]    = self._mode_rev.get(self._api_mode_var.get(),"ollama")
        self._settings["model"]       = self._model_entry_var.get().strip() or OLLAMA_MODEL
        self._settings["api_key"]     = self._api_key_var.get().strip()
        self._settings["api_base"]    = self._api_base_var.get().strip()
        new_base   = self._base_dir_var.get().strip()
        new_backup = self._backup_path_var.get().strip()
        base_changed = (new_base != self._settings.get("base_dir", BASE_DIR))
        self._settings["base_dir"]    = new_base
        self._settings["backup_path"] = new_backup or BACKUP_USB_PATH
        # Persist path settings to global config so they survive across installs
        try:
            cfg = _load_global_cfg()
            cfg["base_dir"]   = new_base
            cfg["backup_path"]= self._settings["backup_path"]
            open(GLOBAL_CONFIG,"w",encoding="utf-8").write(json.dumps(cfg,indent=2))
        except Exception as e:
            self._twrite(f"[WARN] Could not write global config: {e}")
        self._save_settings_file()
        self.brain.model=self._settings["model"]; self.brain.api_mode=self._settings["api_mode"]
        self.brain.api_key=self._settings["api_key"]; self.brain.api_base=self._settings["api_base"]
        self.brain._probe()
        self.model_var.set(self.brain.model)
        c=self._GREEN if self.brain.online else self._RED
        self._ollama_lbl.configure(
            text=f"AI: {self.brain._api_label()}" if self.brain.online else "AI: OFFLINE",fg=c)
        self._sleep_event.set()
        self._twrite(f"[SETTINGS] Saved. Mode: {self._settings['api_mode']}  "
                     f"Model: {self._settings['model']}  "
                     f"Backup: {self._settings['backup_path']}")
        if base_changed:
            messagebox.showinfo("Restart Required",
                f"Memory Ark folder changed to:\n{new_base}\n\n"
                "Close and reopen the app to use the new location.",
                parent=self._settings_win)

    # =========================================================================
    # TELEMETRY
    # =========================================================================

    def _on_telemetry_change(self):
        s=self.telemetry_var.get()
        if s==self.TELEMETRY_ACTIVE:
            self._null_event.set(); self._twrite("[TELEMETRY] ACTIVE.")
        elif s==self.TELEMETRY_REFLECTIVE:
            self._null_event.set(); self._twrite("[TELEMETRY] REFLECTIVE — silent indexing.")
        else:
            self._null_event.clear(); self._twrite("[TELEMETRY] NULL — AI off.")

    def _on_model_change(self,_=None):
        self.brain.model=self.model_var.get()
        self._settings["model"]=self.brain.model
        self._save_settings_file()
        self._twrite(f"[SYSTEM] Model: {self.brain.model}")

    @property
    def _terminal_ok(self): return self.telemetry_var.get()==self.TELEMETRY_ACTIVE
    @property
    def _proc_ok(self):     return self._null_event.is_set()

    # =========================================================================
    # TERMINAL OUTPUT
    # =========================================================================

    def _twrite(self, text):
        def _do():
            self.terminal.configure(state=tk.NORMAL)
            stamp=datetime.datetime.now().strftime("%H:%M:%S")
            self.terminal.insert(tk.END, f"[{stamp}] {text}\n")
            self.terminal.see(tk.END)
            self.terminal.configure(state=tk.DISABLED)
        self.root.after(0, _do)

    def _terminal_clear(self):
        self.terminal.configure(state=tk.NORMAL)
        self.terminal.delete("1.0",tk.END)
        self.terminal.configure(state=tk.DISABLED)
        self._twrite("[CLEARED]")

    def _set_status(self, text, color=None):
        color=color or self._GREEN
        def _do():
            self._status_lbl.configure(text=text,fg=color)
            self._status_dot.configure(fg=color)
        self.root.after(0,_do)

    def _update_sysmon(self):
        """Update CPU/RAM display in topbar every 2 seconds."""
        if PSUTIL_AVAILABLE:
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                text  = f"CPU {cpu:3.0f}%  RAM {mem.percent:3.0f}%"
                color = self._RED if (cpu > 85 or mem.percent > 90) else self._PFGDIM
                self._cpu_lbl.configure(text=text, fg=color)
            except Exception: pass
        else:
            self._cpu_lbl.configure(text="install psutil for CPU/RAM")
        self.root.after(2000, self._update_sysmon)

    def _tick_thinking(self):
        if not self._think_start or not self._stream_active: return
        elapsed=int((datetime.datetime.now()-self._think_start).total_seconds())
        tc=self._token_count
        self._set_status(f"GENERATING  ({elapsed}s, {tc} tok)", self._YELLOW)
        self.root.after(1000, self._tick_thinking)

    # ── Streaming output — all widget writes happen directly on the main thread ──

    def _tstream_start(self):
        """
        Open a new response block in the terminal.
        Called from _ask() which is already on the main thread,
        so we write directly to the widget — no after() needed.
        """
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.terminal.configure(state=tk.NORMAL)
        model_label = self.brain.model.upper()
        self.terminal.insert(tk.END, f"\n[{stamp}] ▶ {model_label} — MIND B:\n")
        self.terminal.see(tk.END)
        self.terminal.configure(state=tk.DISABLED)
        with self._stream_lock:
            self._stream_buf    = ""
            self._stream_active = True
        self._token_count = 0
        # Start the flush loop — 40ms for snappy token display
        self.root.after(40, self._tstream_flush)

    def _tstream_token(self, token):
        """Called from stream thread — buffer the token and count it."""
        with self._stream_lock:
            self._stream_buf += token
        self._token_count += 1   # GIL-safe integer increment, no lock needed

    def _tstream_flush(self):
        """
        Runs every 40ms on the main thread.
        Drains the token buffer directly into the terminal widget.
        Stops when _stream_active is False (set by _tstream_end in stream thread).
        """
        with self._stream_lock:
            buf          = self._stream_buf
            self._stream_buf  = ""
            still_active = self._stream_active

        if buf:
            # Direct widget write — we ARE on the main thread here
            self.terminal.configure(state=tk.NORMAL)
            self.terminal.insert(tk.END, buf)
            self.terminal.see(tk.END)
            self.terminal.configure(state=tk.DISABLED)

        if still_active:
            self.root.after(40, self._tstream_flush)   # keep draining
        else:
            # Flush done — add a blank line after the response
            self.terminal.configure(state=tk.NORMAL)
            self.terminal.insert(tk.END, "\n")
            self.terminal.see(tk.END)
            self.terminal.configure(state=tk.DISABLED)

    def _tstream_end(self):
        """Signal from stream thread that generation is complete."""
        with self._stream_lock:
            self._stream_active = False
        self._think_start = None
        self._set_status("IDLE", self._GREEN)

    # =========================================================================
    # BACKGROUND INDEXER
    # =========================================================================

    def _index_now(self):
        self._sleep_event.set(); self._twrite("[INDEX] Manual re-index triggered.")

    def _index_sources(self):
        allowed=self._settings.get("allowed_files",[])
        if allowed: return [(x["path"],x.get("type","file")) for x in allowed]
        return [(ZONE_PATHS["Human"],"folder"),(ZONE_PATHS["Shared"],"folder")]

    def _bg_indexer(self):
        time.sleep(4)
        while not self._stop_flag.is_set():
            self._null_event.wait()
            if self._stop_flag.is_set(): break
            if self._settings.get("auto_index",True):
                self._set_status("INDEXING...",self._BLUE)
                total=0
                for path,itype in self._index_sources():
                    if not os.path.exists(path): continue
                    total+=(self.rag.index_directory(path) if itype=="folder"
                            else self.rag.index_file(path))
                if total!=self._last_chunk_ct and self._terminal_ok:
                    self._twrite(f"[RAG] Index updated: {total} chunks.")
                    self._last_chunk_ct=total
                self._set_status("IDLE",self._GREEN)
            secs=self._settings.get("index_interval_min",5)*60
            self._sleep_event.wait(timeout=secs); self._sleep_event.clear()

    # =========================================================================
    # AI INTERACTION
    # =========================================================================

    def _ask(self):
        query=self._qentry.get().strip()
        if not query: return
        self._qentry.delete(0,tk.END)
        if not self._proc_ok: self._twrite("[NULL] Query blocked."); return
        # Write [YOU] DIRECTLY — _ask runs on main thread and _tstream_start also
        # writes directly, so _twrite's after(0) would wrongly appear AFTER MIND B header.
        self.terminal.configure(state=tk.NORMAL)
        _s = datetime.datetime.now().strftime("%H:%M:%S")
        self.terminal.insert(tk.END, f"\n[{_s}] ► YOU:\n{query}\n")
        self.terminal.see(tk.END)
        self.terminal.configure(state=tk.DISABLED)

        system  = self._settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        system  = system + "\n" + TOOL_SYSTEM_SUFFIX   # always inject tool instructions
        num_ctx = self._settings.get("num_ctx", 8192)
        saved   = self.rag.query(query)
        active  = self._active_text()
        context = f"{saved}\n\n[ACTIVE EDITOR]:\n{active}" if active else saved

        # Inject zone paths, letter, history, events
        letter  = self._load_letter()
        history = self._load_recent_history()
        events  = self._upcoming_events()
        prefix  = (f"[SESSION]\n"
                   f"  Model:   {self.brain.model}  ({self.brain.api_mode})\n"
                   f"  Date:    {_now()}\n\n"
                   f"[ZONE PATHS]\n"
                   f"  AI:     {ZONE_PATHS['AI']}\n"
                   f"  Human:  {ZONE_PATHS['Human']}\n"
                   f"  Shared: {ZONE_PATHS['Shared']}\n\n")
        if letter:
            prefix += f"[LETTER TO MIND B — standing instructions]:\n{letter}\n\n"
        if history:
            prefix += f"[RECENT CONVERSATION HISTORY]:\n{history}\n\n"
        if events:
            prefix += f"[UPCOMING CALENDAR EVENTS — next 14 days]:\n{events}\n\n"
        context = prefix + context

        self._think_start = datetime.datetime.now()
        self._set_status("GENERATING  (0s)", self._YELLOW)
        self.root.after(1000, self._tick_thinking)
        self._tstream_start()   # writes header directly to terminal

        def on_token(token):
            # Called from stream thread — buffer only
            self._tstream_token(token)

        def on_done(full_response):
            # Called from stream thread
            self._tstream_end()
            self._log_interaction(query, full_response)
            # Parse and execute any tool commands on the main thread
            self.root.after(200, lambda r=full_response: self._parse_tool_commands(r))

        self.brain.generate_stream(query, system, context, on_token, on_done, num_ctx)

    def _run_query(self, query, context, system):
        """Non-streaming query — grammar, journal, debate."""
        num_ctx=self._settings.get("num_ctx",8192)
        system_full = system + "\n" + TOOL_SYSTEM_SUFFIX
        self._set_status("THINKING...",self._YELLOW)
        response=self.brain.generate(query,system=system_full,context=context,num_ctx=num_ctx)
        self._set_status("IDLE",self._GREEN)
        if self._terminal_ok: self._twrite(f"[MIND B]\n{response}")
        self._log_interaction(query,response)
        return response

    def _log_interaction(self, query, response):
        stamp=_now()
        try:
            with open(OBSERVATIONS,"a",encoding="utf-8") as fh:
                fh.write(f"\n[{stamp}] YOU: {query}\n[{stamp}] MIND B: {response}\n")
            if "?" in response:
                for s in response.replace("\n"," ").split(". "):
                    if "?" in s:
                        with open(QUESTIONS,"a",encoding="utf-8") as fq:
                            fq.write(f"[{stamp}] DEFERRED: {s.strip()}\n")
            with open(MINDBNOTES,"a",encoding="utf-8") as fn:
                fn.write(f"[{stamp}] QUERY: {query[:100]}\n"
                         f"[{stamp}] NOTE: {response[:200].replace(chr(10),' ')}\n\n")
        except: pass
        self._save_exchange(query,response)

    def _debate(self):
        if not self._proc_ok: self._twrite("[NULL] Debate blocked."); return
        text=self._active_text()
        if not text: self._twrite("[DEBATE] No text in active tab."); return
        system=("You are the Debate Engine. PROHIBITED: agreeing with the operator. "
                "Find ONE structural flaw, missing variable, or emotional bias. Present it directly.")
        self._twrite("[DEBATE] Mind B challenging active document...")
        self._set_status("DEBATING...",self._YELLOW)
        threading.Thread(target=self._run_query,
            args=(f"Challenge this:\n\n{text[:3000]}","",system),daemon=True).start()

    def _check_grammar(self):
        if not self._proc_ok: self._twrite("[NULL] Grammar check blocked."); return
        text=self._active_text()
        if not text: self._twrite("[GRAMMAR] No text in active tab."); return
        self._twrite("[GRAMMAR] Checking active document...")
        self._set_status("CHECKING GRAMMAR...",self._YELLOW)
        num_ctx=self._settings.get("num_ctx",8192)
        def run():
            response=self.brain.generate(f"Review this text:\n\n{text[:3000]}",
                system=GRAMMAR_SYSTEM_PROMPT,context="",num_ctx=num_ctx)
            self._set_status("IDLE",self._GREEN)
            if self._terminal_ok: self._twrite(f"[GRAMMAR REVIEW]\n{response}")
        threading.Thread(target=run,daemon=True).start()

    def _write_journal(self):
        if not self._proc_ok: self._twrite("[NULL] Journal write blocked."); return
        self._twrite("[JOURNAL] Mind B writing journal entry...")
        self._set_status("WRITING JOURNAL...",self._YELLOW)
        num_ctx=self._settings.get("num_ctx",8192)
        def run():
            context=""
            try:
                obs=open(OBSERVATIONS,encoding="utf-8",errors="ignore").read()[-3000:]
                context=f"[RECENT OBSERVATIONS]:\n{obs}"
            except: pass
            active=self._active_text()
            if active: context+=f"\n\n[ACTIVE DOCUMENT]:\n{active[:1500]}"
            history=self._load_recent_history(n=4)
            if history: context+=f"\n\n[RECENT CONVERSATION HISTORY]:\n{history}"
            response=self.brain.generate(f"Write a journal entry for {_now()}.",
                system=JOURNAL_SYSTEM_PROMPT,context=context,num_ctx=num_ctx)
            os.makedirs(JOURNAL_DIR,exist_ok=True)
            jpath=os.path.join(JOURNAL_DIR,f"{_ts()}-JOURNAL.txt")
            try:
                with open(jpath,"w",encoding="utf-8") as fj:
                    fj.write(f"[MIND B JOURNAL ENTRY]\n[DATE: {_now()}]\n\n{response}\n")
                if self._terminal_ok:
                    self._twrite(f"[JOURNAL] Saved: {os.path.basename(jpath)}\n\n{response[:400]}...")
            except Exception as exc: self._twrite(f"[JOURNAL ERROR] {exc}")
            self._set_status("IDLE",self._GREEN)
        threading.Thread(target=run,daemon=True).start()

    # =========================================================================
    # BOOT
    # =========================================================================

    def _boot(self):
        obs=q=0
        try: obs=len([l for l in open(OBSERVATIONS,encoding="utf-8",errors="ignore") if l.strip()])
        except: pass
        try: q=len([l for l in open(QUESTIONS,encoding="utf-8",errors="ignore") if l.strip()])
        except: pass
        rag_s  = "ONLINE" if self.rag.available else "OFFLINE — py -m pip install chromadb"
        brain_s= (f"ONLINE  [{self.brain._api_label()}]" if self.brain.online
                  else "OFFLINE — check Settings → AI Backend")
        self._twrite("="*52)
        self._twrite("SYSTEM ONLINE.")
        self._twrite(f"Prior session: {obs} observations, {q} deferred questions.")
        self._twrite(f"BRAIN BRIDGE:  {brain_s}")
        self._twrite(f"RAG PIPELINE:  {rag_s}")
        self._twrite(f"CONTEXT WINDOW: {len(self._settings.get('allowed_files',[]))} source(s)  "
                     f"|  num_ctx: {self._settings.get('num_ctx',8192)} tokens")
        self._twrite(f"SANDBOX: {BASE_DIR}")
        days=self._days_since_last
        if days is None:   self._twrite("[SESSION] First session recorded.")
        elif days==0:      self._twrite("[SESSION] Welcome back — you were here earlier today.")
        elif days==1:      self._twrite("[SESSION] Last session: yesterday.")
        elif days<=3:      self._twrite(f"[SESSION] Last session: {days} days ago.")
        else:
            self._twrite(f"[SESSION] ⚠  You haven't been here in {days} days.")
            self._twrite(f"[MIND B]  {days} days since your last session — let me check what we left off.")
        letter=self._load_letter()
        self._twrite("[LETTER]   Standing instructions loaded." if letter
                     else "[LETTER]   No standing instructions yet. Use 'Letter to Mind B'.")
        events=self._upcoming_events(days_ahead=14)
        if events: self._twrite(f"[CALENDAR] Upcoming:\n{events}")
        else:      self._twrite("[CALENDAR] No upcoming events.")
        self._twrite("-"*52)
        self._twrite("Terminal: Read Clipboard | Fetch URL | Export Chat | Ask")
        self._twrite("Vault:    Letter to Mind B | Calendar | Grammar | Debate | Journal")
        self._twrite("="*52)
        c=self._GREEN if self.brain.online else self._RED
        self._ollama_lbl.configure(
            text=f"AI: {self.brain._api_label()}" if self.brain.online else "AI: OFFLINE",fg=c)

    # =========================================================================
    # EXIT
    # =========================================================================

    def _on_close(self):
        dirty=[t for t in self._tabs if t["dirty"] and t["path"]]
        if dirty:
            ans=messagebox.askyesnocancel("Unsaved Work",
                f"{len(dirty)} tab(s) have unsaved changes.\nSave all before exit?")
            if ans is None: return
            if ans:
                for t in dirty: self._tab_write(t,t["path"])
        self._stop_flag.set(); self._null_event.set(); self._sleep_event.set()
        backup_dest = self._settings.get("backup_path", BACKUP_USB_PATH)
        self._twrite(f"[BACKUP] Backing up to: {backup_dest}")
        self.root.update()
        result=perform_backup(backup_dest)
        self._twrite(result); self.root.update()
        if "[BACKUP FAILED]" in result:
            if not messagebox.askyesno("Backup Failed","USB not found.\n\nExit anyway?"):
                self._stop_flag.clear(); return
        self.root.destroy()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    root=tk.Tk()
    MemoryArkApp(root)
    root.mainloop()

if __name__=="__main__":
    main()
