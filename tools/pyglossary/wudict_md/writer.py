# Copyright (C) 2026 glowinthedark
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import html
import os
from typing import TYPE_CHECKING

from pyglossary.core import log

from . import wumd

if TYPE_CHECKING:
	from collections.abc import Generator

	from pyglossary.glossary_types import EntryType, WriterGlossaryType

__all__ = ["Writer"]

# Info keys the header has its own place for, or that describe the conversion
# rather than the dictionary.
_OWN_KEYS = frozenset(("name", "title", "sourcelang", "targetlang", "description",
	"input_file_size", "sourcelangcode", "targetlangcode"))


def _text_html(s: str) -> str:
	"""A plain-text definition as HTML, as wudict itself makes one."""
	return "<p>" + html.escape(s, quote=False).replace("\n", "<br/>") + "</p>"


def _lang_code(lang) -> str:
	if lang is None:
		return ""
	return getattr(lang, "code", "") or ""


class Writer:
	depends = {"markdown_it": "markdown-it-py"}

	_mode: str = "html"
	_resources: bool = True

	def __init__(self, glos: WriterGlossaryType) -> None:
		self._glos = glos
		self._file = None
		self._filename = ""
		self._resDir = ""
		self.empty = self.nameless = 0

	def _body(self, src: str) -> str:
		return wumd.html_body(src) if self._mode == "html" else wumd.clean_body(src)

	def open(self, filename: str) -> None:
		if self._mode not in ("clean", "html"):
			raise ValueError(f"mode {self._mode!r}: want clean or html")
		self._filename = filename
		base = filename[:-3] if filename.lower().endswith(".md") else filename
		self._resDir = base + ".files"  # R2.3
		self._file = open(filename + ".tmp", "w", encoding="utf-8", newline="\n")
		glos = self._glos

		stem = os.path.basename(base)
		name = wumd.repair_name(glos.getInfo("name") or "") or wumd.repair_name(stem) or "dictionary"
		out = ["# " + wumd.heading_esc(name), "wudict: 1"]
		for key, lang in (("from", glos.sourceLang), ("to", glos.targetLang)):
			code = wumd.repair_name(_lang_code(lang))
			if code:
				out.append(f"{key}: {code}")
		for key, value in glos.iterInfo():
			if key.lower() in _OWN_KEYS:
				continue
			v = wumd.repair_name(value)
			if not v:
				continue
			if key == "meta":
				out.append("meta: " + v)
			elif k := wumd.field_key(key):
				out.append(f"{k}: {v}")
			elif n := wumd.repair_name(key):
				out.append(f"meta: {n}: {v}")
		text = "\n".join(out)
		desc = glos.getInfo("description") or ""
		if desc:
			src = desc if "<" in desc and ">" in desc else _text_html(desc)
			try:
				md = self._body(src)
			except wumd.CleanError as e:
				raise ValueError(f"the description: {e}") from e
			if md:
				text += "\n\n" + md
		self._file.write(text)

	def write(self) -> Generator[None, EntryType, None]:
		index = 0
		while True:
			entry = yield
			if entry is None:
				break
			if entry.isData():
				if self._resources:
					os.makedirs(self._resDir, exist_ok=True)
					entry.save(self._resDir)
				continue
			index += 1
			names, seen = [], set()
			for n in entry.l_term:
				n = wumd.repair_name(n)
				if n and n not in seen:
					seen.add(n)
					names.append(n)
			if not names:
				self.nameless += 1
				continue
			src = entry.defi if entry.defiFormat == "h" else _text_html(entry.defi)
			try:
				md = self._body(src)
			except wumd.CleanError as e:
				# R6.8: stop, show the entry, say how to keep its HTML.
				print("\n".join("## " + n for n in names) + "\n\n" + src)
				raise ValueError(
					f"entry {names[0]!r} (#{index}): {e}\n"
					"hint: keep the dictionary's HTML instead: --write-options=mode=html",
				) from e
			if not md:
				self.empty += 1
				continue
			self._file.write("\n\n" + "\n".join("## " + wumd.heading_esc(n) for n in names) + "\n\n" + md)

	def finish(self) -> None:
		if self._file is None:
			return
		self._file.write("\n")
		self._file.close()
		self._file = None
		os.replace(self._filename + ".tmp", self._filename)
		if self.empty:
			log.info(f"{self.empty} article(s) with an empty body left out")
		if self.nameless:
			log.info(f"{self.nameless} entry(ies) without a headword left out")
		if os.path.isdir(self._resDir) and not os.listdir(self._resDir):
			os.rmdir(self._resDir)
