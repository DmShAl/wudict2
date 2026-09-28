// Copyright (C) 2026 glowinthedark
//
// SPDX-License-Identifier: GPL-3.0-or-later

package server

import (
	"errors"
	"io/fs"
	"net/http"

	"github.com/wuweidict/wudict/internal/howto"
)

// handleHowtoCopy puts an editable copy of the wudict howto into the folder
// imports go to, then rescans: the copy is listed in place of the built-in
// guide (Builtin), and the user can open it in any editor and watch a change
// appear. The same destination and the same rules as an import (intake.go).
func (s *Server) handleHowtoCopy(w http.ResponseWriter, r *http.Request) {
	dir := s.importDir()
	if dir == "" {
		httpErr(w, 409, "no dictionary folder is configured")
		return
	}
	p, err := howto.CopyTo(dir)
	switch {
	case errors.Is(err, fs.ErrExist):
		httpErr(w, 409, "%s is already in %s", howto.FileName, dir)
		return
	case err != nil:
		httpErr(w, 500, "%v", err)
		return
	}
	if err := s.reg.Rescan(); err != nil {
		httpErr(w, 500, "%v", err)
		return
	}
	s.reg.Warm()
	writeJSON(w, map[string]string{"path": p})
}
