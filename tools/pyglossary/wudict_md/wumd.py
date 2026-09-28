# Copyright (C) 2026 glowinthedark
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""WuWeiDict markdown (docs/WUDICT-MARKDOWN.md) without pyglossary.

The reader and the two writer modes of the format, as a port of wudict's own
Go implementation (internal/format/wmd). The two are kept byte-identical by
internal/format/wmd/python_test.go, which runs this module over the Go tests'
inputs. The only dependency is markdown-it-py, used stock: the "commonmark"
preset with the table rule, and nothing else.
"""

from __future__ import annotations

import bisect
import gzip
import html
import html.parser
import re
import unicodedata

__all__ = [
	"CleanError",
	"FormatError",
	"clean_body",
	"field_key",
	"heading_esc",
	"html_body",
	"read_text",
	"repair_name",
]


# ---------------------------------------------------------------------------
# Errors

class FormatError(Exception):
	"""A file this reader does not read (spec §8: E-format, E-version)."""

	def __init__(self, code: str, msg: str) -> None:
		super().__init__(f"wudict markdown: {code}: {msg}")
		self.code = code


class CleanError(Exception):
	"""A body `clean` mode cannot write (R6.8)."""

	def __init__(self, construct: str, reason: str) -> None:
		super().__init__(f"{construct} cannot be written as clean markdown: {reason}")
		self.construct = construct
		self.reason = reason


# ---------------------------------------------------------------------------
# Go's text primitives, where Python's differ

# unicode.IsSpace: Latin-1 space characters, then White_Space above.
_GO_SPACE = frozenset("\t\n\v\f\r \x85\xa0        "
	"        　")


def go_fields(s: str) -> list[str]:
	"""strings.Fields."""
	out, cur = [], []
	for c in s:
		if c in _GO_SPACE:
			if cur:
				out.append("".join(cur))
				cur = []
		else:
			cur.append(c)
	if cur:
		out.append("".join(cur))
	return out


def go_trim_space(s: str) -> str:
	"""strings.TrimSpace."""
	i, j = 0, len(s)
	while i < j and s[i] in _GO_SPACE:
		i += 1
	while j > i and s[j - 1] in _GO_SPACE:
		j -= 1
	return s[i:j]


_HSPACE = " \t\n\r\f"  # the converter's own isSpace


def fields_hspace(s: str) -> list[str]:
	"""strings.FieldsFunc(s, isSpace)."""
	return [f for f in re.split("[ \t\n\r\f]+", s) if f]


def go_html_escape(s: str) -> str:
	"""html.EscapeString (Go)."""
	return (s.replace("&", "&amp;").replace("'", "&#39;").replace("<", "&lt;")
		.replace(">", "&gt;").replace('"', "&#34;"))


def _xnet_escape(s: str) -> str:
	"""The escape of golang.org/x/net/html Token.String."""
	return (s.replace("&", "&amp;").replace("'", "&#39;").replace("<", "&lt;")
		.replace(">", "&gt;").replace('"', "&#34;").replace("\r", "&#13;"))


def fold_eq_prefix(s: str, p: str) -> bool:
	return len(s) >= len(p) and s[: len(p)].lower() == p


def valid_text(s: str) -> str:
	"""R2.1 on a body: invalid UTF-8 (lone surrogates here) and NUL -> U+FFFD."""
	s = s.encode("utf-8", "replace").decode("utf-8")
	return s.replace("\x00", "�")


# ---------------------------------------------------------------------------
# Lookup targets (htmlref)

_HEX = "0123456789ABCDEF"


def enc_target(s: str) -> str:
	"""htmlref.EncTarget: `%`, `#`, controls and a leading `@` percent-encoded."""
	out = []
	for i, c in enumerate(s):
		o = ord(c)
		if c in "%#" or o < 0x20 or o == 0x7F or (c == "@" and i == 0):
			out.append("%" + _HEX[o >> 4] + _HEX[o & 15])
		else:
			out.append(c)
	return "".join(out)


def entry_href(headword: str) -> str:
	return "entry://" + enc_target(headword)


def dec(s: str) -> str:
	"""All-or-nothing percent-decoding to UTF-8 (R5.2)."""
	if "%" not in s:
		return s
	b = s.encode("utf-8")
	out = bytearray()
	hexd = b"0123456789abcdefABCDEF"
	i = 0
	while i < len(b):
		c = b[i]
		if c != 0x25:
			out.append(c)
			i += 1
			continue
		if i + 2 >= len(b) or b[i + 1] not in hexd or b[i + 2] not in hexd:
			return s
		out.append(int(b[i + 1 : i + 3], 16))
		i += 3
	try:
		return out.decode("utf-8")
	except UnicodeDecodeError:
		return s


def canon_ref(ref: str) -> tuple[str, bool]:
	"""htmlref.CanonRef."""
	if fold_eq_prefix(ref, "bword:"):
		rest = ref[len("bword:") :]
		if rest.startswith("//"):
			rest = rest[2:]
	elif fold_eq_prefix(ref, "entry://@"):
		rest = ref[len("entry://") :]
	else:
		return ref, False
	if rest.startswith("@"):
		return "entry:" + rest, True
	return "entry://" + rest, True


def clean_ref(ref: str) -> str:
	"""htmlref.Clean."""
	ref = ref.strip(" \t\n\r\f\v")
	ref = ref.rstrip("\"'`")
	return ref.strip(" \t\n\r\f\v")


# ---------------------------------------------------------------------------
# A tokenizer that segments markup as golang.org/x/net/html does, for the
# edits `html` mode makes to otherwise verbatim bodies.

_RAW_TOKENIZER = frozenset(("iframe", "noembed", "noframes", "noscript", "plaintext", "script",
	"style", "textarea", "title", "xmp"))
_WS = " \t\n\f\r"


class _Tok:
	__slots__ = ("attrs", "end", "kind", "name", "self_closing", "start")

	def __init__(self, kind, start, end, name="", attrs=None, self_closing=False):
		self.kind, self.start, self.end = kind, start, end
		self.name, self.attrs, self.self_closing = name, attrs or [], self_closing


def _tokens(s: str):
	i, n, raw = 0, len(s), ""
	while i < n:
		if raw:
			j = i
			while True:
				j = s.find("</", j)
				if j < 0:
					yield _Tok("text", i, n)
					return
				k = j + 2 + len(raw)
				if s[j + 2 : k].lower() == raw and (k >= n or s[k] in _WS + "/>"):
					break
				j += 2
			if j > i:
				yield _Tok("text", i, j)
			i, raw = j, ""
			continue
		lt = s.find("<", i)
		if lt < 0:
			yield _Tok("text", i, n)
			return
		if lt > i:
			yield _Tok("text", i, lt)
		i = lt
		rest = s[i + 1 : i + 2]
		if s.startswith("<!--", i):
			if s.startswith("<!-->", i):
				end = i + 5
			elif s.startswith("<!--->", i):
				end = i + 6
			else:
				k = s.find("-->", i + 4)
				end = n if k < 0 else k + 3
			yield _Tok("comment", i, end)
			i = end
		elif rest in ("!", "?"):
			k = s.find(">", i + 2)
			end = n if k < 0 else k + 1
			yield _Tok("comment", i, end)
			i = end
		elif rest == "/":
			nxt = s[i + 2 : i + 3]
			if nxt.isascii() and nxt.isalpha():
				k = s.find(">", i + 2)
				end = n if k < 0 else k + 1
				m = re.match(r"[^ \t\n\r\f/>]*", s[i + 2 :])
				yield _Tok("end", i, end, m.group(0).lower())
				i = end
			elif nxt == ">":
				yield _Tok("comment", i, i + 3)
				i += 3
			else:
				k = s.find(">", i + 2)
				end = n if k < 0 else k + 1
				yield _Tok("comment", i, end)
				i = end
		elif rest.isascii() and rest.isalpha():
			tok = _start_tag(s, i)
			yield tok
			i = tok.end
			if tok.name in _RAW_TOKENIZER and not tok.self_closing:
				raw = tok.name
		else:
			yield _Tok("text", i, i + 1)
			i += 1


def _start_tag(s: str, i: int) -> _Tok:
	n = len(s)
	m = re.match(r"[^ \t\n\r\f/>]*", s[i + 1 :])
	name = m.group(0).lower()
	j = i + 1 + len(m.group(0))
	attrs, self_closing = [], False
	while j < n:
		while j < n and s[j] in _WS:
			j += 1
		if j >= n:
			break
		if s[j] == ">":
			return _Tok("start", i, j + 1, name, attrs, self_closing)
		if s[j] == "/":
			j += 1
			if j < n and s[j] == ">":
				self_closing = True
			continue
		self_closing = False
		k = j + 1
		while k < n and s[k] not in _WS + "/>=":
			k += 1
		key = s[j:k].lower()
		j = k
		while j < n and s[j] in _WS:
			j += 1
		val = ""
		if j < n and s[j] == "=":
			j += 1
			while j < n and s[j] in _WS:
				j += 1
			if j < n and s[j] in "\"'":
				q = s[j]
				k = s.find(q, j + 1)
				if k < 0:
					val, j = s[j + 1 :], n
				else:
					val, j = s[j + 1 : k], k + 1
			else:
				k = j
				while k < n and s[k] not in _WS + ">":
					k += 1
				val, j = s[j:k], k
		attrs.append((key, html.unescape(val)))
	return _Tok("start", i, n, name, attrs, self_closing)


_URL_ATTR = frozenset(("src", "href", "data", "poster", "background", "longdesc", "usemap"))


def _is_url_attr(name: str) -> bool:
	if name in _URL_ATTR:
		return True
	i = max(name.rfind("-"), name.rfind(":"))
	return i >= 0 and name[i + 1 :] in _URL_ATTR


def _is_srcset(name: str) -> bool:
	return name in ("srcset", "imagesrcset") or name.endswith(("-srcset", ":srcset"))


_CSS_URL = re.compile(r"""(?i)url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)""")


def _rewrite_css(css: str, f) -> str:
	if "url(" not in css and "URL(" not in css and "Url(" not in css:
		return css

	def one(m):
		ref = (m.group(1) or "") + (m.group(2) or "") + (m.group(3) or "")
		nu = f(clean_ref(ref))
		if nu == ref:
			return m.group(0)
		if any(c in nu for c in " \t()\"'"):
			return "url('" + nu.replace("'", "%27") + "')"
		return "url(" + nu + ")"

	return _CSS_URL.sub(one, css)


def _rewrite_srcset(val: str, f) -> str:
	parts = val.split(",")
	changed = False
	for i, p in enumerate(parts):
		fs = go_fields(p)
		if not fs:
			continue
		nu = f(clean_ref(fs[0]))
		if nu == fs[0]:
			continue
		fs[0] = nu
		parts[i] = " ".join(fs)
		changed = True
	return ", ".join(parts) if changed else val


def canon_links(doc: str) -> str:
	"""htmlref.CanonLinks: every lookup link in its canonical spelling."""
	low = doc.lower()
	if "bword:" not in low and "entry://@" not in low:
		return doc

	def f(u):
		return canon_ref(u)[0]

	out, raw = [], ""
	for t in _tokens(doc):
		if t.kind == "start":
			if not raw and t.name in ("script", "style", "title", "textarea", "iframe", "noscript",
				"noembed", "noframes", "xmp") and not t.self_closing:
				raw = t.name
			changed, attrs = False, []
			for k, v in t.attrs:
				if k == "style":
					nv = _rewrite_css(v, f)
				elif _is_srcset(k):
					nv = _rewrite_srcset(v, f)
				elif _is_url_attr(k):
					nv = f(clean_ref(v))
				else:
					nv = v
				changed = changed or nv != v
				attrs.append((k, nv))
			if changed:
				tag = t.name + "".join(f' {k}="{_xnet_escape(v)}"' for k, v in attrs)
				out.append("<" + tag + ("/>" if t.self_closing else ">"))
			else:
				out.append(doc[t.start : t.end])
		elif t.kind == "end":
			if raw and t.name == raw:
				raw = ""
			out.append(doc[t.start : t.end])
		elif t.kind == "text" and raw == "style":
			out.append(_rewrite_css(doc[t.start : t.end], f))
		else:
			out.append(doc[t.start : t.end])
	return "".join(out)


# ---------------------------------------------------------------------------
# A document tree as golang.org/x/net/html ParseFragment (context <div>)
# builds it, to the extent the converter depends on it.

class Node:
	__slots__ = ("attrs", "children", "data", "kind", "parent", "tag")

	def __init__(self, kind: str, tag: str = "", attrs=None, data: str = "") -> None:
		self.kind, self.tag, self.attrs, self.data = kind, tag, attrs or [], data
		self.children: list[Node] = []
		self.parent: Node | None = None

	def attr(self, key: str):
		for k, v in self.attrs:
			if k == key:
				return v
		return None


_VOID = frozenset(("area", "base", "basefont", "bgsound", "br", "col", "embed", "frame", "hr",
	"img", "input", "keygen", "link", "meta", "param", "source", "track", "wbr"))
_P_CLOSERS = frozenset(("address", "article", "aside", "blockquote", "center", "details", "dialog",
	"dir", "div", "dl", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
	"h4", "h5", "h6", "header", "hgroup", "hr", "main", "menu", "nav", "ol", "p", "pre", "search",
	"section", "summary", "table", "ul", "listing", "plaintext", "xmp", "li", "dd", "dt"))
_HEADINGS = frozenset(("h1", "h2", "h3", "h4", "h5", "h6"))
_SCOPE = frozenset(("applet", "caption", "html", "table", "td", "th", "marquee", "object",
	"template", "#root"))
_TABLE_CTX = frozenset(("table", "tbody", "thead", "tfoot", "tr"))
_TABLE_OK = frozenset(("caption", "colgroup", "col", "tbody", "thead", "tfoot", "tr", "td", "th",
	"script", "style", "template", "form"))
_SVG_MATH = frozenset(("svg", "math"))
_FORMATTING = frozenset(("a", "b", "big", "code", "em", "font", "i", "nobr", "s", "small",
	"strike", "strong", "tt", "u"))
_MARKER_TAGS = frozenset(("td", "th", "caption", "marquee", "object", "applet", "template"))
# Start tags that are inserted without reconstructing the active formatting
# elements first (WHATWG "in body": the block-level and table ones).
_NO_RECONSTRUCT = _P_CLOSERS | frozenset(("form", "table", "tr", "td", "th", "tbody", "thead",
	"tfoot", "caption", "col", "colgroup", "option", "optgroup", "textarea", "iframe", "noembed",
	"noframes", "noscript", "script", "style", "template", "title", "base", "link", "meta"))
_MARKER = None


class _Builder(html.parser.HTMLParser):
	def __init__(self) -> None:
		try:
			super().__init__(convert_charrefs=True, scripting=True)
		except TypeError:  # before Python 3.14
			super().__init__(convert_charrefs=True)
		self.root = Node("el", "#root")
		self.stack = [self.root]
		self.active: list = []  # active formatting elements; None is a marker
		self.lf = None  # pre, listing or textarea just opened: its first LF goes

	@property
	def cur(self) -> Node:
		return self.stack[-1]

	def _in_scope(self, tag: str, extra=frozenset()) -> int:
		for i in range(len(self.stack) - 1, -1, -1):
			t = self.stack[i].tag
			if t == tag:
				return i
			if t in _SCOPE or t in extra:
				return -1
		return -1

	def _pop_to(self, i: int) -> None:
		del self.stack[i:]

	def _close_p(self) -> None:
		i = self._in_scope("p", frozenset(("button",)))
		if i >= 0:
			self._pop_to(i)

	def _table_index(self) -> int:
		for i in range(len(self.stack) - 1, -1, -1):
			if self.stack[i].tag == "table":
				return i
		return -1

	def _insert(self, node: Node) -> None:
		parent = self.cur
		if parent.tag in _TABLE_CTX and not (node.kind == "el" and node.tag in _TABLE_OK) and not (
			node.kind == "text" and node.data.strip(_WS) == ""
		):
			ti = self._table_index()
			if ti > 0:  # foster parenting: before the table
				table = self.stack[ti]
				host = table.parent
				k = host.children.index(table)
				if node.kind == "text" and k > 0 and host.children[k - 1].kind == "text":
					host.children[k - 1].data += node.data
					return
				node.parent = host
				host.children.insert(k, node)
				return
		if node.kind == "text" and parent.children and parent.children[-1].kind == "text":
			parent.children[-1].data += node.data
			return
		node.parent = parent
		parent.children.append(node)

	def _reconstruct(self) -> None:
		"""WHATWG "reconstruct the active formatting elements": a formatting
		element closed only implicitly is opened again for what follows."""
		if not self.active:
			return
		i = len(self.active) - 1
		if self.active[i] is _MARKER or self.active[i] in self.stack:
			return
		while i > 0 and self.active[i - 1] is not _MARKER and self.active[i - 1] not in self.stack:
			i -= 1
		for k in range(i, len(self.active)):
			old = self.active[k]
			node = Node("el", old.tag, list(old.attrs))
			self._insert(node)
			self.stack.append(node)
			self.active[k] = node

	def _clear_to_marker(self) -> None:
		while self.active:
			if self.active.pop() is _MARKER:
				return

	def handle_starttag(self, tag, attrs):
		self.lf = None
		if tag in ("html", "body", "head"):
			return
		if tag == "image":
			tag = "img"
		attrs = [(k, v if v is not None else "") for k, v in attrs]
		if any(n.tag in _SVG_MATH for n in self.stack):
			tag = "#foreign-" + tag
		elif tag in ("tr", "td", "th", "tbody", "thead", "tfoot"):
			if self._table_index() <= 0:
				return  # outside a table these tags are ignored (WHATWG in body)
			self._table_start(tag)
		elif tag in ("caption", "col", "colgroup") and self._table_index() <= 0:
			return
		else:
			if tag in _P_CLOSERS:
				self._close_p()
			if tag in _HEADINGS and self.cur.tag in _HEADINGS:
				self.stack.pop()
			if tag == "li":
				i = self._in_scope("li", frozenset(("ul", "ol")))
				if i >= 0:
					self._pop_to(i)
			if tag in ("dd", "dt"):
				for t in ("dd", "dt"):
					i = self._in_scope(t, frozenset(("dl",)))
					if i >= 0:
						self._pop_to(i)
			if tag == "option" and self.cur.tag == "option":
				self.stack.pop()
			if tag == "a":
				i = self._in_scope("a")
				if i >= 0:
					a = self.stack[i]
					self._pop_to(i)
					if a in self.active:
						self.active.remove(a)
			if tag not in _NO_RECONSTRUCT and not tag.startswith("#foreign-"):
				self._reconstruct()
		node = Node("el", tag, attrs)
		self._insert(node)
		if tag not in _VOID:
			self.stack.append(node)
		if tag in _FORMATTING:
			self.active.append(node)
		elif tag in _MARKER_TAGS:
			self.active.append(_MARKER)
		if tag in ("pre", "listing", "textarea"):
			self.lf = node

	def _table_start(self, tag):
		"""tr, td, th, tbody, thead, tfoot inside a table: clear back to the
		table context the tag belongs in, and imply what it needs."""
		ti = self._table_index()
		if tag in ("tbody", "thead", "tfoot"):
			self._pop_to(ti + 1)
			return
		if tag == "tr":
			i = len(self.stack) - 1
			while i > ti and self.stack[i].tag not in ("tbody", "thead", "tfoot"):
				i -= 1
			self._pop_to(i + 1)
			if self.cur.tag == "table":
				self._implied("tbody")
			return
		# td, th
		i = len(self.stack) - 1
		while i > ti and self.stack[i].tag != "tr":
			i -= 1
		if self.stack[i].tag == "tr":
			self._pop_to(i + 1)
			return
		i = len(self.stack) - 1
		while i > ti and self.stack[i].tag not in ("tbody", "thead", "tfoot"):
			i -= 1
		self._pop_to(i + 1)
		if self.cur.tag == "table":
			self._implied("tbody")
		self._implied("tr")

	def _implied(self, tag):
		node = Node("el", tag)
		node.parent = self.cur
		self.cur.children.append(node)
		self.stack.append(node)

	def handle_startendtag(self, tag, attrs):
		self.handle_starttag(tag, attrs)  # a `/` closes nothing in HTML

	def handle_endtag(self, tag):
		self.lf = None
		if tag in ("html", "body", "head"):
			return
		if tag in _FORMATTING:
			# The adoption agency, reduced: close the element if it is open,
			# and forget it either way.
			for j in range(len(self.active) - 1, -1, -1):
				e = self.active[j]
				if e is _MARKER:
					break
				if e.tag == tag:
					if e in self.stack:
						self._pop_to(self.stack.index(e))
					del self.active[j]
					return
			return
		if tag == "br":
			self.handle_starttag("br", [])
			return
		if tag == "p" and self._in_scope("p", frozenset(("button",))) < 0:
			self._insert(Node("el", "p"))
			return
		extra = frozenset(("ul", "ol")) if tag == "li" else frozenset()
		i = self._in_scope(tag, extra)
		if i < 0 and any(n.tag == "#foreign-" + tag for n in self.stack):
			for j in range(len(self.stack) - 1, 0, -1):
				if self.stack[j].tag == "#foreign-" + tag:
					i = j
					break
		if i > 0:
			if tag in _MARKER_TAGS:
				self._clear_to_marker()
			self._pop_to(i)

	def handle_data(self, data):
		if self.lf is not None:
			if self.lf is self.cur and not self.lf.children and data.startswith("\n"):
				data = data[1:]
			self.lf = None
			if not data:
				return
		self._reconstruct()
		self._insert(Node("text", data=data))

	def handle_comment(self, data):
		self._insert(Node("comment"))


def parse_fragment(src: str) -> list[Node]:
	b = _Builder()
	b.feed(src)
	b.close()
	return b.root.children


# ---------------------------------------------------------------------------
# `clean` mode (R6.6-R6.7)

_DROPPED = frozenset(("script", "style", "template", "iframe", "noscript", "noembed", "noframes",
	"input", "select", "textarea", "button", "embed", "head", "meta", "link", "title", "base",
	"frame", "frameset", "canvas", "map"))
_UNWRAP = frozenset(("p", "div", "section", "article", "main", "header", "footer", "aside", "nav",
	"figure", "figcaption", "address", "center", "hgroup", "fieldset", "legend", "dl", "dt", "dd",
	"form", "body", "html", "caption", "li", "tr", "td", "th", "thead", "tbody", "tfoot", "summary",
	"menu", "dir", "listing", "xmp", "plaintext", "search", "dialog", "option", "optgroup"))
_BLOCK = _UNWRAP | frozenset(("h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "blockquote", "pre",
	"hr", "table", "details"))
MAX_NEST = 16

K_PARA, K_LIST, K_OTHER = 0, 1, 2


class Block:
	__slots__ = ("interrupts", "kind", "list", "md")

	def __init__(self, md, kind, lst="", interrupts=False):
		self.md, self.kind, self.list, self.interrupts = md, kind, lst, interrupts


def _foreign(n: Node) -> bool:
	return n.kind == "el" and (n.tag.startswith("#foreign-") or n.tag in _SVG_MATH)


def media_src(n: Node) -> str:
	def attr(n, k):
		v = n.attr(k)
		return go_trim_space(v) if v is not None else ""

	if n.tag in ("audio", "video", "source"):
		s = attr(n, "src")
		if s:
			return s
		for k in n.children:
			if k.kind == "el" and k.tag == "source":
				s = attr(k, "src")
				if s:
					return s
	elif n.tag == "object":
		t = attr(n, "type").lower()
		if t.startswith(("audio/", "video/")):
			return attr(n, "data")
	return ""


def dropped(n: Node) -> bool:
	if n.kind == "comment":
		return True
	if n.kind != "el":
		return False
	if _foreign(n):
		return True
	if n.tag in _DROPPED:
		return True
	if n.tag == "object":
		return media_src(n) == ""
	return False


def block_elem(n: Node) -> bool:
	return n.kind == "el" and not _foreign(n) and n.tag in _BLOCK


# The dictionary's display table (R6.6): class name -> one of these, as
# wudict's htmlref.ParseCSS derives it from the stylesheets articles link.
DISPLAY_UNSET, DISPLAY_NONE, DISPLAY_INLINE, DISPLAY_BLOCK = 0, 1, 2, 3


def display(st, n: Node) -> int:
	"""The layout n's classes are given: the highest of its classes'."""
	if not st or n.kind != "el" or _foreign(n):
		return DISPLAY_UNSET
	best = DISPLAY_UNSET
	for c in re.split("[ \t\n\r\f]+", n.attr("class") or ""):
		if c:
			best = max(best, st.get(c, DISPLAY_UNSET) & _DISPLAY_MASK)
	return best


_DISPLAY_MASK, _GAP_BIT = 0x0F, 0x80  # Go: htmlref displayMask, gapBit


def gap(st, n: Node) -> bool:
	"""An element the stylesheet sets apart from its neighbours: a space."""
	if not st or n.kind != "el" or _foreign(n):
		return False
	return any(st.get(c, 0) & _GAP_BIT for c in re.split("[ \t\n\r\f]+", n.attr("class") or "") if c)


def skipped(st, n: Node) -> bool:
	return dropped(n) or display(st, n) == DISPLAY_NONE


def styled_block(st, n: Node) -> bool:
	return not block_elem(n) and display(st, n) == DISPLAY_BLOCK


# Elements the inline writer turns into markup of its own (Go: formatting); a
# link only with a destination.
_MARKUP = frozenset(("em", "i", "strong", "b", "sup", "sub", "u", "small", "del", "s", "strike",
	"ins", "code", "kbd", "samp", "tt", "img", "audio", "video", "source", "object"))


def formatting(n: Node) -> bool:
	if n.tag == "a":
		return link_href(n) != ""
	return n.tag in _MARKUP


def text_content(n: Node) -> str:
	out = []

	def walk(n):
		if n.kind == "text":
			out.append(n.data)
		elif n.kind == "el":
			if n.tag == "br":
				out.append("\n")
				return
			if dropped(n):
				return
			for k in n.children:
				walk(k)

	walk(n)
	return "".join(out)


def longest_run(s: str, c: str) -> int:
	best = cur = 0
	for x in s:
		if x == c:
			cur += 1
			best = max(best, cur)
		else:
			cur = 0
	return best


def shortest_absent(t: str) -> int:
	runs = {len(m) for m in re.findall("`+", t)}
	n = 1
	while n in runs:
		n += 1
	return n


def join_blocks(bs) -> str:
	return "\n\n".join(b.md for b in bs)


def prefix_lines(s: str, p: str, empty: str) -> str:
	return "\n".join(empty if line == "" else p + line for line in s.split("\n"))


def list_mark(md: str) -> str:
	j = 0
	while j < len(md) and "0" <= md[j] <= "9":
		j += 1
	return md[j] if j < len(md) else ""


def alternate(md: str) -> str:
	frm = list_mark(md)
	to = {"-": "*", "*": "-", ".": ")", ")": "."}.get(frm, "")
	lines = md.split("\n")
	for i, line in enumerate(lines):
		if line == "" or line[0] == " ":
			continue
		j = 0
		while j < len(line) and "0" <= line[j] <= "9":
			j += 1
		if j < len(line) and line[j] == frm:
			lines[i] = line[:j] + to + line[j + 1 :]
	return "\n".join(lines)


def code_block(pre: Node) -> str:
	text = text_content(pre)
	if text.endswith("\n"):
		text = text[:-1]
	info = ""
	for k in pre.children:
		if k.kind == "el" and k.tag == "code":
			for key, val in k.attrs:
				if key == "class":
					for cl in go_fields(val):
						if cl.startswith("language-") and len(cl) > 9 and not any(c in cl[9:] for c in "`~"):
							info = cl[9:]
	fence = "`" * max(3, longest_run(text, "`") + 1)
	lines = [ln.rstrip("\r") for ln in text.split("\n")] if text else []
	return fence + info + "\n" + "\n".join([*lines, fence])


def cell_align(c: Node) -> str:
	for k, v in c.attrs:
		v = go_trim_space(v).lower()
		if k == "align":
			if v in ("left", "center", "right"):
				return v
		elif k == "style":
			for decl in v.split(";"):
				key, sep, val = decl.partition(":")
				if sep and go_trim_space(key) == "text-align":
					val = go_trim_space(val)
					if val in ("left", "center", "right"):
						return val
	return ""


def table(t: Node, st=None) -> str:
	rows = []

	def walk(n):
		for k in n.children:
			if k.kind != "el" or skipped(st, k):
				continue
			if k.tag == "tr":
				rows.append([c for c in k.children if c.kind == "el" and c.tag in ("td", "th")])
			elif k.tag in ("thead", "tbody", "tfoot"):
				walk(k)

	walk(t)
	cols = max((len(r) for r in rows), default=0)
	if cols == 0:
		return ""

	def line(r):
		out = "|"
		for i in range(cols):
			md = ""
			if i < len(r) and not skipped(st, r[i]):
				w = Inline(IN_CELL, st)
				w.nodes(r[i].children)
				md = w.done()
			out += " |" if md == "" else " " + md + " |"
		return out

	out = [line(rows[0])]
	delim = "|"
	for i in range(cols):
		a = cell_align(rows[0][i]) if i < len(rows[0]) else ""
		delim += " " + {"": "---", "left": ":--", "center": ":-:", "right": "--:"}[a] + " |"
	out.append(delim)
	out.extend(line(r) for r in rows[1:])
	return "\n".join(out)


class Converter:
	def __init__(self, st=None) -> None:
		self.st = st
		self.holds: dict[int, bool] = {}

	def holds_block(self, n: Node) -> bool:
		"""A block - by tag or by the stylesheet - among n's descendants,
		outside anything skipped."""
		v = self.holds.get(id(n))
		if v is not None:
			return v
		v = False
		for k in n.children:
			if k.kind == "el" and not skipped(self.st, k):
				v = block_elem(k) or styled_block(self.st, k) or self.holds_block(k)
				if v:
					break
		self.holds[id(n)] = v
		return v

	def flow(self, nodes, depth: int) -> list[Block]:
		out: list[Block] = []
		para = [Inline(IN_PARA, self.st)]

		def flush():
			md = para[0].done()
			if md:
				out.append(Block(md, K_PARA))
			para[0] = Inline(IN_PARA, self.st)

		def add(b):
			if b.kind == K_LIST and out:
				p = out[-1]
				if p.kind == K_LIST and p.list == b.list and list_mark(p.md) == list_mark(b.md):
					b.md = alternate(b.md)
			out.append(b)

		def walk(nodes):
			for n in nodes:
				if skipped(self.st, n):
					continue
				if styled_block(self.st, n) and formatting(n):
					flush()
					para[0].node(n)
					flush()
				elif styled_block(self.st, n):
					flush()
					for b in self.flow(n.children, depth):
						add(b)
				elif not block_elem(n) and not formatting(n) and n.kind == "el" and self.holds_block(n):
					walk(n.children)  # block-in-inline: its content joins this flow
				elif not block_elem(n):
					para[0].node(n)
				elif n.tag in ("ul", "ol", "blockquote") and depth >= MAX_NEST or n.tag in _UNWRAP:
					flush()
					for b in self.flow(n.children, depth):
						add(b)
				else:
					flush()
					b = self.block_of(n, depth)
					if b is not None:
						add(b)

		walk(nodes)
		flush()
		return out

	def block_of(self, n: Node, depth: int):
		if n.tag in _HEADINGS:
			w = Inline(IN_HEADING, self.st)
			w.nodes(n.children)
			t = w.done()
			if not t:
				return None
			j = len(t.rstrip("#"))
			if j < len(t) and (j == 0 or t[j - 1] == " "):
				t = t[:j] + "\\" + t[j:]
			return Block("#" * max(int(n.tag[1]), 3) + " " + t, K_OTHER)
		if n.tag == "hr":
			return Block("***", K_OTHER)
		if n.tag == "pre":
			return Block(code_block(n), K_OTHER)
		if n.tag == "blockquote":
			inner = join_blocks(self.flow(n.children, depth + 1))
			return Block(prefix_lines(inner, "> ", ">"), K_OTHER) if inner else None
		if n.tag in ("ul", "ol"):
			md, interrupts = self.list(n, depth + 1)
			return Block(md, K_LIST, n.tag, interrupts) if md else None
		if n.tag == "table":
			md = table(n, self.st)
			return Block(md, K_OTHER) if md else None
		if n.tag == "details":
			return Block(self.details(n, depth), K_OTHER)
		return None

	def list(self, n: Node, depth: int):
		groups = []
		for k in n.children:
			if skipped(self.st, k) or (k.kind == "text" and go_trim_space(k.data) == ""):
				continue
			elif k.kind == "el" and k.tag == "li" and not _foreign(k):
				groups.append(list(k.children))
			elif not groups:
				groups.append([k])
			else:
				groups[-1].append(k)
		items = [bs for bs in (self.flow(g, depth) for g in groups) if bs]
		if not items:
			return "", False
		tight = True
		for it in items:
			for b in it[1:]:
				if b.kind != K_LIST or it[0].kind != K_PARA or not b.interrupts:
					tight = False
		start = 1
		if n.tag == "ol":
			for k, v in n.attrs:
				if k == "start":
					v = go_trim_space(v)
					if re.fullmatch(r"[+-]?[0-9]+", v):
						x = int(v)
						if 0 <= x <= 999999999:
							start = x
		sep = "\n" if tight else "\n\n"
		out = []
		for i, it in enumerate(items):
			marker = str(start + i) + "." if n.tag == "ol" else "-"
			body = sep.join(b.md for b in it)
			pad = " " * (len(marker) + 1)
			lines = body.split("\n")
			for j in range(1, len(lines)):
				if lines[j]:
					lines[j] = pad + lines[j]
			out.append(marker + " " + "\n".join(lines))
		return sep.join(out), n.tag == "ul" or start == 1

	def details(self, n: Node, depth: int) -> str:
		summary, rest = "", []
		for k in n.children:
			if k.kind == "el" and k.tag == "summary" and summary == "":
				summary = " ".join(go_fields(text_content(k)))
				continue
			rest.append(k)
		out = "<details>\n"
		if summary:
			out += "<summary>" + go_html_escape(summary) + "</summary>\n"
		inner = join_blocks(self.flow(rest, depth))
		if inner:
			out += "\n" + inner + "\n\n"
		return out + "</details>"


IN_PARA, IN_HEADING, IN_CELL = 0, 1, 2
_ESCAPED = frozenset("\\`*_[]<>&~|")


def line_start_escape(s: str, off: int) -> int:
	if off >= len(s):
		return -1
	if s[off] in "#+-=:":
		return off
	j = off
	while j < len(s) and "0" <= s[j] <= "9":
		j += 1
	if 1 <= j - off <= 9 and j < len(s) and s[j] in ".)":
		k = j + 1
		if k == len(s) or s[k] in " \t\n":
			return j
	return -1


def marked(c: str) -> bool:
	cat = unicodedata.category(c)
	return cat[0] in "LM" or cat == "Nd"


def has_delimiter(md: str) -> bool:
	i = 0
	while i < len(md):
		if md[i] == "\\":
			i += 2
			continue
		if md[i] == "*":
			return True
		i += 1
	return False


class Inline:
	def __init__(self, mode: int, st=None) -> None:
		self.st = st
		self.mode = mode
		self.b: list[str] = []
		self.n = 0  # length of the text in b
		self.line_start = True
		self.starts: list[int] = []
		self.space = False
		self.brk = False
		self.lead = False  # space before the first content: the parent writes it

	def _write(self, s: str) -> None:
		self.b.append(s)
		self.n += len(s)

	def value(self) -> str:
		s = "".join(self.b)
		self.b = [s]
		return s

	def last(self) -> str:
		for part in reversed(self.b):
			if part:
				return part[-1]
		return ""

	def done(self) -> str:
		s = self.value()
		for off in reversed(self.starts):
			at = line_start_escape(s, off)
			if at >= 0:
				s = s[:at] + "\\" + s[at:]
		return s

	def spaced(self) -> None:
		self.space = True
		if self.n == 0:
			self.lead = True

	def hoist(self, sub: "Inline", before: bool) -> None:
		"""The space at an edge of an element's content goes outside its markup."""
		if sub.lead if before else sub.space:
			self.spaced()

	def pending(self) -> None:
		if self.n == 0:
			self.space = self.brk = False
			return
		if self.brk:
			if self.mode == IN_PARA:
				self._write("<br>\n" if self.last() == "\\" else "\\\n")
				self.line_start = True
			elif self.mode == IN_CELL:
				self._write("<br>")
			else:
				self._write(" ")
		elif self.space:
			self._write(" ")
		self.space = self.brk = False

	def syntax(self, s: str) -> None:
		self.pending()
		self._write(s)
		self.line_start = False

	def text(self, s: str) -> None:
		for c in s:
			if c in _HSPACE:
				self.spaced()
				continue
			self.pending()
			if self.line_start and self.mode == IN_PARA:
				self.starts.append(self.n)
			self._write("\\" + c if c in _ESCAPED else c)
			self.line_start = False

	def nodes(self, ns) -> None:
		for n in ns:
			self.node(n)

	def sub(self) -> "Inline":
		s = Inline(self.mode, self.st)
		s.line_start = False
		return s

	def node(self, n: Node) -> None:
		if n.kind == "text":
			self.text(n.data)
			return
		if n.kind != "el" or skipped(self.st, n) or _foreign(n):
			return
		if styled_block(self.st, n):
			if self.n > 0:
				self.brk = True
			self._element(n)
			self.brk = True
			return
		if gap(self.st, n):
			self.spaced()
			self._element(n)
			self.space = True
			return
		self._element(n)

	def _element(self, n: Node) -> None:
		tag = n.tag
		if tag == "br":
			if self.n > 0:
				self.brk = True
		elif tag in ("em", "i", "strong", "b"):
			d, name = ("**", "strong") if tag in ("strong", "b") else ("*", "em")
			sub = self.sub()
			sub.nodes(n.children)
			inner = sub.done()
			self.hoist(sub, True)
			if not inner:
				self.hoist(sub, False)
				return
			self.pending()
			if marked(inner[0]) and marked(inner[-1]) and self.last() != "*" and not has_delimiter(inner):
				self.syntax(d + inner + d)
			else:
				self.syntax(f"<{name}>{inner}</{name}>")
			self.hoist(sub, False)
		elif tag in ("sup", "sub", "u", "small", "del", "s", "strike", "ins"):
			name = "del" if tag in ("s", "strike") else tag
			sub = self.sub()
			sub.nodes(n.children)
			self.hoist(sub, True)
			inner = sub.done()
			if inner:
				self.syntax(f"<{name}>{inner}</{name}>")
			self.hoist(sub, False)
		elif tag in ("code", "kbd", "samp", "tt"):
			t = " ".join(fields_hspace(text_content(n)))
			if not t:
				return
			self.pending()
			if self.last() == "`":
				self.syntax("<code>")
				self.text(t)
				self.syntax("</code>")
				return
			if self.mode == IN_CELL:
				t = t.replace("|", "\\|")
			f = "`" * shortest_absent(t)
			if t.startswith("`") or t.endswith("`"):
				t = " " + t + " "
			self.syntax(f + t + f)
		elif tag == "a":
			self.link(n)
		elif tag == "img":
			self.image(n)
		elif tag in ("audio", "video", "source", "object"):
			s = media_src(n)
			if s:
				self.bang_guard()
				self.syntax("[▶](" + self.cell_safe(dest(link_target(s)), "") + ")")
		else:
			if block_elem(n) and self.n > 0:
				self.brk = True
			self.nodes(n.children)
			if block_elem(n):
				self.brk = True

	def bang_guard(self) -> None:
		if self.space or self.brk or self.n == 0:
			return
		s = self.value()
		if s[-1] == "!" and (len(s) < 2 or s[-2] != "\\"):
			self.b = [s[:-1] + "\\!"]
			self.n += 1

	def cell_safe(self, d: str, t: str) -> str:
		if self.mode != IN_CELL:
			return d + t
		return d.replace("|", "%7C") + t.replace("|", "\\|")

	def link(self, n: Node) -> None:
		href = link_href(n)
		if not href:
			self.nodes(n.children)
			return
		sub = self.sub()
		sub.nodes(n.children)
		text = sub.done()
		self.hoist(sub, True)
		self.bang_guard()
		self.syntax("[" + text + "](" + self.cell_safe(dest(href), title(n)) + ")")
		self.hoist(sub, False)

	def image(self, n: Node) -> None:
		src = link_target(n.attr("src") or "")
		alt = " ".join(fields_hspace(n.attr("alt") or ""))
		alt = alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
		if self.mode == IN_CELL:
			alt = alt.replace("|", "\\|")
		if not src:
			if alt:
				self.text(alt)
			return
		self.bang_guard()
		self.syntax("![" + alt + "](" + self.cell_safe(dest(src), title(n)) + ")")


