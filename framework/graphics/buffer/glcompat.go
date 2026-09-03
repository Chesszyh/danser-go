package buffer

import (
	"unsafe"

	"github.com/go-gl/gl/v3.3-core/gl"

	"github.com/wieku/danser-go/framework/graphics/glcaps"
)

func createBuffer(handle *uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.CreateBuffers(1, handle)
	} else {
		gl.GenBuffers(1, handle)
	}
}

func withArrayBuffer(handle uint32, action func()) {
	var previous int32
	gl.GetIntegerv(gl.ARRAY_BUFFER_BINDING, &previous)
	gl.BindBuffer(gl.ARRAY_BUFFER, handle)
	action()
	gl.BindBuffer(gl.ARRAY_BUFFER, uint32(previous))
}

func setBufferData(handle uint32, size int, data unsafe.Pointer, usage uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedBufferData(handle, size, data, usage)
	} else {
		withArrayBuffer(handle, func() {
			gl.BufferData(gl.ARRAY_BUFFER, size, data, usage)
		})
	}
}

func setBufferSubData(handle uint32, offset, size int, data unsafe.Pointer) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedBufferSubData(handle, offset, size, data)
	} else {
		withArrayBuffer(handle, func() {
			gl.BufferSubData(gl.ARRAY_BUFFER, offset, size, data)
		})
	}
}

func setBufferStorage(handle uint32, size int, data unsafe.Pointer, flags uint32) {
	if glcaps.Current().DirectStateAccess {
		gl.NamedBufferStorage(handle, size, data, flags)
	} else {
		withArrayBuffer(handle, func() {
			gl.BufferStorage(gl.ARRAY_BUFFER, size, data, flags)
		})
	}
}

func mapBufferRange(handle uint32, offset, length int, access uint32) unsafe.Pointer {
	if glcaps.Current().DirectStateAccess {
		return gl.MapNamedBufferRange(handle, offset, length, access)
	}

	var pointer unsafe.Pointer
	withArrayBuffer(handle, func() {
		pointer = gl.MapBufferRange(gl.ARRAY_BUFFER, offset, length, access)
	})

	return pointer
}
