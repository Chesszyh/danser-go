package buffer

import (
	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/graphics/history"
	color2 "github.com/wieku/danser-go/framework/math/color"
	"github.com/wieku/danser-go/framework/profiler"
	"runtime"

	"github.com/go-gl/gl/v3.3-core/gl"
	"github.com/wieku/danser-go/framework/graphics/texture"
)

// Framebuffer is a fixed resolution texture that you can draw on.
type Framebuffer struct {
	handle uint32

	width  int
	height int

	tex             *texture.TextureSingle
	texs            []texture.Texture
	multisampled    bool
	helperHandle    uint32
	helperTexture   uint32
	depth           uint32
	texRenderbuffer uint32

	disposed bool
}

// NewFrame creates a new fully transparent Framebuffer with given dimensions in pixels.
func NewFrame(width, height int, smooth, depth bool) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height

	f.tex = texture.NewTextureSingle(width, height, 0)

	createFramebuffer(&f.handle)

	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT0, f.tex.GetID(), 0, 0)

	if depth {
		createRenderbuffer(&f.depth)

		setRenderbufferStorage(f.depth, gl.DEPTH_COMPONENT, int32(width), int32(height))
		attachFramebufferRenderbuffer(f.handle, gl.DEPTH_ATTACHMENT, f.depth)
	}

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameF(width, height int) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height

	f.tex = texture.NewTextureSingleFormat(width, height, texture.RGBA32F, 0)
	f.tex.SetFiltering(texture.Filtering.Nearest, texture.Filtering.Nearest)

	createFramebuffer(&f.handle)

	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT0, f.tex.GetID(), 0, 0)

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameLayer(texture texture.Texture, layer int) *Framebuffer {
	f := new(Framebuffer)
	f.width = int(texture.GetWidth())
	f.height = int(texture.GetHeight())

	createFramebuffer(&f.handle)

	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT0, texture.GetID(), 0, int32(layer))

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameDepth(width, height int, smooth bool) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height

	f.tex = texture.NewTextureSingleFormat(width, height, texture.Depth, 0)

	createFramebuffer(&f.handle)

	attachFramebufferTextureLayer(f.handle, gl.DEPTH_ATTACHMENT, f.tex.GetID(), 0, 0)

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameMultisample(width, height int, samples int) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height
	f.multisampled = true

	createFramebuffer(&f.handle)

	createRenderbuffer(&f.texRenderbuffer)
	setRenderbufferStorageMultisample(f.texRenderbuffer, int32(samples), texture.RGBA.InternalFormat(), int32(width), int32(height))
	attachFramebufferRenderbuffer(f.handle, gl.COLOR_ATTACHMENT0, f.texRenderbuffer)

	f.tex = texture.NewTextureSingle(width, height, 0)

	createFramebuffer(&f.helperHandle)
	attachFramebufferTextureLayer(f.helperHandle, gl.COLOR_ATTACHMENT0, f.tex.GetID(), 0, 0)

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameMultisampleScreen(width, height int, depth bool, samples int) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height
	f.multisampled = true

	createFramebuffer(&f.handle)

	createRenderbuffer(&f.texRenderbuffer)
	setRenderbufferStorageMultisample(f.texRenderbuffer, int32(samples), texture.RGBA.InternalFormat(), int32(width), int32(height))
	attachFramebufferRenderbuffer(f.handle, gl.COLOR_ATTACHMENT0, f.texRenderbuffer)

	if depth {
		createRenderbuffer(&f.depth)
		setRenderbufferStorageMultisample(f.depth, int32(samples), gl.DEPTH_COMPONENT, int32(width), int32(height))
		attachFramebufferRenderbuffer(f.handle, gl.DEPTH_ATTACHMENT, f.depth)
	}

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameYUV(width, height int) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height

	f.texs = append(f.texs, texture.NewTextureSingleFormat(width, height, texture.Red, 0))
	f.texs = append(f.texs, texture.NewTextureSingleFormat(width, height, texture.Red, 0))
	f.texs = append(f.texs, texture.NewTextureSingleFormat(width, height, texture.Red, 0))

	createFramebuffer(&f.handle)

	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT0, f.texs[0].GetID(), 0, 0)
	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT1, f.texs[1].GetID(), 0, 0)
	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT2, f.texs[2].GetID(), 0, 0)

	attchs := []uint32{gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1, gl.COLOR_ATTACHMENT2}

	setFramebufferDrawBuffers(f.handle, attchs)

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func NewFrameYUVSmall(width, height int) *Framebuffer {
	f := new(Framebuffer)
	f.width = width
	f.height = height

	f.texs = append(f.texs, texture.NewTextureSingleFormat(width, height, texture.RG, 0))
	f.texs = append(f.texs, texture.NewTextureSingleFormat(width, height, texture.Red, 0))

	createFramebuffer(&f.handle)

	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT0, f.texs[0].GetID(), 0, 0)
	attachFramebufferTextureLayer(f.handle, gl.COLOR_ATTACHMENT1, f.texs[1].GetID(), 0, 0)

	attchs := []uint32{gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1}

	setFramebufferDrawBuffers(f.handle, attchs)

	runtime.SetFinalizer(f, (*Framebuffer).Dispose)

	return f
}