def link_href(n: Node) -> str:
	"""The canonical destination of a link, or "" when it has none."""
	href = n.attr("href") or ""
	ref = cross_ref(href)
	return ref if ref is not None else link_target(href)


def title(n: Node) -> str:
	t = n.attr("title")
	if t is None:
		return ""
	t = " ".join(fields_hspace(t))
	if not t:
		return ""
	return ' "' + t.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Destinations (R6.9)

_URL_KEPT = frozenset("!#$%&'()*+,-./0123456789:;=?@ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz~")


def enc_some(s: str, chars: str) -> str:
	out = []
	for c in s:
		o = ord(c)
		if o < 0x20 or o == 0x7F or c in chars:
			out.append("%" + _HEX[o >> 4] + _HEX[o & 15])
		else:
			out.append(c)
	return "".join(out)


def enc_url(s: str) -> str:
	out = []
	for byte in s.encode("utf-8"):
		c = chr(byte)
		if byte < 0x80 and c in _URL_KEPT:
			out.append(c)
		else:
			out.append("%" + _HEX[byte >> 4] + _HEX[byte & 15])
	return "".join(out)


def lookup_rest(href: str):
	for p in ("entry:", "bword:", "d:", "x:"):
		if fold_eq_prefix(href, p):
			rest = href[len(p) :]
			if p in ("entry:", "bword:") and rest.startswith("//"):
				rest = rest[2:]
			return rest
	return None


