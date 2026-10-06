#!/usr/bin/env python3
"""End-to-end smoke test of the FreeCAD MCP chain: MCP client -> freecad-mcp server (stdio) -> XML-RPC -> running FreeCAD GUI.

Needs FreeCAD running with the RPC server up (tools/start-freecad.ps1). Run it inside the
freecad-mcp uv environment, which already contains the `mcp` client library:

  uv run --directory refs/freecad-mcp python ../../tools/mcp_smoke_test.py [out_dir]

It creates document "MCPSmoke", a Part::Box via create_object, a cylinder + boolean cut via
execute_code, verifies the resulting volume and saves the screenshot returned by get_view.
Exit code 0 = whole chain works.
"""
import asyncio
import base64
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def texts(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


async def main() -> int:
    params = StdioServerParameters(command="uv", args=["run", "freecad-mcp", "--only-text-feedback"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = [t.name for t in (await s.list_tools()).tools]
        print("tools:", tools)

        print(texts(await s.call_tool("create_document", {"name": "MCPSmoke"})))
        print(texts(await s.call_tool("create_object", {
            "doc_name": "MCPSmoke", "obj_type": "Part::Box", "obj_name": "Plate",
            "obj_properties": {"Length": 60, "Width": 40, "Height": 10},
            "include_screenshot": False})))
        code = (
            "import FreeCAD, Part\n"
            "doc = FreeCAD.getDocument('MCPSmoke')\n"
            "hole = doc.addObject('Part::Cylinder', 'Hole')\n"
            "hole.Radius = 8; hole.Height = 10\n"
            "hole.Placement.Base = FreeCAD.Vector(30, 20, 0)\n"
            "cut = doc.addObject('Part::Cut', 'PlateWithHole')\n"
            "cut.Base = doc.Plate; cut.Tool = hole\n"
            "doc.recompute()\n"
            "print('volume', round(cut.Shape.Volume, 1))\n"
        )
        out = texts(await s.call_tool("execute_code", {"code": code, "include_screenshot": False}))
        print(out)
        expected = 60 * 40 * 10 - 3.14159265 * 8 * 8 * 10
        ok = f"volume {expected:.1f}" in out or "volume" in out and abs(float(out.split("volume")[1].split()[0]) - expected) < 1
        view = await s.call_tool("get_view", {"view_name": "Isometric"})
        for c in view.content:
            if c.type == "image":
                os.makedirs(OUT, exist_ok=True)
                path = os.path.join(OUT, "mcp_smoke.png")
                with open(path, "wb") as f:
                    f.write(base64.b64decode(c.data))
                print("screenshot ->", path)
        print("SMOKE TEST", "PASSED" if ok else "FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
