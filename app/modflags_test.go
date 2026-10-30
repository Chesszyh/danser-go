package app

import (
	"flag"
	"testing"
)

func TestModsArgumentDefaultsAndOverrides(t *testing.T) {
	for _, tc := range []struct {
		name      string
		args      []string
		knockout  bool
		want      string
		wantError bool
	}{
		{name: "default lazer", want: "LZ"},
		{name: "launcher stable", args: []string{"-mods2", "[]"}, want: ""},
		{name: "launcher HR autoplay", args: []string{"-mods2", `[{"acronym":"HR"},{"acronym":"AT"}]`}, want: ""},
		{name: "launcher lazer", args: []string{"-mods2", `[{"acronym":"LZ"}]`}, want: ""},
		{name: "explicit stable", args: []string{"-mods="}, want: ""},
		{name: "explicit legacy HR", args: []string{"-mods=HR"}, want: "HR"},
		{name: "explicit conflict", args: []string{"-mods=HR", "-mods2", "[]"}, wantError: true},
		{name: "explicit empty legacy with JSON", args: []string{"-mods=", "-mods2", "[]"}, want: ""},
		{name: "knockout preserves replay scoring", knockout: true, want: ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			fs := flag.NewFlagSet("danser", flag.ContinueOnError)
			mods := fs.String("mods", "LZ", "")
			mods2 := fs.String("mods2", "", "")
			if err := fs.Parse(tc.args); err != nil {
				t.Fatal(err)
			}
			got, err := resolveModsArgument(fs, *mods, *mods2, tc.knockout)
			if (err != nil) != tc.wantError || got != tc.want {
				t.Fatalf("mods=%q error=%v; want %q, error=%v", got, err, tc.want, tc.wantError)
			}
		})
	}
}
