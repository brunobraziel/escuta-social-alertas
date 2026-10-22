"""Run as root on the VM. Never prints the API key or unrelated group data."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import secrets
from urllib.request import Request, urlopen


def request(path, accept="application/json", *, body=None, method=None):
    key = Path("/etc/escuta-whatsapp/secrets/waha_api_key").read_text().strip()
    req = Request("http://127.0.0.1:3000" + path, headers={"X-Api-Key": key, "Accept": accept, "Content-Type": "application/json"},
                  data=json.dumps(body).encode() if body is not None else None, method=method)
    with urlopen(req, timeout=30) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "qr", "select-group", "enable-reactions"])
    parser.add_argument("--name")
    parser.add_argument("--community", help="Require membership in this community")
    args = parser.parse_args()
    if args.command == "status":
        session = json.loads(request("/api/sessions/default"))
        print(json.dumps({"session": session.get("name"), "status": session.get("status")}, ensure_ascii=False))
        dbpath = Path("/var/lib/escuta-whatsapp/delivery/deliveries.sqlite")
        if dbpath.exists():
            with sqlite3.connect(dbpath) as db:
                print("Deliveries:", db.execute("SELECT status,COUNT(*) FROM deliveries GROUP BY status").fetchall())
    elif args.command == "enable-reactions":
        key_path = Path('/etc/escuta-whatsapp/secrets/reaction_hmac_key')
        if not key_path.exists():
            key_path.write_text(secrets.token_hex(32))
            key_path.chmod(0o600)
        session = json.loads(request('/api/sessions/default'))
        config = session.get('config') or {}
        url = 'http://worker:8080/reactions'
        hooks = [h for h in config.get('webhooks', []) if h.get('url') != url]
        hooks.append({'url':url, 'events':['message.reaction'],
                      'hmac':{'key':key_path.read_text().strip()},
                      'retries':{'policy':'constant','delaySeconds':3,'attempts':10}})
        config['webhooks'] = hooks
        updated = json.loads(request('/api/sessions/default', body={'name':'default','config':config}, method='PUT'))
        print(json.dumps({'reactions_configured':True,'status':updated.get('status')}))
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
        normalize = lambda value: " ".join(str(value or "").casefold().split())
        matches = [g for g in groups if normalize(g.get("subject", g.get("name"))) == normalize(args.name)]
        if args.community:
            verified = []
            from urllib.parse import quote
            for candidate in matches:
                candidate_id = candidate.get("id")
                if isinstance(candidate_id, dict):
                    candidate_id = candidate_id.get("_serialized")
                details = json.loads(request("/api/default/groups/" + quote(candidate_id, safe="")))
                parent = details.get("linkedParent") or details.get("parentGroupId")
                if not parent:
                    continue
                community = json.loads(request("/api/default/groups/" + quote(parent, safe="")))
                if normalize(community.get("subject", community.get("name"))) == normalize(args.community):
                    verified.append(candidate)
            matches = verified
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
