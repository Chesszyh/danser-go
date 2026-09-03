package glcaps

import "testing"

func TestDetectOpenGL41Compatibility(t *testing.T) {
	supported := map[string]bool{
		"GL_ARB_texture_storage": true,
	}

	capabilities := Detect(4, 1, func(extension string) bool {
		return supported[extension]
	})

	if capabilities.DirectStateAccess || capabilities.BufferStorage || capabilities.VertexAttribBinding || capabilities.ClearTexture || capabilities.BaseInstance || capabilities.CopyImage || capabilities.GetTextureSubImage || capabilities.DebugOutput {
		t.Fatalf("OpenGL 4.1 unexpectedly enabled a post-4.1 capability: %+v", capabilities)
	}

	if !capabilities.TextureStorage {
		t.Fatal("ARB_texture_storage should enable immutable texture storage")
	}
}

func TestDetectModernCoreCapabilities(t *testing.T) {
	capabilities := Detect(4, 5, func(string) bool { return false })

	if !capabilities.DirectStateAccess || !capabilities.BufferStorage || !capabilities.VertexAttribBinding || !capabilities.ClearTexture || !capabilities.TextureStorage || !capabilities.BaseInstance || !capabilities.CopyImage || !capabilities.GetTextureSubImage || !capabilities.DebugOutput {
		t.Fatalf("OpenGL 4.5 should expose all core capabilities: %+v", capabilities)
	}
}

func TestDetectExtensionCapabilities(t *testing.T) {
	supported := map[string]bool{
		"GL_ARB_direct_state_access":   true,
		"GL_ARB_buffer_storage":        true,
		"GL_ARB_vertex_attrib_binding": true,
		"GL_ARB_clear_texture":         true,
		"GL_ARB_texture_storage":       true,
		"GL_ARB_base_instance":         true,
		"GL_ARB_copy_image":            true,
		"GL_ARB_get_texture_sub_image": true,
		"GL_KHR_debug":                 true,
	}

	capabilities := Detect(3, 3, func(extension string) bool {
		return supported[extension]
	})

	if !capabilities.DirectStateAccess || !capabilities.BufferStorage || !capabilities.VertexAttribBinding || !capabilities.ClearTexture || !capabilities.TextureStorage || !capabilities.BaseInstance || !capabilities.CopyImage || !capabilities.GetTextureSubImage || !capabilities.DebugOutput {
		t.Fatalf("extensions should enable all optional capabilities: %+v", capabilities)
	}
}