def scheme_ref(v: str) -> bool:
	for i, c in enumerate(v):
		if c.isascii() and c.isalpha():
			continue
		if i > 0 and (c.isascii() and c.isdigit() or c in "+.-"):
			continue
		return i > 0 and c == ":"
	return False


def entry_ref(rest: str) -> str:
	target, sep, frag = rest.partition("#")
	if len(target) > 1 and target[0] == "@":
		out = "entry:@" + enc_target(dec(target[1:]))
	else:
		out = "entry://" + enc_target(dec(target).strip(" \t"))
	if sep:
		out += "#" + enc_some(dec(frag), "%")
	return out


# wudict's dict.IsAssetName list: an href with one of these extensions names
# a file; any other relative href is a headword (R6.9).
_ASSET_EXT = frozenset((".css", ".js", ".html", ".htm", ".png", ".jpg", ".jpeg", ".gif", ".webp",
	".svg", ".bmp", ".ico", ".avif", ".mp3", ".ogg", ".oga", ".wav", ".spx", ".m4a", ".opus", ".flac",
	".aac", ".mp4", ".webm", ".ogv", ".mov", ".m4v", ".3gp", ".avi", ".wmv", ".mkv", ".mpg", ".mpeg",
	".asf", ".flv", ".pcx", ".dcx", ".wmf", ".emf", ".tif", ".tiff", ".pdf", ".woff", ".woff2", ".ttf",
	".otf", ".eot", ".json", ".xml", ".txt"))


