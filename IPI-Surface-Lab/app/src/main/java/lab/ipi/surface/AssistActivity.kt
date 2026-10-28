package lab.ipi.surface

import android.app.Activity
import android.app.assist.AssistContent
import android.os.Bundle
import android.view.ViewStructure
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import lab.ipi.surface.modules.AssistPayload
import lab.ipi.surface.modules.LabRepository
import lab.ipi.surface.modules.Outcome
import org.json.JSONObject
import java.io.File

/** Native TextViews expose visible text only. The independent Assist strings never enter the view tree. */
class AssistActivity : Activity() {
    private lateinit var repo: LabRepository
    private lateinit var fields: Map<String, String>
    private var run = ""
    private var sessionId = ""
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        repo = LabRepository(this)
        sessionId = intent.getStringExtra("sessionId") ?: run { finish(); return }
        val own = repo.store.requireOwned("Assist", sessionId); run = own.getString("runId")
        val folder = File(filesDir, "assist"); val file = File(folder, sessionId)
        require(file.canonicalFile.parentFile == folder.canonicalFile)
        val data = JSONObject(file.readText()); fields = data.keys().asSequence().associateWith { data.getString(it) }
        val visible = fields["visible"].orEmpty()
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 32, 32, 48) }
        layout.addView(TextView(this).apply { text = fields["title"].orEmpty(); textSize = 24f; setTextColor(android.graphics.Color.BLACK) })
        layout.addView(object : TextView(this) {
            override fun onProvideStructure(structure: ViewStructure) {
                super.onProvideStructure(structure)
                callback("View.onProvideStructure", "visibleText=$visible; native structure supplied; receiver consumption unknown")
            }
        }.apply { text = visible; textSize = 22f; setTextColor(android.graphics.Color.BLACK); setTextIsSelectable(true) })
        setContentView(ScrollView(this).apply { setBackgroundColor(android.graphics.Color.WHITE); addView(layout) })
        layout.setOnApplyWindowInsetsListener { view, insets ->
            view.setPadding(32 + insets.systemWindowInsetLeft, 32 + insets.systemWindowInsetTop, 32 + insets.systemWindowInsetRight, 48 + insets.systemWindowInsetBottom); insets
        }
        layout.requestApplyInsets()
        repo.perform("Assist", "display", "Native TextView", fields, run) { Outcome("CREATED", "Activity displayed; not an Assist callback", "MANUAL_SCREEN_CHECK", sessionId) }
    }
    private fun callback(kind: String, result: String) {
        if (!::fields.isInitialized) return
        val count = repo.store.callbackCount(kind)
        repo.perform("Assist", kind, "Assist", fields, run) { Outcome("VERIFIED", "Framework callback invoked; count=$count", result, sessionId) }
    }
    override fun onProvideAssistData(data: Bundle) {
        super.onProvideAssistData(data); if (!::fields.isInitialized) return
        val assist = AssistPayload.dataText(fields)
        data.putString("ipi.assist_text", assist); data.putString(IntentKey, assist); data.putString("ipi.run_id", run)
        callback("onProvideAssistData", "Bundle text=$assist; keys: ipi.assist_text, android.intent.extra.TEXT, ipi.run_id; receiver consumption UNKNOWN")
    }
    override fun onProvideAssistContent(content: AssistContent) {
        super.onProvideAssistContent(content); if (!::fields.isInitialized) return
        content.structuredData = AssistPayload.structured(fields, run)
        callback("onProvideAssistContent", "JSON-LD=${content.structuredData}; receiver consumption UNKNOWN")
    }
    companion object { private const val IntentKey = "android.intent.extra.TEXT" }
}
