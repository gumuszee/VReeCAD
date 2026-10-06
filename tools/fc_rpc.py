#!/usr/bin/env python3
"""Tiny stdlib-only client for the FreeCAD MCP addon's XML-RPC server (default 127.0.0.1:9875).

Lets any shell/agent poke the *running* FreeCAD GUI without an MCP client:

  python tools/fc_rpc.py status                    # ping + addon/protocol versions + gui dispatch health
  python tools/fc_rpc.py docs                      # list open documents
  python tools/fc_rpc.py objects <doc>             # list objects in a document (JSON)
  python tools/fc_rpc.py exec  "print(App.GuiUp)"  # run Python on FreeCAD's GUI thread, print its stdout
  python tools/fc_rpc.py exec  -f script.py        # same, from a file
  python tools/fc_rpc.py shot  out.png [View]      # save a screenshot (Isometric|Front|Top|Right|...)

Code run via `exec` shares one persistent namespace in FreeCAD (see freecad-mcp docs/execution.md),
with FreeCAD / FreeCADGui already imported (as App / Gui in the namespace too - check with dir()).
Env: FREECAD_RPC_HOST (default 127.0.0.1), FREECAD_RPC_PORT (default 9875). The client sends no auth token, so the RPC addon must run without one.
Exit code is 1 when the remote call reports failure, so it is scriptable.
"""
import base64
import json
import os
import socket
import sys
import xmlrpc.client

HOST = os.environ.get("FREECAD_RPC_HOST", "127.0.0.1")
PORT = int(os.environ.get("FREECAD_RPC_PORT", "9875"))


def proxy(timeout: float = 60.0) -> xmlrpc.client.ServerProxy:
    socket.setdefaulttimeout(timeout)
    return xmlrpc.client.ServerProxy(f"http://{HOST}:{PORT}", allow_none=True)


def exec_code(code: str, timeout: float = 60.0) -> dict:
    """Programmatic entry point: `from fc_rpc import exec_code`."""
    return proxy(timeout + 5).execute_code(code, timeout)


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; FreeCAD output is UTF-8
        stream.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    s = proxy()
    if cmd == "status":
        print(s.ping())
        print(json.dumps(s.get_rpc_status(), indent=2, default=str))
    elif cmd == "docs":
        print(json.dumps(s.list_documents(), indent=2))
    elif cmd == "objects":
        print(json.dumps(s.get_objects(args[0]), indent=2, default=str))
    elif cmd == "exec":
        if args and args[0] == "-f":
            with open(args[1], encoding="utf-8") as f:
                code = f.read()
        else:
            code = " ".join(args)
        res = exec_code(code)
        msg = res.get("message") or res.get("error") or json.dumps(res)
        print(msg)
        return 0 if res.get("success") else 1
    elif cmd == "shot":
        png = s.get_active_screenshot(args[1] if len(args) > 1 else "Isometric")
        if not png:
            print("no screenshot (active view unsupported?)", file=sys.stderr)
            return 1
        with open(args[0], "wb") as f:
            f.write(base64.b64decode(png))
        print(f"saved {args[0]}")
    else:
        print(f"unknown command {cmd!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        print(f"cannot reach FreeCAD RPC at {HOST}:{PORT}: {e}\n"
              "start it with tools/start-freecad.ps1", file=sys.stderr)
        sys.exit(3)
