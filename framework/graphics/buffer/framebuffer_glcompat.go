package buffer

import (
	"github.com/go-gl/gl/v3.3-core/gl"

	"github.com/wieku/danser-go/framework/graphics/glcaps"
)

func createFramebuffer(handle *uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.CreateFramebuffers(1, handle)
	} else {
		gl.GenFramebuffers(1, handle)
	}
}

func createRenderbuffer(handle *uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.CreateRenderbuffers(1, handle)
	} else {
		gl.GenRenderbuffers(1, handle)
	}
}

func withDrawFramebuffer(handle uint32, action func()) {
	var previous int32
	gl.GetIntegerv(gl.DRAW_FRAMEBUFFER_BINDING, &previous)
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, handle)
	action()
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, uint32(previous))
}

func withReadFramebuffer(handle uint32, action func()) {
	var previous int32
	gl.GetIntegerv(gl.READ_FRAMEBUFFER_BINDING, &previous)
	gl.BindFramebuffer(gl.READ_FRAMEBUFFER, handle)
	action()
	gl.BindFramebuffer(gl.READ_FRAMEBUFFER, uint32(previous))
}

func attachFramebufferTextureLayer(framebuffer, attachment, texture uint32, level, layer int32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedFramebufferTextureLayer(framebuffer, attachment, texture, level, layer)
	} else {
		withDrawFramebuffer(framebuffer, func() {
			gl.FramebufferTextureLayer(gl.DRAW_FRAMEBUFFER, attachment, texture, level, layer)
		})
	}
}

func setRenderbufferStorage(renderbuffer, internalFormat uint32, width, height int32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedRenderbufferStorage(renderbuffer, internalFormat, width, height)
		return
	}

	var previous int32
	gl.GetIntegerv(gl.RENDERBUFFER_BINDING, &previous)
	gl.BindRenderbuffer(gl.RENDERBUFFER, renderbuffer)
	gl.RenderbufferStorage(gl.RENDERBUFFER, internalFormat, width, height)
	gl.BindRenderbuffer(gl.RENDERBUFFER, uint32(previous))
}

func setRenderbufferStorageMultisample(renderbuffer uint32, samples int32, internalFormat uint32, width, height int32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedRenderbufferStorageMultisample(renderbuffer, samples, internalFormat, width, height)
		return
	}

	var previous int32
	gl.GetIntegerv(gl.RENDERBUFFER_BINDING, &previous)
	gl.BindRenderbuffer(gl.RENDERBUFFER, renderbuffer)
	gl.RenderbufferStorageMultisample(gl.RENDERBUFFER, samples, internalFormat, width, height)
	gl.BindRenderbuffer(gl.RENDERBUFFER, uint32(previous))
}

func attachFramebufferRenderbuffer(framebuffer, attachment, renderbuffer uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedFramebufferRenderbuffer(framebuffer, attachment, gl.RENDERBUFFER, renderbuffer)
	} else {
		withDrawFramebuffer(framebuffer, func() {
			gl.FramebufferRenderbuffer(gl.DRAW_FRAMEBUFFER, attachment, gl.RENDERBUFFER, renderbuffer)
		})
	}
}

func setFramebufferDrawBuffers(framebuffer uint32, buffers []uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedFramebufferDrawBuffers(framebuffer, int32(len(buffers)), &buffers[0])
	} else {
		withDrawFramebuffer(framebuffer, func() {
			gl.DrawBuffers(int32(len(buffers)), &buffers[0])
		})
	}
}

func resolveFramebuffer(source, destination uint32, width, height int32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedFramebufferReadBuffer(source, gl.COLOR_ATTACHMENT0)
		if destination > 0 {
			gl.NamedFramebufferDrawBuffer(destination, gl.COLOR_ATTACHMENT0)
		}
		gl.BlitNamedFramebuffer(source, destination, 0, 0, width, height, 0, 0, width, height, gl.COLOR_BUFFER_BIT, gl.LINEAR)
		return
	}

	var previousRead, previousDraw int32
	gl.GetIntegerv(gl.READ_FRAMEBUFFER_BINDING, &previousRead)
	gl.GetIntegerv(gl.DRAW_FRAMEBUFFER_BINDING, &previousDraw)
	gl.BindFramebuffer(gl.READ_FRAMEBUFFER, source)
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, destination)
	gl.ReadBuffer(gl.COLOR_ATTACHMENT0)
	if destination > 0 {
		gl.DrawBuffer(gl.COLOR_ATTACHMENT0)
	} else {
		gl.DrawBuffer(gl.BACK)
	}
	gl.BlitFramebuffer(0, 0, width, height, 0, 0, width, height, gl.COLOR_BUFFER_BIT, gl.LINEAR)
	gl.BindFramebuffer(gl.READ_FRAMEBUFFER, uint32(previousRead))
	gl.BindFramebuffer(gl.DRAW_FRAMEBUFFER, uint32(previousDraw))
}

func clearFramebuffer(framebuffer, buffer uint32, drawBuffer int32, value *float32) {
	if glcaps.Current().DirectStateAccess {
		gl.ClearNamedFramebufferfv(framebuffer, buffer, drawBuffer, value)
	} else {
		withDrawFramebuffer(framebuffer, func() {
			gl.ClearBufferfv(buffer, drawBuffer, value)
		})
	}
}
