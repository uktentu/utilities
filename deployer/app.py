"""Static site deployer + form capture (Python 3.9 compatible)."""
from __future__ import annotations

import csv
import io
import json
import platform
import re
import secrets
import shutil
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
SITES_DIR = BASE_DIR / "sites"
SUBMISSIONS_DIR = BASE_DIR / "submissions"
DATA_DIR = BASE_DIR / "data"
EXAMPLES_DIR = BASE_DIR / "examples"
SITES_DIR.mkdir(exist_ok=True)
SUBMISSIONS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.secret_key = "change-me-in-prod"


@app.context_processor
def inject_globals():
    return {"py_version": platform.python_version()}


def _safe_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        abort(400, "name must be lowercase alphanumeric / dash / underscore, 1–50 chars")
    return name


def _site_path(site: str) -> Path:
    p = (SITES_DIR / _safe_name(site)).resolve()
    if SITES_DIR.resolve() not in p.parents and p != SITES_DIR.resolve():
        abort(400, "invalid site path")
    return p


def _form_files(site: str, form: str) -> Dict[str, Path]:
    folder = SUBMISSIONS_DIR / _safe_name(site)
    folder.mkdir(parents=True, exist_ok=True)
    safe_form = _safe_name(form)
    return {
        "csv": folder / f"{safe_form}.csv",
        "json": folder / f"{safe_form}.json",
    }


def _list_sites() -> List[str]:
    return sorted(p.name for p in SITES_DIR.iterdir() if p.is_dir())


def _list_forms(site: str) -> List[str]:
    folder = SUBMISSIONS_DIR / _safe_name(site)
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))


def _read_submissions(site: str, form: str, limit: int = 200) -> List[dict]:
    json_path = _form_files(site, form)["json"]
    if not json_path.exists():
        return []
    rows: List[dict] = []
    with json_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows[-limit:][::-1]


_dataset_locks: Dict[str, threading.Lock] = {}
_dataset_locks_master = threading.Lock()


def _dataset_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _dataset_locks_master:
        lock = _dataset_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _dataset_locks[key] = lock
        return lock


def _dataset_path(site: str, dataset: str) -> Path:
    folder = DATA_DIR / _safe_name(site)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_safe_name(dataset)}.json"


def _read_dataset(path: Path) -> dict:
    if not path.exists():
        return {"rev": 0, "items": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"rev": 0, "items": []}
    if not isinstance(data, dict):
        return {"rev": 0, "items": []}
    return {
        "rev": int(data.get("rev", 0) or 0),
        "items": list(data.get("items", []) or []),
    }


def _write_dataset(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)


def _scrub(fields: dict) -> dict:
    """Drop reserved keys from a client-supplied object."""
    out = {}
    for k, v in (fields or {}).items():
        sk = str(k)
        if sk == "id" or sk.startswith("_"):
            continue
        out[sk] = v
    return out


def _count_submissions(site: str, form: str) -> int:
    json_path = _form_files(site, form)["json"]
    if not json_path.exists():
        return 0
    n = 0
    with json_path.open("rb") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _list_datasets(site: str) -> List[str]:
    folder = DATA_DIR / _safe_name(site)
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if not p.name.endswith(".tmp"))


def _read_dataset_summary(site: str, dataset: str) -> dict:
    path = _dataset_path(site, dataset)
    with _dataset_lock(path):
        data = _read_dataset(path)
    items = data["items"]
    # Discover columns from items, server keys last for readability.
    user_cols: List[str] = []
    server_cols: List[str] = []
    seen = set()
    for it in items[-50:]:
        for k in it.keys():
            if k in seen:
                continue
            seen.add(k)
            (server_cols if str(k).startswith("_") or k == "id" else user_cols).append(k)
    return {
        "name": dataset,
        "rev": data["rev"],
        "total": len(items),
        "rows": items[-50:][::-1],
        "columns": user_cols + server_cols,
    }


@app.route("/")
def home():
    return redirect(url_for("admin"))


@app.route("/guide")
def guide():
    return render_template("guide.html")


# ---------- JSON API (used by live UI polling) ----------

@app.route("/api/sites/<site>/state")
def api_site_state(site: str):
    site = _safe_name(site)
    if not _site_path(site).exists():
        abort(404)
    forms = [
        {"name": fname, "total": _count_submissions(site, fname)}
        for fname in _list_forms(site)
    ]
    datasets = []
    for dname in _list_datasets(site):
        with _dataset_lock(_dataset_path(site, dname)):
            d = _read_dataset(_dataset_path(site, dname))
        datasets.append({"name": dname, "rev": d["rev"], "total": len(d["items"])})
    return {"site": site, "forms": forms, "datasets": datasets}