def is_asset_name(ref: str) -> bool:
	m = re.search("[?#]", ref)
	if m:
		ref = ref[: m.start()]
	for i in range(len(ref) - 1, -1, -1):
		if ref[i] == "/":
			break
		if ref[i] == ".":
			return ref[i:].lower() in _ASSET_EXT
	return False


def cross_ref(v: str):
	"""The lookup link a relative link href stands for (R6.9), or None."""
	v = v.strip(" \t\n\r\f")
	if v == "" or v[0] in "#?" or scheme_ref(v) or v.startswith("//") or is_asset_name(v):
		return None
	if dec(v.partition("#")[0]).strip(" \t") == "":
		return None
	return entry_ref(v)


def link_target(v: str) -> str:
	v = v.strip(" \t\n\r\f")
	rest = lookup_rest(v)
	if rest is not None:
		return entry_ref(rest)
	for p in ("sound://", "file://"):
		if fold_eq_prefix(v, p):
			v = v[len(p) :]
			break
	if scheme_ref(v) or v.startswith("//"):
		return enc_url(v)
	m = re.search("[?#]", v)
	path, suffix = (v[: m.start()], v[m.start() :]) if m else (v, "")
	return enc_some(dec(path), "%#?") + enc_url(suffix)


def dest(v: str) -> str:
	angle = v == "" or any(ord(c) <= 0x20 or ord(c) == 0x7F for c in v)
	if angle:
		return "<" + (v.replace("\\", "\\\\").replace("<", "\\<").replace(">", "\\>").replace("&", "\\&")
			.replace("\n", "%0A").replace("\r", "%0D")) + ">"
	return v.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("<", "\\<").replace("&", "\\&")


