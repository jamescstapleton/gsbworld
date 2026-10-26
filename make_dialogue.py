"""
Turn the blast-email export into web/emails.json, the chat lines for the game.

Usage:
    python make_dialogue.py gsb_blast_emails.csv web/emails.json

The game shows one email per conversation, in the CSV's order (top to bottom).
Re-run this whenever the CSV changes. Expected columns:
    Date Sent (PT), Sender, Sender Email, Subject, Body, Attachments

Privacy: email addresses, phone numbers, meeting PINs and links in the text are
always masked, and sender addresses are moved to example.edu. People's names are replaced with initials if they are listed in
private_names.txt next to the CSV (one name per line, e.g. "Jane Doe" -> "JD",
"Sam" -> "S."). That file holds real names, so it is git-ignored: keep it local.
"""

import csv
import json
import os
import re
import sys

URL_IN_ANGLES = re.compile(r"\s*<(?:https?|mailto):[^>]*>")  # "text <https://...>" -> "text [link]"
BARE_URL = re.compile(r"https?://\S+")
IMAGE_TAG = re.compile(r"\[image:[^\]]*\]")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
PIN = re.compile(r"(PIN:\s*)\d+")
NAMES_FILE = "private_names.txt"
# The game is public, so sender addresses keep only their local part on a reserved
# domain that can't belong to anyone: "abc@university.edu" -> "abc@example.edu".
PUBLIC_DOMAIN = "example.edu"


def public_address(address):
    local = address.strip().split("@")[0]
    return f"{local}@{PUBLIC_DOMAIN}" if local else ""


def initials(name):
    words = name.split()
    return words[0][0] + "." if len(words) == 1 else "".join(w[0] for w in words)


def load_names(csv_path):
    path = os.path.join(os.path.dirname(os.path.abspath(csv_path)), NAMES_FILE)
    if not os.path.isfile(path):
        print(f"note: no {NAMES_FILE} next to the CSV; names in the email text are left as they are")
        return []
    with open(path, encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return sorted(set(names), key=len, reverse=True)  # longest first: "Jane Doe" before "Jane"


def redact(text, names):
    text = URL_IN_ANGLES.sub(" [link]", text)
    text = BARE_URL.sub("[link]", text)
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    text = PIN.sub(r"\1[PIN]", text)
    for name in names:
        text = re.sub(rf"\b{re.escape(name)}\b", initials(name), text)
    return text


LIST_START = re.compile(r"^\s|^[-*•|]|^\d+[.)]\s")  # indented, bulleted or numbered lines
WRAP_WIDTH = 55  # lines at least this long were probably hard-wrapped by the mail client


def unwrap(text):
    """Rejoin lines that the sender's mail client hard-wrapped at ~72 columns, so
    paragraphs reflow to the chat box's width. Lists, short lines and blank-line
    paragraph breaks are kept as they are."""
    lines = text.split("\n")
    out = []
    for line in lines:
        prev = out[-1] if out else ""
        if (prev and len(prev) >= WRAP_WIDTH and line.strip() and not LIST_START.match(line)
                and not prev.rstrip().endswith(":")):
            out[-1] = prev.rstrip() + " " + line.strip()
        else:
            out.append(line)
    return "\n".join(out)


def clean_body(text, names):
    text = redact(text.replace("\r\n", "\n"), names)
    text = re.sub(r"\[link\](?=\w)", "[link] ", text)  # "[link]and" -> "[link] and"
    text = IMAGE_TAG.sub("[image]", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)  # at most one blank line in a row
    return unwrap(text.strip())


def main(csv_path, out_path):
    names = load_names(csv_path)
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    emails = []
    for r in rows:
        attachments = [redact(a.strip(), names) for a in (r.get("Attachments") or "").split(";") if a.strip()]
        emails.append({
            "date": r["Date Sent (PT)"].strip(),
            "sender": redact(r["Sender"].strip(), names),
            "email": public_address(r["Sender Email"]),
            "subject": redact(r["Subject"].strip(), names),
            "body": clean_body(r["Body"], names),
            "attachments": attachments,
        })
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(emails, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(emails)} emails to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