@app.route("/api/sites/<site>/datasets/<dataset>")
def api_dataset(site: str, dataset: str):
    site = _safe_name(site)
    if not _site_path(site).exists():
        abort(404)
    return _read_dataset_summary(site, dataset)


@app.route("/api/sites/<site>/forms/<form>/submissions")
def api_form_submissions(site: str, form: str):
    site = _safe_name(site)
    form = _safe_name(form)
    if not _site_path(site).exists():
        abort(404)
    rows = _read_submissions(site, form, limit=200)
    columns: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)
    return {
        "site": site,
        "form": form,
        "total": _count_submissions(site, form),
        "columns": columns,
        "rows": rows,
    }


# ---------- Datasets API (collaborative state for static pages) ----------

@app.route("/data/<site>/<dataset>/items", methods=["GET", "POST", "DELETE"])
def data_items(site: str, dataset: str):
    site = _safe_name(site)
    dataset = _safe_name(dataset)
    if not _site_path(site).exists():
        abort(404, "unknown site")
    path = _dataset_path(site, dataset)
    lock = _dataset_lock(path)

    if request.method == "GET":
        with lock:
            data = _read_dataset(path)
        since_raw = request.args.get("since")
        if since_raw is not None:
            try:
                since = int(since_raw)
            except ValueError:
                since = -1
            if since == data["rev"]:
                return {"changed": False, "rev": data["rev"]}
        return {
            "changed": True,
            "rev": data["rev"],
            "items": data["items"],
        }

    if request.method == "DELETE":
        with lock:
            data = _read_dataset(path)
            cleared = len(data["items"])
            data["items"] = []
            data["rev"] += 1
            _write_dataset(path, data)
        return {"cleared": cleared, "rev": data["rev"]}

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, "POST body must be a JSON object")
    fields = _scrub(body)
    actor = str(body.get("_actor") or "").strip()[:60]
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    item = {
        "id": secrets.token_urlsafe(8),
        "_ts": now,
        "_created_by": actor,
        **fields,
    }
    with lock:
        data = _read_dataset(path)
        data["items"].append(item)
        data["rev"] = data["rev"] + 1
        _write_dataset(path, data)
        return {"item": item, "rev": data["rev"]}, 201


@app.route("/data/<site>/<dataset>/items/<item_id>", methods=["PATCH", "DELETE"])
def data_item(site: str, dataset: str, item_id: str):
    site = _safe_name(site)
    dataset = _safe_name(dataset)
    if not _site_path(site).exists():
        abort(404, "unknown site")
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", item_id or ""):
        abort(400, "bad item id")
    path = _dataset_path(site, dataset)
    lock = _dataset_lock(path)

    with lock:
        data = _read_dataset(path)
        idx = next(
            (i for i, it in enumerate(data["items"]) if it.get("id") == item_id),
            -1,
        )
        if idx == -1:
            abort(404, "item not found")

        if request.method == "DELETE":
            data["items"].pop(idx)
            data["rev"] += 1
            _write_dataset(path, data)
            return {"rev": data["rev"], "id": item_id}

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, "PATCH body must be a JSON object")
        actor = str(body.get("_actor") or "").strip()[:60]
        merged = dict(data["items"][idx])
        merged.update(_scrub(body))
        merged["_updated"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        if actor:
            merged["_updated_by"] = actor
        data["items"][idx] = merged
        data["rev"] += 1
        _write_dataset(path, data)
        return {"item": merged, "rev": data["rev"]}


# Seed endpoint — bulk-initialise a dataset from a hardcoded master array.
#
# Body: { "items": [...], "key": "fieldName", "mode": "init"|"upsert"|"replace" }
#
#   mode "init"    (default) — seeds only if the dataset is currently empty; no-op otherwise.
#   mode "upsert"  — merges into existing items by the value of `key`; creates missing ones.
#   mode "replace" — clears all items first, then seeds fresh (for full master-data resets).
#
# Reserved server fields in input items (id, _ts, _updated, _created_by, _updated_by)
# are stripped before writing; each new item gets a server-generated `id`.
#
# Returns: { seeded, updated, skipped, rev, items }
@app.route("/data/<site>/<dataset>/seed", methods=["POST"])
def data_seed(site: str, dataset: str):
    site = _safe_name(site)
    dataset = _safe_name(dataset)
    if not _site_path(site).exists():
        abort(404, "unknown site")

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, "body must be a JSON object with an 'items' array")
    raw_items = body.get("items")
    if not isinstance(raw_items, list):
        abort(400, "'items' must be an array")

    mode = str(body.get("mode") or "init").strip()
    if mode not in ("init", "upsert", "replace"):
        abort(400, "mode must be 'init', 'upsert', or 'replace'")
    key = str(body.get("key") or "").strip()
    if mode == "upsert" and not key:
        abort(400, "'key' field name is required for mode 'upsert'")

    path = _dataset_path(site, dataset)
    lock = _dataset_lock(path)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    with lock:
        data = _read_dataset(path)

        if mode == "init" and len(data["items"]) > 0:
            return {
                "seeded": 0, "updated": 0,
                "skipped": len(data["items"]),
                "rev": data["rev"],
                "items": data["items"],
            }

        if mode == "replace":
            data["items"] = []

        # Build lookup index for upsert mode.
        key_index: Dict[str, int] = {}
        if mode == "upsert":
            key_index = {
                str(it.get(key, "")): i
                for i, it in enumerate(data["items"])
                if it.get(key) is not None
            }

        seeded = 0
        updated = 0
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            fields = _scrub(raw)
            actor = str(raw.get("_actor") or "").strip()[:60]

            if mode == "upsert":
                key_val = str(fields.get(key, ""))
                if key_val in key_index:
                    idx = key_index[key_val]
                    merged = dict(data["items"][idx])
                    merged.update(fields)
                    merged["_updated"] = now
                    if actor:
                        merged["_updated_by"] = actor
                    data["items"][idx] = merged
                    updated += 1
                    continue

            item: Dict[str, object] = {
                "id": secrets.token_urlsafe(8),
                "_ts": now,
                "_created_by": actor,
                **fields,
            }
            data["items"].append(item)
            if mode == "upsert":
                key_index[str(item.get(key, ""))] = len(data["items"]) - 1
            seeded += 1

        if seeded or updated:
            data["rev"] += 1
        _write_dataset(path, data)
        return {
            "seeded": seeded,
            "updated": updated,
            "skipped": 0,
            "rev": data["rev"],
            "items": data["items"],
        }


