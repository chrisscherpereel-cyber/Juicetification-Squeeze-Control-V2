#!/usr/bin/env python3
"""
================================================================================
 Juicetification: Squeeze Control — LMS Completion-Code Verifier  (instructor tool)
================================================================================
A completion code looks like:   SQZ-12-0128-4913A0
    SQZ      fixed prefix
    12       weeks diagnosed          (readable directly)
    0128     score                    (readable directly)
    4913A0   checksum = first 6 hex of SHA-256(name|score|weeks|salt)

Codes are NOT decrypted — they are *verified by recomputation*. Given the
student's name plus the weeks/score printed in the code, this tool rebuilds the
checksum with your secret salt. If it matches, the code is authentic for that
student; if not, the name, score, or weeks was altered (or it's someone else's
code).

IMPORTANT: set SALT below to the exact same string as COMPLETION_SALT in the
game file (juicetification.py). If you changed it there, change it here too,
or pass it at runtime with  --salt "your-secret".

USAGE
    # 1) Interactive — just run it and answer the prompts:
    python verify_code.py

    # 2) One submission on the command line:
    python verify_code.py "Ada Lovelace" SQZ-12-0128-4913A0

    # 3) A whole class from a CSV (needs columns 'name' and 'code'):
    python verify_code.py --csv submissions.csv
    python verify_code.py --csv submissions.csv --out results.csv

    # Override the salt without editing this file:
    python verify_code.py --salt "my-course-secret" "Ada Lovelace" SQZ-12-0128-4913A0
================================================================================
"""

import argparse
import csv
import hashlib
import sys

# Must match COMPLETION_SALT in juicetification.py
SALT = "squeeze-control-2026"


def make_code(name, score, weeks, salt):
    """Recreate the exact code the game would generate."""
    key = f"{name.strip().lower()}|{int(score)}|{int(weeks)}|{salt}"
    h = hashlib.sha256(key.encode()).hexdigest()[:6].upper()
    return f"SQZ-{int(weeks):02d}-{int(score):04d}-{h}"


def normalize(code):
    """Clean up a pasted code: strip spaces, uppercase."""
    return "".join(str(code).split()).upper()


def verify(name, code, salt=SALT):
    """
    Return a dict describing the result:
        ok:      True/False (is the code authentic for this name?)
        weeks:   int or None (parsed from the code, if well-formed)
        score:   int or None
        reason:  short explanation
        code:    the normalized code
    """
    raw = normalize(code)
    parts = raw.split("-")
    if len(parts) != 4 or parts[0] != "SQZ":
        return dict(ok=False, weeks=None, score=None, code=raw,
                    reason="malformed code (expected SQZ-WW-SSSS-HHHHHH)")
    try:
        weeks = int(parts[1])
        score = int(parts[2])
    except ValueError:
        return dict(ok=False, weeks=None, score=None, code=raw,
                    reason="weeks/score are not numbers")

    expected = make_code(name, score, weeks, salt)
    if expected == raw:
        return dict(ok=True, weeks=weeks, score=score, code=raw,
                    reason="authentic")
    return dict(ok=False, weeks=weeks, score=score, code=raw,
                reason="checksum mismatch — name/score/weeks altered, wrong name, "
                       "or a different salt")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def print_one(name, res):
    mark = "\u2713 VALID  " if res["ok"] else "\u2717 INVALID"
    if res["weeks"] is not None:
        detail = f'{res["weeks"]} weeks, score {res["score"]}'
    else:
        detail = res["reason"]
    line = f'{mark}  {name!r:24}  {res["code"]:20}  {detail}'
    if not res["ok"] and res["weeks"] is not None:
        line += f'   ({res["reason"]})'
    print(line)


def run_csv(path, salt, out_path=None):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = {h.lower().strip(): h for h in (reader.fieldnames or [])}
        if "name" not in headers or "code" not in headers:
            sys.exit("CSV must have 'name' and 'code' columns. "
                     f"Found: {reader.fieldnames}")
        rows = list(reader)

    results = []
    valid = 0
    print(f"\nVerifying {len(rows)} submission(s) from {path}\n" + "-" * 78)
    for row in rows:
        name = row[headers["name"]].strip()
        code = row[headers["code"]]
        res = verify(name, code, salt)
        valid += res["ok"]
        print_one(name, res)
        results.append(dict(name=name, code=res["code"], valid=res["ok"],
                            weeks=res["weeks"] if res["weeks"] is not None else "",
                            score=res["score"] if res["score"] is not None else "",
                            reason=res["reason"]))
    print("-" * 78)
    print(f"{valid} valid, {len(rows) - valid} invalid, {len(rows)} total.\n")

    if out_path:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["name", "code", "valid", "weeks",
                                              "score", "reason"])
            w.writeheader()
            w.writerows(results)
        print(f"Wrote results to {out_path}")


def main():
    ap = argparse.ArgumentParser(
        description="Verify Squeeze Control LMS completion codes.")
    ap.add_argument("name", nargs="?", help="student name or ID")
    ap.add_argument("code", nargs="?", help="the completion code, e.g. SQZ-12-0128-4913A0")
    ap.add_argument("--csv", help="verify a CSV file with 'name' and 'code' columns")
    ap.add_argument("--out", help="write CSV results to this path (with --csv)")
    ap.add_argument("--salt", default=SALT, help="override the secret salt")
    args = ap.parse_args()

    if args.csv:
        run_csv(args.csv, args.salt, args.out)
        return

    if args.name and args.code:
        print()
        print_one(args.name, verify(args.name, args.code, args.salt))
        print()
        return

    # Interactive
    print("Squeeze Control — code verifier  (blank name to quit)")
    if args.salt != SALT:
        print(f"Using custom salt.")
    while True:
        try:
            name = input("\nStudent name/ID: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not name:
            break
        code = input("Completion code: ").strip()
        print_one(name, verify(name, code, args.salt))


if __name__ == "__main__":
    main()
