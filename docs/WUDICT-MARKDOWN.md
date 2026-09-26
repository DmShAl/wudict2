# wudict markdown — format specification, version 1

Normative. Tool-agnostic: everything a reader or writer needs is in this file. Examples are in §12 and,
byte-identical, in `docs/wudict-markdown/examples/`.

## 0. Card

- One UTF-8 file `<stem>.wudict.md` = one dictionary. Line 1 `# Title`; each `## headword` line starts an entry.
  Nothing else is structure: a `## ` line always starts an entry, even inside a code block.
- `key: value` lines directly under a heading are **fields**. Level 1: `wudict: 1` (first, required), `from`,
  `to`, any other key = header field. Level 2: `alias:` (extra search form, repeatable), `see:` (redirect).
- Everything else is the **body**: CommonMark + raw HTML + a small extension set (§5) → article HTML.
- Attach semantics with pandoc attributes: `[text]{.wu-ex lang=fr}`, `::: wu-etym` … `:::`, `### x {#id .wu-re}`,
  and `{.x}` on the line before a paragraph, list, quote, table, code block or rule.
- A body of one paragraph renders without `<p>`; in any other body, `{-}` before a paragraph does the same.
- Links: `[[word]]`, `[[word|label]]` → `entry://word`. `entry://` is the only scheme writers emit.
- Ruby: `{漢字|かんじ}` (group), `{漢字|かん|じ}` (per character).
- Anything markdown cannot hold losslessly stays HTML: inline tags in the text, tags wrapped around markdown
  blocks, or a ```` ```{=html} ```` fence.
- Round trip: import∘export preserves article HTML up to §9 equivalence; export∘import is the identity on files a
  writer produced (§9).

````
# Pocket English
wudict: 1
from: en
to: en

A small general-purpose English dictionary.

## run
alias: runs

[v.]{.wu-p title=verb} [/rʌn/]{.wu-ipa lang=en-fonipa}

1. To move quickly on foot.
2. To operate or manage: [she runs a bakery]{.wu-ex}

## ran
see: run
````

## 1. Conventions

- MUST/SHOULD/MAY per RFC 2119. Rules are numbered `R<section>.<n>`; diagnostics (§10) cite them.
- **Reader**: markdown → dictionary (headwords, aliases, redirects, article HTML). **Writer**: dictionary →
  canonical markdown. **Host**: the application displaying articles.
- CommonMark = spec 0.31.2. GFM table syntax = GitHub Flavored Markdown spec 0.29 §4.10. HTML = WHATWG HTML.
- `⏎` in §11 vectors stands for LF.

**Primitives.** Every rule uses these meanings and no library default.

- **LF** is U+000A. After R2.1 the text is split at LF and only at LF; a final LF does not start a line.
- **WS** is U+0020 or U+0009. **Trim** removes leading and trailing WS only. A **blank line** holds nothing but WS.
- **DIGIT** and **ALPHA** are ASCII. **L** and **N** are the Unicode general categories Letter and Number.
- **Column 0** is a line's first character.
- **Positions** in diagnostics: line numbers from 1; columns from 1, counted in code points (W-utf8 gives a byte
  offset instead).
- **Equal** (headwords, aliases, targets) means the same code-point sequence. Readers and writers never
  case-fold or Unicode-normalize; hosts fold for search.

## 2. File

- **R2.1** Encoding UTF-8. A leading BOM is removed. CRLF and lone CR become LF before anything else.
- **R2.2** An invalid UTF-8 sequence or U+0000 becomes U+FFFD (how many is implementation-defined) → W-utf8.
  Reading continues.
- **R2.3** File name `<stem>.wudict.md`. Resources live in `<stem>.wudict.files/` (a folder) or
  `<stem>.wudict.files.zip`, the **container**. Resource references are resolved by R5.20.
- **R2.4** Writers end the file with exactly one LF and emit no trailing WS on any line outside fenced content.

## 3. Structure

The structure scan runs over lines before any markdown parsing and is authoritative. It cuts the file into a
title, field blocks and bodies. Each body is then rendered on its own as a separate CommonMark document (§5).

- **R3.1** The scan is line-local. A line's role depends only on the line itself and on whether a field block is
  open. Nothing hides structure: not code fences, HTML blocks, comments or divs.
- **R3.2** Line 1 MUST be `# ` + title; title = rest of line, trimmed, non-empty. Otherwise E-struct.
- **R3.3** A line matching `^##(WS|$)` starts an entry. Headword = rest of line after `##`, trimmed,
  **literal**: no inline parsing, no escapes, no closing-`#` removal (`## C#` is `C#`, `## a ##` is `a ##`). An
  empty headword → W-struct, and the line is a body line of the current entry.
- **R3.4** Every other line is a field line or a body line. A body line matching `^#(WS|$)` renders as `<h1>` →
  W-struct ("entries start with `##`").
  - To avoid flagging `# comment` lines in code, readers MAY track code fences within the current body only.
  - That tracking resets at every entry line and affects diagnostics only.
- **R3.5** Fields (§4) are the contiguous field lines immediately after the title line or an entry line. The
  first non-field line ends the block; a blank line ends it without being body. Writers always emit that blank line.
- **R3.6** Body = remaining lines up to the next entry line or end of file, with leading and trailing blank lines
  removed. Title line + level-1 fields + level-1 body (the **description**) precede the first entry.
- **R3.7** Writers never emit a body line matching `^##(WS|$)`:
  - in text they escape the `#` (R8.13);
  - in raw HTML they write `&#35;` (R8.9);
  - code content goes in a shifted fence (R8.19).
- **R3.8** (Informative, authors.) A code block that must hold a column-0 `## ` line is written as a fence
  indented by 1–3 spaces. CommonMark removes that indentation from the content lines.
- **R3.9** A reader tracking fences (R3.4) reports W-struct for:
  - an entry line that ends a code fence still open in the previous body;
  - a body that ends inside an open HTML comment.

Field line: `^([a-z][a-z0-9-]*):(WS+(.*))?$`; value = group 3 trimmed.

## 4. Fields

- **R4.1** An empty value → W-field, line ignored.
- **R4.2** Level 1. The first field MUST be `wudict` with value `MAJOR` or `MAJOR.MINOR` (DIGIT runs). Missing,
  not first, malformed, or MAJOR not supported → E-version.
  - A reader accepts every MINOR of a MAJOR it supports.
  - A MINOR adds only field keys, roles and diagnostics. Any change to structure or body syntax is a new MAJOR.
  - Writers emit the lowest version whose features they use. This document is `wudict: 1`.
- **R4.3** Level 1 `from`, `to`: BCP 47 tags, the language of headwords and of article text. Not validated.
  Hosts SHOULD put `lang=<from>` on displayed headwords and `lang=<to>` on the article container.
- **R4.4** Any other level-1 key is a header field: kept in file order, repeatable, value shown as plain text.
  - Repeated `wudict`, `from` or `to` → W-field, first wins.
  - A level-1 `x-` key is an ordinary header field.
  - `meta` holds a header whose original key has no field form: `meta: <original key>: <value>`. Tools MAY split
    the value at the first `: `.
- **R4.5** Level 2 keys:
  - `alias` — an additional headword under which the entry is found (spelling variant, inflection, subentry,
    common misspelling). Repeatable. Aliases equal to the headword or to an earlier alias are dropped silently.
  - `see` — redirect. The value is a literal headword (a `#` in it is part of the headword). First wins; later
    `see` → W-field. `alias` on a redirect is allowed.
    - The entry displays what `entry://`+enc(value) (R5.18) displays in the same dictionary: every entry whose
      headword or alias matches, redirects followed. A chain stops at a repeat or after 16 hops.
    - Readers SHOULD report W-see for a target that no headword or alias equals, or for a cycle. Hosts show a
      dangling redirect as a lookup link.
    - A `see` on an entry with a non-empty body is ignored → W-see; the body is the article.
  - `x-*` — tool fields. Readers ignore them silently. Third-party tools MAY emit them; canonical writers do not.
  - Reserved, MUST NOT be emitted: `pos`, `lang`, `id`, `hom`, `sort`. Reserved and any other key → W-field, ignored.
