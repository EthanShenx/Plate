import Foundation

final class Backend {
    let token = UUID().uuidString + UUID().uuidString
    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()

    init(resources: URL, python: String, plotPython: String, support: URL) throws {
        try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        let log = support.appendingPathComponent("backend.log")
        try Data().write(to: log, options: .atomic)

        process.executableURL = URL(fileURLWithPath: python)
        process.currentDirectoryURL = resources
        process.arguments = ["-I", "-B", resources.appendingPathComponent("backend.py").path,
                             "--desktop", "--workspaces", support.appendingPathComponent("workspaces").path]
        var environment = ProcessInfo.processInfo.environment
        environment["PLATE_DESKTOP_TOKEN"] = token
        environment["PLATE_DEFAULT_PYTHON"] = plotPython
        process.environment = environment
        process.standardInput = input
        process.standardOutput = output
        process.standardError = try FileHandle(forWritingTo: log)
    }

    func start(ready: @escaping (URL?) -> Void, exited: @escaping (Int32) -> Void) throws {
        process.terminationHandler = { child in
            DispatchQueue.main.async { exited(child.terminationStatus) }
        }
        try process.run()
        try? input.fileHandleForReading.close()
        try? output.fileHandleForWriting.close()
        let stream = output.fileHandleForReading
        DispatchQueue.global(qos: .utility).async {
            var line = Data()
            while line.count < 128, let byte = try? stream.read(upToCount: 1), !byte.isEmpty {
                if byte.first == 10 { break }
                line.append(byte)
            }
            let prefix = "Plate is running at "
            let message = String(decoding: line, as: UTF8.self)
            let url = message.hasPrefix(prefix) ? URL(string: String(message.dropFirst(prefix.count))) : nil
            let valid = url.map { $0.scheme == "http" && $0.host == "127.0.0.1" &&
                $0.port != nil && $0.path.isEmpty && $0.user == nil && $0.password == nil &&
                $0.query == nil && $0.fragment == nil } ?? false
            DispatchQueue.main.async { ready(valid ? url : nil) }
        }
    }

    func stop() {
        try? input.fileHandleForWriting.close()
    }

    deinit { stop() }
}
