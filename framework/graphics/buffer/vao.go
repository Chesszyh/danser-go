package buffer

import (
	"fmt"
	"runtime"

	"github.com/go-gl/gl/v3.3-core/gl"

	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/graphics/attribute"
	"github.com/wieku/danser-go/framework/graphics/glcaps"
	"github.com/wieku/danser-go/framework/graphics/hacks"
	"github.com/wieku/danser-go/framework/graphics/history"
	"github.com/wieku/danser-go/framework/graphics/shader"
	"github.com/wieku/danser-go/framework/profiler"
)

type attributeBinding struct {
	location   uint32
	components int32
	typeID     uint32
	normalized bool
	offset     int
}

type bufferHolder struct {
	buffer     StreamingBuffer
	divisor    int
	format     attribute.Format
	binding    int
	attributes []attributeBinding
}

type VertexArrayObject struct {
	handle uint32

	buffers map[string]*bufferHolder

	capacity int

	bound    bool
	disposed bool

	ibo *IndexBufferObject

	legacyBaseInstance int
}

func NewVertexArrayObject() *VertexArrayObject {
	vao := new(VertexArrayObject)
	vao.buffers = make(map[string]*bufferHolder)
	vao.legacyBaseInstance = -1

	if vao.hasModernBinding() {
		gl.CreateVertexArrays(1, &vao.handle)
	} else {
		gl.GenVertexArrays(1, &vao.handle)
	}

	runtime.SetFinalizer(vao, (*VertexArrayObject).Dispose)

	return vao
}

func (vao *VertexArrayObject) AddVBO(name string, maxVertices int, divisor int, format attribute.Format) {
	vao.addVBO(name, maxVertices, divisor, false, format)
}

func (vao *VertexArrayObject) AddMappedVBO(name string, maxVertices int, divisor int, format attribute.Format) {
	vao.addVBO(name, maxVertices, divisor, true, format)
}

func (vao *VertexArrayObject) addVBO(name string, maxVertices int, divisor int, mapped bool, format attribute.Format) {
	if _, exists := vao.buffers[name]; exists {
		panic(fmt.Sprintf("VBO with name \"%s\" already exists", name))
	}

	holder := &bufferHolder{
		buffer:  NewVertexBufferObject(maxVertices*format.Size()/4, mapped, DynamicDraw),
		divisor: divisor,
		format:  format,
		binding: -1,
	}

	if divisor == 0 {
		vao.capacity = maxVertices
	}

	vao.buffers[name] = holder
}

func (vao *VertexArrayObject) AddPersistentVBO(name string, maxVertices int, divisor int, format attribute.Format) {
	if _, exists := vao.buffers[name]; exists {
		panic(fmt.Sprintf("VBO with name \"%s\" already exists", name))
	}

	var streamingBuffer StreamingBuffer
	if glcaps.Current().BufferStorage {
		streamingBuffer = NewPersistentBufferObject(maxVertices / 100 * format.Size() / 4)
	} else {
		streamingBuffer = NewVertexBufferObject(maxVertices*format.Size()/4, true, StreamDraw)
	}

	holder := &bufferHolder{
		buffer:  streamingBuffer,
		divisor: divisor,
		format:  format,
		binding: -1,
	}

	if holder.buffer.Capacity() != maxVertices*format.Size()/4 {
		holder.buffer.Resize(maxVertices * format.Size() / 4)
	}

	if divisor == 0 {
		vao.capacity = maxVertices
	}

	vao.buffers[name] = holder
}

func (vao *VertexArrayObject) GetVBOFormat(name string) attribute.Format {
	if holder, exists := vao.buffers[name]; exists {
		return holder.format
	}

	panic(fmt.Sprintf("VBO with name \"%s\" doesn't exist", name))
}

func (vao *VertexArrayObject) GetVBO(name string) StreamingBuffer {
	if holder, exists := vao.buffers[name]; exists {
		return holder.buffer
	}

	panic(fmt.Sprintf("VBO with name \"%s\" doesn't exist", name))
}

func (vao *VertexArrayObject) Resize(name string, maxVertices int) {
	if holder, exists := vao.buffers[name]; exists {
		size := maxVertices * holder.format.Size() / 4
		if holder.buffer.Capacity() != size {
			holder.buffer.Resize(size)

			// If we have persistent buffer object that was bound we want to bind it again because new object was created on resize
			if _, ok := holder.buffer.(*PersistentBufferObject); ok && holder.binding >= 0 {
				if vao.hasModernBinding() {
					gl.VertexArrayVertexBuffer(vao.handle, uint32(holder.binding), holder.buffer.GetID(), 0, int32(holder.format.Size()))
				} else {
					vao.configureLegacyBaseInstance(vao.legacyBaseInstance)
				}
			}
		}

		return
	}

	panic(fmt.Sprintf("VBO with name \"%s\" doesn't exist", name))
}

