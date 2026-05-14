# Memory Ark Workstation

**100% offline Python/Tkinter desktop application.**  
No browser, no Flask, no cloud API.  All storage is local.

---

## Requirements

| Requirement | Install |
|---|---|
| Python 3.10+ | system package manager |
| `requests` (Ollama bridge) | `pip install requests` |
| `chromadb` (RAG pipeline, optional) | `pip install chromadb` |
| [Ollama](https://ollama.com) | download and install |

Pull a local model once:
```
ollama pull llama3
```

## Run

```
python ark-app/desktop_app.py
```

or from inside `ark-app/`:

```
python desktop_app.py
```

## Architecture

Implements the **10-Step Software Engineering Schematic** from the Memory Ark Blueprint.

| Component | Description |
|---|---|
| **Module A — Brain Bridge** | `http://localhost:11434` (Ollama, no open internet) |
| **Module B — RAG Pipeline** | Local ChromaDB stored in `~/Memory_Ark/AI/chroma_db` |
| **4-Zone Sandbox** | `Human / Shared / AI / Debate` under `~/Memory_Ark/` |
| **Dual-pane UI** | Left: Human Vault editor · Right: Mind B Terminal (read-only) |
| **Telemetry** | Active / Reflective / Null — gates AI thread via `threading.Event()` |
| **HITL loop** | Approve Link / Reject Link buttons halt AI writes pending human decision |
| **Step 10 Backup** | `shutil.copytree` backup to hard-coded USB path `E:\Memory_Ark_Backup` on exit |

## Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `MEMORY_ARK_DIR` | `~/Memory_Ark` | Override sandbox root |
| `MEMORY_ARK_MODEL` | `llama3` | Override Ollama model name |