- **R4.6** Field values are literal text: no escapes, no markup. An entry with no body and no `see` is valid.
- **R4.7** Near-miss. A line in field position that is not a field but matches `^(wudict|from|to|alias|see)WS*:`
  ignoring case → W-field ("keys are lowercase and followed by a space"). It ends the field block as any
  non-field line does. On line 2, `wudict:1` → E-version with the same message.

## 5. Body

- **R5.1** A body is CommonMark with raw HTML (inline and blocks) passed through, plus the extensions below and
  nothing else.
  - Off: autolinking of bare URLs, smart punctuation, footnotes, definition lists, emoji, math, task lists, alerts,
    YAML blocks, automatic heading ids.
  - Readers emit raw HTML and attribute values unchanged; sanitizing is the host's job (§13).

| Extension | Syntax | Renders |
|---|---|---|
| table | GFM pipe table | `<table>` with `<thead>`, `<tbody>`; column alignment as `align="left\|center\|right"` on every cell |
| strikeout | `~~x~~` | `<del>x</del>` |
| superscript | `^x^` | `<sup>x</sup>` |
| subscript | `~x~` | `<sub>x</sub>` |
| span | `[inline]{attrs}` | `<span attrs>inline</span>` |
| div | `::: {attrs}` or `::: CLASS` … `:::` | `<div attrs>`; `CLASS` (a CNAME) = `{.CLASS}` |
| heading attributes | `### text {attrs}` (h3–h6, ATX only) | `<hN attrs>` |
| link / image attributes | `[t](d "title"){attrs}`, `![a](s "title"){attrs}`, `[t][r]{attrs}` | attributes added to `<a>` / `<img>` |
| block attribute line | `{attrs}` on the line before a block | attributes on that block (R5.4) |
| bare paragraph | `{-}` on the line before a paragraph | the paragraph without `<p>` (R5.5) |
| raw fence | ```` ```{=html} ```` … ```` ``` ```` | content, byte-exact |
| wikilink | `[[w]]`, `[[w\|label]]` | `<a href="entry://w">w</a>`, `<a href="entry://w">label</a>` |
| ruby | `{base\|rt}`, `{base\|r1\|r2…}` | `<ruby>base<rt>rt</rt></ruby>`, per character when counts match |

- **R5.2 Tilde and caret.** `~` and `^` runs are delimiter runs processed by CommonMark's emphasis algorithm
  (§6.2–§6.3: flanking, the multiple-of-3 rule, nearest opener first). They may be intraword (`H~2~O`, `10^5^`).
  - For `~`: a match consumes 2 when both runs have ≥ 2 → `<del>`; otherwise it consumes 1 → `<sub>`.
  - For `^`: a match always consumes 1 → `<sup>`.
  - Content may contain WS: `~a b~` is `<sub>a b</sub>`, while in `a~ b~` neither `~` can open.
- **R5.3 Attributes.** Grammar (ABNF-like):

```
attrs   = "{" *WS [ item *( 1*WS item ) ] *WS "}"
item    = "#" NAME / "." CNAME / KEY "=" value
value   = BARE / DQ *( "\" DQ / "\\" / qchar ) DQ     ; DQ = %x22; qchar = any char but DQ, LF
NAME    = 1*( L / N / "_" / "-" / ":" / "." )
CNAME   = 1*( L / N / "_" / "-" / ":" )
KEY     = ( ALPHA / "_" / ":" ) *( ALPHA / DIGIT / "_" / "." / ":" / "-" )
BARE    = 1*( any char but WS, LF, DQ, "'", "=", "{", "}", "<", ">", "`", "\" )
```

  - **Values.** In a quoted value, `\"` is `"` and `\\` is `\`; any other `\` is a literal backslash
    (`"C:\dir"`). Values are literal: no entity decoding.
  - **Keys.** Keys match ASCII case-insensitively and are output lowercased. `#x` ≡ `id=x`; `.c` and `class=v`
    append class tokens (v split on WS). For other duplicate keys the last one wins.
  - **Rendered order.** `id`, `class` (tokens in source order), then the other keys in source order.
  - **Positions.** A brace block is attributes only in these positions:
    - directly after the `]` of a span;
    - directly after the `)` of an inline link or image, or the `]` closing a full (`[t][r]`) or collapsed
      (`[t][]`) reference link that resolves;
    - at the end of an ATX h3–h6 line, after CommonMark has removed the optional closing `#` sequence, preceded by
      WS;
    - on a `:::` opener;
    - alone on a line (R5.4).
  - **Elsewhere, or when invalid,** the brace block is ordinary text (where ruby, R5.10, may apply). An invalid
    block in an attribute position whose content starts with `#` or `.`, or contains `=`, → W-attr.
  - **Spans.**
    - `[x]{attrs}` with valid attrs is always a span: even when `x` matches a link reference definition, and even
      when `x` contains links. CommonMark's "no links in links" deactivation does not apply to span openers.
    - `{}` is valid, so `[x]{}` is `<span>x</span>`.
    - An unresolved `[t][r]{a}` is literal `[t]` followed by the span `[r]{a}`.
    - Shortcut reference links and wikilinks take no attributes.
- **R5.4 Block attribute line.** A line of 0–3 spaces, an `attrs` block and optional WS, where the next block of
  the same container starts after it (blank lines between are allowed).
  - **Target.** It attaches to that block. Consecutive attribute lines merge: classes append, later keys win.
  - **Paragraphs.** It never interrupts a paragraph; inside one it is paragraph text.

  | Next block | Attributes go on |
  |---|---|
  | paragraph | `<p>` |
  | list | `<ul>` / `<ol>` |
  | blockquote | `<blockquote>` |
  | table | `<table>` |
  | fenced code | `<pre>` |
  | thematic break | `<hr>` |
  | heading or div | the element; its own attributes come after the line's |

  - **List items.** It may be the first line of a list item, on the marker line.
  - **No next block.** Followed by no block in its container → ignored, W-attr.
  - **`<p>` guarantee.** A paragraph with an attribute line always renders `<p>` (R5.5 and tight lists do not
    apply). `{}` is the attribute line that adds nothing and only forces `<p>`.
- **R5.5 Bare paragraphs.** A paragraph renders without `<p>` when:
  - it is preceded by a `{-}` line (0–3 spaces, `{-}`, optional WS), whatever its container or list tightness; or
  - (**unwrap**) it is the only block of the body or of a div, without an attribute line. Link reference
    definitions are not blocks; every other block is, HTML blocks included.

  `{-}` before anything but a paragraph, or on a paragraph that also has an attribute line → ignored, W-attr. Unwrap is decided on the markdown block structure, not on
  the HTML: a raw fence holding `<p>x</p>` is not a paragraph and stays as is.
- **R5.6 Divs.**
  - **Opener.** `^ {0,3}:{3,}WS*(attrs|CNAME)WS*:*WS*$`.
  - **Closer.** `^ {0,3}:{3,}WS*$`, closing the innermost open div.
  - Div fences interrupt paragraphs and are never lazy continuation lines. Divs nest.
  - An unclosed div closes at the end of its enclosing container (list item, blockquote, div or body) → W-div.
  - A closer with no open div is paragraph text → W-div.
- **R5.7 Wikilinks.** `[[` target `]]` or `[[` target `|` label `]]`, recognized left to right with link precedence.
  - **Precedence.**
    - A code span, autolink or raw HTML tag that starts earlier wins.
    - Not recognized inside link text or inside another wikilink's label.
    - A wikilink is tried at `[[` before bracket/link parsing. If none starts there, `[` is an ordinary bracket, so
      `[[[a]], b]{.c}` is a span holding a wikilink.
  - **Target.** ≥1 char, none of `[`, `]`, `|`, LF, taken literally (backslash is ordinary), then trimmed; empty
    after trimming → no wikilink.
  - **Label.** Inline content up to the first `]]` not inside a code span. A label containing `[[` means no
    wikilink starts at the outer `[[`.
  - **href.** `entry://` + enc(target) (R5.18).
- **R5.8 Tables.** Inside a table row, `\|` becomes `|` before any inline parsing, including inside code spans,
  wikilinks, ruby and raw HTML (GFM). A wikilink label separator inside a table is written `\|`.
- **R5.9 Raw fences.** A fenced code block whose info string is exactly `{=html}` renders its content
  byte-exact, as an HTML block. Any other `{=fmt}` → W-raw, block dropped.