func (f *Framebuffer) Dispose() {
	if !f.disposed {
		goroutines.CallNonBlockMain(func() {
			if f.tex != nil {
				f.tex.Dispose()
			}

			if f.texs != nil && len(f.texs) > 0 {
				for _, tex := range f.texs {
					tex.Dispose()
				}
			}

			if f.depth > 0 {
				gl.DeleteRenderbuffers(1, &f.depth)
			}

			if f.texRenderbuffer > 0 {
				gl.DeleteRenderbuffers(1, &f.texRenderbuffer)
			}

			if f.helperHandle > 0 {
				gl.DeleteFramebuffers(1, &f.helperHandle)
			}

			if f.helperTexture > 0 {
				gl.DeleteTextures(1, &f.helperTexture)
			}

			gl.DeleteFramebuffers(1, &f.handle)
		})
	}

	f.disposed = true
}

// GetID returns the OpenGL framebuffer ID of this Framebuffer.
func (f *Framebuffer) GetID() uint32 {
	return f.handle
}

// Bind binds the Framebuffer. All draw operations will target this Framebuffer until Unbind is called.
func (f *Framebuffer) Bind() {
	history.Push(gl.FRAMEBUFFER_BINDING, f.handle)
	gl.BindFramebuffer(gl.FRAMEBUFFER, f.handle)
	profiler.IncrementStat(profiler.FBOBinds)
}

// Unbind unbinds the Framebuffer. All draw operations will go to whatever was bound before this Framebuffer.
func (f *Framebuffer) Unbind() {
	handle := history.Pop(gl.FRAMEBUFFER_BINDING)

	if f.multisampled {
		hHandle := f.helperHandle
		if hHandle == 0 {
			hHandle = handle
		}

		resolveFramebuffer(f.handle, hHandle, int32(f.width), int32(f.height))
	}

	if handle != 0 {
		profiler.IncrementStat(profiler.FBOBinds)
	}
	gl.BindFramebuffer(gl.FRAMEBUFFER, handle)
}

// Texture returns the Framebuffer's underlying Texture that the Framebuffer draws on.
func (f *Framebuffer) Texture() texture.Texture {
	return f.tex
}

func (f *Framebuffer) Textures() []texture.Texture {
	return f.texs
}

func (f *Framebuffer) GetWidth() int {
	return f.width
}

func (f *Framebuffer) GetHeight() int {
	return f.height
}

func (f *Framebuffer) ClearColor(r, g, b, a float32) {
	col := []float32{r, g, b, a}
	clearFramebuffer(f.handle, gl.COLOR, 0, &col[0])
}

func (f *Framebuffer) ClearColorI(index int, r, g, b, a float32) {
	col := []float32{r, g, b, a}
	clearFramebuffer(f.handle, gl.COLOR, int32(index), &col[0])
}

func (f *Framebuffer) ClearColorM(color color2.Color) {
	glColor := color.ToArray()
	clearFramebuffer(f.handle, gl.COLOR, 0, &glColor[0])
}

func (f *Framebuffer) ClearColorIM(index int, color color2.Color) {
	glColor := color.ToArray()
	clearFramebuffer(f.handle, gl.COLOR, int32(index), &glColor[0])
}

func (f *Framebuffer) ClearDepthV(v float32) {
	clearFramebuffer(f.handle, gl.DEPTH, 0, &v)
}

func (f *Framebuffer) ClearDepth() {
	f.ClearDepthV(1)
}
