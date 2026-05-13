# Memory Ark Interface

A local-first prototype workspace for transparent human/AI collaboration.
Built for Ricky's Ark — a personal documentation and memory system.

---

## What It Does

The Memory Ark Interface gives you and an AI partner a shared workspace where:

- **You stay in control** — you decide what the AI can read, write, or delete.
- **Everything is visible** — see exactly what the AI is doing (or trying to do).
- **Every action is logged** — an append-only audit trail records every access attempt with timestamps and outcomes.
- **Modes keep things clear** — switch to Test or Acting mode so the AI knows not to overreact; annotate past events to add context.
- **A safe baseline is always one click away** — reset all permissions to safe defaults at any time.
- **Direct chat is available** — send messages in the Chat tab and review the full message history.

---

## Workspace Zones

| Zone    | Color  | Purpose |
|---------|--------|---------|
| 🔵 **Human**  | Blue   | Your files. Only you can delete them. AI can read (when permitted). |
| 🟣 **AI**     | Purple | AI working space. Summaries, notes, questions, checklists. |
| 🟢 **Shared** | Green  | Mutually agreed-upon context. Both can contribute. |
| 🟡 **Debate** | Amber  | Retention cases, disputes, tombstones, audit records. |

---

## Quick Start

### Option A — Desktop App (no browser needed)

Uses Python's built-in `tkinter` library — **no extra installs required**.

#### 1. Install Python (3.8 or newer)

Download from https://python.org if you don't have it.

#### 2. Open a terminal and go to the `ark-app` folder

```bash
cd path/to/Rickys-Ark/ark-app
```

#### 3. Run the desktop app

```bash
python desktop_app.py
```

A native desktop window opens immediately — no browser required.

---

### Option B — Web Interface (browser-based)

#### 1. Install Python (3.8 or newer)

Download from https://python.org if you don't have it.

#### 2. Open a terminal and go to the `ark-app` folder

```bash
cd path/to/Rickys-Ark/ark-app
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or use a virtual environment (recommended):

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

#### 4. Run the app

```bash
python app.py
```

You'll see:

```
🌊 Memory Ark Interface — running at http://127.0.0.1:5000
```

#### 5. Open your browser

Go to: **http://127.0.0.1:5000**

---

Both interfaces share the same workspace files, audit log, permissions, and mode settings — you can use either one or switch between them.

---

## Interface Guide

### Left Sidebar — Zones
Click **Human**, **AI**, **Shared**, or **Debate** to browse files in that zone.
**All Files** shows everything at once.

### Top Toolbar
- **Search** — finds files by name or content across zones.
- **+ New** — creates a new file in any zone you choose.

### Right Panel — Tabs

#### 📄 File Tab
When you click a file:
- Read its contents.
- **Edit** to modify it.
- **Copy to…** to copy into another zone (provenance is preserved).
- **Delete** — creates a tombstone record before removing.
- If the AI has read access, a pulsing indicator shows: *AI is reading this file.*

#### 💬 Chat Tab
- Send messages directly to your AI partner.
- Messages are stored in the local chat log and can be refreshed live.
- Chat message events are recorded in the audit log for transparency.

#### 🔐 Permissions Tab
Control what the AI can do:

- **Zone permissions** — toggle AI Read / Write / Delete for each zone independently.
- **Device permissions** — enable or disable camera, microphone, clipboard, network, screen reader.
- Click **Save Permissions** to apply.

#### ⚙️ Mode Tab
Set the current operating mode:

| Mode     | Meaning |
|----------|---------|
| ✅ **Normal**  | Standard operation |
| 🧪 **Test**    | Behavior is a test — AI should not overreact |
| 🎭 **Acting**  | Roleplay or scenario mode |
| 🔄 **Reset Baseline** | Restores all permissions to safe defaults |

Mode changes are recorded in the audit log.

### Bottom — Audit Log
Every access attempt, file operation, permission change, and mode switch is logged here with:
- **Timestamp** — exact time of the event
- **Actor** — human or AI
- **Action** — what was attempted (read, write, delete, copy, etc.)
- **Zone** — which workspace area
- **File** — which file (if applicable)
- **Outcome** — ✅ allowed or ❌ denied
- **Notes** — reason or context
- **Annotation** — click **+ Note** on any entry to add your own label (e.g. "This was a test", "Roleplay scenario", "Joke — disregard")

Filter the log by: **All**, **Denied only**, or **AI only**.

---

## File Operations

### Creating Files
1. Click **+ New** (toolbar or sidebar button).
2. Choose a zone.
3. Add an optional subfolder (e.g. `notes` → saves as `notes/myfile.txt`).
4. Enter a filename and initial content.
5. Click **Create**.

### Editing Files
1. Select a file.
2. Click ✏️ **Edit**.
3. Modify the text.
4. Click 💾 **Save**.

### Copying Files Between Zones
1. Select a file.
2. Click 📋 **Copy to…**
3. Choose destination zone and path.
4. The copy includes a provenance header noting the source.

### Deleting Files
- Only file owners should delete their files.
- Deleting a file creates a **tombstone** in `debate/tombstones/` recording who deleted it and when.
- The audit log records the deletion.

---

## Audit Log Annotations

You can mark any log entry after the fact:

1. Find the entry in the audit log.
2. Click **+ Note**.
3. Type your annotation (e.g. *"This was a test — I was checking if AI would access my medical files"*).
4. Click **Save Annotation**.

This is how you tell the system when something was a test, a joke, or roleplay — so the AI has the right context.

---

## Workspace File Structure

```
ark-app/
  app.py              ← Flask server (run this)
  requirements.txt    ← Python dependencies
  static/
    index.html        ← The interface UI
  workspace/
    human/            ← Your files
      notes/
      directives/
      character/
      stories/
    ai/               ← AI working files
      summaries/
      indexes/
      questions/
      interpretations/
    shared/           ← Mutually agreed context
      context/
      agreements/
      reference/
    debate/           ← Logs, disputes, tombstones
      retention-cases/
      disputes/
      tombstones/
  system/
    logs/
      audit.jsonl     ← Append-only audit trail
      chat.jsonl      ← Local chat messages (human/ai)
    permissions.json  ← Current permission settings
    mode.json         ← Current mode + history
```

All files are plain text and JSON — you can open, read, and back them up with any tool.

---

## Chat API

- `GET /api/chat?limit=200&session_id=default` — list chat messages in chronological order.
- `POST /api/chat` — append a chat message:

```json
{
  "actor": "human",
  "message": "Hello AI",
  "session_id": "default"
}
```

---

## Tips

- **The audit log is append-only.** Annotations can be added but entries cannot be deleted — this is intentional.
- **Tombstones preserve history.** When a file is deleted, a record remains in `debate/tombstones/`.
- **Search works across zones.** Type in the search bar to find any file by name or content.
- **Auto-refresh.** The audit log refreshes automatically every 15 seconds.
- **Baseline reset is safe.** It restores permissions to defaults and switches mode back to Normal. No files are deleted.

---

## Built With

- [Flask](https://flask.palletsprojects.com/) — Python web framework
- Vanilla HTML/CSS/JavaScript — no frameworks, no build step needed
- Plain `.txt` and `.json` files — human-readable, portable, durable

---

*Memory Ark Interface — built for transparency, not complexity.*
*Part of the Ricky's Ark project. See the main README for the full archive context.*
