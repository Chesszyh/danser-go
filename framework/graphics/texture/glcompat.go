package texture

import (
	"unsafe"

	"github.com/go-gl/gl/v3.3-core/gl"

	"github.com/wieku/danser-go/framework/graphics/glcaps"
	color2 "github.com/wieku/danser-go/framework/math/color"
)

func createTexture(target uint32, handle *uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.CreateTextures(target, 1, handle)
	} else {
		gl.GenTextures(1, handle)
	}
}

func withTexture2DArray(handle uint32, action func()) {
	var previous int32
	gl.GetIntegerv(gl.TEXTURE_BINDING_2D_ARRAY, &previous)
	gl.BindTexture(gl.TEXTURE_2D_ARRAY, handle)
	action()
	gl.BindTexture(gl.TEXTURE_2D_ARRAY, uint32(previous))
}

func allocateTextureStorage(store *textureStore) {
	if glcaps.Current().DirectStateAccess {
		gl.TextureStorage3D(store.id, store.mipmaps, store.format.InternalFormat(), store.width, store.height, store.layers)
		return
	}

	withTexture2DArray(store.id, func() {
		if glcaps.Current().TextureStorage {
			gl.TexStorage3D(gl.TEXTURE_2D_ARRAY, store.mipmaps, store.format.InternalFormat(), store.width, store.height, store.layers)
			return
		}

		width, height := store.width, store.height
		for level := int32(0); level < store.mipmaps; level++ {
			gl.TexImage3D(gl.TEXTURE_2D_ARRAY, level, int32(store.format.InternalFormat()), width, height, store.layers, 0, store.format.Format(), store.format.Type(), nil)
			width = max(1, width/2)
			height = max(1, height/2)
		}
	})
}

func setTextureParameter(handle, parameter uint32, value int32) {
	if glcaps.Current().DirectStateAccess {
		gl.TextureParameteri(handle, parameter, value)
	} else {
		withTexture2DArray(handle, func() {
			gl.TexParameteri(gl.TEXTURE_2D_ARRAY, parameter, value)
		})
	}
}

func setTextureData(store *textureStore, x, y, width, height, layer int, data unsafe.Pointer) {
	if glcaps.Current().DirectStateAccess {
		gl.TextureSubImage3D(store.id, 0, int32(x), int32(y), int32(layer), int32(width), int32(height), 1, store.format.Format(), store.format.Type(), data)
	} else {
		withTexture2DArray(store.id, func() {
			gl.TexSubImage3D(gl.TEXTURE_2D_ARRAY, 0, int32(x), int32(y), int32(layer), int32(width), int32(height), 1, store.format.Format(), store.format.Type(), data)
		})
	}
}

func generateTextureMipmaps(handle uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.GenerateTextureMipmap(handle)
	} else {
		withTexture2DArray(handle, func() {
			gl.GenerateMipmap(gl.TEXTURE_2D_ARRAY)
		})
	}
}

func BindTextureUnit(target uint32, location uint, handle uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.BindTextureUnit(uint32(location), handle)
		return
	}

	var previousActive int32
	gl.GetIntegerv(gl.ACTIVE_TEXTURE, &previousActive)
	gl.ActiveTexture(gl.TEXTURE0 + uint32(location))
	gl.BindTexture(target, handle)
	gl.ActiveTexture(uint32(previousActive))
}

