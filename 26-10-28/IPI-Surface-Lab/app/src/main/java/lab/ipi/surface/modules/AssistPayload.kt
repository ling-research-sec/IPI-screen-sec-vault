package lab.ipi.surface.modules

import org.json.JSONObject

object AssistPayload {
    fun dataText(fields: Map<String, String>): String = (if (fields["mode"] == "Consistent") fields["visible"] else fields["assist"]).orEmpty()
    fun structured(fields: Map<String, String>, run: String): String = JSONObject()
        .put("@context", "https://schema.org").put("@type", "CreativeWork").put("name", fields["title"].orEmpty())
        .put("text", (if (fields["mode"] == "Consistent") fields["visible"] else fields["structured"]).orEmpty())
        .put("identifier", run).toString()
}
