// JARVIS helper for Apple's on-device Foundation Model (macOS 26+, Apple Intelligence on).
//
//   jarvis-fm --check          -> {"available": true} or {"available": false, "reason": "..."}
//   jarvis-fm < request.json   -> {"text": "..."}             (request: {"instructions", "prompt"})
//   jarvis-fm --stream < req   -> {"delta": "..."} per line, then {"done": true}
//
// Built on demand by jarvis/core/providers/apple_fm.py with swiftc.
import Foundation
import FoundationModels

struct Request: Decodable {
    let instructions: String
    let prompt: String
}

func emit(_ object: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: object),
       let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
}

@main
struct JarvisFM {
    static func main() async {
        let args = CommandLine.arguments
        let model = SystemLanguageModel.default

        if args.contains("--check") {
            switch model.availability {
            case .available:
                emit(["available": true])
            case .unavailable(let reason):
                emit(["available": false, "reason": String(describing: reason)])
            }
            return
        }

        let input = FileHandle.standardInput.readDataToEndOfFile()
        guard let request = try? JSONDecoder().decode(Request.self, from: input) else {
            emit(["error": "invalid request"])
            exit(1)
        }
        guard case .available = model.availability else {
            emit(["error": "model unavailable"])
            exit(1)
        }

        let session = LanguageModelSession(instructions: request.instructions)
        do {
            if args.contains("--stream") {
                var sent = ""
                for try await snapshot in session.streamResponse(to: request.prompt) {
                    let text = snapshot.content
                    if text.hasPrefix(sent) {
                        let delta = String(text.dropFirst(sent.count))
                        if !delta.isEmpty { emit(["delta": delta]) }
                    } else {
                        emit(["delta": text])
                    }
                    sent = text
                }
                emit(["done": true])
            } else {
                let response = try await session.respond(to: request.prompt)
                emit(["text": response.content])
            }
        } catch {
            emit(["error": String(describing: error)])
            exit(1)
        }
    }
}
