import Cocoa
import WebKit
import CoreGraphics
import Carbon

class DraggableOverlayWebView: WKWebView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }

    override func mouseDown(with event: NSEvent) {
        window?.performDrag(with: event)
    }
}

class OverlayDragSurfaceView: NSView {
    private var dragStartMouseLocation: CGPoint?
    private var dragStartWindowOrigin: CGPoint?

    override var acceptsFirstResponder: Bool {
        return true
    }

    override var mouseDownCanMoveWindow: Bool {
        return true
    }

    override var isOpaque: Bool {
        return false
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        return self
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: NSCursor.openHand)
    }

    override func mouseDown(with event: NSEvent) {
        dragStartMouseLocation = NSEvent.mouseLocation
        dragStartWindowOrigin = window?.frame.origin
        NSCursor.closedHand.push()
    }

    override func mouseDragged(with event: NSEvent) {
        guard
            let startMouseLocation = dragStartMouseLocation,
            let startWindowOrigin = dragStartWindowOrigin,
            let window = window
        else {
            return
        }

        let currentMouseLocation = NSEvent.mouseLocation
        let nextOrigin = CGPoint(
            x: startWindowOrigin.x + currentMouseLocation.x - startMouseLocation.x,
            y: startWindowOrigin.y + currentMouseLocation.y - startMouseLocation.y
        )
        window.setFrameOrigin(nextOrigin)
    }

    override func mouseUp(with event: NSEvent) {
        dragStartMouseLocation = nil
        dragStartWindowOrigin = nil
        NSCursor.pop()
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var webView: WKWebView?
    var hotKeyRef: EventHotKeyRef?
    var hotKeyHandler: EventHandlerRef?
    let frameDefaultsKey = "JarvisOverlayWindowFrame"

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenFrame = screen.visibleFrame

        let windowSize = CGSize(width: 380, height: 460)
        let padding: CGFloat = 50
        let defaultWindowFrame = CGRect(
            x: screenFrame.maxX - windowSize.width - padding,
            y: screenFrame.minY + padding,
            width: windowSize.width,
            height: windowSize.height
        )
        let windowFrame = savedWindowFrame(defaultFrame: defaultWindowFrame)

        window = NSWindow(
            contentRect: windowFrame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )

        guard let window = window else { return }

        window.isOpaque = false
        window.backgroundColor = NSColor.clear
        window.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.screenSaverWindow)))
        window.ignoresMouseEvents = false
        window.isMovableByWindowBackground = true
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]

        let webViewConfig = WKWebViewConfiguration()
        webViewConfig.defaultWebpagePreferences.allowsContentJavaScript = true

        let contentView = OverlayDragSurfaceView(frame: CGRect(origin: .zero, size: windowFrame.size))
        contentView.wantsLayer = true
        contentView.layer?.isOpaque = false
        contentView.layer?.backgroundColor = NSColor.clear.cgColor
        window.contentView = contentView

        webView = DraggableOverlayWebView(
            frame: contentView.bounds,
            configuration: webViewConfig
        )
        guard let webView = webView else { return }

        webView.autoresizingMask = [.width, .height]
        webView.wantsLayer = true
        webView.layer?.isOpaque = false
        webView.layer?.backgroundColor = NSColor.clear.cgColor

        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = .clear
        }
        webView.setValue(false, forKey: "drawsBackground")

        contentView.addSubview(webView)

        loadOverlayHTML()
        window.orderFrontRegardless()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(windowDidMove(_:)),
            name: NSWindow.didMoveNotification,
            object: window
        )
        registerGlobalHotKey()
    }

    func savedWindowFrame(defaultFrame: CGRect) -> CGRect {
        guard let frameString = UserDefaults.standard.string(forKey: frameDefaultsKey) else {
            return defaultFrame
        }
        let frame = NSRectFromString(frameString)
        guard
            frame.width > 0,
            frame.height > 0,
            NSScreen.screens.contains(where: { $0.visibleFrame.intersects(frame) })
        else {
            return defaultFrame
        }
        return frame
    }

    @objc func windowDidMove(_ notification: Notification) {
        guard let frame = window?.frame else { return }
        UserDefaults.standard.set(NSStringFromRect(frame), forKey: frameDefaultsKey)
    }

    func loadOverlayHTML() {
        if
            let overlayURLString = ProcessInfo.processInfo.environment["JARVIS_OVERLAY_URL"],
            let overlayURL = URL(string: overlayURLString)
        {
            webView?.load(URLRequest(url: overlayURL))
            return
        }

        guard
            let webView = webView,
            let resourcesURL = Bundle.main.resourceURL,
            let overlayURL = Bundle.main.url(forResource: "overlay", withExtension: "html")
        else {
            webView?.loadHTMLString(
                "<!doctype html><meta charset=\"utf-8\"><body style=\"background:transparent\"></body>",
                baseURL: Bundle.main.resourceURL
            )
            return
        }

        do {
            let htmlContent = try String(contentsOf: overlayURL, encoding: .utf8)
            webView.loadHTMLString(htmlContent, baseURL: resourcesURL)
        } catch {
            NSLog("JARVIS overlay failed to load HTML: \(error.localizedDescription)")
            webView.loadHTMLString(
                "<!doctype html><meta charset=\"utf-8\"><body style=\"background:transparent\"></body>",
                baseURL: resourcesURL
            )
        }
    }

    func registerGlobalHotKey() {
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )

        let callback: EventHandlerUPP = { _, _, userData in
            guard let userData = userData else { return noErr }
            let delegate = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
            DispatchQueue.main.async {
                delegate.handleHotKey()
            }
            return noErr
        }

        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            callback,
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &hotKeyHandler
        )

        guard handlerStatus == noErr else {
            NSLog("JARVIS overlay hotkey handler registration failed: \(handlerStatus)")
            return
        }

        let hotKeyID = EventHotKeyID(signature: fourCharCode("JRVS"), id: 1)
        let hotKeyStatus = RegisterEventHotKey(
            UInt32(kVK_ANSI_J),
            UInt32(controlKey | optionKey),
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )

        if hotKeyStatus != noErr {
            NSLog("JARVIS overlay hotkey registration failed: \(hotKeyStatus)")
        }
    }

    func unregisterGlobalHotKey() {
        if let hotKeyRef = hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let hotKeyHandler = hotKeyHandler {
            RemoveEventHandler(hotKeyHandler)
            self.hotKeyHandler = nil
        }
    }

    func handleHotKey() {
        webView?.evaluateJavaScript(
            "window.jarvisActivateVoice && window.jarvisActivateVoice();",
            completionHandler: nil
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let window = window {
            UserDefaults.standard.set(NSStringFromRect(window.frame), forKey: frameDefaultsKey)
        }
        NotificationCenter.default.removeObserver(self)
        unregisterGlobalHotKey()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool {
        return true
    }
}

func fourCharCode(_ string: String) -> OSType {
    var result: UInt32 = 0
    for scalar in string.unicodeScalars.prefix(4) {
        result = (result << 8) + UInt32(scalar.value)
    }
    return OSType(result)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
