# Copyright (C) 2026 glowinthedark
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import zipfile
from typing import TYPE_CHECKING

from pyglossary.core import log

from . import wumd

if TYPE_CHECKING:
	from collections.abc import Iterator

	from pyglossary.glossary_types import EntryType, ReaderGlossaryType

__all__ = ["Reader"]


def _container_base(filename: str) -> str:
	"""The name the resource container is derived from (R2.3): the file name
	without its compression suffix and its final `.md`."""
	base = filename
	for ext in (".gz", ".dz"):
		if base.lower().endswith(ext):
			base = base[: -len(ext)]
			break
	if base.lower().endswith(".md"):
		base = base[:-3]
	return base


class Reader:
	depends = {"markdown_it": "markdown-it-py"}
	compressions = ("gz", "dz")  # read here, through gzip

	_resources: bool = True

	def __init__(self, glos: ReaderGlossaryType) -> None:
		self._glos = glos
		self._doc = None
		self._filename = ""
		self._resDir = ""
		self._resZip = ""

	def open(self, filename: str) -> None:
		self._filename = filename
		try:
			doc = wumd.read_text(wumd.load(filename))
		except wumd.FormatError as e:
			raise ValueError(f"{filename}: {e}") from e
		for w in doc.warnings:
			log.warning(f"{os.path.basename(filename)}: {w}")
		self._doc = doc
		glos, meta = self._glos, doc.meta
		glos.setInfo("name", meta["name"])
		if meta["from"]:
			glos.setInfo("sourceLang", meta["from"])
		if meta["to"]:
			glos.setInfo("targetLang", meta["to"])
		for key, value in meta["fields"]:
			glos.setInfo(key, value)
		if meta["description"]:
			glos.setInfo("description", meta["description"])
		if self._resources:
			base = _container_base(filename)
			if os.path.isdir(base + ".files"):
				self._resDir = base + ".files"
			elif os.path.isfile(base + ".files.zip"):
				self._resZip = base + ".files.zip"

	def close(self) -> None:
		self._doc = None

	def __len__(self) -> int:
		return len(self._doc) if self._doc is not None else 0

	def __iter__(self) -> Iterator[EntryType | None]:
		if self._doc is None:
			raise RuntimeError("iterating over a reader while it's not open")
		glos = self._glos
		for names, body in self._doc:
			yield glos.newEntry(names, body, defiFormat="h")
		if self._resDir:
			for root, _, files in os.walk(self._resDir):
				for f in sorted(files):
					path = os.path.join(root, f)
					rel = os.path.relpath(path, self._resDir).replace(os.sep, "/")
					with open(path, "rb") as fh:
						yield glos.newDataEntry(rel, fh.read())
		elif self._resZip:
			with zipfile.ZipFile(self._resZip) as z:
				for info in z.infolist():
					if not info.is_dir():
						yield glos.newDataEntry(info.filename, z.read(info))
