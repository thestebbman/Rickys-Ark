"""
Memory Ark Interface — Flask backend
Local-first workspace for transparent human/AI collaboration.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# ── constants ─────────────────────────────────────────────────────────────────
MAX_SEARCH_RESULTS = 50
SNIPPET_CONTEXT_CHARS = 60

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
WORKSPACE = BASE_DIR / "workspace"
SYSTEM_DIR = BASE_DIR / "system"
AUDIT_LOG = SYSTEM_DIR / "logs" / "audit.jsonl"
PERMISSIONS_FILE = SYSTEM_DIR / "permissions.json"
MODE_FILE = SYSTEM_DIR / "mode.json"
STATIC_DIR = BASE_DIR / "static"

ZONES = ["human", "ai", "shared", "debate"]

# ── flask app ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")


# ── helpers ─────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_audit(actor: str, action: str, zone: str, filename: str = "",
                outcome: str = "allowed", notes: str = "") -> dict:
    """Append one entry to the append-only audit log and return it."""
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
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_audit() -> list:
    if not AUDIT_LOG.exists():
        return []
    entries = []
    with open(AUDIT_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return list(reversed(entries))  # newest first


def rewrite_audit(entries: list) -> None:
    """Rewrite the audit log (used only for annotation updates)."""
    with open(AUDIT_LOG, "w", encoding="utf-8") as f:
        for e in reversed(entries):  # restore chronological order
            f.write(json.dumps(e) + "\n")


def load_permissions() -> dict:
    defaults = {
        "zones": {z: {"ai_read": True, "ai_write": z == "ai", "ai_delete": z == "ai"}
                  for z in ZONES},
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


def save_permissions(perms: dict) -> None:
    PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERMISSIONS_FILE.write_text(json.dumps(perms, indent=2), encoding="utf-8")


def load_mode() -> dict:
    default = {"current": "normal", "history": []}
    if MODE_FILE.exists():
        try:
            return json.loads(MODE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def save_mode(data: dict) -> None:
    MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def zone_path(zone: str) -> Path:
    if zone not in ZONES:
        raise ValueError(f"Unknown zone: {zone}")
    return WORKSPACE / zone


def safe_resolve(zone: str, rel: str) -> Path:
    """Resolve a user-supplied relative path inside a zone, preventing traversal.

    Builds the path component by component, explicitly rejecting '..' and
    absolute path separators, then does a final resolved-path check.
    Raises ValueError if the resulting path escapes the zone directory.
    """
    base = zone_path(zone).resolve()
    # Decompose into individual components and filter dangerous ones
    raw_parts = Path(rel).parts
    clean_parts: list = []
    for part in raw_parts:
        # Reject any component that would escape the base
        if part in ("..", ".", "") or part.startswith("/") or part.startswith("\\"):
            raise ValueError(f"Unsafe path component '{part}' in '{rel}'")
        clean_parts.append(part)
    if not clean_parts:
        raise ValueError(f"Empty or invalid path '{rel}'")
    result = base.joinpath(*clean_parts)
    # Final defence: confirm the resolved canonical path is still inside base
    try:
        result.resolve().relative_to(base)
    except ValueError:
        raise ValueError(f"Path '{rel}' escapes zone '{zone}'")
    return result
    return resolved


def check_permission(actor: str, action: str, zone: str) -> bool:
    """Return True if actor is allowed to perform action in zone."""
    if actor == "human":
        # humans can always read; only owners can write/delete their zone
        if action == "read":
            return True
        if zone == "human":
            return True
        if zone in ("shared", "debate"):
            return True
        # human cannot write/delete in ai zone
        return False
    elif actor == "ai":
        perms = load_permissions()["zones"].get(zone, {})
        if action == "read":
            return perms.get("ai_read", False)
        if action == "write":
            return perms.get("ai_write", False)
        if action == "delete":
            return perms.get("ai_delete", False)
        return False
    return False


def list_files_in_zone(zone: str) -> list:
    """Return list of file dicts for a zone (recursive)."""
    zp = zone_path(zone)
    files = []
    for p in sorted(zp.rglob("*")):
        if p.is_file():
            rel = p.relative_to(zp)
            files.append({
                "name": p.name,
                "path": str(rel),
                "zone": zone,
                "size": p.stat().st_size,
                "modified": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds"),
            })
    return files


# ── routes — static ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


# ── routes — files ──────────────────────────────────────────────────────────

@app.route("/api/files")
def api_list_all():
    all_files = {}
    for zone in ZONES:
        all_files[zone] = list_files_in_zone(zone)
    return jsonify(all_files)


@app.route("/api/files/<zone>")
def api_list_zone(zone):
    if zone not in ZONES:
        return jsonify({"error": "Unknown zone"}), 400
    return jsonify(list_files_in_zone(zone))


@app.route("/api/files/<zone>/<path:filepath>", methods=["GET"])
def api_read_file(zone, filepath):
    actor = request.args.get("actor", "human")
    if zone not in ZONES:
        return jsonify({"error": "Unknown zone"}), 400
    if not check_permission(actor, "read", zone):
        write_audit(actor, "read", zone, filepath, "denied", "Permission denied")
        return jsonify({"error": "Permission denied"}), 403

    try:
        fpath = safe_resolve(zone, filepath)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not fpath.exists() or not fpath.is_file():
        return jsonify({"error": "File not found"}), 404

    write_audit(actor, "read", zone, filepath, "allowed")
    try:
        content = fpath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = "[Binary file - cannot display]"
    return jsonify({"content": content, "zone": zone, "path": filepath})


@app.route("/api/files/<zone>/<path:filepath>", methods=["POST", "PUT"])
def api_write_file(zone, filepath):
    actor = request.json.get("actor", "human") if request.json else "human"
    if zone not in ZONES:
        return jsonify({"error": "Unknown zone"}), 400
    if not check_permission(actor, "write", zone):
        write_audit(actor, "write", zone, filepath, "denied", "Permission denied")
        return jsonify({"error": "Permission denied"}), 403

    try:
        fpath = safe_resolve(zone, filepath)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    fpath.parent.mkdir(parents=True, exist_ok=True)
    content = (request.json or {}).get("content", "")
    fpath.write_text(content, encoding="utf-8")
    write_audit(actor, "write", zone, filepath, "allowed")
    return jsonify({"ok": True, "path": filepath, "zone": zone})


@app.route("/api/files/<zone>/<path:filepath>", methods=["DELETE"])
def api_delete_file(zone, filepath):
    actor = (request.json or {}).get("actor", "human") if request.json else "human"
    if zone not in ZONES:
        return jsonify({"error": "Unknown zone"}), 400
    if not check_permission(actor, "delete", zone):
        write_audit(actor, "delete", zone, filepath, "denied", "Permission denied")
        return jsonify({"error": "Permission denied"}), 403

    try:
        fpath = safe_resolve(zone, filepath)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not fpath.exists():
        return jsonify({"error": "File not found"}), 404

    # create tombstone before deleting — use hash of path to avoid name collisions
    tombstone = {
        "original_path": str(filepath),
        "zone": zone,
        "deleted_by": actor,
        "deleted_at": now_iso(),
    }
    ts_dir = WORKSPACE / "debate" / "tombstones"
    ts_dir.mkdir(parents=True, exist_ok=True)
    path_hash = hashlib.sha256(f"{zone}/{filepath}".encode()).hexdigest()[:12]
    ts_name = (
        f"tombstone-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        f"-{path_hash}.json"
    )
    (ts_dir / ts_name).write_text(json.dumps(tombstone, indent=2), encoding="utf-8")

    fpath.unlink()
    write_audit(actor, "delete", zone, filepath, "allowed", "Tombstone created")
    return jsonify({"ok": True})


@app.route("/api/copy", methods=["POST"])
def api_copy_file():
    data = request.json or {}
    actor = data.get("actor", "human")
    src_zone = data.get("src_zone")
    src_path = data.get("src_path")
    dst_zone = data.get("dst_zone")
    dst_path = data.get("dst_path", src_path)

    if not all([src_zone, src_path, dst_zone]):
        return jsonify({"error": "Missing parameters"}), 400
    if src_zone not in ZONES or dst_zone not in ZONES:
        return jsonify({"error": "Unknown zone"}), 400

    if not check_permission(actor, "read", src_zone):
        write_audit(actor, "copy", src_zone, src_path, "denied",
                    f"Cannot read source zone {src_zone}")
        return jsonify({"error": "Cannot read source zone"}), 403

    if not check_permission(actor, "write", dst_zone):
        write_audit(actor, "copy", dst_zone, dst_path, "denied",
                    f"Cannot write to zone {dst_zone}")
        return jsonify({"error": "Cannot write to destination zone"}), 403

    try:
        src_fpath = safe_resolve(src_zone, src_path)
        dst_fpath = safe_resolve(dst_zone, dst_path)
    except ValueError:
        return jsonify({"error": "Invalid path"}), 400

    if not src_fpath.exists():
        return jsonify({"error": "Source file not found"}), 404

    dst_fpath.parent.mkdir(parents=True, exist_ok=True)

    content = src_fpath.read_text(encoding="utf-8")
    # prepend provenance header
    provenance = (
        f"[Copied from {src_zone}/{src_path} by {actor} at {now_iso()}]\n\n"
    )
    dst_fpath.write_text(provenance + content, encoding="utf-8")

    write_audit(actor, "copy", dst_zone, dst_path, "allowed",
                f"Copied from {src_zone}/{src_path}")
    return jsonify({"ok": True, "dst_zone": dst_zone, "dst_path": dst_path})


# ── routes — permissions ────────────────────────────────────────────────────

@app.route("/api/permissions", methods=["GET"])
def api_get_permissions():
    return jsonify(load_permissions())


@app.route("/api/permissions", methods=["POST"])
def api_set_permissions():
    data = request.json or {}
    perms = load_permissions()

    if "zones" in data:
        for zone, settings in data["zones"].items():
            if zone in perms["zones"]:
                perms["zones"][zone].update(settings)

    if "devices" in data:
        for device, val in data["devices"].items():
            if device in perms["devices"]:
                perms["devices"][device] = bool(val)
                write_audit("human", "permission_change", "system",
                            device, "allowed", f"Device {'enabled' if val else 'disabled'}")

    save_permissions(perms)
    write_audit("human", "permission_update", "system", "", "allowed")
    return jsonify(perms)


# ── routes — mode ───────────────────────────────────────────────────────────

@app.route("/api/mode", methods=["GET"])
def api_get_mode():
    return jsonify(load_mode())


@app.route("/api/mode", methods=["POST"])
def api_set_mode():
    data = request.json or {}
    new_mode = data.get("mode", "normal")
    valid_modes = ["normal", "test", "acting", "baseline"]
    if new_mode not in valid_modes:
        return jsonify({"error": f"Invalid mode. Valid: {valid_modes}"}), 400

    mode_data = load_mode()
    old_mode = mode_data["current"]
    mode_data["current"] = new_mode
    mode_data["history"].append({
        "from": old_mode,
        "to": new_mode,
        "at": now_iso(),
    })

    if new_mode == "baseline":
        # reset permissions to defaults
        default_perms = {
            "zones": {z: {"ai_read": True, "ai_write": z == "ai", "ai_delete": z == "ai"}
                      for z in ZONES},
            "devices": {
                "camera": False,
                "microphone": False,
                "clipboard": False,
                "network": False,
                "screen_reader": False,
            },
        }
        save_permissions(default_perms)
        write_audit("human", "baseline_reset", "system", "", "allowed",
                    "All permissions restored to defaults")
        mode_data["current"] = "normal"

    save_mode(mode_data)
    write_audit("human", "mode_change", "system", "", "allowed",
                f"Mode: {old_mode} → {new_mode}")
    return jsonify(mode_data)


# ── routes — audit log ──────────────────────────────────────────────────────

@app.route("/api/audit")
def api_get_audit():
    limit = int(request.args.get("limit", 200))
    entries = read_audit()[:limit]
    return jsonify(entries)


@app.route("/api/audit/<entry_id>/annotate", methods=["POST"])
def api_annotate(entry_id):
    data = request.json or {}
    annotation = data.get("annotation", "").strip()
    entries = read_audit()

    found = False
    for e in entries:
        if e.get("id") == entry_id:
            e["annotation"] = annotation
            found = True
            break

    if not found:
        return jsonify({"error": "Entry not found"}), 404

    rewrite_audit(entries)
    write_audit("human", "annotation", "system", entry_id, "allowed",
                f"Annotated: {annotation[:80]}")
    return jsonify({"ok": True})


# ── routes — search ─────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").lower().strip()
    zone_filter = request.args.get("zone", "")
    if not query:
        return jsonify([])

    results = []
    search_zones = [zone_filter] if zone_filter in ZONES else ZONES
    for zone in search_zones:
        zp = zone_path(zone)
        for fpath in sorted(zp.rglob("*")):
            if not fpath.is_file():
                continue
            rel = str(fpath.relative_to(zp))
            if query in fpath.name.lower():
                results.append({"zone": zone, "path": rel, "match": "filename"})
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
                if query in content.lower():
                    # find a snippet
                    idx = content.lower().find(query)
                    snippet = content[max(0, idx - SNIPPET_CONTEXT_CHARS):idx + SNIPPET_CONTEXT_CHARS].replace("\n", " ")
                    results.append({"zone": zone, "path": rel,
                                    "match": "content", "snippet": f"…{snippet}…"})
            except (UnicodeDecodeError, PermissionError):
                pass
    return jsonify(results[:MAX_SEARCH_RESULTS])


# ── bootstrap ────────────────────────────────────────────────────────────────

def bootstrap():
    """Ensure workspace and system dirs exist with seed files."""
    for zone in ZONES:
        zone_path(zone).mkdir(parents=True, exist_ok=True)

    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    (SYSTEM_DIR / "logs").mkdir(parents=True, exist_ok=True)

    # seed permissions + mode if missing
    if not PERMISSIONS_FILE.exists():
        save_permissions(load_permissions())
    if not MODE_FILE.exists():
        save_mode(load_mode())

    # seed a welcome file in human zone
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

    # seed a starter AI note
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


if __name__ == "__main__":
    bootstrap()
    debug = os.environ.get("ARK_DEBUG", "0") == "1"
    print("\n🌊 Memory Ark Interface — running at http://127.0.0.1:5000\n")
    app.run(debug=debug, port=5000)