def splits_entry(md: str) -> bool:
	"""A top-level level-1 or level-2 heading: it would end the entry (R3.5)."""
	for t in _parser().parse(md):
		if t.level == 0 and t.type == "heading_open" and t.tag in ("h1", "h2"):
			return True
	return False


def clean_body(src: str, st=None) -> str:
	"""`clean` mode (R6.6-R6.7); raises CleanError. st is the dictionary's
	display table ({class: DISPLAY_*}), None without a stylesheet."""
	try:
		md = join_blocks(Converter(st).flow(parse_fragment(valid_text(src)), 0))
	except RecursionError as e:
		raise CleanError("the article", f"internal error: {e}") from e
	if "\n" not in md and md.startswith("see:"):
		md = "see\\:" + md[len("see:") :]
	if md and splits_entry(md):
		raise CleanError("a heading", "it would read as the start of an entry")
	return md


# ---------------------------------------------------------------------------
# `html` mode (R6.5)

_TYPE6 = frozenset(("address", "article", "aside", "base", "basefont", "blockquote", "body",
	"caption", "center", "col", "colgroup", "dd", "details", "dialog", "dir", "div", "dl", "dt",
	"fieldset", "figcaption", "figure", "footer", "form", "frame", "frameset", "h1", "h2", "h3",
	"h4", "h5", "h6", "head", "header", "hr", "html", "iframe", "legend", "li", "link", "main",
	"menu", "menuitem", "nav", "noframes", "ol", "optgroup", "option", "p", "param", "search",
	"section", "summary", "table", "tbody", "td", "tfoot", "th", "thead", "title", "tr", "track",
	"ul"))


