#!/usr/bin/env swift
// macos_ocr.swift — Native Vision framework OCR helper
// Usage: swift macos_ocr.swift /path/to/image.png
// Output: JSON array of detected text strings

import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    print("[]")
    exit(1)
}

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("[]")
    exit(1)
}

var results: [[String: Any]] = []
let semaphore = DispatchSemaphore(value: 0)

let request = VNRecognizeTextRequest { req, err in
    defer { semaphore.signal() }
    guard let observations = req.results as? [VNRecognizedTextObservation] else { return }
    for obs in observations {
        guard let top = obs.topCandidates(1).first else { continue }
        let box = obs.boundingBox
        results.append([
            "text": top.string,
            "confidence": top.confidence,
            "x": box.minX,
            "y": 1.0 - box.maxY,
            "w": box.width,
            "h": box.height
        ])
    }
}
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
// Whitelist chars useful for blackjack
request.customWords = ["A","K","Q","J","10","2","3","4","5","6","7","8","9","BET","BALANCE","TOTAL","WIN","LOSE","PUSH","BUST","BLACKJACK","DEALER","PLAYER"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])
semaphore.wait()

if let json = try? JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted]),
   let str = String(data: json, encoding: .utf8) {
    print(str)
} else {
    print("[]")
}
