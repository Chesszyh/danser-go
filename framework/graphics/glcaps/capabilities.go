package glcaps

import "fmt"

type Capabilities struct {
	Major               int
	Minor               int
	DirectStateAccess   bool
	BufferStorage       bool
	VertexAttribBinding bool
	ClearTexture        bool
	TextureStorage      bool
	BaseInstance        bool
	CopyImage           bool
	GetTextureSubImage  bool
	DebugOutput         bool
}

var current Capabilities

func Detect(major, minor int, supports func(string) bool) Capabilities {
	atLeast := func(wantMajor, wantMinor int) bool {
		return major > wantMajor || major == wantMajor && minor >= wantMinor
	}

	return Capabilities{
		Major:               major,
		Minor:               minor,
		DirectStateAccess:   atLeast(4, 5) || supports("GL_ARB_direct_state_access"),
		BufferStorage:       atLeast(4, 4) || supports("GL_ARB_buffer_storage"),
		VertexAttribBinding: atLeast(4, 3) || supports("GL_ARB_vertex_attrib_binding"),
		ClearTexture:        atLeast(4, 4) || supports("GL_ARB_clear_texture"),
		TextureStorage:      atLeast(4, 2) || supports("GL_ARB_texture_storage"),
		BaseInstance:        atLeast(4, 2) || supports("GL_ARB_base_instance"),
		CopyImage:           atLeast(4, 3) || supports("GL_ARB_copy_image"),
		GetTextureSubImage:  atLeast(4, 5) || supports("GL_ARB_get_texture_sub_image"),
		DebugOutput:         atLeast(4, 3) || supports("GL_KHR_debug"),
	}
}

func Set(capabilities Capabilities) {
	current = capabilities
}

func Current() Capabilities {
	return current
}

func (capabilities Capabilities) String() string {
	return fmt.Sprintf(
		"OpenGL %d.%d, DSA=%t, buffer-storage=%t, vertex-attrib-binding=%t, clear-texture=%t, texture-storage=%t, base-instance=%t, copy-image=%t, get-texture-sub-image=%t, debug-output=%t",
		capabilities.Major,
		capabilities.Minor,
		capabilities.DirectStateAccess,
		capabilities.BufferStorage,
		capabilities.VertexAttribBinding,
		capabilities.ClearTexture,
		capabilities.TextureStorage,
		capabilities.BaseInstance,
		capabilities.CopyImage,
		capabilities.GetTextureSubImage,
		capabilities.DebugOutput,
	)
}
