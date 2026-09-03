//go:build !darwin

package gcontext

import "github.com/Zyko0/go-sdl3/sdl"

func configureGLContext() {
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_MAJOR_VERSION, 3)
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_MINOR_VERSION, 3)
	_ = sdl.GL_SetAttribute(sdl.GL_CONTEXT_PROFILE_MASK, sdl.GL_CONTEXT_PROFILE_CORE)
}
