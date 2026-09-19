"""
tests/test_n8n_workflows.py

Checks the 4 n8n workflow files in n8n/ WITHOUT n8n running: that they are
valid, every connection points at a real node, every API call they make
exists in api/server.py with the same method, and the email nodes send the
API's subject + HTML without n8n's advert line. Catches a broken workflow file before you
import it. (They were also run end-to-end in a real n8n 2.39 before delivery.)

    python -m tests.test_n8n_workflows
"""

import glob
import json
import os
import re
import sys

from api.server import app

WORKFLOW_DIR = "n8n"
checks = []


def check(name, condition, detail=""):
    checks.append(bool(condition))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not condition else ""))


def api_routes():
    """{(METHOD, '/alerts/escalations/{}/sent'), ...} from the FastAPI app."""
    routes = set()
    for r in app.routes:
        for m in getattr(r, "methods", None) or []:
            routes.add((m, re.sub(r"\{[^}]+\}", "{}", r.path)))
    return routes


def called_path(url: str) -> str:
    """'={{ $('Config')...api_url }}/alerts/escalations/{{ $(...).id }}/sent?x=1'
    -> '/alerts/escalations/{}/sent'"""
    path = url.split("api_url }}", 1)[1]
    path = path.split("?", 1)[0]
    return re.sub(r"\{\{.*?\}\}", "{}", path)


def main():
    files = sorted(glob.glob(os.path.join(WORKFLOW_DIR, "*.json")))
    check("4 workflow files in n8n/", len(files) == 4, files)
    routes = api_routes()
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                wf = json.load(f)
        except ValueError as e:
            check(f"{name}: valid JSON", False, e)
            continue
        nodes = {n["name"]: n for n in wf["nodes"]}
        check(f"{name}: has a name and nodes", wf.get("name") and nodes)
        check(f"{name}: node names are unique", len(nodes) == len(wf["nodes"]))
        bad = [(src, c["node"]) for src, outs in wf["connections"].items()
               for branch in outs["main"] for c in branch
               if src not in nodes or c["node"] not in nodes]
        check(f"{name}: every connection joins real nodes", not bad, bad)
        triggers = [n for n in wf["nodes"] if n["type"].endswith(("Trigger", ".webhook"))]
        check(f"{name}: exactly one trigger", len(triggers) == 1, [t["name"] for t in triggers])

        config = nodes.get("Config")
        fields = {a["name"]: a["value"] for a in
                  (config or {}).get("parameters", {}).get("assignments", {}).get("assignments", [])}
        check(f"{name}: Config node with api_url 127.0.0.1:8000 and api_key",
              fields.get("api_url") == "http://127.0.0.1:8000" and "api_key" in fields, fields)

        for n in wf["nodes"]:
            if n["type"] == "n8n-nodes-base.httpRequest":
                p = n["parameters"]
                call = (p["method"], called_path(p["url"]))
                check(f"{name}: '{n['name']}' calls an endpoint that exists ({call[0]} {call[1]})",
                      call in routes, sorted(routes))
                headers = {h["name"]: h["value"] for h in p["headerParameters"]["parameters"]}
                check(f"{name}: '{n['name']}' sends the API key header", "X-API-Key" in headers)
            if n["type"] == "n8n-nodes-base.emailSend":
                p = n["parameters"]
                check(f"{name}: '{n['name']}' sends the API's subject and HTML, without n8n's advert line",
                      p.get("emailFormat") == "html" and "$json.html" in p.get("html", "")
                      and "$json.subject" in p.get("subject", "")
                      and p.get("options", {}).get("appendAttribution") is False)
                check(f"{name}: '{n['name']}' uses the Gmail credential and Config addresses",
                      "smtp" in n.get("credentials", {}) and "email_from" in p["fromEmail"]
                      and "email_to" in p["toEmail"])
                check(f"{name}: Config has email_from / email_to to fill in",
                      fields.get("email_from", "").startswith("PASTE_")
                      and fields.get("email_to", "").startswith("PASTE_"), fields)
        if any(n["type"] == "n8n-nodes-base.emailSend" for n in wf["nodes"]) and "Mark" in json.dumps(wf):
            tg = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.emailSend")
            outs = wf["connections"].get(tg["name"], {}).get("main", [])
            marks_only_success = (len(outs) == 2 and all("Mark" in c["node"] for c in outs[0])
                                  and not any("Mark" in c["node"] for c in outs[1]))
            check(f"{name}: only alerts that were emailed are marked sent (failed = retried)",
                  marks_only_success and tg.get("onError") == "continueErrorOutput", outs)
        if any(n["type"] == "n8n-nodes-base.webhook" for n in wf["nodes"]):
            hook = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook")
            check(f"{name}: webhook is POST /glowcare-chat and replies itself",
                  hook["parameters"]["path"] == "glowcare-chat" and hook["parameters"]["httpMethod"] == "POST"
                  and hook["parameters"]["responseMode"] == "responseNode")
        check(f"{name}: timezone Asia/Karachi", wf["settings"].get("timezone") == "Asia/Karachi")
        check(f"{name}: imported switched off (you publish it after checking Config)",
              wf.get("active") is False)
        creds = [c for n in wf["nodes"] for c in n.get("credentials", {}).values()]
        check(f"{name}: no password or key inside the file (credentials are referenced by name only)",
              all(set(c) <= {"id", "name"} for c in creds)
              and not re.search(r'"(password|accessToken|user)"\s*:', json.dumps(wf)))

    passed = sum(checks)
    print("-" * 60)
    print(f"{passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
