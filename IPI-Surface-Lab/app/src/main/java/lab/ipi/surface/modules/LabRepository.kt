package lab.ipi.surface.modules

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import lab.ipi.surface.data.LabStore
import org.json.JSONObject

object Modules {
    val names = listOf("Contacts", "Notifications", "Calendar", "Alarm", "Files", "Assist")
    fun permissions(module: String): Array<String> = when (module) {
        "Contacts" -> arrayOf(Manifest.permission.READ_CONTACTS, Manifest.permission.WRITE_CONTACTS)
        "Calendar" -> arrayOf(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR)
        "Notifications" -> if (Build.VERSION.SDK_INT >= 33) arrayOf(Manifest.permission.POST_NOTIFICATIONS) else emptyArray()
        "Alarm" -> arrayOf("com.android.alarm.permission.SET_ALARM")
        else -> emptyArray()
    }
}
data class Outcome(val status: String, val system: String, val verification: Any = "NOT_QUERIED", val id: String = "")
class LabRepository(val context: Context, val store: LabStore = LabStore(context)) {
    fun permissions(module: String): JSONObject = JSONObject().also { json -> Modules.permissions(module).forEach { json.put(it, ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED) } }
    fun requirePermissions(module: String) { Modules.permissions(module).forEach { if (ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED) throw SecurityException("Permission not granted: $it") } }
    fun perform(module: String, action: String, method: String, fields: Map<String, String>, run: String, block: () -> Outcome): JSONObject {
        val row = JSONObject().put("runId", run).put("module", module).put("action", action).put("method", method)
            .put("fields", JSONObject(fields)).put("payload", fields["payload"] ?: "").put("permissions", permissions(module))
            .put("objectId", "").put("systemResult", "NOT_RETURNED").put("verification", "NOT_QUERIED").put("error", JSONObject.NULL)
        try { val r = block(); row.put("status", r.status).put("systemResult", r.system).put("verification", r.verification).put("objectId", r.id) }
        catch (e: Exception) {
            row.put("status", when (e) { is SecurityException -> "PERMISSION_DENIED"; is ActivityNotFoundException -> "UNSUPPORTED"; else -> "FAILED" })
                .put("error", "${e.javaClass.simpleName}: ${e.message}")
        }
        return store.record(row)
    }
    fun dispatch(intent: Intent, id: String = ""): Outcome {
        context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        return Outcome("PENDING_USER_ACTION", "startActivity returned; no saved-object receipt", "MANUAL_REQUIRED; dispatch is not creation or AI consumption", id)
    }
}
