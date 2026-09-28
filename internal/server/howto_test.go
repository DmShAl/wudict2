// Copyright (C) 2026 glowinthedark
//
// SPDX-License-Identifier: GPL-3.0-or-later

package server

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	_ "github.com/wuweidict/wudict/internal/format/wmd"
	"github.com/wuweidict/wudict/internal/howto"
)

// TestBuiltinGuide: the wudict howto is listed under its fixed id beside the
// user's dictionaries, cannot be removed, and stands down for the user's own
// copy - which POST /api/howto puts in the import folder.
func TestBuiltinGuide(t *testing.T) {
	t.Setenv("WUDICT_DB_DIR", t.TempDir())
	guide, err := howto.Install(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	folder := t.TempDir()
	reg, err := NewRegistry([]string{folder}, false, WithBuiltin(Builtin{ID: howto.ID, Path: guide}))
	if err != nil {
		t.Fatal(err)
	}
	e, err := reg.get(howto.ID)
	if err != nil {
		t.Fatalf("the guide is not listed under %q: %v", howto.ID, err)
	}
	s := New(reg)
	if info := s.dictInfoFor(e); !info.Builtin || info.Name != "wudict howto" {
		t.Errorf("row = builtin %v, name %q", info.Builtin, info.Name)
	}
	if _, err := reg.Remove(howto.ID, true, true); err == nil {
		t.Error("the built-in guide was removable")
	}
	if _, err := os.Stat(guide); err != nil {
		t.Errorf("the guide file is gone: %v", err)
	}

	rec := httptest.NewRecorder()
	s.handleHowtoCopy(rec, httptest.NewRequest(http.MethodPost, "/api/howto", nil))
	if rec.Code != 200 {
		t.Fatalf("copy: %d %s", rec.Code, rec.Body)
	}
	var got struct{ Path string }
	json.Unmarshal(rec.Body.Bytes(), &got)
	if got.Path != filepath.Join(folder, howto.FileName) {
		t.Errorf("copied to %q", got.Path)
	}
	// The copy stands in under the guide's id, so the guide's own links
	// (/browse?dict=wudict-howto) reach it - and it is the user's file.
	ce, err := reg.get(howto.ID)
	if err != nil {
		t.Fatalf("the copy is not listed under %q: %v", howto.ID, err)
	}
	// the same file, however the scan spelled its path (/var vs /private/var)
	if a, b := stat(t, ce.Path), stat(t, got.Path); !os.SameFile(a, b) {
		t.Errorf("listed under %q: %s, want the copy %s", howto.ID, ce.Path, got.Path)
	}
	if ce.builtin {
		t.Error("the user's copy is flagged builtin")
	}
	if reg.Count() != 1 {
		t.Errorf("%d dictionaries listed, want the user's copy alone", reg.Count())
	}
	rec = httptest.NewRecorder()
	s.handleHowtoCopy(rec, httptest.NewRequest(http.MethodPost, "/api/howto", nil))
	if rec.Code != 409 {
		t.Errorf("second copy: %d, want 409", rec.Code)
	}
}

func stat(t *testing.T, p string) os.FileInfo {
	t.Helper()
	fi, err := os.Stat(p)
	if err != nil {
		t.Fatal(err)
	}
	return fi
}