# ---------- Examples (one-click deploy of starter sites) ----------

@app.route("/admin/examples/<example>/deploy", methods=["POST"])
def admin_deploy_example(example: str):
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,49}$", example or ""):
        abort(400, "bad example name")
    src = (EXAMPLES_DIR / example).resolve()
    if EXAMPLES_DIR.resolve() not in src.parents or not src.is_dir():
        abort(404, "unknown example")

    requested = (request.form.get("name") or example).strip().lower()
    name = _safe_name(requested)
    target = _site_path(name)
    if target.exists():
        # Pick the first free suffix so we don't clobber an existing site.
        for i in range(2, 100):
            cand = f"{name}-{i}"
            if not (SITES_DIR / cand).exists():
                name = cand
                target = _site_path(name)
                break
    target.mkdir(parents=True)
    for child in src.iterdir():
        if child.is_dir():
            shutil.copytree(child, target / child.name)
        else:
            shutil.copy2(child, target / child.name)

    flash(f"deployed example '{example}' as site '{name}'", "ok")
    return redirect(url_for("admin_site", site=name))


# ---------- Admin UI ----------

@app.route("/admin")
def admin():
    sites = []
    total_forms = 0
    total_subs = 0
    total_datasets = 0
    for name in _list_sites():
        forms = _list_forms(name)
        sub_count = sum(_count_submissions(name, f) for f in forms)
        datasets = _list_datasets(name)
        total_forms += len(forms)
        total_subs += sub_count
        total_datasets += len(datasets)
        sites.append({
            "name": name,
            "forms": forms,
            "submission_count": sub_count,
            "datasets": datasets,
        })
    totals = {
        "sites": len(sites),
        "forms": total_forms,
        "submissions": total_subs,
        "datasets": total_datasets,
    }
    return render_template("admin.html", sites=sites, totals=totals)


@app.route("/admin/<site>")
def admin_site(site: str):
    site = _safe_name(site)
    if not _site_path(site).exists():
        abort(404)
    forms = []
    total_subs = 0
    for fname in _list_forms(site):
        rows = _read_submissions(site, fname, limit=50)
        total = _count_submissions(site, fname)
        total_subs += total
        columns: List[str] = []
        seen = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    columns.append(k)
        forms.append({"name": fname, "rows": rows, "columns": columns, "total": total})

    datasets = [_read_dataset_summary(site, d) for d in _list_datasets(site)]
    total_items = sum(d["total"] for d in datasets)
    return render_template(
        "site_detail.html",
        site=site,
        forms=forms,
        total_submissions=total_subs,
        datasets=datasets,
        total_dataset_items=total_items,
    )


