import Cocoa
import WebKit
import CoreGraphics
import Carbon

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var webView: WKWebView?
    var hotKeyRef: EventHotKeyRef?
    var hotKeyHandler: EventHandlerRef?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenFrame = screen.frame

        let windowSize = CGSize(width: 360, height: 400)
        let padding: CGFloat = 50
        let windowFrame = CGRect(
            x: screenFrame.width - windowSize.width - padding,
            y: padding,
            width: windowSize.width,
            height: windowSize.height
        )

        window = NSWindow(
            contentRect: windowFrame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )

        guard let window = window else { return }

        window.isOpaque = false
        window.backgroundColor = NSColor.clear
        window.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.floatingWindow)))
        window.ignoresMouseEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]

        let webViewConfig = WKWebViewConfiguration()
        webViewConfig.defaultWebpagePreferences.allowsContentJavaScript = true

        webView = WKWebView(
            frame: window.contentView?.bounds ?? CGRect(origin: .zero, size: windowSize),
            configuration: webViewConfig
        )
        guard let webView = webView else { return }

        webView.autoresizingMask = [.width, .height]
        webView.wantsLayer = true
        webView.layer?.backgroundColor = NSColor.clear.cgColor

        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = .clear
        }
        webView.setValue(false, forKey: "drawsBackground")

        window.contentView = webView
        loadOverlayHTML()
        window.makeKeyAndOrderFront(nil)
        registerGlobalHotKey()
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
