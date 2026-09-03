package env

import "testing"

func TestIsMacOSBundleExecutable(t *testing.T) {
	tests := []struct {
		name    string
		path    string
		bundled bool
	}{
		{name: "app bundle", path: "/Applications/danser.app/Contents/MacOS", bundled: true},
		{name: "case insensitive suffix", path: "/Applications/Danser.APP/Contents/MacOS", bundled: true},
		{name: "ordinary executable directory", path: "/usr/local/bin", bundled: false},
		{name: "missing app suffix", path: "/Applications/danser/Contents/MacOS", bundled: false},
		{name: "wrong contents directory", path: "/Applications/danser.app/Resources/MacOS", bundled: false},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if bundled := isMacOSBundleExecutable(test.path); bundled != test.bundled {
				t.Fatalf("isMacOSBundleExecutable(%q) = %t, want %t", test.path, bundled, test.bundled)
			}
		})
	}
}