func (vao *VertexArrayObject) Attach(s *shader.RShader) {
	var index int
	for _, holder := range vao.buffers {
		holder.attributes = holder.attributes[:0]
		var offset int
		for _, attr := range holder.format {
			location := s.GetAttributeInfo(attr.Name).Location

			holder.attributes = append(holder.attributes, attributeBinding{
				location:   uint32(location),
				components: int32(attr.Type.Components()),
				typeID:     uint32(attr.Type.InternalType()),
				normalized: attr.Type.Normalize(),
				offset:     offset,
			})

			if vao.hasModernBinding() {
				gl.EnableVertexArrayAttrib(vao.handle, uint32(location))
				gl.VertexArrayAttribBinding(vao.handle, uint32(location), uint32(index))
				gl.VertexArrayAttribFormat(
					vao.handle,
					uint32(location),
					int32(attr.Type.Components()),
					uint32(attr.Type.InternalType()),
					attr.Type.Normalize(),
					uint32(offset),
				)
			}

			offset += attr.Type.Size()
		}

		holder.binding = index
		if vao.hasModernBinding() {
			gl.VertexArrayVertexBuffer(vao.handle, uint32(index), holder.buffer.GetID(), 0, int32(holder.format.Size()))
			gl.VertexArrayBindingDivisor(vao.handle, uint32(index), uint32(holder.divisor))
		}

		index++
	}

	if !vao.hasModernBinding() {
		vao.configureLegacyBaseInstance(0)
	}
}

func (vao *VertexArrayObject) SetData(name string, offset int, data []float32) {
	holder, exists := vao.buffers[name]
	if !exists {
		panic(fmt.Sprintf("VBO with name \"%s\" doesn't exist", name))
	}

	holder.buffer.SetData(offset, data)

	profiler.AddStat(profiler.VertexUpload, int64(len(data)*4/holder.format.Size()))
}

func (vao *VertexArrayObject) MapVBO(name string, size int) MemoryChunk {
	holder, exists := vao.buffers[name]
	if !exists {
		panic(fmt.Sprintf("VBO with name \"%s\" doesn't exist", name))
	}

	return holder.buffer.Map(size)
}

func (vao *VertexArrayObject) UnmapVBO(name string, offset int, size int) {
	holder, exists := vao.buffers[name]
	if !exists {
		panic(fmt.Sprintf("VBO with name \"%s\" doesn't exist", name))
	}

	holder.buffer.Unmap(offset, size)

	profiler.AddStat(profiler.VertexUpload, int64(size*4/holder.format.Size()))
}

func (vao *VertexArrayObject) Draw() {
	vao.prepareBaseInstance(0)
	if vao.ibo != nil {
		vao.check(0, 0)
		vao.ibo.Draw()
	} else {
		vao.DrawPart(0, vao.capacity)
	}
}

func (vao *VertexArrayObject) DrawInstanced(baseInstance, instanceCount int) {
	vao.prepareBaseInstance(baseInstance)
	if vao.ibo != nil {
		vao.check(0, 0)
		vao.ibo.DrawInstanced(baseInstance, instanceCount)
	} else {
		vao.DrawPartInstanced(0, vao.capacity, baseInstance, instanceCount)
	}
}

func (vao *VertexArrayObject) DrawPart(offset, length int) {
	vao.prepareBaseInstance(0)
	if vao.ibo != nil {
		vao.check(0, 0)
		vao.ibo.DrawPart(offset, length)
	} else {
		vao.check(offset, length)

		profiler.AddStat(profiler.VerticesDrawn, int64(length))
		profiler.IncrementStat(profiler.DrawCalls)

		gl.DrawArrays(gl.TRIANGLES, int32(offset), int32(length))

		if hacks.IsIntel {
			gl.Flush()
		}
	}
}

