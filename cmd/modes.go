package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"strings"
)

// mode is one entry of the run-mode table (API-12, R-65). A mode that is not built carries no
// run function: it can only refuse, naming the phase that delivers it and the BLOCKERS entry.
type mode struct {
	name    string
	built   bool
	phase   string
	blocker string
	run     func() error
}

// ModeUnavailableError is returned for a run mode that has not been built.
type ModeUnavailableError struct {
	Mode    string
	Phase   string
	Blocker string
}

func (e *ModeUnavailableError) Error() string {
	return fmt.Sprintf("--%s is unavailable: it is delivered in %s (see %s in .planning/BLOCKERS.md)", e.Mode, e.Phase, e.Blocker)
}

// usageError reports bad flag usage (exit code 2).
type usageError struct{ msg string }

func (e *usageError) Error() string { return e.msg }

func modeTable(runAPI func() error) []mode {
	return []mode{
		{name: "api", built: true, run: runAPI},
		{name: "admin", phase: "Phase 8", blocker: "B-07"},
		{name: "ingestor", phase: "v2 (mirrors D-01)", blocker: "B-07"},
		{name: "syncer", phase: "v2 (mirrors D-01)", blocker: "B-07"},
		{name: "migrate", built: true, run: runMigrate},
	}
}

func usage(table []mode) string {
	names := make([]string, len(table))
	for i, m := range table {
		names[i] = "--" + m.name
	}
	return "usage: ragflow_server exactly one of " + strings.Join(names, " | ")
}

// selectMode parses args and returns the single requested mode.
func selectMode(table []mode, args []string, out io.Writer) (mode, error) {
	fs := flag.NewFlagSet("ragflow_server", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	set := make(map[string]*bool, len(table))
	for _, m := range table {
		set[m.name] = fs.Bool(m.name, false, "run the "+m.name+" mode")
	}
	if err := fs.Parse(args); err != nil {
		return mode{}, &usageError{msg: err.Error() + "\n" + usage(table)}
	}
	var chosen []mode
	for _, m := range table {
		if *set[m.name] {
			chosen = append(chosen, m)
		}
	}
	switch len(chosen) {
	case 1:
		return chosen[0], nil
	case 0:
		return mode{}, &usageError{msg: "no run mode given\n" + usage(table)}
	default:
		return mode{}, &usageError{msg: "more than one run mode given\n" + usage(table)}
	}
}

// execute runs the selected mode and returns the process exit code.
func execute(args []string, runAPI func() error, stderr io.Writer) int {
	table := modeTable(runAPI)
	m, err := selectMode(table, args, stderr)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	if !m.built || m.run == nil {
		fmt.Fprintln(stderr, &ModeUnavailableError{Mode: m.name, Phase: m.phase, Blocker: m.blocker})
		return 2
	}
	if err := m.run(); err != nil {
		var ue *usageError
		if errors.As(err, &ue) {
			fmt.Fprintln(stderr, err)
			return 2
		}
		fmt.Fprintln(stderr, "error:", err)
		return 1
	}
	return 0
}
