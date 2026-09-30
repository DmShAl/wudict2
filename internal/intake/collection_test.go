// Copyright (C) 2026 glowinthedark
//
// SPDX-License-Identifier: GPL-3.0-or-later

package intake

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"
)

func TestUnwrap(t *testing.T) {
	for _, tc := range []struct{ in, want string }{
		{"https://legbehindneck.com/wudict#https://a.org/x.zip", "https://a.org/x.zip"},
		{"https://legbehindneck.com/wudict/#https://a.org/dir/", "https://a.org/dir/"},
		{"  https://www.legbehindneck.com/wudict#https://a.org/x.zip  ", "https://a.org/x.zip"},
		{"https://legbehindneck.com/wudict#https%3A%2F%2Fa.org%2Fx%20y.zip", "https://a.org/x y.zip"},
		// the short form: a path on the share link's own site
		{"https://legbehindneck.com/wudict/#/dict/euskera/", "https://legbehindneck.com/dict/euskera/"},
		{"https://legbehindneck.com/wudict#/dict/euskera/list.txt", "https://legbehindneck.com/dict/euskera/list.txt"},
		// ...never another host without its scheme
		{"https://legbehindneck.com/wudict#//evil.org/x.zip", "//evil.org/x.zip"},
		// the inner link keeps its own escapes
		{"https://legbehindneck.com/wudict#https://a.org/%E8%8B%B1.mdx", "https://a.org/%E8%8B%B1.mdx"},
		// not ours: left exactly as given
		{"https://a.org/page#https://b.org/x.zip", "https://a.org/page#https://b.org/x.zip"},
		{"https://legbehindneck.com/wudictionary#https://b.org/x.zip", "https://legbehindneck.com/wudictionary#https://b.org/x.zip"},
		{"https://a.org/x.zip", "https://a.org/x.zip"},
		{"not a link", "not a link"},
	} {
		if got := Unwrap(tc.in); got != tc.want {
			t.Errorf("Unwrap(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestParseText(t *testing.T) {
	base, _ := url.Parse("https://h.org/dict/euskera/list.txt")
	l := parseText("# Basque · Elhuyar\r\n\n# a comment\nen-eu.mdx\nOxford Advanced.mdx\nC#.mdx\n"+
		"https://other.org/x.slob\nsee (https://legbehindneck.com/wudict#https://w.org/y.zim).\n", base)
	if l.title != "Basque · Elhuyar" {
		t.Errorf("title = %q", l.title)
	}
	var got []string
	for _, u := range l.links {
		got = append(got, u.String())
	}
	want := []string{
		"https://h.org/dict/euskera/en-eu.mdx",
		"https://h.org/dict/euskera/Oxford%20Advanced.mdx",
		"https://h.org/dict/euskera/C%23.mdx",
		"https://other.org/x.slob",
		"https://w.org/y.zim",
	}
	if !slices.Equal(got, want) {
		t.Errorf("links =\n%v\nwant\n%v", got, want)
	}
	if !l.text {
		t.Error("a list must be marked as text, so its main files get their companions looked for")
	}

	// Pasted text has nothing to resolve a bare name against, so prose
	// contributes only its links.
	p := parseText("grab these: https://a.org/1.mdx and\nhttps://a.org/2.slob, thanks", nil)
	if len(p.links) != 2 || p.links[1].String() != "https://a.org/2.slob" {
		t.Errorf("pasted = %v", p.links)
	}
}

func TestParseHTML(t *testing.T) {
	base, _ := url.Parse("https://h.org/dict/euskera/")
	page := `<table><tr><td><a href="..">Parent</a></td></tr>
<tr><td><a href="?C=N;O=D">Name</a></td></tr>
<tr><td><A HREF="en-eu-Elhuyar.mdx">en-eu</A></td></tr>
<tr><td><a class="x" href='en-eu-Elhuyar.mdd'>media</a></td></tr>
<tr><td><a href=/abs/b.slob>b</a></td></tr>
<tr><td><a href="Tom&amp;Jerry.mdx">t</a></td></tr>
<tr><td><a href="#top">top</a></td></tr></table>`
	l := parseHTML(page, base)
	var got []string
	for _, u := range l.links {
		got = append(got, u.String())
	}
	want := []string{
		"https://h.org/dict/",
		"https://h.org/dict/euskera/?C=N;O=D",
		"https://h.org/dict/euskera/en-eu-Elhuyar.mdx",
		"https://h.org/dict/euskera/en-eu-Elhuyar.mdd",
		"https://h.org/abs/b.slob",
		"https://h.org/dict/euskera/Tom&Jerry.mdx",
	}
	if !slices.Equal(got, want) {
		t.Errorf("links =\n%v\nwant\n%v", got, want)
	}
}

// colSite serves files under /dict/ with sizes and dates, a folder page that
// links to them, and a list; broken names answer HEAD and then fail the GET.
type colSite struct {
	files  map[string]string // path under /dict/ -> body
	broken map[string]bool
	date   time.Time
}

func (s *colSite) serve(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := strings.TrimPrefix(r.URL.Path, "/dict/")
		switch {
		case r.URL.Path == "/dict/folder":
			http.Redirect(w, r, "/dict/folder/", http.StatusMovedPermanently)
			return
		case r.URL.Path == "/dict/folder/":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			var b strings.Builder
			b.WriteString(`<html><body><a href="../">..</a> <a href="index.html">index</a>`)
			for name := range s.files {
				if dir, file, ok := strings.Cut(name, "/"); ok && dir == "folder" {
					b.WriteString(`<a href="` + file + `">` + file + `</a>`)
				}
			}
			b.WriteString(`</body></html>`)
			_, _ = w.Write([]byte(b.String()))
			return
		}
		body, ok := s.files[p]
		if !ok {
			http.NotFound(w, r)
			return
		}
		if s.broken[p] && r.Method == http.MethodGet && r.Header.Get("Range") == "" {
			http.Error(w, "gone", http.StatusInternalServerError)
			return
		}
		if strings.HasSuffix(p, ".txt") {
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		} else {
			w.Header().Set("Content-Type", "application/octet-stream")
		}
		http.ServeContent(w, r, filepath.Base(p), s.date, strings.NewReader(body))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func colReady(t *testing.T, m *Manager) Job {
	t.Helper()
	m.Wait()
	st := m.Status()
	if st.State != StateReady {
		t.Fatalf("state = %q (%s)", st.State, st.Error)
	}
	if !st.Collection {
		t.Fatal("a folder, a list or pasted links must be reported as a collection")
	}
	return st
}

func candNames(cands []Candidate) []string {
	var out []string
	for _, c := range cands {
		out = append(out, c.Name)
	}
	return out
}

// The case this exists for: a web folder of dictionaries, as a link. Nothing
// is downloaded until the user chooses; the .mdd is offered as a tickbox of
// its own; the size and date come from the colSite.
func TestCollectionFromAFolderPage(t *testing.T) {
	s := &colSite{
		files: map[string]string{
			"folder/en-eu.mdx": "english basque",
			"folder/en-eu.mdd": "media media media",
			"folder/eu.slob":   "basque slob",
			"folder/notes.pdf": "not a dictionary",
		},
		date: time.Date(2026, 9, 22, 20, 34, 51, 0, time.UTC),
	}
	srv := s.serve(t)
	dest := t.TempDir()
	m := &Manager{}
	// Without the trailing slash: relative links must resolve against the
	// address the redirect landed on, or every one of them points at /dict/.
	if _, err := m.BeginURL(dest, srv.URL+"/dict/folder", loopback()); err != nil {
		t.Fatal(err)
	}
	st := colReady(t, m)
	if got := candNames(st.Candidates); !slices.Equal(got, []string{"en-eu", "eu"}) {
		t.Fatalf("candidates = %v", got)
	}
	if st.Source != "folder" {
		t.Errorf("title = %q, want the folder's name", st.Source)
	}
	c := st.Candidates[0]
	if !slices.Equal(c.Files, []string{"en-eu.mdx"}) || c.Size != int64(len("english basque")) {
		t.Errorf("en-eu = files %v size %d: the media belongs in extras, not in the row", c.Files, c.Size)
	}
	if c.Date != "2026-09-22" {
		t.Errorf("date = %q", c.Date)
	}
	if len(st.Extras) != 1 || st.Extras[0].Name != "en-eu.mdd" || st.Extras[0].Need != NeedMedia {
		t.Fatalf("extras = %+v", st.Extras)
	}
	if entries, _ := os.ReadDir(DownloadDir(dest)); len(entries) != 0 {
		t.Fatalf("something was downloaded before the user chose: %v", entries)
	}

	if _, err := m.Confirm(dest, []int{0, 1}, Options{Keep: true, Extras: []int{0}}); err != nil {
		t.Fatal(err)
	}
	m.Wait()
	st = m.Status()
	if st.State != StateDone || st.Error != "" {
		t.Fatalf("state = %q (%s)", st.State, st.Error)
	}
	if !slices.Equal(st.Installed, []string{"en-eu", "eu"}) {
		t.Fatalf("installed = %v", st.Installed)
	}
	for _, f := range []string{"en-eu/en-eu.mdx", "en-eu/en-eu.mdd", "eu/eu.slob"} {
		if _, err := os.Stat(filepath.Join(dest, f)); err != nil {
			t.Errorf("%s: %v", f, err)
		}
	}

	// The same link again: identical dictionaries say so and start unticked.
	if _, err := m.BeginURL(dest, srv.URL+"/dict/folder/", loopback()); err != nil {
		t.Fatal(err)
	}
	st = colReady(t, m)
	for _, c := range st.Candidates {
		if c.Existing != c.Name || !c.Unchanged {
			t.Errorf("%s: existing=%q unchanged=%v, want itself and unchanged", c.Name, c.Existing, c.Unchanged)
		}
	}

	// A changed .mdd is a changed dictionary, although the row does not list it.
	s.files["folder/en-eu.mdd"] = "media media media, reissued"
	if _, err := m.BeginURL(dest, srv.URL+"/dict/folder/", loopback()); err != nil {
		t.Fatal(err)
	}
	st = colReady(t, m)
	if c := st.Candidates[0]; c.Existing != "en-eu" || c.Unchanged {
		t.Errorf("en-eu after its media changed: existing=%q unchanged=%v", c.Existing, c.Unchanged)
	}
}

// A list names only the .mdx - as a person pasting links would - and its .mdd
// is found beside it the way a single pasted link's is. Unticked media is not
// downloaded.
func TestCollectionFromAList(t *testing.T) {
	s := &colSite{files: map[string]string{
		"lists/set.txt":   "# My set\nOxford.mdx\n\nmissing.slob\n",
		"lists/Oxford.mdx": "oxford",
		"lists/Oxford.mdd": "oxford media",
	}}
	srv := s.serve(t)
	dest := t.TempDir()
	m := &Manager{}
	if _, err := m.BeginURL(dest, srv.URL+"/dict/lists/set.txt", loopback()); err != nil {
		t.Fatal(err)
	}
	st := colReady(t, m)
	if st.Source != "My set" {
		t.Errorf("title = %q", st.Source)
	}
	if got := candNames(st.Candidates); !slices.Equal(got, []string{"Oxford"}) {
		t.Fatalf("candidates = %v (a listed file the colSite does not have must not be offered)", got)
	}
	if len(st.Extras) != 1 || st.Extras[0].Name != "Oxford.mdd" {
		t.Fatalf("extras = %+v, want the .mdd found beside the listed .mdx", st.Extras)
	}
	if _, err := m.Confirm(dest, []int{0}, Options{Keep: true}); err != nil {
		t.Fatal(err)
	}
	m.Wait()
	if st := m.Status(); st.State != StateDone {
		t.Fatalf("state = %q (%s)", st.State, st.Error)
	}
	if _, err := os.Stat(filepath.Join(dest, "Oxford", "Oxford.mdx")); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(DownloadDir(dest), "Oxford.mdd")); !os.IsNotExist(err) {
		t.Errorf("unticked media was downloaded anyway: %v", err)
	}
}

// Several links pasted at once, one of them wrapped in a share link, and one
// that dies on download: the others still install, and the failure is named.
func TestCollectionFromPastedLinks(t *testing.T) {
	s := &colSite{
		files:  map[string]string{"a/one.slob": "one", "b/two.slob": "two", "b/dead.slob": "dead"},
		broken: map[string]bool{"b/dead.slob": true},
	}
	srv := s.serve(t)
	dest := t.TempDir()
	m := &Manager{}
	text := "# Mine\n" + srv.URL + "/dict/a/one.slob\n" +
		"https://legbehindneck.com/wudict#" + srv.URL + "/dict/b/two.slob\n" +
		"and " + srv.URL + "/dict/b/dead.slob."
	if _, err := m.BeginURL(dest, text, loopback()); err != nil {
		t.Fatal(err)
	}
	st := colReady(t, m)
	if got := candNames(st.Candidates); !slices.Equal(got, []string{"dead", "one", "two"}) {
		t.Fatalf("candidates = %v", got)
	}
	if st.Source != "Mine" {
		t.Errorf("title = %q", st.Source)
	}
	if _, err := m.Confirm(dest, []int{0, 1, 2}, Options{Keep: true}); err != nil {
		t.Fatal(err)
	}
	m.Wait()
	st = m.Status()
	if st.State != StateDone {
		t.Fatalf("state = %q (%s): one dead link must not fail the rest", st.State, st.Error)
	}
	if !slices.Equal(st.Installed, []string{"one", "two"}) {
		t.Errorf("installed = %v", st.Installed)
	}
	if !strings.HasPrefix(st.Error, "dead: ") {
		t.Errorf("error = %q, want the failure named", st.Error)
	}
}

// One link that is a share link to a single file is today's path, unchanged.
func TestShareLinkToOneFileIsASingleImport(t *testing.T) {
	s := &colSite{files: map[string]string{"a/one.slob": "one"}}
	srv := s.serve(t)
	dest := t.TempDir()
	m := &Manager{}
	if _, err := m.BeginURL(dest, "https://legbehindneck.com/wudict#"+srv.URL+"/dict/a/one.slob", loopback()); err != nil {
		t.Fatal(err)
	}
	m.Wait()
	st := m.Status()
	if st.State != StateReady || st.Collection || len(st.Candidates) != 1 || st.Candidates[0].Name != "one" {
		t.Fatalf("state=%q collection=%v candidates=%v (%s)", st.State, st.Collection, candNames(st.Candidates), st.Error)
	}
}

// A page that names no dictionary keeps a refusal, now about the right thing.
func TestCollectionOfNothingIsRefused(t *testing.T) {
	s := &colSite{files: map[string]string{"folder/readme.pdf": "x"}}
	srv := s.serve(t)
	m := &Manager{}
	if _, err := m.BeginURL(t.TempDir(), srv.URL+"/dict/folder/", loopback()); err != nil {
		t.Fatal(err)
	}
	m.Wait()
	if st := m.Status(); st.State != StateError || st.Error != ErrNoLinks.Error() {
		t.Fatalf("state = %q, error = %q", st.State, st.Error)
	}
}

// The report that led here: the dictionaries were already in the library, in
// another configured folder, loose - and the import folder is only the first
// one. A dictionary of the same NAME anywhere in the library is reported, and
// the same files at the same sizes are told apart from a different copy.
func TestCollectionKnowsTheWholeLibrary(t *testing.T) {
	s := &colSite{files: map[string]string{
		"folder/en-eu.mdx": "english basque",
		"folder/en-eu.mdd": "media",
		"folder/eu-es.mdx": "basque spanish",
		"folder/new.slob":  "new one",
	}}
	srv := s.serve(t)
	dest := t.TempDir()
	other := filepath.Join(t.TempDir(), "Euskera")
	if err := os.MkdirAll(other, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, body := range map[string]string{
		"en-eu.mdx": "english basque", "en-eu.mdd": "media", // the same files
		"EU-ES.mdx": "an older edition", // same name, another case, different size
	} {
		if err := os.WriteFile(filepath.Join(other, name), []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	m := &Manager{Library: func() []string {
		return []string{filepath.Join(other, "en-eu.mdx"), filepath.Join(other, "EU-ES.mdx")}
	}}
	if _, err := m.BeginURL(dest, srv.URL+"/dict/folder/", loopback()); err != nil {
		t.Fatal(err)
	}
	st := colReady(t, m)
	want := map[string]struct {
		where string
		same  bool
	}{"en-eu": {"Euskera", true}, "eu-es": {"Euskera", false}, "new": {"", false}}
	for _, c := range st.Candidates {
		w := want[c.Name]
		if c.Elsewhere != w.where || c.Unchanged != w.same || c.Existing != "" {
			t.Errorf("%s: elsewhere=%q unchanged=%v existing=%q, want %q/%v", c.Name, c.Elsewhere, c.Unchanged, c.Existing, w.where, w.same)
		}
	}
}
