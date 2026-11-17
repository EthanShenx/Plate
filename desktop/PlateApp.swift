import AppKit
import UniformTypeIdentifiers
import WebKit

final class PlateWebView: WKWebView {
    var appearanceChanged: (() -> Void)?

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        appearanceChanged?()
    }
}

@MainActor
final class PlateApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate,
                     WKUIDelegate, WKScriptMessageHandlerWithReply, NSMenuItemValidation {
    private let settingsKey = "PlateAppearance"
    private let frameName = "Plate Main Window"
    private let bridgeName = "plate"
    private let defaults = UserDefaults.standard
    private var backend: Backend?
    private var origin: URL?
    private var ready = false
    private var starting = false
    private var quitting = false
    private var recovering = false
    private var dialog: NSSavePanel?
    private var settings: NSWindow?
    private var pendingFile: URL?
    private var window: NSWindow!
    private(set) var webView: PlateWebView!
    #if PLATE_SMOKE
    var smokeStarted = false
    #endif
    private let plateType = UTType(exportedAs: "org.platesci.figure", conformingTo: .data)

    var supportDirectory: URL {
        #if PLATE_SMOKE
        if let path = ProcessInfo.processInfo.environment["PLATE_SMOKE_SUPPORT"] {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        #endif
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Plate/Desktop", isDirectory: true)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        configureMenus()
        applyAppearance()
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: bridgeName)
        webView = PlateWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = false
        webView.isInspectable = defaults.bool(forKey: "PlateWebInspector")
        webView.appearanceChanged = { [weak self] in self?.updateAppearance() }

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1250, height: 820),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Plate"
        window.contentMinSize = NSSize(width: 880, height: 580)
        window.tabbingMode = .disallowed
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.delegate = self
        window.center()
        window.setFrameUsingName(frameName)
        window.setFrameAutosaveName(frameName)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(woke),
            name: NSWorkspace.didWakeNotification, object: nil)
        showWindow()
        startBackend()
    }

    private func startBackend() {
        guard !starting, !quitting, let resources = Bundle.main.resourceURL else { return }
        starting = true
        ready = false
        origin = nil
        window.subtitle = "Starting Plate…"
        do {
            guard let python = Bundle.main.infoDictionary?["PlatePython"] as? String,
                  FileManager.default.isExecutableFile(atPath: python) else {
                throw CocoaError(.fileNoSuchFile, userInfo: [
                    NSLocalizedDescriptionKey: "The Python installation used to build Plate is unavailable. Rebuild the app with make macos."
                ])
            }
            let plotPython = Bundle.main.infoDictionary?["PlatePlotPython"] as? String ?? ""
            let next = try Backend(resources: resources, python: python, plotPython: plotPython,
                                   support: supportDirectory)
            try next.start { [weak self, weak next] url in
                guard let self, let next, self.backend === next, !self.quitting else { return }
                self.starting = false
                guard let url else {
                    self.backend = nil
                    next.stop()
                    self.showBackendError("The local rendering service could not start.")
                    return
                }
                self.load(url, token: next.token)
            } exited: { [weak self, weak next] status in
                guard let self, let next, self.backend === next, !self.quitting else { return }
                self.backend = nil
                self.ready = false
                self.starting = false
                self.showBackendError("The local rendering service exited (status \(status)).")
            }
            backend = next
        } catch {
            starting = false
            showBackendError(error.localizedDescription)
        }
    }

    private func load(_ url: URL, token: String) {
        origin = url
        let header = ["Set-Cookie": "plate_desktop=\(token); Path=/; HttpOnly; SameSite=Strict"]
        guard let cookie = HTTPCookie.cookies(withResponseHeaderFields: header, for: url).first,
              cookie.isHTTPOnly else {
            showBackendError("Plate could not create a private session.")
            return
        }
        webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { [weak self] in
            guard let self, self.origin == url, !self.quitting else { return }
            self.webView.load(URLRequest(url: url))
        }
    }

    private func showBackendError(_ message: String) {
        ready = false
        window.subtitle = "Plate could not start"
        #if PLATE_SMOKE
        if ProcessInfo.processInfo.environment["PLATE_SMOKE_SUPPORT"] != nil {
            smokeFail(message)
            return
        }
        #endif
        let alert = NSAlert()
        alert.messageText = message
        alert.informativeText = "Backend log: " + supportDirectory.appendingPathComponent("backend.log").path
        alert.addButton(withTitle: "Restart")
        alert.addButton(withTitle: "Close")
        alert.beginSheetModal(for: window) { [weak self] response in
            guard let self else { return }
            if response == .alertFirstButtonReturn {
                self.backend?.stop()
                self.backend = nil
                self.startBackend()
            } else { self.window.orderOut(nil) }
        }
    }

    private func isLocal(_ url: URL?) -> Bool {
        guard let url, let origin else { return false }
        return url.scheme == origin.scheme && url.host == origin.host && url.port == origin.port &&
            url.user == nil && url.password == nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(action.targetFrame?.isMainFrame == true && isLocal(action.request.url) ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(response.isForMainFrame && isLocal(response.response.url) ? .allow : .cancel)
        if let http = response.response as? HTTPURLResponse, http.statusCode >= 400 {
            showBackendError("Plate could not load the workspace (HTTP \(http.statusCode)).")
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled && !quitting { showBackendError(error.localizedDescription) }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        ready = false
        guard !quitting else { return }
        if let origin, !recovering {
            recovering = true
            window.subtitle = "Restoring the workspace…"
            webView.load(URLRequest(url: origin))
        } else {
            showBackendError("The workspace renderer stopped.")
        }
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler reply: @escaping (Any?, String?) -> Void) {
        guard message.name == bridgeName, message.webView === webView, message.frameInfo.isMainFrame,
              isLocal(message.frameInfo.request.url), let body = message.body as? [String: Any],
              let kind = body["kind"] as? String else {
            reply(nil, "Unrecognized Plate request.")
            return
        }
        if kind == "ready" {
            ready = true
            recovering = false
            window.subtitle = ""
            reply(NSNull(), nil)
            updateVisibility()
            updateAppearance()
            if let url = pendingFile {
                pendingFile = nil
                openFile(url)
            }
            #if PLATE_SMOKE
            beginSmokeWhenReady()
            #endif
            return
        }
        guard ready, window.isVisible, window.attachedSheet == nil, dialog == nil else {
            reply(nil, "A Plate window must be open to choose a file.")
            return
        }
        let panel: NSSavePanel
        switch kind {
        case "openProject", "openRaster", "openVector", "chooseFolder":
            let open = NSOpenPanel()
            open.allowsMultipleSelection = false
            open.canChooseFiles = kind != "chooseFolder"
            open.canChooseDirectories = kind == "chooseFolder"
            switch kind {
            case "openProject": open.allowedContentTypes = [plateType]
            case "openVector": open.allowedContentTypes = [.pdf, .svg]
            case "openRaster": open.allowedContentTypes = [.png, .jpeg, .tiff, .webP]
            default: break
            }
            panel = open
        case "saveProject", "saveStyle", "exportPDF", "exportPNG", "exportTIFF":
            let save = NSSavePanel()
            save.allowedContentTypes = ["saveProject": plateType, "saveStyle": .json, "exportPDF": .pdf,
                                        "exportPNG": .png, "exportTIFF": .tiff][kind].map { [$0] } ?? []
            save.canCreateDirectories = true
            save.isExtensionHidden = false
            if let name = body["suggested"] as? String {
                save.nameFieldStringValue = String((name as NSString).lastPathComponent.prefix(240))
            }
            panel = save
        default:
            reply(nil, "Unknown file dialog.")
            return
        }
        dialog = panel
        panel.beginSheetModal(for: window) { [weak self] result in
            self?.dialog = nil
            if result == .OK, let path = panel.url?.path { reply(path, nil) }
            else { reply(NSNull(), nil) }
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler done: @escaping () -> Void) {
        guard frame.isMainFrame, isLocal(frame.request.url) else { done(); return }
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window) { _ in done() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler done: @escaping (Bool) -> Void) {
        guard frame.isMainFrame, isLocal(frame.request.url) else { done(false); return }
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { done($0 == .alertFirstButtonReturn) }
    }

    private func showWindow() {
        if window.isMiniaturized { window.deminiaturize(nil) }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        updateVisibility()
    }

    @objc private func showWorkspace(_ sender: Any?) { showWindow() }
    @objc private func woke(_ notification: Notification) { updateVisibility() }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        if window != nil { showWindow() }
        return false
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        if let url = urls.first(where: { $0.isFileURL && $0.pathExtension.lowercased() == "plate" }) {
            openFile(url)
        }
    }

    private func openFile(_ url: URL) {
        guard ready else { pendingFile = url; return }
        showWindow()
        send("openPath", url.path)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        window.saveFrame(usingName: frameName)
        window.orderOut(nil)
        updateVisibility()
        return false
    }

    func windowDidMiniaturize(_ notification: Notification) { updateVisibility() }
    func windowDidDeminiaturize(_ notification: Notification) { updateVisibility() }
    func applicationDidHide(_ notification: Notification) { updateVisibility() }
    func applicationDidUnhide(_ notification: Notification) { updateVisibility() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    private func updateVisibility() {
        send("visibility", window.isVisible && !window.isMiniaturized && !NSApp.isHidden)
    }

    private func applyAppearance() {
        switch defaults.string(forKey: settingsKey) {
        case "light": NSApp.appearance = NSAppearance(named: .aqua)
        case "dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        default: NSApp.appearance = nil
        }
        updateAppearance()
    }

    private func updateAppearance() {
        guard let webView else { return }
        let dark = webView.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        send("appearance", dark ? "dark" : "light")
    }

    @objc private func appearanceSelected(_ sender: NSPopUpButton) {
        defaults.set(["system", "light", "dark"][sender.indexOfSelectedItem], forKey: settingsKey)
        applyAppearance()
    }

    @objc private func showSettings(_ sender: Any?) {
        if settings == nil {
            let choices = NSPopUpButton(frame: .zero, pullsDown: false)
            choices.addItems(withTitles: ["System", "Light", "Dark"])
            choices.selectItem(at: ["system", "light", "dark"].firstIndex(of: defaults.string(forKey: settingsKey) ?? "") ?? 0)
            choices.target = self
            choices.action = #selector(appearanceSelected(_:))
            let row = NSStackView(views: [NSTextField(labelWithString: "Appearance"), choices])
            row.spacing = 16
            let container = NSView()
            row.translatesAutoresizingMaskIntoConstraints = false
            container.addSubview(row)
            NSLayoutConstraint.activate([
                row.centerYAnchor.constraint(equalTo: container.centerYAnchor),
                row.centerXAnchor.constraint(equalTo: container.centerXAnchor)
            ])
            let panel = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 360, height: 140),
                                 styleMask: [.titled, .closable], backing: .buffered, defer: false)
            panel.title = "Plate Settings"
            panel.contentView = container
            panel.isReleasedWhenClosed = false
            panel.center()
            settings = panel
        }
        settings?.makeKeyAndOrderFront(nil)
    }

    private func send(_ name: String, _ value: Any = NSNull(),
                      done: (@MainActor @Sendable (Result<Any, Error>) -> Void)? = nil) {
        guard ready else { return }
        webView.callAsyncJavaScript("return await window.plateDesktopCommand(name, value)",
                                    arguments: ["name": name, "value": value], in: nil, in: .page,
                                    completionHandler: done)
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateLater }
        if !ready { return .terminateNow }
        quitting = true
        send("prepareQuit") { [weak self] result in
            guard let self else { return }
            if case let .success(value) = result, value as? Bool == true {
                sender.reply(toApplicationShouldTerminate: true)
            } else {
                self.showWindow()
                let alert = NSAlert()
                alert.messageText = "Plate could not save your script edits."
                alert.addButton(withTitle: "Keep Plate Open")
                alert.addButton(withTitle: "Quit Without Saving")
                alert.beginSheetModal(for: self.window) { response in
                    let discard = response == .alertSecondButtonReturn
                    self.quitting = discard
                    sender.reply(toApplicationShouldTerminate: discard)
                }
            }
        }
        return .terminateLater
    }

    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        window?.saveFrame(usingName: frameName)
        webView?.configuration.userContentController.removeScriptMessageHandler(forName: bridgeName)
        NSWorkspace.shared.notificationCenter.removeObserver(self)
        backend?.stop()
    }

    @objc private func runCommand(_ sender: NSMenuItem) {
        if let name = sender.representedObject as? String {
            showWindow()
            send(name)
        }
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        item.action != #selector(runCommand(_:)) || ready
    }

    private func configureMenus() {
        let menu = NSMenu()
        func section(_ title: String) -> NSMenu {
            let root = NSMenuItem()
            root.submenu = NSMenu(title: title)
            menu.addItem(root)
            return root.submenu!
        }
        @discardableResult
        func entry(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "",
                   firstResponder: Bool = false) -> NSMenuItem {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
            if !firstResponder { item.target = self }
            menu.addItem(item)
            return item
        }
        func command(_ menu: NSMenu, _ title: String, _ name: String, _ key: String, shift: Bool = false) {
            let item = entry(menu, title, #selector(runCommand(_:)), key)
            item.representedObject = name
            if shift { item.keyEquivalentModifierMask = [.command, .shift] }
        }
        let app = section("Plate")
        entry(app, "About Plate", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), firstResponder: true)
        entry(app, "Settings…", #selector(showSettings(_:)), ",")
        app.addItem(.separator())
        entry(app, "Hide Plate", #selector(NSApplication.hide(_:)), "h", firstResponder: true)
        entry(app, "Quit Plate", #selector(NSApplication.terminate(_:)), "q", firstResponder: true)
        let file = section("File")
        command(file, "New Project", "new", "n")
        command(file, "Open…", "open", "o")
        file.addItem(.separator())
        command(file, "Save", "save", "s")
        command(file, "Save As…", "saveAs", "s", shift: true)
        command(file, "Save Shareable Copy…", "shareCopy", "")
        command(file, "Export…", "export", "e")
        file.addItem(.separator())
        entry(file, "Close Window", #selector(NSWindow.performClose(_:)), "w", firstResponder: true)
        let edit = section("Edit")
        command(edit, "Undo", "undo", "z")
        command(edit, "Redo", "redo", "z", shift: true)
        edit.addItem(.separator())
        for (label, selector, key) in [("Cut", "cut:", "x"), ("Copy", "copy:", "c"),
                                       ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            entry(edit, label, NSSelectorFromString(selector), key, firstResponder: true)
        }
        let windows = section("Window")
        entry(windows, "Minimize", #selector(NSWindow.performMiniaturize(_:)), "m", firstResponder: true)
        entry(windows, "Zoom", #selector(NSWindow.performZoom(_:)), firstResponder: true)
        entry(windows, "Show Plate", #selector(showWorkspace(_:)))
        NSApp.windowsMenu = windows
        NSApp.mainMenu = menu
    }
}

@main
struct Main {
    static func main() {
        let app = NSApplication.shared
        let delegate = PlateApp()
        app.setActivationPolicy(.regular)
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
