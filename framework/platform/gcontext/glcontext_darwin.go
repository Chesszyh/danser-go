//go:build darwin

package gcontext

import "github.com/Zyko0/go-sdl3/sdl"

func configureGLContext() {
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_MAJOR_VERSION, 4)
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_MINOR_VERSION, 1)
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_PROFILE_MASK, sdl.GL_CONTEXT_PROFILE_CORE)

	// macOS requires the forward-compatible bit when creating a 3.2+ core context.
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_FLAGS, 0x0002)
}
