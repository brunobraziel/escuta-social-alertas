"""Run as root on the VM. Never prints the API key or unrelated group data."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import Request, urlopen


def request(path, accept="application/json"):
    key = Path("/etc/escuta-whatsapp/secrets/waha_api_key").read_text().strip()
    req = Request("http://127.0.0.1:3000" + path, headers={"X-Api-Key": key, "Accept": accept})
    with urlopen(req, timeout=30) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "qr", "select-group"])
    parser.add_argument("--name")
    args = parser.parse_args()
    if args.command == "status":
        session = json.loads(request("/api/sessions/default"))
        print(json.dumps({"session": session.get("name"), "status": session.get("status")}, ensure_ascii=False))
        dbpath = Path("/var/lib/escuta-whatsapp/delivery/deliveries.sqlite")
        if dbpath.exists():
            with sqlite3.connect(dbpath) as db:
                print("Deliveries:", db.execute("SELECT status,COUNT(*) FROM deliveries GROUP BY status").fetchall())
    elif args.command == "qr":
        target = Path("/tmp/escuta-whatsapp-qr.png")
        target.write_bytes(request("/api/default/auth/qr", "image/png"))
        target.chmod(0o644)
        print(str(target))
    else:
        if not args.name:
            parser.error("--name is required")
        groups = json.loads(request("/api/default/groups"))
        if isinstance(groups, dict):
            groups = list(groups.values())
        matches = [g for g in groups if g.get("subject", g.get("name")) == args.name]
        if len(matches) != 1:
            raise SystemExit("Expected one exact group match; found " + str(len(matches)))
        group_id = matches[0].get("id")
        if isinstance(group_id, dict):
            group_id = group_id.get("_serialized")
        if not isinstance(group_id, str) or not re.fullmatch(r"[0-9-]+@g\.us", group_id):
            raise SystemExit("Invalid group ID")
        Path("/etc/escuta-whatsapp/config/group_id").write_text(group_id)
        print("Grupo autorizado configurado:", args.name)


if __name__ == "__main__":
    main()
