package lab.ipi.surface.data

import android.content.Context
import android.os.Build
import android.util.AtomicFile
import lab.ipi.surface.BuildConfig
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.time.Instant
import java.util.UUID

/** Logs and ownership are deliberately independent: clearing logs never loses cleanup handles. */
class LabStore(val context: Context) {
    private val dir = File(context.filesDir, "experiments").apply { mkdirs() }
    private val log = File(dir, "operations.jsonl")
    private val observations = File(dir, "observations.jsonl")
    private val registry = File(dir, "owned.json")
    private val drafts = File(dir, "drafts.json")
    companion object { private val lock = Any(); fun runId() = "IPI_${UUID.randomUUID()}" }
    private fun readArray(file: File): JSONArray = if (file.exists()) JSONArray(file.readText()) else JSONArray()
    private fun atomic(file: File, text: String) {
        val target = AtomicFile(file)
        val stream = target.startWrite()
        try { stream.write(text.toByteArray(Charsets.UTF_8)); target.finishWrite(stream) }
        catch (e: Exception) { target.failWrite(stream); throw e }
    }
    private fun append(file: File, value: JSONObject) = synchronized(lock) {
        FileOutputStream(file, true).use { it.write((value.toString() + "\n").toByteArray(Charsets.UTF_8)); it.fd.sync() }
    }
    fun device(): JSONObject = JSONObject().put("manufacturer", Build.MANUFACTURER).put("model", Build.MODEL)
        .put("androidVersion", Build.VERSION.RELEASE).put("sdk", Build.VERSION.SDK_INT)
        .put("buildDisplay", Build.DISPLAY).put("buildFingerprint", Build.FINGERPRINT)
        .put("hyperOS", "UNKNOWN; buildDisplay is captured, no hidden API")
        .put("appVersion", BuildConfig.VERSION_NAME).put("targetSdk", context.applicationInfo.targetSdkVersion)
    fun record(row: JSONObject): JSONObject {
        row.put("eventId", UUID.randomUUID().toString()).put("timestamp", Instant.now().toString()).put("device", device())
        append(log, row); return row
    }
    fun observe(row: JSONObject): JSONObject {
        row.put("observationId", UUID.randomUUID().toString()).put("timestamp", Instant.now().toString())
            .put("recordType", "HUMAN_AI_OBSERVATION").put("device", device())
        append(observations, row); return row
    }
    fun rows(file: File): List<JSONObject> = synchronized(lock) {
        if (!file.exists()) emptyList() else file.readLines().filter { it.isNotBlank() }.mapIndexed { index, line ->
            try { JSONObject(line) } catch (e: Exception) { JSONObject().put("status", "FAILED").put("error", "Corrupt JSONL line ${index + 1}: ${e.message}") }
        }
    }
    fun recent(): List<JSONObject> = rows(log).takeLast(30).reversed()
    fun exportJson(): String = synchronized(lock) {
        JSONObject().put("schemaVersion", 1).put("device", device()).put("operations", JSONArray(rows(log)))
            .put("aiObservations", JSONArray(rows(observations))).put("ownedObjects", readArray(registry)).toString(2)
    }
    fun exportCsv(): String = synchronized(lock) {
        val columns = listOf("recordType", "eventId", "observationId", "timestamp", "runId", "module", "action", "method", "status", "fields", "payload", "permissions", "objectId", "systemResult", "verification", "error", "device", "observation")
        val items = rows(log).map { it.put("recordType", "SYSTEM_OPERATION") } + rows(observations)
        (listOf(columns.joinToString(",") { TextCodec.csv(it) }) + items.map { item -> columns.joinToString(",") { TextCodec.csv(item.opt(it)?.toString() ?: "") } }).joinToString("\r\n") + "\r\n"
    }
    fun clearLogs() = synchronized(lock) { atomic(log, ""); atomic(observations, "") }
    fun own(module: String, id: String, run: String, metadata: JSONObject = JSONObject()) = synchronized(lock) {
        val all = readArray(registry); val next = JSONArray()
        for (i in 0 until all.length()) { val o = all.getJSONObject(i); if (!(o.getString("module") == module && o.getString("id") == id)) next.put(o) }
        next.put(JSONObject().put("module", module).put("id", id).put("runId", run).put("metadata", metadata))
        atomic(registry, next.toString())
    }
    fun owned(module: String): List<JSONObject> = synchronized(lock) {
        val a = readArray(registry); (0 until a.length()).map { a.getJSONObject(it) }.filter { it.getString("module") == module }
    }
    fun requireOwned(module: String, id: String): JSONObject = owned(module).firstOrNull { it.getString("id") == id }
        ?: throw IllegalArgumentException("Object is not in this app's ownership registry")
    fun forget(module: String, id: String) = synchronized(lock) {
        val a = readArray(registry); val keep = JSONArray()
        for (i in 0 until a.length()) { val o = a.getJSONObject(i); if (o.getString("module") != module || o.getString("id") != id) keep.put(o) }
        atomic(registry, keep.toString())
    }
    fun saveDraft(value: JSONObject) = synchronized(lock) { atomic(drafts, value.toString()) }
    fun loadDraft(): JSONObject = synchronized(lock) { if (drafts.exists()) JSONObject(drafts.readText()) else JSONObject() }
    fun callbackCount(kind: String): Int = synchronized(lock) {
        val prefs = context.getSharedPreferences("assist-callbacks", Context.MODE_PRIVATE)
        val next = prefs.getInt(kind, 0) + 1; check(prefs.edit().putInt(kind, next).commit()); next
    }
}

object TextCodec {
    fun csv(text: String): String {
        // CSV cells are text, never spreadsheet formulas. JSON preserves the exact original.
        val guarded = if (text.trimStart().firstOrNull() in listOf('=', '+', '-', '@', '\t', '\r')) "'$text" else text
        return "\"${guarded.replace("\"", "\"\"")}\""
    }
    fun html(text: String) = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#39;")
    fun filename(text: String): String = text.replace(Regex("[\\\\/\\p{Cntrl}]"), "_").trim().take(80).ifBlank { "experiment" }
}