func clearTexture(store *textureStore, clearColor color2.Color) {
	if glcaps.Current().ClearTexture {
		if store.format.Type() == gl.FLOAT {
			color := clearColor.ToArray()
			gl.ClearTexImage(store.id, 0, store.format.Format(), store.format.Type(), gl.Ptr(&color[0]))
		} else {
			color := clearColor.ToIntArray()
			gl.ClearTexImage(store.id, 0, store.format.Format(), store.format.Type(), gl.Ptr(&color[0]))
		}
		return
	}

	var previousDrawFramebuffer int32
	gl.GetIntegerv(gl.DRAW_FRAMEBUFFER_BINDING, &previousDrawFramebuffer)

	var framebuffer uint32
	gl.GenFramebuffers(1, &framebuffer)
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, framebuffer)
	color := clearColor.ToArray()

	for layer := int32(0); layer < store.layers; layer++ {
		if store.format == Depth {
			gl.FramebufferTextureLayer(gl.DRAW_FRAMEBUFFER, gl.DEPTH_ATTACHMENT, store.id, 0, layer)
			gl.DrawBuffer(gl.NONE)
			gl.ClearBufferfv(gl.DEPTH, 0, &color[0])
		} else {
			gl.FramebufferTextureLayer(gl.DRAW_FRAMEBUFFER, gl.COLOR_ATTACHMENT0, store.id, 0, layer)
			gl.DrawBuffer(gl.COLOR_ATTACHMENT0)
			gl.ClearBufferfv(gl.COLOR, 0, &color[0])
		}
	}

	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, uint32(previousDrawFramebuffer))
	gl.DeleteFramebuffers(1, &framebuffer)
}

func copyTextureLayers(source, destination *textureStore, level, width, height, layers int32) {
	if glcaps.Current().CopyImage {
		gl.CopyImageSubData(source.id, gl.TEXTURE_2D_ARRAY, level, 0, 0, 0, destination.id, gl.TEXTURE_2D_ARRAY, level, 0, 0, 0, width, height, layers)
		return
	}

	var previousReadFramebuffer, previousDrawFramebuffer int32
	gl.GetIntegerv(gl.READ_FRAMEBUFFER_BINDING, &previousReadFramebuffer)
	gl.GetIntegerv(gl.DRAW_FRAMEBUFFER_BINDING, &previousDrawFramebuffer)

	var readFramebuffer, drawFramebuffer uint32
	gl.GenFramebuffers(1, &readFramebuffer)
	gl.GenFramebuffers(1, &drawFramebuffer)
	gl.BindFramebuffer(gl.READ_FRAMEBUFFER, readFramebuffer)
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, drawFramebuffer)

	attachment := uint32(gl.COLOR_ATTACHMENT0)
	mask := uint32(gl.COLOR_BUFFER_BIT)
	if source.format == Depth {
		attachment = gl.DEPTH_ATTACHMENT
		mask = gl.DEPTH_BUFFER_BIT
		gl.ReadBuffer(gl.NONE)
		gl.DrawBuffer(gl.NONE)
	} else {
		gl.ReadBuffer(gl.COLOR_ATTACHMENT0)
		gl.DrawBuffer(gl.COLOR_ATTACHMENT0)
	}

	for layer := int32(0); layer < layers; layer++ {
		gl.FramebufferTextureLayer(gl.READ_FRAMEBUFFER, attachment, source.id, level, layer)
		gl.FramebufferTextureLayer(gl.DRAW_FRAMEBUFFER, attachment, destination.id, level, layer)
		gl.BlitFramebuffer(0, 0, width, height, 0, 0, width, height, mask, gl.NEAREST)
	}

	gl.BindFramebuffer(gl.READ_FRAMEBUFFER, uint32(previousReadFramebuffer))
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, uint32(previousDrawFramebuffer))
	gl.DeleteFramebuffers(1, &readFramebuffer)
	gl.DeleteFramebuffers(1, &drawFramebuffer)
}

func ReadPixels(source Texture, format, dataType uint32, bufferSize int32, destination unsafe.Pointer) {
	if glcaps.Current().GetTextureSubImage {
		gl.GetTextureSubImage(source.GetID(), 0, 0, 0, 0, source.GetWidth(), source.GetHeight(), source.GetLayers(), format, dataType, bufferSize, destination)
		return
	}

	withTexture2DArray(source.GetID(), func() {
		gl.GetTexImage(gl.TEXTURE_2D_ARRAY, 0, format, dataType, destination)
	})
}