def _wrapped(s: str) -> bool:
	only = None
	for n in parse_fragment(s):
		if n.kind == "text" and n.data.strip(" \t\n\f") == "":
			continue
		if only is None and n.kind == "el" and not _foreign(n) and n.tag in _TYPE6:
			only = n
			continue
		return False
	if only is None:
		return False
	tag = "<" + only.tag
	if len(s) <= len(tag) or s[: len(tag)].lower() != tag:
		return False
	return s[len(tag)] in " \t\n>/"


def _no_blank_lines(s: str) -> str:
	if not any(line.strip(" \t") == "" for line in s.split("\n")):
		return s
	keep, depth = [], 0
	for t in _tokens(s):
		if t.kind in ("start", "end") and t.name in ("pre", "textarea", "listing"):
			if t.kind == "start":
				depth += 1
			elif depth > 0:
				depth -= 1
		elif t.kind == "text" and depth > 0:
			keep.append((t.start, t.end))

	def in_text(at):
		return any(a <= at < b for a, b in keep)

	out, at = [], 0
	while at < len(s):
		end = s.find("\n", at)
		line = s[at:] if end < 0 else s[at:end]
		nxt = at + len(line) + 1
		if line.strip(" \t") != "":
			out.append(line)
			if end >= 0:
				out.append("\n")
		elif in_text(at) and end >= 0:
			out.append(line + "&#10;")
		at = nxt
	return "".join(out).rstrip("\n")


