#!/usr/bin/env python3
# Copyright (C) 2026 glowinthedark
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check wumd.py against wudict's Go implementation.

Run by internal/format/wmd/python_test.go with a JSON file of cases the Go
code produced:

	{"bodies": [{"html": ..., "clean": ..., "cleanErr": false, "raw": ...,
	             "styles": {class: display, ...}}],
	 "docs":   [{"text": ..., "names": [[...], ...]}]}

Every body must convert to exactly Go's markdown in both modes. Every
document must read as the same entries, and read the same in the smallest
chunks as read whole. Differences are printed as JSON; the exit status is 1
when there is any.
"""

import importlib.util
import json
import os
import sys


def load_wumd():
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wumd.py")
	spec = importlib.util.spec_from_file_location("wumd", path)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def main() -> int:
	wumd = load_wumd()
	with open(sys.argv[1], encoding="utf-8") as f:
		cases = json.load(f)
	bad = []
	for c in cases.get("bodies", []):
		h = c["html"]
		try:
			got = wumd.clean_body(h, c.get("styles"))
			err = False
		except wumd.CleanError:
			got, err = "", True
		if err != c["cleanErr"] or (not err and got != c["clean"]):
			bad.append({"mode": "clean", "html": h, "go": c["clean"], "py": got, "pyErr": err})
		got = wumd.html_body(h)
		if got != c["raw"]:
			bad.append({"mode": "html", "html": h, "go": c["raw"], "py": got})
	for d in cases.get("docs", []):
		text = d["text"]
		try:
			doc = wumd.read_text(text)
		except wumd.FormatError as e:
			bad.append({"doc": text[:80], "error": str(e)})
			continue
		whole = [(list(n), b) for n, b in doc]
		names = [n for n, _ in whole]
		if names != d["names"]:
			bad.append({"doc": text[:80], "go": d["names"], "py": names})
		saved = wumd.CHUNK_SIZE
		wumd.CHUNK_SIZE = 1
		try:
			small = [(list(n), b) for n, b in wumd.read_text(text)]
		finally:
			wumd.CHUNK_SIZE = saved
		if small != whole:
			bad.append({"doc": text[:80], "chunked": "differs from whole"})
	if bad:
		json.dump(bad[:50], sys.stdout, ensure_ascii=False, indent=1)
		print(f"\n{len(bad)} difference(s)")
		return 1
	print(f"ok: {len(cases.get('bodies', []))} bodies, {len(cases.get('docs', []))} documents")
	return 0


if __name__ == "__main__":
	sys.exit(main())