@app.route("/admin/<site>/upload", methods=["POST"])
@app.route("/admin/upload", methods=["POST"], defaults={"site": None})
def admin_upload(site):
    name = _safe_name(request.form.get("name") or site or "")
    file = request.files.get("zip")
    if not file or not file.filename:
        flash("no zip uploaded", "error")
        return redirect(url_for("admin"))
    if not file.filename.lower().endswith(".zip"):
        flash("file must be a .zip", "error")
        return redirect(url_for("admin"))

    target = _site_path(name)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    try:
        # Buffer to BytesIO: Werkzeug's SpooledTemporaryFile lacks .seekable on Python 3.9.
        raw = io.BytesIO(file.read())
        with zipfile.ZipFile(raw) as zf:
            for member in zf.infolist():
                # Block path traversal & absolute paths
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    continue
                dest = (target / member_path).resolve()
                if target.resolve() not in dest.parents and dest != target.resolve():
                    continue
                if member.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
    except zipfile.BadZipFile:
        shutil.rmtree(target, ignore_errors=True)
        flash("invalid zip file", "error")
        return redirect(url_for("admin"))

    # If the zip wrapped everything in a single top folder, lift it up.
    entries = [p for p in target.iterdir()]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for child in inner.iterdir():
            shutil.move(str(child), target / child.name)
        inner.rmdir()

    flash(f"deployed site '{name}'", "ok")
    return redirect(url_for("admin_site", site=name))


@app.route("/admin/<site>/delete", methods=["POST"])
def admin_delete(site: str):
    site = _safe_name(site)
    path = _site_path(site)
    if path.exists():
        shutil.rmtree(path)
        flash(f"deleted site '{site}'", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/<site>/<form>.csv")
def admin_download_csv(site: str, form: str):
    csv_path = _form_files(site, form)["csv"]
    if not csv_path.exists():
        abort(404)
    return send_file(csv_path, as_attachment=True, download_name=f"{form}.csv")


# ---------- Static site serving ----------

@app.route("/sites/<site>/")
@app.route("/sites/<site>/<path:relpath>")
def serve_site(site: str, relpath: str = ""):
    site_dir = _site_path(site)
    if not site_dir.exists():
        abort(404)
    if not relpath:
        relpath = "index.html"
    full = (site_dir / relpath).resolve()
    if site_dir.resolve() not in full.parents and full != site_dir.resolve():
        abort(403)
    if full.is_dir():
        full = full / "index.html"
    if not full.exists():
        abort(404)
    return send_from_directory(site_dir, str(full.relative_to(site_dir)))


# ---------- Form capture ----------

@app.route("/submit/<site>/<form>", methods=["POST"])
def submit(site: str, form: str):
    site = _safe_name(site)
    form = _safe_name(form)
    if not _site_path(site).exists():
        abort(404, "unknown site")

    payload: Dict[str, str] = {}
    for key in request.form.keys():
        values = request.form.getlist(key)
        payload[key] = values[0] if len(values) == 1 else json.dumps(values)
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            for k, v in body.items():
                payload.setdefault(str(k), v if isinstance(v, str) else json.dumps(v))

    record = {
        "_ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "_ip": request.remote_addr or "",
        **payload,
    }

    files = _form_files(site, form)

    with files["json"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    csv_exists = files["csv"].exists()
    existing_cols: List[str] = []
    if csv_exists:
        with files["csv"].open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            try:
                existing_cols = next(reader)
            except StopIteration:
                existing_cols = []

    new_cols = [c for c in record.keys() if c not in existing_cols]
    all_cols = existing_cols + new_cols

    if new_cols and csv_exists:
        # Rewrite CSV to add the new columns to the header.
        rows: List[List[str]] = []
        with files["csv"].open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                rows.append(row + [""] * (len(all_cols) - len(row)))
        with files["csv"].open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(all_cols)
            writer.writerows(rows)
    elif not csv_exists:
        with files["csv"].open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(all_cols)

    with files["csv"].open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([str(record.get(c, "")) for c in all_cols])

    # If the form posted from a browser, send them somewhere friendly.
    accept = request.headers.get("Accept", "")
    if request.is_json or "application/json" in accept:
        return {"ok": True}, 201
    redirect_to = request.form.get("_redirect")
    if redirect_to:
        return redirect(redirect_to)
    return render_template("thanks.html", site=site, form=form)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