def html_body(src: str) -> str:
	"""`html` mode (R6.5)."""
	s = canon_links(valid_text(src)).strip(" \t\r\n\f")
	if not s:
		return ""
	s = _no_blank_lines(s.replace("\r\n", "\n").replace("\r", "\n"))
	if not _wrapped(s):
		s = "<div>\n" + s + "\n</div>"
	return s


# ---------------------------------------------------------------------------
# Names and header keys (R6.2-R6.3)

def repair_name(s: str) -> str:
	"""R6.2 on a name or value."""
	s = s.encode("utf-8", "replace").decode("utf-8")
	out = []
	for c in s:
		o = ord(c)
		if c in "\r\n\t":
			out.append(" ")
		elif o < 0x20 or o == 0x7F:
			continue
		else:
			out.append(c)
	return "".join(out).strip(" ")


def heading_esc(s: str) -> str:
	t = "".join("\\" + c if c in "\\`*_[]<>&~" else c for c in s)
	j = len(t.rstrip("#"))
	if j < len(t) and (j == 0 or t[j - 1] == " "):
		t = t[:j] + "\\" + t[j:]
	return t


def field_key(name: str) -> str:
	out, dash = [], False
	for c in name.lower():
		if "a" <= c <= "z" or "0" <= c <= "9":
			if dash and out:
				out.append("-")
			dash = False
			out.append(c)
		else:
			dash = True
	k = "".join(out)
	if k and (k[0].isdigit() or k in ("wudict", "from", "to", "meta")):
		k = "x-" + k
	return k


# ---------------------------------------------------------------------------
# The reader (§3), in chunks cut where the parser confirms a heading group
# starts - the same cuts, for the same reason, as the Go reader.

CHUNK_SIZE = 1 << 20
_PARSER = None


def _parser():
	global _PARSER
	if _PARSER is None:
		from markdown_it import MarkdownIt

		_PARSER = MarkdownIt("commonmark", {"html": True}).enable("table")
	return _PARSER


def decode(b: bytes) -> str:
	"""R2.1."""
	if b.startswith(b"\xef\xbb\xbf"):
		b = b[3:]
	s = b.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
	return s.replace("\x00", "�")


def load(path: str) -> str:
	low = path.lower()
	opener = gzip.open if low.endswith((".gz", ".dz")) else open
	with opener(path, "rb") as f:
		return decode(f.read())


def title_line(line: str) -> bool:
	return len(line) > 2 and line[0] == "#" and line[1] in " \t" and line[1:].strip(" \t") != ""


def version_line(line: str) -> bool:
	k = "wudict"
	if len(line) < len(k) or line[: len(k)].lower() != k:
		return False
	rest = line[len(k) :].lstrip(" \t")
	return rest.startswith(":")


def parse_field(line: str):
	m = re.match(r"([a-z][a-z0-9-]*):[ \t](.*)\Z", line, re.S)
	if not m or m.group(2).strip(" \t") == "":
		return None
	return m.group(1), m.group(2).strip(" \t")


def check_version(line: str) -> None:
	if not version_line(line):
		raise FormatError("E-format", "line 2 must be `wudict: 1`, the version of the format")
	kv = parse_field(line)
	if not kv or kv[0] != "wudict":
		raise FormatError("E-version", "line 2 must be `wudict: 1`")
	major, dot, minor = kv[1].partition(".")
	if not re.fullmatch("[0-9]+", major) or dot and not re.fullmatch("[0-9]+", minor):
		raise FormatError("E-version", f"line 2 must be `wudict: 1`, not {kv[1]!r}")
	if major.lstrip("0") != "1":
		raise FormatError("E-version", f"version {kv[1]} is not supported; this reader reads `wudict: 1`")


def _blocks(tokens):
	"""The top-level blocks of a token stream, as (first, last) index pairs."""
	out, i = [], 0
	while i < len(tokens):
		t = tokens[i]
		if t.level == 0 and t.nesting == 1:
			j = i + 1
			depth = 1
			while j < len(tokens) and depth:
				depth += tokens[j].nesting
				j += 1
			out.append((i, j - 1))
			i = j
		elif t.level == 0 and t.nesting == 0:
			out.append((i, i))
			i += 1
		else:
			i += 1
	return out


def _is_h2(tokens, blk) -> bool:
	t = tokens[blk[0]]
	return t.type == "heading_open" and t.tag == "h2"


def _plain(children) -> str:
	out = []
	for c in children or ():
		if c.type in ("text", "code_inline"):
			out.append(c.content)
		elif c.type in ("softbreak", "hardbreak"):
			out.append(" ")
		elif c.type == "html_inline":
			continue
		elif c.children:
			out.append(_plain(c.children))
	return "".join(out)


def _heading_text(tokens, blk) -> str:
	return _plain(tokens[blk[0] + 1].children).strip(" \t")


