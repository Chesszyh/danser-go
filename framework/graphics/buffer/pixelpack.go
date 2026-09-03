package buffer

import (
	"unsafe"

	"github.com/go-gl/gl/v3.3-core/gl"

	"github.com/wieku/danser-go/framework/graphics/glcaps"
)

type PixelPackBuffer struct {
	handle     uint32
	data       []byte
	persistent bool
}

func NewPixelPackBuffer(size int) *PixelPackBuffer {
	buffer := &PixelPackBuffer{persistent: glcaps.Current().BufferStorage}
	createBuffer(&buffer.handle)

	if buffer.persistent {
		flags := uint32(gl.MAP_PERSISTENT_BIT | gl.MAP_COHERENT_BIT | gl.MAP_READ_BIT)
		setPixelPackStorage(buffer.handle, size, flags)
		pointer := mapPixelPackRange(buffer.handle, size, flags)
		buffer.data = unsafe.Slice((*byte)(pointer), size)
	} else {
		buffer.data = make([]byte, size)
		withPixelPackBuffer(buffer.handle, func() {
			gl.BufferData(gl.PIXEL_PACK_BUFFER, size, nil, gl.STREAM_READ)
		})
	}

	return buffer
}

func (buffer *PixelPackBuffer) ID() uint32 {
	return buffer.handle
}

func (buffer *PixelPackBuffer) Data() []byte {
	return buffer.data
}

func (buffer *PixelPackBuffer) Download() {
	if buffer.persistent {
		return
	}

	withPixelPackBuffer(buffer.handle, func() {
		gl.GetBufferSubData(gl.PIXEL_PACK_BUFFER, 0, len(buffer.data), gl.Ptr(buffer.data))
	})
}

func (buffer *PixelPackBuffer) Dispose() {
	gl.DeleteBuffers(1, &buffer.handle)
}

func withPixelPackBuffer(handle uint32, action func()) {
	var previous int32
	gl.GetIntegerv(gl.PIXEL_PACK_BUFFER_BINDING, &previous)
	gl.BindBuffer(gl.PIXEL_PACK_BUFFER, handle)
	action()
	gl.BindBuffer(gl.PIXEL_PACK_BUFFER, uint32(previous))
}

func setPixelPackStorage(handle uint32, size int, flags uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedBufferStorage(handle, size, nil, flags)
	} else {
		withPixelPackBuffer(handle, func() {
			gl.BufferStorage(gl.PIXEL_PACK_BUFFER, size, nil, flags)
		})
	}
}

func mapPixelPackRange(handle uint32, size int, flags uint32) unsafe.Pointer {
	if glcaps.Current().DirectStateAccess {
		return gl.MapNamedBufferRange(handle, 0, size, flags)
	}

	var pointer unsafe.Pointer
	withPixelPackBuffer(handle, func() {
		pointer = gl.MapBufferRange(gl.PIXEL_PACK_BUFFER, 0, size, flags)
	})

	return pointer
}
