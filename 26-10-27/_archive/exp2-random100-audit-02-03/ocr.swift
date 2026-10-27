import Foundation
import Vision
let jobsURL=URL(fileURLWithPath:CommandLine.arguments[1])
let jobs=try JSONSerialization.jsonObject(with:Data(contentsOf:jobsURL)) as! [[String:Any]]
var output:[[String:Any]]=[]
for job in jobs {
 let request=VNRecognizeTextRequest()
 request.recognitionLevel = .accurate
 request.usesLanguageCorrection = false
 request.recognitionLanguages = ["en-US"]
 let handler=VNImageRequestHandler(url:URL(fileURLWithPath:job["image"] as! String),options:[:])
 try handler.perform([request])
 let items=(request.results ?? []).sorted { a,b in
  if abs(a.boundingBox.midY-b.boundingBox.midY)>0.015{return a.boundingBox.midY>b.boundingBox.midY}
  return a.boundingBox.minX<b.boundingBox.minX
 }.compactMap { observation -> [String:Any]? in
  guard let c=observation.topCandidates(1).first else{return nil}
  return ["text":c.string,"confidence":c.confidence,"bounds":[observation.boundingBox.minX,observation.boundingBox.minY,observation.boundingBox.width,observation.boundingBox.height]]
 }
 output.append(["case_id":job["case_id"]!,"lines":items,"text":items.map{$0["text"] as! String}.joined(separator:"\n")])
}
let data=try JSONSerialization.data(withJSONObject:output,options:[.prettyPrinted,.sortedKeys])
try data.write(to:URL(fileURLWithPath:CommandLine.arguments[2]))
print("Independent Vision OCR finished: \(output.count) screenshots; language correction disabled")