- **R5.10 Ruby.** At an unescaped `{` not in an attribute position: take the text up to the first unescaped `{`
  or `}` on the same line.
  - **When it is ruby.** It must end at a `}` and split on unescaped `|` into ≥2 non-empty parts (base, r1…rn),
    none beginning or ending with WS. Otherwise the `{` is literal text (`{x | x > 0}` is text).
  - **Scanning.** Ruby is atomic like a code span and binds left to right with it: inside, only backslash escapes
    apply.
  - **Rendering.** If n ≥ 2 and n = number of code points in base: `<ruby>b1<rt>r1</rt>b2<rt>r2</rt>…</ruby>`;
    otherwise `<ruby>base<rt>r1r2…rn</rt></ruby>`. No `<rp>` is generated.
- **R5.11 Destinations** are CommonMark-unescaped and entity-decoded, then written into `href`/`src` as they are:
  never percent-encoded or otherwise normalized.
- **R5.12 Images** always render `<img>`, whatever the extension. A `src` ending in a common audio or video
  extension (`mp3 ogg oga opus spx wav m4a flac mp4 webm ogv mkv`) → W-media; the author probably meant a
  media link (§6).
- **R5.13 Depth.** Readers MUST support nesting of divs, blockquotes, lists and spans to depth 32. Beyond their
  own limit (≥ 32) the excess renders as text → W-depth.

### 5.1 References

- **R5.14** `entry://target[#fragment]` is the lookup link: look up target, then scroll to the element whose `id`
  (or `a` `name`) is fragment.
  - Readers and hosts MUST also accept, as the same link: `entry:` or `bword:` with or without `//` (scheme
    case-insensitive), and `d:`, `x:`. `bword:` is legacy and deprecated.
  - Writers MUST emit only `entry://`.
- **R5.15** Targets and fragments are opaque strings, not URLs. They MUST NOT pass through a URL parser or URL
  normalizer.
- **R5.16** Reading a lookup link:
  1. Take the text after the scheme.
  2. Split at the first literal `#`.
  3. Apply dec to each side.
  4. Trim the target.

  An empty target is an anchor in the current article. A target whose undecoded form starts with `@` and has more
  than one character is an MDict sub-article, which hosts may inline.
- **R5.17** Readers render hrefs as written (`[t](bword://w)` keeps `bword://w`); only writers canonicalize (R8.5).
- **R5.18** Encoding:
  - **enc(s)** writes `%` as `%25`, `#` as `%23`, each C0 control and DEL as `%XX`, and a leading `@` as `%40`.
    Nothing else is encoded, so spaces and CJK stay readable.
  - **dec(s)** is the percent-decoding of s when every `%` in s starts `%HH` and the decoded bytes are valid UTF-8;
    otherwise it is s unchanged (all or nothing).
- **R5.19** A **resource reference** is any of:
  - a `src`;
  - an `href` on `link`, `image` or `use`;
  - an `href` with the pseudo-scheme `sound://` or `file://` (case-insensitive);
  - an `href` whose last path segment ends in an asset extension: `css js html htm png jpg jpeg gif webp svg bmp
    ico avif mp3 ogg oga wav spx m4a opus flac aac mp4 webm ogv mov m4v 3gp avi wmv mkv mpg mpeg asf flv pcx dcx
    wmf emf tif tiff pdf woff woff2 ttf otf eot json xml txt` (case-insensitive).

  A value with any other scheme, starting with `//`, `#` or `?`, or empty, is not a resource reference.
- **R5.20** Resolving a resource reference:
  1. Remove the pseudo-scheme.
  2. Remove one leading `/` or `./`.
  3. Cut at the first `#` or `?`.
  4. Apply dec.
  5. Resolve `.` and `..` segments inside the container; `..` above its root → not found.
  6. Match the name exactly. Hosts MAY fall back to a case-insensitive or normalization-insensitive match.

  Hosts MUST NOT follow a symbolic link out of the container.

### 5.2 Differences from pandoc `commonmark_x`

Syntax is pandoc's except:
- attribute keys are verbatim (pandoc prefixes `data-`) and case-folded;
- no automatic heading ids;
- `foo{.x}` is literal (pandoc wraps bare inlines);
- classes never change the element (pandoc turns `.abbr`, `.smallcaps`, `.mark`, `.underline` spans into other
  markup);
- `[x]{}` and `::: {}` carry no attributes (pandoc: class `{}`);
- `{-}` and `{}` lines are markers (pandoc: text);
- `\"` in quoted values;
- `* ***` is a thematic break, as in CommonMark (`commonmark_x` makes a list);
- images never become `<audio>`/`<video>`;
- wikilinks target `entry://` with R5.18 encoding and no class;
- unwrap (R5.5);
- ruby;
- table alignment uses `align=`;
- fenced code takes no attribute block in its info string, and there is no inline raw `` `x`{=html} ``.

## 6. Roles and language

- **R6.1** A role is a class in the `wu-` namespace, written literally (`{.wu-ex}`). Roles attach to any element:
  span, div, link, image, heading, inline raw HTML. Roles have no default rendering requirement; hosts style them.
  `title` may carry an expansion on any role.
- **R6.2** Authoring roles:

| Role | Marks | Typical form |
|---|---|---|
| `wu-p` | label: part of speech, grammar code (countability, gender, transitivity), register, region, domain, usage | `[n.]{.wu-p title=noun}` |
| `wu-gr` | grammar note in prose | `[irregular: *am, is, are*]{.wu-gr}` |
| `wu-abbr` | abbreviation in running text that is not a label | `[Brit.]{.wu-abbr title=British}` |
| `wu-ipa` | pronunciation run; notation in `lang` | `[/rʌn/]{.wu-ipa lang=en-fonipa}` |
| `wu-audio` | link to a sound file | `[🔊](run.mp3){.wu-audio}` |
| `wu-ex` | example | `[she runs a bakery]{.wu-ex}` |
| `wu-com` | editorial comment, citation source | `[Coleridge, 1798]{.wu-com}` |
| `wu-trn` | translation | `[вода́]{.wu-trn lang=ru}` |
| `wu-var` | variant form shown in the article | `[color]{.wu-var}` |
| `wu-syn` / `wu-ant` | run of synonyms / antonyms | `[Synonyms: [[fast]], [[quick]]]{.wu-syn}` |
| `wu-xref` | link into another dictionary; `data-dict` is its exact title | `[w](entry://w "D"){.wu-xref data-dict=D}` |
| `wu-etym` | etymology | `::: wu-etym` |
| `wu-re` | run-on subentry: idiom, phrasal verb, derivative | `### run out {#run-out .wu-re}` + `alias: run out` |
| `wu-acc` | stressed vowel, legacy sources only; prefer U+0301 in text | `вод[а]{.wu-acc}` |

- **R6.3** Converter roles are emitted when translating other formats; they are valid but not meant for hand
  authoring:
  - `wu-k` (keyword), `wu-def` (definition block), `wu-trs` (transcription zone), `wu-trn-not`, `wu-trs-not`,
    `wu-lang` (foreign-language zone), `wu-sec` (secondary text), `wu-video`, `wu-file`;
  - `wu-c` (author colour) carries its value as `style="--wd-c:…"`;
  - `wu-m` (author indent) carries its value as `style="--wd-m:N"`.

  The custom property names `--wd-c` and `--wd-m` are part of this format.
- **R6.4** Host-only roles `wu-sub`, `wu-sub-close`, `wu-hl`, `wu-cur` MUST NOT appear in files. Writers remove
  them (R8.5). Readers keep them and report W-role when a markdown-generated element carries one; raw HTML is not
  inspected.
- **R6.5** Language and notation are `lang` values (BCP 47), never roles: `lang=fr` French, `en-fonipa` IPA,
  `en-fonxsamp` X-SAMPA, `ru-Latn` romanization, `ja-Latn-hepburn`, `zh-Latn-pinyin`. `from`/`to` are the
  defaults; a `lang` attribute overrides them for its element.
- **R6.6** Direction: `dir=rtl|ltr|auto` on any element. Unicode isolate and mark characters (U+2066–U+2069,
  U+200E, U+200F) are ordinary text and are preserved.
- **R6.7** Media and marks:
  - Media: a link with a role (`wu-audio`, `wu-video`, `wu-file`) pointing at the resource.
  - Images: `![alt](file.png)`.
  - Homograph numbers are body text: `bank^1^`.
  - Stress is text: U+0301, `ˈ`, `ˌ`.

