import AppKit
import WebKit

private struct SmokeError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

@MainActor
extension PlateApp {
    func smokeFail(_ message: String) {
        FileHandle.standardError.write(Data(("Desktop smoke test failed: " + message + "\n").utf8))
        exit(1)
    }

    func beginSmokeWhenReady() {
        guard !smokeStarted, let fixture = ProcessInfo.processInfo.environment["PLATE_SMOKE_FIXTURE"] else { return }
        smokeStarted = true
        Task {
            do {
                try await smoke(URL(fileURLWithPath: fixture))
                print("Desktop smoke test passed")
                fflush(stdout)
                NSApp.terminate(nil)
            } catch { smokeFail(error.localizedDescription) }
        }
    }

    private func js(_ body: String, _ arguments: [String: Any] = [:]) async throws -> Any? {
        try await webView.callAsyncJavaScript(body, arguments: arguments, in: nil, contentWorld: .page)
    }

    private func require(_ condition: Bool, _ message: String) throws {
        if !condition { throw SmokeError(message: message) }
    }

    private func waitFor(_ message: String, seconds: Double = 20,
                         _ check: () async throws -> Bool) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + seconds
        repeat {
            if try await check() { return }
            try await Task.sleep(nanoseconds: 150_000_000)
        } while ProcessInfo.processInfo.systemUptime < deadline
        throw SmokeError(message: "Timed out waiting for " + message)
    }

    private func menu(_ section: String, _ title: String) throws {
        guard let item = NSApp.mainMenu?.items.compactMap(\.submenu).first(where: { $0.title == section })?
                .item(withTitle: title), let action = item.action,
              NSApp.sendAction(action, to: item.target, from: item) else {
            throw SmokeError(message: "Missing menu action " + section + " → " + title)
        }
    }

    private func smoke(_ fixture: URL) async throws {
        guard let url = webView.url, let window = webView.window else {
            throw SmokeError(message: "The workspace did not appear.")
        }
        let session = URLSession(configuration: .ephemeral)
        let (_, response) = try await session.data(from: url)
        try require((response as? HTTPURLResponse)?.statusCode == 403, "Loopback accepted an unauthenticated request.")
        let privateCookie = try await js("""
            const res = await fetch("/");
            return res.ok && !document.cookie.includes("plate_desktop") &&
                res.headers.get("Content-Security-Policy").includes("script-src 'self'");
            """)
        try require(privateCookie as? Bool == true, "The WebView session or CSP is missing.")
        print("Private loopback session verified")
        fflush(stdout)

        _ = try await js("document.querySelector('#home-new').click()")
        try await waitFor("the new project artboard") {
            try await js("""
                const empty = document.querySelector("#empty-canvas");
                const card = empty.getBoundingClientRect();
                const frame = document.querySelector("#frame").getBoundingClientRect();
                const button = document.querySelector("#empty-add").getBoundingClientRect();
                return document.querySelector("#measure").textContent === "122 × 183 mm" &&
                    frame.height > frame.width && card.height > 0 && card.height < 150 &&
                    button.height >= 30 && button.height < 48 &&
                    Math.abs(card.left + card.width / 2 - frame.left - frame.width / 2) < 1 &&
                    Math.abs(card.top + card.height / 2 - frame.top - frame.height / 2) < 1;
                """) as? Bool == true
        }
        _ = try await js("document.querySelector('#empty-add').click()")
        try await waitFor("the Add panel menu") {
            try await js("return document.querySelector('#panel-types').matches(':popover-open')") as? Bool == true
        }
        _ = try await js("""
            [...document.querySelectorAll("#panel-types button")]
                .find(button => button.textContent === "Text").click();
            """)
        try await waitFor("the first panel to replace the empty state") {
            try await js("return document.querySelector('#empty-canvas').hidden && !!document.querySelector('#frame .tile')") as? Bool == true
        }
        _ = try await js("""
            document.querySelector("#figure-settings").click();
            document.querySelector('[name="swap-artboard-dimensions"]').click();
            """)
        try await waitFor("the landscape artboard") {
            try await js("""
                const frame = document.querySelector("#frame").getBoundingClientRect();
                return document.querySelector("#measure").textContent === "183 × 122 mm" && frame.width > frame.height;
                """) as? Bool == true
        }
        _ = try await js("document.querySelector('#undo').click()")
        try await waitFor("undo to restore the portrait artboard") {
            try await js("return document.querySelector('#measure').textContent === '122 × 183 mm'") as? Bool == true
        }

        try menu("File", "Open…")
        try await waitFor("the native Open panel") { window.attachedSheet is NSOpenPanel }
        (window.attachedSheet as? NSOpenPanel)?.cancel(nil)
        try await waitFor("the file picker to close") { window.attachedSheet == nil }
        let rejected = try await js("""
            try { await window.webkit.messageHandlers.plate.postMessage({kind: "arbitraryCommand"}); }
            catch (_) { return true; }
            return false;
            """)
        try require(rejected as? Bool == true, "The file picker bridge accepted an unknown action.")
        _ = try await js("location.assign('https://example.invalid/plate')")
        try await Task.sleep(nanoseconds: 350_000_000)
        try require(webView.url == url, "The WebView left the private origin.")

        application(NSApp, open: [fixture])
        try await waitFor("both plotting runtimes and all six previews", seconds: 125) {
            try await js("""
                const data = await fetch("/api/project").then(r => r.json());
                return data.project.panels.length === 6 &&
                    Object.values(data.renders).every(render => render.state === "fresh") &&
                    document.querySelectorAll("#frame img").length >= 6;
                """) as? Bool == true
        }
        print("Native Open and mixed R/Python rendering verified")
        fflush(stdout)

        let initial = try await js("""
            document.querySelector('.panel-row[data-panel="facet"]').click();
            const value = document.querySelector('input[name="x-mm"]');
            const original = value.valueAsNumber;
            value.value = original + 2;
            value.dispatchEvent(new Event("change"));
            return original;
            """) as? Double
        guard let initial else { throw SmokeError(message: "Could not edit geometry.") }
        try await waitFor("the geometry change") {
            try await js("""
                const data = await fetch("/api/project").then(r => r.json());
                return data.geometry.rects.facet.x === target;
                """, ["target": initial + 2]) as? Bool == true
        }
        _ = try await js("document.querySelector('#frame').focus()")
        try menu("Edit", "Undo")
        try await waitFor("native Edit → Undo") {
            try await js("""
                const data = await fetch("/api/project").then(r => r.json());
                return data.geometry.rects.facet.x === target;
                """, ["target": initial]) as? Bool == true
        }

        try menu("File", "Save As…")
        try await waitFor("the save dialog") {
            try await js("return document.querySelector('#save-dialog').open") as? Bool == true
        }
        _ = try await js("document.querySelector('#browse-bundle').click()")
        try await waitFor("the native Save dialog") {
            window.attachedSheet is NSSavePanel && !(window.attachedSheet is NSOpenPanel)
        }
        (window.attachedSheet as? NSSavePanel)?.cancel(nil)
        try await waitFor("the save picker to close") { window.attachedSheet == nil }
        let saved = fixture.deletingLastPathComponent().appendingPathComponent("Saved.plate")
        _ = try await js("""
            document.querySelector("#bundle-path").value = path;
            document.querySelector("#save-form button[type=submit]").click();
            """, ["path": saved.path])
        try await waitFor("the saved bundle") { FileManager.default.fileExists(atPath: saved.path) }

        try menu("File", "Export…")
        try await waitFor("the export dialog") {
            try await js("return document.querySelector('#export-dialog').open") as? Bool == true
        }
        _ = try await js("document.querySelector('#browse-export').click()")
        try await waitFor("the native export destination picker") { window.attachedSheet is NSSavePanel }
        (window.attachedSheet as? NSSavePanel)?.cancel(nil)
        try await waitFor("the export picker to close") { window.attachedSheet == nil }
        let pdf = fixture.deletingLastPathComponent().appendingPathComponent("Desktop.pdf")
        _ = try await js("""
            document.querySelector("#export-path").value = path;
            document.querySelector("#submit-export").click();
            """, ["path": pdf.path])
        try await waitFor("the exported PDF") { FileManager.default.fileExists(atPath: pdf.path) }
        print("Geometry, native file sheets, save, and export verified")
        fflush(stdout)

        try menu("Plate", "Settings…")
        guard let settings = NSApp.windows.first(where: { $0.title == "Plate Settings" }),
              let stack = settings.contentView?.subviews.first as? NSStackView,
              let picker = stack.arrangedSubviews.last as? NSPopUpButton, let action = picker.action else {
            throw SmokeError(message: "Native Settings did not open.")
        }
        let original = picker.indexOfSelectedItem
        picker.selectItem(at: 2)
        NSApp.sendAction(action, to: picker.target, from: picker)
        try await waitFor("dark appearance") {
            try await js("""
                return document.documentElement.dataset.appearance === 'dark' &&
                    getComputedStyle(document.querySelector('#frame')).backgroundColor === 'rgb(255, 255, 255)';
                """) as? Bool == true
        }
        picker.selectItem(at: original)
        NSApp.sendAction(action, to: picker.target, from: picker)
        settings.close()

        _ = try await js("""
            const request = window.fetch;
            window.smokePolls = 0;
            window.fetch = (...args) => {
                if (args[0] === "/api/scripts") window.smokePolls++;
                return request(...args);
            };
            """)
        try await waitFor("visible polling") { (try await js("return window.smokePolls") as? Int ?? 0) > 0 }
        window.performClose(nil)
        try require(!window.isVisible, "Closing the window left it visible.")
        try await Task.sleep(nanoseconds: 350_000_000)
        let hiddenPolls = try await js("return window.smokePolls") as? Int
        try await Task.sleep(nanoseconds: 1_400_000_000)
        let stillHidden = try await js("return window.smokePolls") as? Int
        try require(hiddenPolls == stillHidden, "The hidden window kept polling.")
        _ = applicationShouldHandleReopen(NSApp, hasVisibleWindows: false)
        try await waitFor("polling after reopening") {
            (try await js("return window.smokePolls") as? Int ?? 0) > (hiddenPolls ?? 0)
        }
        let beforeWake = try await js("return window.smokePolls") as? Int ?? 0
        NSWorkspace.shared.notificationCenter.post(name: NSWorkspace.didWakeNotification, object: nil)
        try await waitFor("polling after the wake notification", seconds: 3) {
            (try await js("return window.smokePolls") as? Int ?? 0) > beforeWake
        }
        print("Dark appearance, close/reopen, and polling pause verified")
        fflush(stdout)

        let seconds = Double(ProcessInfo.processInfo.environment["PLATE_SMOKE_SOAK"] ?? "") ?? 0
        if seconds > 0 {
            let deadline = ProcessInfo.processInfo.systemUptime + seconds
            var cycles = 0
            while ProcessInfo.processInfo.systemUptime < deadline {
                _ = try await js("""
                    document.querySelector('.panel-row[data-panel="facet"]').click();
                    document.querySelector("#edit-script").click();
                    document.querySelector("#close-editor").click();
                    document.querySelector("#show-checks").click();
                    document.querySelector("#figure-settings").click();
                    """)
                cycles += 1
                try await Task.sleep(nanoseconds: 3_000_000_000)
            }
            print("Completed \(cycles) editor and inspector cycles in \(Int(seconds)) seconds.")
        }
    }
}
