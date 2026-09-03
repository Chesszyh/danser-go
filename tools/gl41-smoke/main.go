package main

import (
	"fmt"
	"os"
	"runtime"
	"unsafe"

	"github.com/Zyko0/go-sdl3/sdl"
	"github.com/go-gl/gl/v3.3-core/gl"

	"github.com/wieku/danser-go/framework/env"
	"github.com/wieku/danser-go/framework/goroutines"
	"github.com/wieku/danser-go/framework/graphics/buffer"
	"github.com/wieku/danser-go/framework/graphics/texture"
	"github.com/wieku/danser-go/framework/platform/gcontext"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: gl41-smoke <macOS dependency directory>")
		os.Exit(2)
	}

	runtime.LockOSThread()
	goroutines.RunMain(func() {
		goroutines.CallMain(runSmoke)
	})
}

func runSmoke() {
	if err := os.Setenv("DANSER_MACOS_DEPS_DIR", os.Args[1]); err != nil {
		panic(err)
	}

	env.Init("danser")
	if err := gcontext.Initialize(true); err != nil {
		panic(err)
	}
	gcontext.SDLCreateWindow(64, 64, "danser OpenGL 4.1 smoke test", gcontext.OptionalProps{Hidden: true})
	if err := gcontext.GLInit(false); err != nil {
		panic(err)
	}

	testTextureCopy()
	testMultisampleResolve()
	testInputEvents()
	fmt.Println("OpenGL 4.1 texture copy, readback, MSAA resolve, and SDL input events: PASS")
}

func testTextureCopy() {
	tex := texture.NewTextureMultiLayer(2, 2, 1, 1)
	defer tex.Dispose()

	red := []byte{
		255, 0, 0, 255, 255, 0, 0, 255,
		255, 0, 0, 255, 255, 0, 0, 255,
	}
	tex.SetData(0, 0, 2, 2, 0, red)
	tex.NewLayer()

	pixels := make([]byte, 2*2*4*2)
	texture.ReadPixels(tex, gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
	if !equalBytes(pixels[:len(red)], red) {
		panic("texture layer was not preserved during expansion")
	}
	for _, value := range pixels[len(red):] {
		if value != 0 {
			panic("new texture layer was not cleared")
		}
	}
	checkGLError("texture copy and readback")
}

func testMultisampleResolve() {
	framebuffer := buffer.NewFrameMultisample(8, 8, 4)
	defer framebuffer.Dispose()

	framebuffer.Bind()
	gl.ClearColor(0, 1, 0, 1)
	gl.Clear(gl.COLOR_BUFFER_BIT)
	framebuffer.Unbind()

	pixels := make([]byte, 8*8*4)
	texture.ReadPixels(framebuffer.Texture(), gl.RGBA, gl.UNSIGNED_BYTE, int32(len(pixels)), gl.Ptr(pixels))
	for offset := 0; offset < len(pixels); offset += 4 {
		if pixels[offset] != 0 || pixels[offset+1] != 255 || pixels[offset+2] != 0 || pixels[offset+3] != 255 {
			panic(fmt.Sprintf("unexpected resolved pixel at %d: %v", offset/4, pixels[offset:offset+4]))
		}
	}
	checkGLError("multisample resolve")
}

func testInputEvents() {
	var received []gcontext.Action
	gcontext.RegisterListener(func(event gcontext.KeyEvent) {
		received = append(received, event.Action)
	})

	pushKeyEvent(sdl.EVENT_KEY_DOWN, true)
	gcontext.HandleEvents()
	if gcontext.GetKeyState(sdl.K_A) != gcontext.Press {
		panic("SDL key-down event did not update keyboard state")
	}

	pushKeyEvent(sdl.EVENT_KEY_UP, false)
	gcontext.HandleEvents()
	if gcontext.GetKeyState(sdl.K_A) != gcontext.Release {
		panic("SDL key-up event did not update keyboard state")
	}
	if len(received) != 2 || received[0] != gcontext.Press || received[1] != gcontext.Release {
		panic(fmt.Sprintf("unexpected keyboard listener actions: %v", received))
	}
}

func pushKeyEvent(eventType sdl.EventType, down bool) {
	var event sdl.Event
	*(*sdl.KeyboardEvent)(unsafe.Pointer(&event)) = sdl.KeyboardEvent{
		Type:     eventType,
		Scancode: sdl.SCANCODE_A,
		Key:      sdl.K_A,
		Down:     down,
	}
	if err := sdl.PushEvent(&event); err != nil {
		panic(err)
	}
}

func equalBytes(left, right []byte) bool {
	if len(left) != len(right) {
		return false
	}
	for i := range left {
		if left[i] != right[i] {
			return false
		}
	}
	return true
}

func checkGLError(operation string) {
	if glError := gl.GetError(); glError != gl.NO_ERROR {
		panic(fmt.Sprintf("%s generated OpenGL error 0x%x", operation, glError))
	}
}
