package app

import (
	"flag"
	"fmt"
)

func resolveModsArgument(flags *flag.FlagSet, mods, mods2 string, knockout bool) (string, error) {
	explicit := false
	flags.Visit(func(f *flag.Flag) { explicit = explicit || f.Name == "mods" })
	if explicit && mods != "" && mods2 != "" {
		return "", fmt.Errorf("You can't specify classic and lazer mods at the same time")
	}
	if !explicit && (mods2 != "" || knockout) {
		return "", nil
	}
	return mods, nil
}