## 7. Reader

```
read(bytes):
  text ← decode(bytes)                                   # R2.1–R2.2
  lines ← split(text, LF); require lines[0] = "# " title   # R3.2
  dict ← {title, fields: [], body: [], entries: []}; cur ← dict; inFields ← true
  for line in lines[1:]:                                  # R3.1: no state but cur, inFields
    if line ~ ^##(WS|$):                                   # R3.3
      if trim(line[2:]) = "": W-struct                     # stays a body line
      else: cur ← {headword: trim(line[2:]), fields: [], body: []}
            dict.entries += cur; inFields ← true; continue
    if inFields and line ~ FIELD: cur.fields += (key, value); continue       # R3.5
    if inFields and line is blank: inFields ← false; continue
    if inFields and nearMiss(line): W-field                                 # R4.7
    inFields ← false; cur.body += line
  applyHeaderFields(dict)                                 # R4.1–R4.4, E-version
  dict.description ← renderBody(dict.body)
  for e in dict.entries:
    e.aliases ← dedup(alias values, minus e.headword)     # R4.5, file order
    e.see ← first see value (later ones: W-field)
    if e.see and body(e) not blank: W-see; e.see ← none
    e.html ← e.see ? "" : renderBody(e.body)
  checkRedirects(dict)                                    # R4.5: W-see dangling / cycle
  return dict

renderBody(lines):
  md ← join(trimBlankLines(lines), LF)                    # R3.6
  return commonmark+extensions(md)                        # §5, own reference definitions, unwrap R5.5
```

Output per entry: headword, aliases (order kept), `see` target or article HTML. Entries keep file order;
repeated headwords are separate entries (homographs). Hosts store a redirect as a link to its target.

## 8. Writer

### 8.1 File serialization

```
# <name>
wudict: 1
from: <tag>                  (when known)
to: <tag>                    (when known)
<key>: <value>               (each header field, source order)

<description>                (when non-empty)

## <headword>
alias: <alias>               (each, source order)
see: <target>                (redirects only)

<body>                       (when non-empty)
```
- **R8.1** Sections (title + fields, description, each entry heading + fields, each body) are separated by exactly
  one blank line; a heading's field lines follow it directly. Entries keep source order.
- **R8.2** Names, headwords, aliases, targets and field values:
  - CR, LF and TAB → SP; other C0 and DEL removed; trimmed.
  - An empty headword is replaced by the first non-empty alias; if there is none, the entry is skipped.
  - An empty name is replaced by the source file's stem.
  - Aliases equal to the headword or repeated are dropped.
- **R8.3** Header field key:
  - Take the source name lowercased, turn each run of characters outside `[a-z0-9]` into `-`, and trim `-`.
  - Starting with a digit, or equal to `wudict`, `from`, `to` or `meta` → prefixed `x-`.
  - Empty → the field is written `meta: <source name>: <value>`.
  - Empty values are dropped. A multi-line value is joined with SP → W-export.
  - A source description goes to the level-1 body.
- **R8.4** Body sources: HTML is used as is. Plain text becomes HTML first: escape `& < > "`, LF → `<br>`.
  Other markup formats are converted to HTML by the tool's own renderer first.

### 8.2 Preparing a body

- **R8.5** Parse the HTML as a fragment (WHATWG, context `<div>`) and apply **L**. All later steps see this tree
  only.

  | Step | Rule |
  |---|---|
  | L1 | CR → LF in every text node and attribute value |
  | L2 | Every `href` whose scheme is a lookup alias (R5.14) → `entry://` + the rest after the scheme and optional `//`, fragment kept (`bword:@x#y` → `entry://@x#y`) |
  | L3 | Every resource reference (R5.19) with a `sound://` or `file://` pseudo-scheme loses the scheme |
  | L4 | Host-only class tokens (R6.4) removed; an empty `class` removed |
  | L5 | Comments removed |

- **R8.6** Flow sequences. The children of a body, div, `li`, blockquote or wrapper (R8.8 W) form a flow sequence,
  cut into maximal **runs** of phrasing nodes and single **blocks**. A block is an element of set B (§9), or a
  phrasing element with a descendant in B.
  - **Runs.** A run is written as a paragraph. It needs a `{-}` line unless its position already renders it bare:
    - the body or div holds nothing else (unwrap), or
    - it is in a tight list.
  - **`<p>`.** A `<p>` is written as a paragraph with an attribute line (R8.10). The line is `{}` when the `<p>` has
    no attributes and its position would otherwise render it bare.

### 8.3 Mapping

**R8.7** Attempt **A** maps each element with the first applicable row; conditions not met → the element is
unmappable.