func (vao *VertexArrayObject) DrawPartInstanced(offset, length, baseInstance, instanceCount int) {
	vao.prepareBaseInstance(baseInstance)
	if vao.ibo != nil {
		vao.check(0, 0)
		vao.ibo.DrawPartInstanced(offset, length, baseInstance, instanceCount)
	} else {
		vao.check(offset, length)

		profiler.AddStat(profiler.VerticesDrawn, int64(length*instanceCount))
		profiler.IncrementStat(profiler.DrawCalls)

		if glcaps.Current().BaseInstance {
			gl.DrawArraysInstancedBaseInstance(gl.TRIANGLES, int32(offset), int32(length), int32(instanceCount), uint32(baseInstance))
		} else {
			gl.DrawArraysInstanced(gl.TRIANGLES, int32(offset), int32(length), int32(instanceCount))
		}

		if hacks.IsIntel {
			gl.Flush()
		}
	}
}

func (vao *VertexArrayObject) check(offset, length int) {
	currentVAO := history.GetCurrent(gl.VERTEX_ARRAY_BINDING)
	if currentVAO != vao.handle {
		panic(fmt.Sprintf("VAO mismatch. Target VAO: %d, current: %d", vao.handle, currentVAO))
	}

	if offset+length > vao.capacity {
		panic(fmt.Sprintf("Draw exceeds VAO's capacity. Draw length: %d, offset: %d, capacity: %d", length, offset, vao.capacity))
	}
}

func (vao *VertexArrayObject) hasModernBinding() bool {
	capabilities := glcaps.Current()
	return capabilities.DirectStateAccess && capabilities.VertexAttribBinding
}

func (vao *VertexArrayObject) prepareBaseInstance(baseInstance int) {
	if vao.hasModernBinding() || vao.legacyBaseInstance == baseInstance {
		return
	}

	vao.configureLegacyBaseInstance(baseInstance)
}

func (vao *VertexArrayObject) configureLegacyBaseInstance(baseInstance int) {
	var previousVAO, previousArrayBuffer int32
	gl.GetIntegerv(gl.VERTEX_ARRAY_BINDING, &previousVAO)
	gl.GetIntegerv(gl.ARRAY_BUFFER_BINDING, &previousArrayBuffer)
	gl.BindVertexArray(vao.handle)

	for _, holder := range vao.buffers {
		gl.BindBuffer(gl.ARRAY_BUFFER, holder.buffer.GetID())

		baseOffset := 0
		if holder.divisor > 0 {
			baseOffset = baseInstance * holder.format.Size()
		}

		for _, attr := range holder.attributes {
			gl.EnableVertexAttribArray(attr.location)
			gl.VertexAttribPointer(attr.location, attr.components, attr.typeID, attr.normalized, int32(holder.format.Size()), gl.PtrOffset(baseOffset+attr.offset))
			gl.VertexAttribDivisor(attr.location, uint32(holder.divisor))
		}
	}

	gl.BindBuffer(gl.ARRAY_BUFFER, uint32(previousArrayBuffer))
	gl.BindVertexArray(uint32(previousVAO))
	vao.legacyBaseInstance = baseInstance
}

func (vao *VertexArrayObject) Bind() {
	if vao.disposed {
		panic("Can't bind disposed VAO")
	}

	if vao.bound {
		panic(fmt.Sprintf("VAO %d is already bound", vao.handle))
	}

	vao.bound = true

	history.Push(gl.VERTEX_ARRAY_BINDING, vao.handle)

	profiler.IncrementStat(profiler.VAOBinds)

	gl.BindVertexArray(vao.handle)
}

func (vao *VertexArrayObject) Unbind() {
	if !vao.bound || vao.disposed {
		return
	}

	vao.bound = false

	handle := history.Pop(gl.VERTEX_ARRAY_BINDING)

	if handle > 0 {
		profiler.IncrementStat(profiler.VAOBinds)
	}

	gl.BindVertexArray(handle)
}

func (vao *VertexArrayObject) Dispose() {
	if !vao.disposed {
		for _, holder := range vao.buffers {
			holder.buffer.Dispose()
		}

		goroutines.CallNonBlockMain(func() {
			gl.DeleteVertexArrays(1, &vao.handle)
		})
	}

	vao.disposed = true
}

func (vao *VertexArrayObject) AttachIBO(ibo *IndexBufferObject) {
	ibo.attached = true
	vao.ibo = ibo
	if vao.hasModernBinding() {
		gl.VertexArrayElementBuffer(vao.handle, ibo.handle)
	} else {
		var previousVAO int32
		gl.GetIntegerv(gl.VERTEX_ARRAY_BINDING, &previousVAO)
		gl.BindVertexArray(vao.handle)
		gl.BindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo.handle)
		gl.BindVertexArray(uint32(previousVAO))
	}
}