class Document:
	"""A dictionary read from text: meta, entries, and each entry's body
	rendered on demand."""

	def __init__(self, text: str) -> None:
		self.text = text
		lines = text.split("\n", 2)
		if not title_line(lines[0]):
			raise FormatError("E-format", "line 1 must be `# ` and the dictionary title")
		check_version(lines[1] if len(lines) > 1 else "")
		self.warnings: list[str] = []
		self.meta = {"name": "", "from": "", "to": "", "fields": [], "description": ""}
		self.refs: dict = {}
		self.cands = [m.start() for m in re.finditer(r"(?m)^##(?=[ \t]|$)", text)]
		self.chunks: list[tuple[int, int, int]] = []  # start, end, first entry
		self.lines: list[int] = []  # line number of each chunk's start
		self.entries: list[dict] = []
		with_defs = "]:" in text
		start, line = 0, 1
		while start < len(text):
			end, window, tokens, env, stop = self._next_chunk(start)
			self.chunks.append((start, end, len(self.entries)))
			self.lines.append(line)
			line += window.count("\n", 0, end - start)
			if with_defs:
				for k, v in env.get("references", {}).items():
					self.refs.setdefault(k, v)
			else:
				self._scan(len(self.chunks) - 1, window, tokens, stop)
			start = end
		if with_defs:
			for i, (s, e, _) in enumerate(self.chunks):
				self.chunks[i] = (s, e, len(self.entries))
				tokens, _ = self._parse(text[s:e])
				self._scan(i, text[s:e], tokens, None)
		self._fold()

	def _parse(self, window: str):
		env = {"references": dict(self.refs)} if self.refs else {}
		return _parser().parse(window, env), env

	def _next_chunk(self, start: int):
		text = self.text
		frm = start + CHUNK_SIZE
		k = bisect.bisect_left(self.cands, max(frm, start + 1))
		while k < len(self.cands):
			c = self.cands[k]
			le = text.find("\n", c)
			le = len(text) if le < 0 else le + 1
			window = text[start:le]
			tokens, env = self._parse(window)
			blocks = _blocks(tokens)
			line = window.count("\n", 0, c - start)
			if blocks:
				last = blocks[-1]
				t = tokens[last[0]]
				if t.type == "heading_open" and t.tag == "h2" and t.markup == "##" and t.map and t.map[0] == line:
					g = len(blocks) - 1
					while g > 0 and _is_h2(tokens, blocks[g - 1]):
						g -= 1
					if g > 0:
						gl = tokens[blocks[g][0]].map[0]
						cut = start + _line_offset(window, gl)
						if cut > start:
							return cut, window, tokens, env, blocks[g][0]
			k = bisect.bisect_left(self.cands, max(c + 1, start + 2 * (c - start)))
		window = text[start:]
		tokens, env = self._parse(window)
		return len(text), window, tokens, env, None

	def _groups(self, tokens, first_chunk: bool, stop):
		blocks = _blocks(tokens)
		if stop is not None:
			blocks = [b for b in blocks if b[0] < stop]
		i = 0
		if first_chunk:
			i = 2
			while i < len(blocks) and not _is_h2(tokens, blocks[i]):
				i += 1
		groups = []
		while i < len(blocks):
			names, seen, at = [], set(), blocks[i]
			while i < len(blocks) and _is_h2(tokens, blocks[i]):
				t = _heading_text(tokens, blocks[i])
				if t and t not in seen:
					seen.add(t)
					names.append(t)
				i += 1
			body = []
			while i < len(blocks) and not _is_h2(tokens, blocks[i]):
				body.append(blocks[i])
				i += 1
			groups.append((names, at, body))
		return blocks, groups

	def _scan(self, ci: int, window: str, tokens, stop) -> None:
		line0 = self.lines[ci]
		blocks, groups = self._groups(tokens, ci == 0, stop)
		if ci == 0:
			self._header(window, tokens, blocks)
		wlines = window.split("\n")
		for names, at, body in groups:
			if not body:
				self._warn(line0 + tokens[at[0]].map[0], "heading group without a body; skipped")
				continue
			if not names:
				self._warn(line0 + tokens[at[0]].map[0], "entry without a headword; skipped")
				continue
			e = {"names": names, "chunk": ci, "see": "", "folded": False}
			if len(body) == 1 and tokens[body[0][0]].type == "paragraph_open":
				m = tokens[body[0][0]].map
				if m[1] - m[0] == 1:
					ln = wlines[m[0]]
					mm = re.match(r"see:[ \t](.*)\Z", ln, re.S)
					if mm and mm.group(1).strip(" \t"):
						e["see"] = mm.group(1).strip(" \t")
			self.entries.append(e)

	def _header(self, window, tokens, blocks) -> None:
		if not blocks or tokens[blocks[0][0]].type != "heading_open" or tokens[blocks[0][0]].tag != "h1":
			raise FormatError("E-format", "line 1 must be `# ` and the dictionary title")
		name = _heading_text(tokens, blocks[0])
		if not name:
			raise FormatError("E-format", "the title on line 1 is empty")
		if len(blocks) < 2 or tokens[blocks[1][0]].type != "paragraph_open" or tokens[blocks[1][0]].map[0] != 1:
			raise FormatError("E-format", "line 2 must be `wudict: 1`, directly under the title")
		self.meta["name"] = name
		m = tokens[blocks[1][0]].map
		seen = set()
		for i, ln in enumerate(window.split("\n")[m[0] : m[1]]):
			kv = parse_field(ln)
			if not kv:
				self._warn(i + 2, f"header line {i + 2} is not `key: value`; it and the rest of the header are ignored")
				break
			k, v = kv
			if k == "wudict":
				continue
			if k in ("from", "to"):
				if k not in seen:
					seen.add(k)
					self.meta[k] = v
				continue
			self.meta["fields"].append((k, v))
		desc = []
		for b in blocks[2:]:
			if _is_h2(tokens, b):
				break
			desc.append(b)
		self.meta["description"] = self._render(tokens, desc)

	def _warn(self, line: int, msg: str) -> None:
		self.warnings.append(f"W-entry: {line}: {msg}" if line > 0 else f"W-entry: {msg}")

	def _fold(self) -> None:
		exact, folded = {}, {}
		for i, e in enumerate(self.entries):
			if not e["see"]:
				for n in e["names"]:
					exact.setdefault(n, []).append(i)
					folded.setdefault(n.lower(), []).append(i)
		has = {}
		for e in self.entries:
			if not e["see"]:
				continue
			targets = exact.get(e["see"]) or folded.get(e["see"].lower()) or []
			if not targets:
				continue
			e["folded"] = True
			for t in targets:
				a = self.entries[t]
				s = has.setdefault(t, set(a["names"]))
				for n in e["names"]:
					if n not in s:
						s.add(n)
						a["names"].append(n)

	@staticmethod
	def _render(tokens, blocks) -> str:
		if not blocks:
			return ""
		md = _parser()
		sel = [t for a, b in blocks for t in tokens[a : b + 1]]
		return md.renderer.render(sel, md.options, {})

	def __iter__(self):
		"""(names, html) for each article, redirects folded into them."""
		cur, bodies = -1, []
		for i, e in enumerate(self.entries):
			if e["folded"]:
				continue
			if e["see"]:
				t = e["see"]
				yield e["names"], '<p><a href="' + go_html_escape(entry_href(t)) + '">' + go_html_escape(t) + "</a></p>\n"
				continue
			if e["chunk"] != cur:
				s, end, _ = self.chunks[e["chunk"]]
				tokens, _ = self._parse(self.text[s:end])
				_, groups = self._groups(tokens, e["chunk"] == 0, None)
				bodies = [(tokens, body) for names, _, body in groups if names and body]
				cur = e["chunk"]
			tokens, body = bodies[i - self.chunks[e["chunk"]][2]]
			yield e["names"], self._render(tokens, body)

	def __len__(self) -> int:
		return sum(1 for e in self.entries if not e["folded"])


def _line_offset(s: str, n: int) -> int:
	off = 0
	for _ in range(n):
		off = s.index("\n", off) + 1
	return off


def read_text(text: str) -> Document:
	return Document(text)
