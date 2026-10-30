"""Tamilnilam A-register + chitta exactly as the website returns them (no cleaning, no area conversion, no flags, no retries
with other subdivision numbers). One request per input row to
    https://www.tnagrisnet.tn.gov.in/RES/landdetail/index/<district>/<taluk>/<village>/<survey>/<subdivision>

Input Excel (the CLIP output layout): survey_no, sub_division, district_id, taluk_id, village_id   (sub_division '-' or blank -> '-')
Output Excel, three sheets:
    AReg     one row per input row: the input columns, then every field of aregData.areg as returned
    Chitta   one row per owner entry of chittaData.chitta, with the input columns in front ('-' when the site sent '-')
    Requests one row per input row: url, HTTP status, what came back (Success / the website's own message / error)

Usage: python tools/tamilnilam_raw.py <input.xlsx> <output.xlsx> [--workers 4]"""
import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

URL = "https://www.tnagrisnet.tn.gov.in/RES/landdetail/index/{d}/{t}/{v}/{s}/{sd}"
KEYS = ["survey_no", "sub_division", "district_id", "taluk_id", "village_id"]
_local = threading.local()


def session():
    if getattr(_local, "s", None) is None:      # one kept-alive connection per worker (a new TLS connection per row costs ~1 s)
        _local.s = requests.Session()
    return _local.s


def fetch(row):
    sd = str(row["sub_division"]).strip() or "-"
    url = URL.format(d=str(row["district_id"]).strip(), t=str(row["taluk_id"]).strip(), v=str(row["village_id"]).strip(),
                     s=str(row["survey_no"]).strip(), sd=sd)
    last = None
    for _ in range(3):                           # network errors only; the website's answer is never re-asked
        try:
            r = session().get(url, timeout=40)
            try:
                j = r.json()
            except ValueError:
                return row, url, r.status_code, f"Not JSON: {r.text[:200]}", None
            return row, url, r.status_code, None, j
        except requests.RequestException as e:
            last = e; _local.s = None; time.sleep(3)
    return row, url, None, f"Error: {last!r}"[:300], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("output"); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    inp = pd.read_excel(a.input, dtype=str).fillna("")
    inp.columns = [c.strip() for c in inp.columns]
    miss = [k for k in KEYS if k not in inp.columns]
    if miss:
        raise SystemExit(f"input is missing columns {miss} (needs {KEYS})")
    rows = inp[KEYS].to_dict("records")
    areg, chitta, log = [], [], []
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (row, url, code, err, j) in enumerate(ex.map(fetch, rows), 1):
            if j is None:
                log.append({**row, "url": url, "http_status": code, "result": err}); continue
            a_ = (j.get("aregData") or {}).get("areg") if isinstance(j, dict) else None
            c_ = (j.get("chittaData") or {}).get("chitta") if isinstance(j, dict) else None
            if isinstance(a_, dict):
                areg.append({**row, **a_})
                result = "Success"
            else:   # e.g. {"0": "Enter valid Survey No and Subdivision"} - kept word for word
                result = json.dumps(j, ensure_ascii=False)[:500]
            for o in (c_ if isinstance(c_, list) else [c_] if isinstance(c_, dict) else []):
                chitta.append({**row, **o})
            if isinstance(c_, str):
                chitta.append({**row, "chitta": c_})
            log.append({**row, "url": url, "http_status": code, "result": result})
            if i % 100 == 0 or i == len(rows):
                print(f"{i}/{len(rows)} ({(time.time() - t0) / i:.2f} s each)", flush=True)
    with pd.ExcelWriter(a.output, engine="openpyxl") as w:
        pd.DataFrame(areg).to_excel(w, sheet_name="AReg", index=False)
        pd.DataFrame(chitta).to_excel(w, sheet_name="Chitta", index=False)
        pd.DataFrame(log).to_excel(w, sheet_name="Requests", index=False)
    ok = sum(1 for x in log if x["result"] == "Success")
    print(f"saved {a.output}: {ok} of {len(rows)} rows returned an A-register record; {len(chitta)} chitta rows")


if __name__ == "__main__":
    main()
