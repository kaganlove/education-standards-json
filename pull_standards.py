import os, json, time, pathlib, argparse, re, sys
from typing import Any, Dict, List, Optional, Callable
import requests

API_BASE = "https://api.commonstandardsproject.com/api/v1"
OUT_ROOT = pathlib.Path("standards")
INDEX_ROOT = OUT_ROOT / "_index"
PATH_INDEX_FILE = INDEX_ROOT / "standard_set_paths.json"
FALLBACK_LOG = INDEX_ROOT / "fallback_log.jsonl"

# ------------- helpers -------------
def slug(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-") or "unnamed"

def _short(s: str, n: int) -> str:
    return slug(s)[:n] if s else "unnamed"

def safe_filename(label: str, set_id: str, max_label: int = 40) -> str:
    base = f"{_short(label, max_label)}__{set_id.lower()}"
    return f"{base}.json"

def ensure_parent(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def _too_long(p: pathlib.Path, threshold: int = 240) -> bool:
    return len(os.fspath(p)) >= threshold

def _fallback_path(jur_slug_short: str, set_id: str) -> pathlib.Path:
    # very short and flat to avoid MAX_PATH problems
    return OUT_ROOT / jur_slug_short / f"{set_id.lower()}.json"

def write_text_json(path: pathlib.Path, data: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_api_key() -> str:
    k = os.getenv("STANDARDS_API_KEY")
    if k:
        return k.strip()
    env = pathlib.Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("STANDARDS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("Missing API key. Put STANDARDS_API_KEY=... in .env or set the env var.")

def with_retries(fn: Callable[[], requests.Response], retries: int = 3, backoff: float = 0.6) -> requests.Response:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            r = fn()
            r.raise_for_status()
            return r
        except (requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last = e
            if attempt < retries:
                time.sleep(backoff * attempt)
            else:
                raise
    assert False, last  # type checkers

def get_json(path: str, key: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{API_BASE}{path}"
    r = with_retries(lambda: requests.get(url, headers={"Api-Key": key}, params=params or {}, timeout=30))
    data = r.json()
    return data.get("data", data)

# ------------- API wrappers -------------
def list_jurisdictions(key: str) -> List[Dict[str, Any]]:
    payload = get_json("/jurisdictions", key)
    return payload if isinstance(payload, list) else []

def get_jurisdiction(jur_id: str, key: str) -> Dict[str, Any]:
    return get_json(f"/jurisdictions/{jur_id}", key)

def get_standard_set(set_id: str, key: str) -> Dict[str, Any]:
    return get_json(f"/standard_sets/{set_id}", key)

# ------------- index persistence -------------
def load_path_index() -> Dict[str, Any]:
    if PATH_INDEX_FILE.exists():
        try:
            return json.loads(PATH_INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            PATH_INDEX_FILE.rename(PATH_INDEX_FILE.with_suffix(".json.bak"))
    return {}

def persist_path_index(idx: Dict[str, Any]) -> None:
    ensure_parent(PATH_INDEX_FILE)
    PATH_INDEX_FILE.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

def log_fallback(entry: Dict[str, Any]) -> None:
    ensure_parent(FALLBACK_LOG)
    with FALLBACK_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

def update_path_index(entry: Dict[str, Any], idx: Dict[str, Any]) -> None:
    set_id = entry["set_id"]
    idx[set_id] = entry
    persist_path_index(idx)

# ------------- safe write with fallback -------------
def write_json_with_fallback(primary: pathlib.Path, data: Any, fallback: pathlib.Path, fallback_reason: str, meta_for_log: Dict[str, Any]) -> pathlib.Path:
    """
    Attempts to write to primary path. If the path is too long or write fails, writes to fallback.
    Returns the path actually written.
    """
    try:
        if _too_long(primary):
            raise OSError("path too long")
        write_text_json(primary, data)
        print(f"wrote: {primary}")
        return primary
    except Exception as e:
        try:
            write_text_json(fallback, data)
            print(f"wrote (fallback): {fallback}")
            log_fallback({
                "reason": fallback_reason,
                "error": str(e),
                "primary": os.fspath(primary),
                "fallback": os.fspath(fallback),
                **meta_for_log
            })
            return fallback
        except Exception as e2:
            raise RuntimeError(f"Failed writing both primary and fallback paths. Primary error: {e}. Fallback error: {e2}")

# ------------- main -------------
def main():
    ap = argparse.ArgumentParser(description="Pull CSP standard sets grouped by jurisdiction")
    ap.add_argument("--delay", type=float, default=0.15, help="Delay between requests in seconds")
    ap.add_argument("--max-jur", type=int, default=0, help="Limit jurisdictions processed, 0 for all")
    ap.add_argument("--max-sets", type=int, default=0, help="Limit sets per jurisdiction, 0 for all")
    ap.add_argument("--jur", nargs="*", help="Only pull these jurisdiction IDs")
    ap.add_argument("--states-only", action="store_true", help="Process only jurisdictions where type == 'state'")
    ap.add_argument("--overwrite", action="store_true", help="Re-download even if output file exists")
    args = ap.parse_args()

    key = load_api_key()

    # Save jurisdiction list for reference
    jurs = list_jurisdictions(key)
    ensure_parent(INDEX_ROOT / "jurisdictions.json")
    write_text_json(INDEX_ROOT / "jurisdictions.json", jurs)

    # Load or create the set_id -> path index
    path_index: Dict[str, Any] = load_path_index()

    total_j = len(jurs)
    processed = 0

    try:
        for idx_j, j in enumerate(jurs, start=1):
            jur_id = str(j.get("id") or "")
            jur_title = (j.get("title") or j.get("name") or jur_id).strip()
            if not jur_id:
                continue
            if args.jur and jur_id not in args.jur:
                continue
            if args.states_only and (j.get("type") or "").strip().lower() != "state":
                continue

            jur_slug_full = slug(jur_title)
            jur_slug_short = jur_slug_full[:40]

            # Fetch jurisdiction detail
            try:
                detail = get_jurisdiction(jur_id, key)
            except Exception as e:
                print(f"[{idx_j}/{total_j}] skip {jur_title} ({jur_id}) -> {e}")
                continue

            sets = detail.get("standardSets") or []
            print(f"[{idx_j}/{total_j}] {jur_title}: {len(sets)} sets")

            # Write jurisdiction sets index with fallback
            jur_sets_primary = INDEX_ROOT / f"standard_sets_{jur_slug_full}.json"
            jur_sets_fallback = INDEX_ROOT / f"standard_sets_{jur_slug_short}.json"
            _ = write_json_with_fallback(
                jur_sets_primary,
                sets,
                jur_sets_fallback,
                "jurisdiction_index_path_too_long",
                {"jurisdiction_id": jur_id, "jurisdiction_title": jur_title}
            )

            pulled = 0
            for s in sets:
                set_id = str(s.get("id") or "").strip()
                if not set_id:
                    continue

                subject = s.get("subject") or "unspecified"
                levels = s.get("educationLevels") or []
                grade_label = "-".join(levels) if isinstance(levels, list) and levels else (s.get("title") or set_id)

                subject_slug_short = _short(subject, 40)

                out_dir = OUT_ROOT / jur_slug_short / subject_slug_short
                out_name = safe_filename(grade_label, set_id, max_label=40)
                out_file = out_dir / out_name
                fallback_file = _fallback_path(jur_slug_short, set_id)

                if out_file.exists() and not args.overwrite:
                    print(f"skip exists -> {out_file}")
                    update_path_index({
                        "set_id": set_id,
                        "path": out_file.as_posix(),
                        "jurisdiction_id": jur_id,
                        "jurisdiction_slug": jur_slug_short,
                        "jurisdiction_title": jur_title,
                        "subject": subject,
                        "grade_label": grade_label,
                        "filename": out_name,
                        "used_fallback": False
                    }, path_index)
                    continue

                try:
                    full = get_standard_set(set_id, key)
                except Exception as e:
                    print(f"failed set {set_id} -> {e}")
                    continue

                written_path = out_file
                try:
                    # try primary, fallback if too long or fails
                    written_path = write_json_with_fallback(
                        out_file,
                        full,
                        fallback_file,
                        "standard_set_path_too_long_or_write_error",
                        {
                            "set_id": set_id,
                            "jurisdiction_id": jur_id,
                            "jurisdiction_title": jur_title,
                            "subject": subject,
                            "grade_label": grade_label
                        }
                    )
                except Exception as e:
                    print(f"failed write {set_id} -> {e}")
                    continue

                used_fallback = os.fspath(written_path) != os.fspath(out_file)

                update_path_index({
                    "set_id": set_id,
                    "path": written_path.as_posix(),
                    "jurisdiction_id": jur_id,
                    "jurisdiction_slug": jur_slug_short,
                    "jurisdiction_title": jur_title,
                    "subject": subject,
                    "grade_label": grade_label,
                    "filename": written_path.name,
                    "used_fallback": used_fallback
                }, path_index)

                pulled += 1
                if args.max_sets and pulled >= args.max_sets:
                    break
                if args.delay:
                    time.sleep(args.delay)

            processed += 1
            if args.max_jur and processed >= args.max_jur:
                break

    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C). You can rerun to resume; existing files are skipped unless --overwrite is set.")
        sys.exit(130)

if __name__ == "__main__":
    main()
