"""
Feedback from the site's "Suggest a feature / report a bug" form.

Stored for Nate to read; nothing here is shown publicly. The API's role may
only insert rows (it can't read them back), and the form is rate-limited
with a honeypot field, so a spammer gets nowhere and learns nothing.

Tables are created by scripts/setup_feedback.py (and schema.sql).

Usage:
    python feedback.py            # the latest 20
    python feedback.py --days 7   # everything from the last week
"""

import argparse
import os
import re

KINDS = ("idea", "bug")
MAX_MESSAGE = 1000
MAX_CONTACT = 120

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id          SERIAL PRIMARY KEY,
    kind        VARCHAR(8) NOT NULL,      -- idea or bug
    message     TEXT NOT NULL,
    contact     VARCHAR(120),             -- optional: how to reply
    page        VARCHAR(200),             -- where on the site it was sent from
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
# Insert only: the API can't read feedback back out, so nothing it serves can leak it.
GRANTS_SQL = """
GRANT INSERT ON feedback TO nhl_api_readonly;
GRANT USAGE ON SEQUENCE feedback_id_seq TO nhl_api_readonly;
"""

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text, limit):
    """Trimmed, without control characters (newlines kept), at most `limit` characters; None if empty."""
    text = _CONTROL.sub("", (text or "")).strip()[:limit]
    return text or None


def main():
    import psycopg2
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        if args.days:
            cur.execute("SELECT kind, message, contact, page, created_at FROM feedback "
                        "WHERE created_at > NOW() - make_interval(days => %s) ORDER BY created_at", (args.days,))
        else:
            cur.execute("SELECT kind, message, contact, page, created_at FROM feedback ORDER BY created_at DESC LIMIT 20")
        rows = cur.fetchall()
    for kind, message, contact, page, at in rows:
        print(f"[{at:%Y-%m-%d %H:%M}] {kind.upper()} on {page or '?'}{f' (contact: {contact})' if contact else ''}\n  {message}\n")
    print(f"{len(rows)} item(s)")


if __name__ == "__main__":
    main()