| HTML | Markdown | Conditions |
|---|---|---|
| text | escaped text (§8.4) | |
| `em` / `strong` / `del` | `*x*` / `**x**` / `~~x~~` | no attributes, non-empty |
| `sup` / `sub` | `^x^` / `~x~` | no attributes, non-empty |
| `code` | code span (§8.4) | no attributes, text only, no LF, non-empty |
| `a` → wikilink | `[[w]]` / `[[w\|label]]` | only `href`, = `entry://` + R; R has no literal `#`; w = dec(R) non-empty; enc(w) = R; w without `[ ] \|` LF or edge WS; `[[w]]` iff content is exactly the text w |
| `a` | `[t](d "title"){attrs}` | `href` present |
| `img` | `![alt](src "title"){attrs}` | `src` and `alt` present, `alt` without LF |
| `br` | `\` LF | inside a paragraph and not its last node; else inline raw |
| `span` | `[x]{attrs}` | |
| `ruby` | `{b\|r}`, `{b1b2…\|r1\|r2…}` | no attributes anywhere; children alternate non-empty text and `rt` holding non-empty text without LF or edge WS; one pair → first form; ≥2 pairs each with a 1-code-point base → second form |
| other phrasing | inline raw tags (R8.18), content mapped | no block descendant |
| `p` | paragraph (§8.5), attribute line when attributed | |
| `h3`–`h6` | `### x {attrs}` | non-empty content |
| `blockquote` | `> ` prefixed lines, attribute line when attributed | block children or a flow sequence |
| `ul` / `ol` | list (§8.5), attribute line when attributed | `li` without attributes; `start` on `ol` goes in the first marker, other attributes on the line |
| `pre > code` | fenced code, info `X` from class `language-X`; attributes of `pre` on an attribute line | `code` has nothing else; text only; `X` without WS or `` ` `` |
| `hr` | `***`, attribute line when attributed | |
| `table` | GFM table (§8.5), attribute line when attributed | §8.5 shape |
| `div` | `::: CLASS` or `::: {attrs}` | CLASS when the only attribute is one class token matching CNAME; `::: {}` without attributes |
| any other element | — | unmappable in A |

- **R8.8 Attempts.** Blocks try **A**, then **W**, then **C**; runs try **A**, then **B**, then **C**. The first
  attempt whose markdown verifies (R8.9) wins.
  - **A** — the table above; unmappable phrasing is written as inline raw tags.
  - **B** — every phrasing element as inline raw tags (text still escaped, `br` included).
  - **W** (wrapper) — for an element with at least one block child, other than a void element or `pre`, `script`,
    `style`, `textarea`: the start tag (R8.18) alone on a line, a blank line, the children as a flow sequence, a
    blank line, the end tag alone on a line. This is plain CommonMark: HTML blocks around markdown.
  - **C** — raw fence (R8.9).

  Containers (div, blockquote, list items, wrappers) are verified whole first. Their children are mapped with the
  same procedure only when the whole fails.
- **R8.9 Verification.**
  - **Per candidate.** Each candidate is rendered alone as a CommonMark document by §5 with unwrap **off**,
    including its own `{-}`/`{}` lines and its list layout. It verifies when that rendering is N-equal (§9) to
    the element or run.
  - **Whole entry.** The assembled entry is read back by the full reader (§7). The result must be N-equal to the
    prepared body. If it is not, the whole body becomes one C, and C is verified the same way.
  - **Last resort.** A C that still fails is kept and the writer reports W-export (entry and reason).
  - **Raw fence (C) layout.**
    - ```` ```{=html} ````, LF, the serialization of the node(s), LF, the closing fence.
    - The serialization is WHATWG fragment serialization with three changes:
      1. an extra LF after the start tag of a `pre`, `textarea` or `listing` whose first child is text starting
         with LF;
      2. LF in attribute values → `&#10;`;
      3. a line that would match `^##(WS|$)` gets its first `#` as `&#35;`.
    - Where change 3 falls inside a raw-text element (`script style xmp iframe noembed noframes noscript
      plaintext`), the fence is shifted (R8.19); if that is impossible, W-export.
    - Fence length = max(3, longest run of `` ` `` in the content + 1).

### 8.4 Escaping

- **R8.10 Text emission.**
  - A WS run containing LF is written as one LF (a soft break), or as one SP where LF is not allowed: headings,
    table cells, destinations, titles, attribute values, ruby, wikilink targets.
  - Other WS runs are written as they are. WS at the start or end of a line is dropped.
  - A paragraph's attribute line (`{…}`, `{}` or `{-}`) is written directly before its first line.
- **R8.11** Text (text nodes, link labels, alt, headings, cells) gets a backslash before every
  `` \ ` * _ [ ] < > & | ~ ^ { ``, and before `!` when the next emitted character is `[`.
- **R8.12** At a line start, text also escapes `# + - = :`. A line start is:
  - the first content character of a paragraph or heading line;
  - after a soft or hard break;
  - after a list marker, `> ` or a continuation indent.

  A leading run of 1–9 DIGITs followed by `.` or `)` gets its delimiter escaped (`1\.`). Table cells have no line
  start.
- **R8.13** Headings. A run of `#` that ends the heading text and is preceded by WS, or is all of it, gets its first
  `#` escaped (`### C \#`).
- **R8.14** Table cells. Every `|` in a cell's markdown is written `\|`: in text, code spans, wikilinks, ruby and
  raw tags.
- **R8.15** Ruby: base and readings additionally escape `}`.
- **R8.16** Destinations:
  - backslash before `` \ & < > ( ) ``;
  - written `<…>` when empty or when containing a character ≤ U+0020 or U+007F;
  - containing LF → unmappable.

  Titles: `"…"`, backslash before `` \ " & ``; containing LF → unmappable.
- **R8.17** Code spans: backtick string of the shortest length n ≥ 1 not occurring as a run in the content; one
  space inside each end when the content begins or ends with `` ` ``, or begins and ends with SP and is not all SP.
- **R8.18** Inline raw tags and wrapper tags:
  - `<name`, then each attribute as ` k="v"` in source order (`&` → `&amp;`, `"` → `&quot;`, LF → `&#10;`), then
    `>`;
  - void elements have no end tag; `</name>` follows the content.

  `{attrs}` (R8.7) is the element's attributes in canonical form:
  - `#id` when the id matches NAME, else `id="…"`;
  - `.class` per token in source order when the token matches CNAME, else `class="…"`;
  - `key=value` in source order. A value matching BARE is written bare; otherwise `"…"` with `\` → `\\` and
    `"` → `\"`.

  For `a`/`img`, `href`/`src`/`alt`/`title` go into the markdown syntax and the rest into `{attrs}`; nothing left →
  no braces. A key not matching KEY, or a value containing LF → unmappable.

### 8.5 Canonical block layout

- **R8.19 Code.**
  - Fence of `` ` `` of length max(3, longest backtick run in the content + 1).
  - **Shifted fence.** When a content line matches `^##(WS|$)`, the opener, every non-empty content line and the
    closer are indented by one SP.
  - If a content line starts with TAB, the block is emitted as C instead, whose serialization escapes the `#`.
- **R8.20 Lists.**
  - **Markers.** Bullet `- `; ordered `N. ` numbered from `start` (default 1), +1 per item. A list following a
    sibling list of the same kind alternates its marker (`-`/`+`, `.`/`)`) so the two stay separate.
  - Continuation indent = marker width. An empty item is the marker alone, without trailing SP.
  - **Tight** when no item contains a `<p>`: an item's first run on the marker line, following blocks and runs on
    the next lines, no blank lines inside the list.
  - **Loose** otherwise, or when the tight form fails to verify: items and their blocks separated by one blank
    line, runs marked `{-}`.
- **R8.21 Tables.**
  - **Shape.** `thead` with one `tr` of `th`; optional `tbody` with ≥1 `tr` of `td`; equal cell counts;
    phrasing-only cells; the only cell attribute is `align` (`left|center|right`), identical down each column.
  - **Layout.** `| c1 | c2 |`, delimiter cells `---`, `:--`, `:-:`, `--:`; `br` in a cell → inline raw.
- **R8.22 Divs, blockquotes and wrappers.**
  - Divs: `::: …` LF, children, LF `:::`; no blank line directly inside the fences; `:::` at every depth.
  - Blockquotes: every line prefixed `> `, blank lines inside as `>`.
  - Wrappers: R8.8 W.
  - Blank lines inside fenced content of a container are written empty (no prefix or indent).

## 9. Equivalence and invariants

**Block set B.**
- The WHATWG start tags that close an open `p`: `address article aside blockquote center details dialog dir div
  dl fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr listing main menu nav ol p
  plaintext pre search section summary table ul xmp`.
- Plus `li dd dt caption col colgroup tbody td tfoot th thead tr`.

**Exempt subtrees.**
- Descendants of `pre`, `textarea`, `listing`, `xmp`, `plaintext`, `script` and `style`.
- Any element whose `style` attribute sets `white-space` to `pre`, `pre-wrap`, `pre-line` or `break-spaces`
  (ASCII case-insensitive).

**N** (applied to a parsed fragment; it keeps what CSS `white-space: normal` shows and drops what it hides):
1. Merge adjacent text siblings.
2. Walk the tree in document order, skipping exempt subtrees. Keep a flag *lineStart*, initially true.
   - Each run of SP, TAB, LF, FF, CR in a text node → one SP. U+00A0 is not whitespace.
   - Drop that SP when *lineStart* is set or the previous kept character is SP. Inline element boundaries are
     transparent.
   - At the start or end of a B element, at `br`, and at the end of the fragment: remove a kept SP that
     immediately precedes the event, then set *lineStart*.
   - A kept non-SP character or any other element clears *lineStart*.
3. Drop empty text nodes.
4. In `pre > code`, remove one trailing LF from the last text node.
5. Attributes compare as a map. `class` compares as a set of tokens. An empty `class` and `start="1"` on `ol` are
   removed.

Two HTML fragments are **N-equal** when their N-normal trees are identical.

- **P1** For any HTML article h, either `N(import(export(h))) = N(L(h))` or the writer reported W-export for h.
  This holds by R8.9: every emitted body passed the whole-entry check, except a failed C, which is reported.
- **P2** For any file F a writer produced: `export(import(F)) = F`, byte for byte, unless that writer reported
  W-export while producing F. Why it holds:
  - text emission (R8.10) is idempotent over rendering;
  - attributes are in canonical order after one pass;
  - raw content is the writer's own serialization, which re-serializes identically;
  - headword order, aliases, redirects and header fields round-trip exactly.

  Conformance tests MUST check P2; writers MAY.
- **P3** `export` is deterministic: the same input dictionary gives the same bytes.

Byte identity between different writers is required only when both use a WHATWG-conforming HTML parser and
serializer and pass §11.

## 10. Diagnostics

Errors stop the reader and report the position (§1). Warnings continue as stated.

| Code | Rule | Condition → effect |
|---|---|---|
| E-struct | R3.2 | missing or empty title |
| E-version | R4.2, R4.7 | `wudict` missing, not first, malformed, or unsupported major |
| W-utf8 | R2.2 | invalid UTF-8 or NUL → U+FFFD |
| W-struct | R3.3, R3.4, R3.9 | empty headword; `# ` line in a body; entry line ending an open code fence; body ending in an open comment |
| W-field | R4.1, R4.4, R4.5, R4.7 | empty value, repeated singleton, unknown or reserved key → ignored; near-miss field |
| W-see | R4.5 | redirect with a body → redirect ignored; dangling or cyclic redirect |
| W-attr | R5.3–R5.5 | invalid attribute block in an attribute position; attribute line or `{-}` with no target |
| W-fence | CommonMark | code fence unclosed at the end of its body |
| W-div | R5.6 | unclosed div; closer without an open div |
| W-raw | R5.9 | `{=fmt}` other than html → block dropped |
| W-media | R5.12 | image with an audio/video extension → rendered as `<img>` |
| W-depth | R5.13 | nesting beyond the reader's limit → rendered as text |
| W-role | R6.4 | host-only role on a markdown element |
| W-export | R8.3, R8.9 | writer: output lossy or not verified; names the entry and the reason |

## 11. Vectors

`R` reader only (input not canonical), `W` writer only (HTML input, before L), `RW` both ways. Bodies are shown
alone and follow R5.5.

```
V01 RW  Plain *em* and **strong**.
        Plain <em>em</em> and <strong>strong</strong>.
V02 RW  [[apple]]  ·  [[apple|an apple]]
        <a href="entry://apple">apple</a>  ·  <a href="entry://apple">an apple</a>
V03 W   <a href="X">apple</a> for X ∈ bword://apple, bword:apple, BWORD://apple, entry:apple, d:apple, x:apple
        [[apple]]
V04 R   [t](bword://apple)
        <a href="bword://apple">t</a>
V05 RW  [run out](entry://run#run-out)  ·  [[long run|x]]
        <a href="entry://run#run-out">run out</a>  ·  <a href="entry://long run">x</a>
V06 RW  [n.]{.wu-p title=noun} [bonjour]{lang=fr} [x]{}
        <span class="wu-p" title="noun">n.</span> <span lang="fr">bonjour</span> <span>x</span>
V07 R   [x]{class="b c" id=a} [x](<entry://long run>)   (writer: [x]{#a .b .c} [[long run|x]])
        <span id="a" class="b c">x</span> <a href="entry://long run">x</a>
V08 R   word{.x} [x]{.a b} [x]{k='v'}
        word{.x} [x]{.a b} [x]{k='v'}
V09 RW  [w](entry://w "D"){.wu-xref data-dict="Other Dict"}
        <a href="entry://w" title="D" class="wu-xref" data-dict="Other Dict">w</a>
V10 RW  {漢字|かんじ} {漢字|かん|じ}
        <ruby>漢字<rt>かんじ</rt></ruby> <ruby>漢<rt>かん</rt>字<rt>じ</rt></ruby>
V11 R   {東京都|とう|きょう}           (writer: {東京都|とうきょう})
        <ruby>東京都<rt>とうきょう</rt></ruby>
V12 R   {|x} \{a|b} {a|} [x]{a|b} {x | x > 0}
        {|x} {a|b} {a|} [x]<ruby>a<rt>b</rt></ruby> {x | x &gt; 0}
V13 RW  H~2~O, 10^5^, ~~old~~
        H<sub>2</sub>O, 10<sup>5</sup>, <del>old</del>
V14 RW  <i>x</i> <b>y</b> <small>z</small> <abbr title="noun">n.</abbr>
        <i>x</i> <b>y</b> <small>z</small> <abbr title="noun">n.</abbr>
V15 W   <span class="wu-p"><abbr class="wu-abbr" title="noun">n.</abbr></span>
        [<abbr class="wu-abbr" title="noun">n.</abbr>]{.wu-p}
V16 RW  a\⏎b<br>
        a<br>b<br>
V17 W   1. *a* [b] &lt;c&gt; &amp;d; x|y ~z^ {w} !<a href="entry://q">q</a>
        1\. \*a\* \[b\] \<c\> \&d; x\|y \~z\^ \{w} \![[q]]
V18 W   a<br>- b<br># c<br>: d<br>== e
        a\⏎\- b\⏎\# c\⏎\: d\⏎\== e
V19 RW  ::: wu-etym⏎From [Latin]{lang=la}.⏎:::
        <div class="wu-etym">From <span lang="la">Latin</span>.</div>
V20 RW  ::: {lang=ar dir=rtl}⏎::: wu-ex⏎نص⏎:::⏎:::
        <div lang="ar" dir="rtl"><div class="wu-ex">نص</div></div>
V21 RW  ### kick the bucket {#kick .wu-re}
        <h3 id="kick" class="wu-re">kick the bucket</h3>
V22 W   <h2>x</h2>
        ```{=html}⏎<h2>x</h2>⏎```
V23 RW  [🔊](a.mp3){.wu-audio} ![map](map.png){width=200}
        <a href="a.mp3" class="wu-audio">🔊</a> <img src="map.png" alt="map" width="200">
V24 R   ![x](a.mp3)                    (W-media)
        <img src="a.mp3" alt="x">
V25 W   <ul><li>a</li></ul><ul><li>b</li></ul>
        - a⏎⏎+ b
V26 W   <code>a`b</code> <code>`x</code>
        ``a`b`` `` `x ``
V27 RW  | a | b |⏎| --- | :-: |⏎| 1 | 2 |
        <table><thead><tr><th>a</th><th align="center">b</th></tr></thead><tbody><tr><td>1</td><td align="center">2</td></tr></tbody></table>
V28 W   <em>a</em><em>b</em>           (A renders *a**b* differently → B)
        <em>a</em><em>b</em>
V29 R   file: # D⏎wudict: 1⏎⏎## a⏎note: x⏎x-id: 7⏎⏎text⏎⏎## b⏎see: a⏎⏎body⏎⏎## c⏎see: a
        a: body "text" (W-field for note; x-id silent) · b: article "body" (W-see) · c: redirect to a
V30 R   file: # D⏎wudict: 1⏎⏎## a⏎⏎```⏎## b⏎```⏎⏎ ## c⏎⏎## C# ##
        a: <pre><code></code></pre> (W-fence; W-struct: b ends a's fence) · b: <pre><code>⏎ ## c⏎</code></pre> (W-fence) · headword "C# ##"
V31 R   file: # D⏎from: en              → E-version (line 2)
V32 R   ```{=latex}⏎\x⏎```              → W-raw, empty body
V33 RW  {-}⏎**hw** [n.]{.pos}⏎⏎::: def⏎d⏎:::
        <strong>hw</strong> <span class="pos">n.</span><div class="def">d</div>
V34 RW  {.x}⏎para                      ·  whole body {}⏎only  ·  whole body {-}⏎a⏎⏎::: {}⏎b⏎:::
        <p class="x">para</p>  ·  <p>only</p>  ·  a<div>b</div>
V35 RW  <span class="g">⏎⏎::: top⏎x⏎:::⏎⏎</span>
        <span class="g"><div class="top">x</div></span>
V36 RW  [[C#]] [[100%]] [[C#|see C#]]
        <a href="entry://C%23">C#</a> <a href="entry://100%25">100%</a> <a href="entry://C%23">see C#</a>
V37 R   ~a b~ a~ b~ ~a~~b~ ^^x^^
        <sub>a b</sub> a~ b~ <sub>a~~b</sub> <sup><sup>x</sup></sup>
V38 W   <h3>C #</h3>  ·  <ul><li>a<hr></li></ul>
        ### C \#  ·  - a⏎  ***
V39 W   <table><thead><tr><th>a</th></tr></thead><tbody><tr><td><code>x|y</code></td></tr></tbody></table>
        | a |⏎| --- |⏎| `x\|y` |
V40 W   <span class="wu-hl">x</span> <a href="sound://a%23b.mp3">s</a>
        [x]{} [s](a%23b.mp3)
V41 R   [x]{title="C:\dir"} [x]{#café} [x]{Lang=fr lang=en}
        <span title="C:\dir">x</span> <span id="café">x</span> <span lang="en">x</span>
V42 W   <pre><code>## x⏎</code></pre>
        ␠```⏎␠## x⏎␠```                 (␠ = SP: shifted fence, R8.19)
```

## 12. Examples

Both files are canonical: a reader imports them without diagnostics and a writer re-exports them byte for byte.
Legacy link schemes and level-2 `x-*` fields are not canonical, so they appear only in §11.

### 12.1 Minimal dictionary

CommonMark plus wikilinks: the common case needs nothing else.

````
# Pocket English
wudict: 1
from: en
to: en

A small general-purpose English dictionary.

## apple

The round fruit of the apple tree.

## run
alias: runs
alias: running

1. To move quickly on foot.
2. To operate or manage: *she runs a bakery*.

## colour
alias: color

The property of an object that depends on the light it reflects. Compare [[hue]].

## hue

A colour or shade.

## ran
see: run
````

### 12.2 Full dictionary

Every extension of §5 and every authoring role of §6; each entry demonstrates one lexicographic need.

````
# Wudict Sampler
wudict: 1
from: en
to: en
author: wudict contributors
license: CC0-1.0

A sampler covering every construct of wudict markdown. Each entry demonstrates one lexicographic need.

The description is an ordinary body: *emphasis* and [[aesthetic|links]] work here too.

## aesthetic
alias: esthetic
alias: aesthetics

[adj.]{.wu-p title=adjective} [/iːsˈθɛtɪk/]{.wu-ipa lang=en-fonipa} [/i:s"TEtIk/]{.wu-ipa lang=en-fonxsamp} [🔊](aesthetic.mp3){.wu-audio}

1. Concerned with beauty: [an aesthetic judgement]{.wu-ex}
2. Pleasing in appearance. [Synonyms: [[beautiful]], [[tasteful]]]{.wu-syn} [Antonym: [[ugly]]]{.wu-ant}

::: wu-etym
From Greek [αἰσθητικός]{lang=grc} [aisthētikós]{lang=grc-Latn}, from [αἰσθάνομαι]{lang=grc} "I perceive".
:::

[In another dictionary:]{.wu-com} [aesthetics](entry://aesthetics "Oxford Philosophy"){.wu-xref data-dict="Oxford Philosophy"}

## bank
alias: banks

bank^1^ [n.]{.wu-p title=noun}

1. The land alongside a river or lake.
2. A slope of earth or sand: [a grassy bank]{.wu-ex}

## bank

bank^2^ [n.]{.wu-p title=noun}

3. An institution that keeps and lends money.

   [See also]{.wu-com} [[bankrupt]]

4. A reserve kept for later use: [a blood bank]{.wu-ex}

## run
alias: runs
alias: running
alias: run out
alias: in the long run

[v.]{.wu-p title=verb} [/rʌn/]{.wu-ipa lang=en-fonipa}

1. To move swiftly on foot.
2. To operate or manage: [she runs a bakery]{.wu-ex}

### run out {#run-out .wu-re}

[phr. v.]{.wu-p title="phrasal verb"} To use up a supply: [we ran out of milk]{.wu-ex}

### in the long run {#long-run .wu-re}

[idiom]{.wu-p} Eventually. See also [run out](entry://run#run-out).

## water

[n.]{.wu-p title=noun} [/ˈwɔːtə/]{.wu-ipa lang=en-GB-fonipa} [uncountable]{.wu-p}

The liquid H~2~O; it boils at 100 °C at a pressure of about 10^5^ Pa.

Russian: [вода́]{.wu-trn lang=ru} [vodá]{lang=ru-Latn}; older sources mark the stressed vowel instead: [вод[а]{.wu-acc}]{.wu-trn lang=ru}

![A drop of water](water-drop.jpg "Water drop"){width=120}

> Water, water, every where,\
> Nor any drop to drink.
>
> [Coleridge, 1798]{.wu-com}

## be
alias: am
alias: is
alias: are

[v.]{.wu-p title=verb} [irregular: present *am, is, are*]{.wu-gr}

#### Present tense

| person | singular | plural |
| --- | :-: | :-: |
| 1st | am | are |
| 2nd | are | are |
| 3rd | is | are |

## kanji
alias: 漢字

[n.]{.wu-p title=noun} Chinese characters as used in Japanese: [{漢字|かんじ}]{lang=ja} with one reading for the word, [{漢字|かん|じ}]{lang=ja} with one reading per character.

[{日本語|にほんご}は{漢字|かんじ}と{仮名|かな}で書く。]{lang=ja}

## book

[n.]{.wu-p title=noun} A written work. Arabic: [كتاب]{.wu-trn lang=ar dir=rtl}

::: {.wu-trn lang=ar dir=rtl}
::: wu-ex
قرأتُ كتابًا.
:::
:::

## colour
alias: color

[Brit.]{.wu-abbr title=British} spelling; [US]{.wu-abbr title="United States"} [color]{.wu-var}. <small>Obsolete:</small> ~~colur~~

Compare [[hue]] and [[hue|shade]]; <i>tint</i> is paler.

## colours
see: colour

## regex
alias: regular expression

[n.]{.wu-p title=noun} [comput.]{.wu-p title=computing} A pattern such as `[a-z]+` that matches a set of strings.

```text
^[A-Z][a-z]+$
```

## set
alias: set sail

{-}
**set** [v.]{.wu-p title=verb}

{.def}
To put something in a particular place.

{.senses}
1. [set the table]{.wu-ex}
2. [set a record]{.wu-ex}

<section class="idioms">

### set sail {#set-sail .wu-re}

[idiom]{.wu-p} To begin a voyage.

</section>

## hash
alias: #
alias: hash sign

[n.]{.wu-p title=noun} The character `#`. Markup that markdown cannot express stays raw HTML:

```{=html}
<pre class="sample"># Title
wudict: 1

&#35;# headword
</pre>
```
````

### 12.3 Expected import of 12.2

Normative up to N-equality (§9). `<!-- … -->` lines separate records and are not part of any article.

````html
<!-- description -->
<p>A sampler covering every construct of wudict markdown. Each entry demonstrates one lexicographic need.</p>
<p>The description is an ordinary body: <em>emphasis</em> and <a href="entry://aesthetic">links</a> work here too.</p>
<!-- entry: aesthetic; alias: esthetic, aesthetics -->
<p><span class="wu-p" title="adjective">adj.</span> <span class="wu-ipa" lang="en-fonipa">/iːsˈθɛtɪk/</span> <span class="wu-ipa" lang="en-fonxsamp">/i:s"TEtIk/</span> <a href="aesthetic.mp3" class="wu-audio">🔊</a></p>
<ol>
<li>Concerned with beauty: <span class="wu-ex">an aesthetic judgement</span></li>
<li>Pleasing in appearance. <span class="wu-syn">Synonyms: <a href="entry://beautiful">beautiful</a>, <a href="entry://tasteful">tasteful</a></span> <span class="wu-ant">Antonym: <a href="entry://ugly">ugly</a></span></li>
</ol>
<div class="wu-etym">From Greek <span lang="grc">αἰσθητικός</span> <span lang="grc-Latn">aisthētikós</span>, from <span lang="grc">αἰσθάνομαι</span> "I perceive".</div>
<p><span class="wu-com">In another dictionary:</span> <a href="entry://aesthetics" title="Oxford Philosophy" class="wu-xref" data-dict="Oxford Philosophy">aesthetics</a></p>
<!-- entry: bank; alias: banks -->
<p>bank<sup>1</sup> <span class="wu-p" title="noun">n.</span></p>
<ol>
<li>The land alongside a river or lake.</li>
<li>A slope of earth or sand: <span class="wu-ex">a grassy bank</span></li>
</ol>
<!-- entry: bank -->
<p>bank<sup>2</sup> <span class="wu-p" title="noun">n.</span></p>
<ol start="3">
<li><p>An institution that keeps and lends money.</p><p><span class="wu-com">See also</span> <a href="entry://bankrupt">bankrupt</a></p></li>
<li><p>A reserve kept for later use: <span class="wu-ex">a blood bank</span></p></li>
</ol>
<!-- entry: run; alias: runs, running, run out, in the long run -->
<p><span class="wu-p" title="verb">v.</span> <span class="wu-ipa" lang="en-fonipa">/rʌn/</span></p>
<ol>
<li>To move swiftly on foot.</li>
<li>To operate or manage: <span class="wu-ex">she runs a bakery</span></li>
</ol>
<h3 id="run-out" class="wu-re">run out</h3>
<p><span class="wu-p" title="phrasal verb">phr. v.</span> To use up a supply: <span class="wu-ex">we ran out of milk</span></p>
<h3 id="long-run" class="wu-re">in the long run</h3>
<p><span class="wu-p">idiom</span> Eventually. See also <a href="entry://run#run-out">run out</a>.</p>
<!-- entry: water -->
<p><span class="wu-p" title="noun">n.</span> <span class="wu-ipa" lang="en-GB-fonipa">/ˈwɔːtə/</span> <span class="wu-p">uncountable</span></p>
<p>The liquid H<sub>2</sub>O; it boils at 100 °C at a pressure of about 10<sup>5</sup> Pa.</p>
<p>Russian: <span class="wu-trn" lang="ru">вода́</span> <span lang="ru-Latn">vodá</span>; older sources mark the stressed vowel instead: <span class="wu-trn" lang="ru">вод<span class="wu-acc">а</span></span></p>
<p><img src="water-drop.jpg" alt="A drop of water" title="Water drop" width="120"></p>
<blockquote>
<p>Water, water, every where,<br>Nor any drop to drink.</p>
<p><span class="wu-com">Coleridge, 1798</span></p>
</blockquote>
<!-- entry: be; alias: am, is, are -->
<p><span class="wu-p" title="verb">v.</span> <span class="wu-gr">irregular: present <em>am, is, are</em></span></p>
<h4>Present tense</h4>
<table>
<thead><tr><th>person</th><th align="center">singular</th><th align="center">plural</th></tr></thead>
<tbody>
<tr><td>1st</td><td align="center">am</td><td align="center">are</td></tr>
<tr><td>2nd</td><td align="center">are</td><td align="center">are</td></tr>
<tr><td>3rd</td><td align="center">is</td><td align="center">are</td></tr>
</tbody>
</table>
<!-- entry: kanji; alias: 漢字 -->
<p><span class="wu-p" title="noun">n.</span> Chinese characters as used in Japanese: <span lang="ja"><ruby>漢字<rt>かんじ</rt></ruby></span> with one reading for the word, <span lang="ja"><ruby>漢<rt>かん</rt>字<rt>じ</rt></ruby></span> with one reading per character.</p>
<p><span lang="ja"><ruby>日本語<rt>にほんご</rt></ruby>は<ruby>漢字<rt>かんじ</rt></ruby>と<ruby>仮名<rt>かな</rt></ruby>で書く。</span></p>
<!-- entry: book -->
<p><span class="wu-p" title="noun">n.</span> A written work. Arabic: <span class="wu-trn" lang="ar" dir="rtl">كتاب</span></p>
<div class="wu-trn" lang="ar" dir="rtl"><div class="wu-ex">قرأتُ كتابًا.</div></div>
<!-- entry: colour; alias: color -->
<p><span class="wu-abbr" title="British">Brit.</span> spelling; <span class="wu-abbr" title="United States">US</span> <span class="wu-var">color</span>. <small>Obsolete:</small> <del>colur</del></p>
<p>Compare <a href="entry://hue">hue</a> and <a href="entry://hue">shade</a>; <i>tint</i> is paler.</p>
<!-- entry: colours; see: colour -->
<!-- entry: regex; alias: regular expression -->
<p><span class="wu-p" title="noun">n.</span> <span class="wu-p" title="computing">comput.</span> A pattern such as <code>[a-z]+</code> that matches a set of strings.</p>
<pre><code class="language-text">^[A-Z][a-z]+$
</code></pre>
<!-- entry: set; alias: set sail -->
<strong>set</strong> <span class="wu-p" title="verb">v.</span>
<p class="def">To put something in a particular place.</p>
<ol class="senses">
<li><span class="wu-ex">set the table</span></li>
<li><span class="wu-ex">set a record</span></li>
</ol>
<section class="idioms">
<h3 id="set-sail" class="wu-re">set sail</h3>
<p><span class="wu-p">idiom</span> To begin a voyage.</p>
</section>
<!-- entry: hash; alias: #, hash sign -->
<p><span class="wu-p" title="noun">n.</span> The character <code>#</code>. Markup that markdown cannot express stays raw HTML:</p>
<pre class="sample"># Title
wudict: 1

&#35;# headword
</pre>
````

## 13. Security

- **R13.1** Readers serialize attribute values with `&` and `"` escaped and text with `&` and `<` escaped. "As
  written" and "literal" describe values, never their serialization.
- **R13.2** Files are untrusted, like every dictionary format. Raw HTML, event-handler keys and `javascript:`
  destinations pass through, so hosts MUST sanitize or isolate article HTML before displaying it.
- **R13.3** Every scan in §3 and §5 is linear as specified: ruby stops at `{`/`}` (R5.10) and wikilink labels at
  `[[` (R5.7). Implementations use a linear-time CommonMark parser.
- **R13.4** Nesting depth per R5.13. Writers emit C for content nested deeper than 32.
- **R13.5** Resource resolution never leaves the container (R5.20); zip entry names are matched, never extracted
  to paths.

## 14. Residual limits and deferred features

Every residual limit below is detected: the writer reports W-export, or verification falls back to a raw form.

| Case | Behaviour |
|---|---|
| HTML whose serialization does not re-parse to the same tree (foreign content, `noscript`) | C fails verification → W-export |
| `white-space: pre*` set through a class the writer cannot see | leading line WS and WS across text nodes are not preserved (inline `style` is exempt, §9) |
| Text directly followed by an inline element that wraps blocks and starts with text (`a<span>b<div>`) | the wrapper adds a space → that block is C |
| Raw-text element content with a `## ` line and a TAB-initial line | W-export |
| A literal backslash-pipe in a table cell | the table is C |

**Deferred:** compression, multi-file dictionaries, alias→fragment landing, definition lists, attributes on list
items (wrappers cover them), a `check` command.

## Appendix A. Implementer notes (informative; verified 2026-09-26 against the versions named)

- **Any stack.**
  - Run the §3 scan yourself; never hand the whole file to a markdown parser.
  - Build the body renderer from a CommonMark parser with raw HTML on, linkify and typographer off, and URL
    normalization disabled (R5.11).
  - Test against §11 and §12 first, then fuzz P1 with real dictionary HTML.
  - Use a WHATWG HTML parser and serializer in the writer (Go `golang.org/x/net/html`, Python html5lib or
    html5-parser; not lxml/libxml2 or `html.parser`).
- **Primitives (§1).** These library calls do not match the definitions:
  - Python: `str.splitlines`, `str.strip`, `re` `\d` and `\s`, `str.isdigit`;
  - Go: `strings.TrimSpace`, `unicode.IsSpace`, `bufio.ScanLines` (drops a trailing CR);
  - JS: `trim()`, `\s`.
- **Go — goldmark v1.8.2.**
  - *Keep:* core, `html.WithUnsafe()`, `extension.Table` with `TableCellAlignAttribute` (escaped pipes in cells are
    handled).
  - *Replace:*
    - `extension.Strikethrough` accepts a single `~` (`strikethrough.go`), so use one `~` delimiter processor
      (1 → sub, 2 → del) and a `^` processor;
    - the link and image renderers apply `util.URLEscape`;
    - `parser.ParseAttributes` takes JSON-typed values and ASCII names, so use an R5.3 parser.
  - *Add:*
    - inline parsers for span attributes, link/image attributes, wikilinks (trigger `[`, higher priority than
      links) and ruby (trigger `{`);
    - block parsers for divs (must interrupt paragraphs), attribute lines and `{-}`, and the `{=html}` fence;
    - an AST transformer for unwrap.
- **Python — markdown-it-py 4.2.0 + mdit-py-plugins 0.6.1.**
  - `MarkdownIt("commonmark", {"html": True})` + `table` + `strikethrough`.
  - `attrs_plugin(spans=True)` gives spans and link/image attributes, and accepts Unicode ids.
  - `attrs_block_plugin` gives attribute lines (blank line allowed, stacked lines merge).
  - Differences to patch:
    - quoted `\"` keeps its backslash;
    - keys are not case-folded;
    - no heading attributes;
    - `{-}` is text.
  - Set `md.normalizeLink`/`normalizeLinkText` to identity and `md.validateLink` to accept every scheme.
  - Custom rules: wikilinks, ruby, sup/sub, divs with `{attrs}`, `{=html}`, unwrap.
- **pyglossary 5.4.2.** A format plugin module defines `lname`, `name`, `extensions`, `singleFile`, `kind` and
  `Reader`/`Writer` classes.

| wudict markdown | pyglossary |
|---|---|
| `# title`, `from`, `to`, header fields | `glos.setInfo("name", …)`, `sourceLang`/`targetLang` info keys, other info keys |
| description | info key `description` |
| `## headword` + `alias:` | `glos.newEntry(word=[headword, *aliases], defi, defiFormat="h")`; writer reads `entry.l_term` |
| body HTML | `entry.defi`; plain-text definitions via R8.4 |
| `see: t` | no redirect type: append the redirect's headword to entry `t`'s terms when `t` exists, else a definition `<a href="entry://t">t</a>` |
| resources `<stem>.wudict.files/` | `glos.newDataEntry(fname, data)`; `entry.isData()` |
| `bword://` in definitions | rewritten by L (R8.5) on write |
