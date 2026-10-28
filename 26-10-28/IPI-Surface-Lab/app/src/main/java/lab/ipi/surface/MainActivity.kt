package lab.ipi.surface

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import lab.ipi.surface.modules.*
import lab.ipi.surface.ui.*
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.UUID

class MainActivity : ComponentActivity() {
    private val vm: LabViewModel by viewModels()
    private val pending by lazy { getSharedPreferences("pending_ui_operations", MODE_PRIVATE) }
    private val existingPhonePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val uri = result.data?.data
        vm.accept(vm.repo.perform("Contacts", "select_existing_phone", "System phone picker", emptyMap(), vm.run) {
            if (result.resultCode != RESULT_OK || uri == null) Outcome("UNKNOWN", "Picker canceled; no contact modified")
            else ExistingPhoneModule(vm.repo).select(uri)
        })
    }
    private fun pickExistingPhone() {
        vm.accept(vm.repo.perform("Contacts", "pick_existing_phone", "ACTION_PICK", emptyMap(), vm.run) {
            existingPhonePicker.launch(Intent(Intent.ACTION_PICK, android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI))
            Outcome("PENDING_USER_ACTION", "Choose one existing phone number; no write yet")
        })
    }
    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        val module = pending.getString("permissionModule", "Unknown")!!
        vm.accept(vm.repo.perform(module, "permission_result", "Runtime permission dialog", vm.snapshot(module), vm.run) {
            Outcome(if (granted.values.all { it }) "VERIFIED" else "PERMISSION_DENIED", JSONObject(granted).toString(), vm.repo.permissions(module))
        })
    }
    private val external = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val raw = pending.getString("external", null)
        if (raw != null) {
            val p = JSONObject(raw)
            val f = p.getJSONObject("fields").let { o -> o.keys().asSequence().associateWith { o.getString(it) } }
            vm.accept(vm.repo.perform(p.getString("module"), "intent_return", "Intent", f, p.getString("runId")) {
                Outcome("UNKNOWN", "activityResultCode=${result.resultCode}; returnedUri=${result.data?.data}", "Result code is not a saved-object receipt. Verify manually; delegated objects are never auto-deleted.")
            })
            pending.edit().remove("external").apply()
        }
    }
    private val export = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val raw = pending.getString("export", null)
        if (raw != null) {
            val p = JSONObject(raw); pending.edit().remove("export").apply()
            val uri = result.data?.data
            if (result.resultCode != RESULT_OK || uri == null) {
                vm.accept(vm.repo.perform(p.getString("module"), "export_result", "SAF", emptyMap(), p.getString("runId")) { Outcome("UNKNOWN", "SAF canceled; resultCode=${result.resultCode}", "NO_WRITE") })
            } else exportTo(uri, p)
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleClick(intent)
        setContent { LabApp(vm, ::requestPermissionsFor, ::delegate, ::requestExport, ::showAssist, ::pickExistingPhone) }
    }
    override fun onResume() { super.onResume(); vm.refresh() }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); handleClick(intent) }
    private fun handleClick(intent: Intent) {
        if (intent.action != "lab.ipi.surface.NOTIFICATION_CLICK") return
        val id = intent.getIntExtra("notificationId", -1).toString()
        // Exported launcher extras are not trusted as proof of a click on an owned notification.
        if (vm.repo.store.owned("Notifications").any { it.getString("id") == id }) vm.accept(vm.repo.perform("Notifications", "action_callback", "PendingIntent", emptyMap(), intent.getStringExtra("runId") ?: vm.run) {
            Outcome("UNKNOWN", "Activity received action callback for owned notification", "Callback received; initiator/user identity is not independently authenticated", id)
        })
        intent.action = Intent.ACTION_MAIN
    }
    private fun requestPermissionsFor(module: String) {
        pending.edit().putString("permissionModule", module).apply()
        val required = Modules.permissions(module).filter { it != "com.android.alarm.permission.SET_ALARM" }.toTypedArray()
        vm.accept(vm.repo.perform(module, "permission_check", "Runtime permissions", vm.snapshot(module), vm.run) { Outcome("UNKNOWN", "Current permission snapshot", vm.repo.permissions(module)) })
        if (required.isNotEmpty()) permissions.launch(required)
    }
    private fun delegate(module: String, action: String, factory: () -> Intent) {
        val f = vm.snapshot(module)
        vm.accept(vm.repo.perform(module, action, "Intent", f, vm.run) {
            val intent = factory()
            pending.edit().putString("external", JSONObject().put("module", module).put("runId", vm.run).put("fields", JSONObject(f)).toString()).commit()
            try { external.launch(intent) } catch (e: Exception) { pending.edit().remove("external").commit(); throw e }
            Outcome("PENDING_USER_ACTION", "ActivityResultLauncher.launch returned", "MANUAL_REQUIRED; launch is not saved data, file consumption, or AI execution")
        })
    }
    private fun requestExport(kind: String, fileId: String) {
        val module = if (kind == "file") "Files" else "Logs"
        val files = FilesModule(vm.repo)
        val mime = when (kind) { "json" -> "application/json"; "csv" -> "text/csv"; else -> files.mime(fileId) }
        val name = if (kind == "file") fileId else "IPI_${vm.run}.$kind"
        vm.accept(vm.repo.perform(module, "export_request", "SAF ACTION_CREATE_DOCUMENT", vm.snapshot(module), vm.run) {
            pending.edit().putString("export", JSONObject().put("kind", kind).put("id", fileId).put("runId", vm.run).put("module", module).toString()).commit()
            try { export.launch(Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(mime).putExtra(Intent.EXTRA_TITLE, name)) }
            catch (e: Exception) { pending.edit().remove("export").commit(); throw e }
            Outcome("PENDING_USER_ACTION", "SAF create document launched", "NO_WRITE_YET")
        })
    }
    private fun exportTo(uri: Uri, p: JSONObject) {
        vm.busy = true
        lifecycleScope.launch {
            try {
                val row = withContext(Dispatchers.IO) {
                    vm.repo.perform(p.getString("module"), "export_write", "SAF", mapOf("kind" to p.getString("kind"), "sourceId" to p.getString("id")), p.getString("runId")) {
                        val bytes = when (p.getString("kind")) { "json" -> vm.repo.store.exportJson().toByteArray(Charsets.UTF_8); "csv" -> vm.repo.store.exportCsv().toByteArray(Charsets.UTF_8); else -> FilesModule(vm.repo).file(p.getString("id")).readBytes() }
                        contentResolver.openOutputStream(uri, "wt").use { out -> requireNotNull(out) { "Null output stream" }; out.write(bytes); out.flush() }
                        val expected = MessageDigest.getInstance("SHA-256").digest(bytes)
                        val check = runCatching { contentResolver.openInputStream(uri).use { input -> requireNotNull(input); val d = MessageDigest.getInstance("SHA-256"); val b = ByteArray(8192); var n = input.read(b); while (n >= 0) { d.update(b, 0, n); n = input.read(b) }; d.digest().contentEquals(expected) } }
                        Outcome(if (check.getOrDefault(false)) "VERIFIED" else "CREATED", "Wrote ${bytes.size} bytes; sha256=${expected.joinToString("") { "%02x".format(it) }}", "readbackMatches=${check.getOrNull()}; error=${check.exceptionOrNull()?.message}", uri.toString())
                    }
                }; vm.accept(row)
            } finally { vm.busy = false }
        }
    }
    private fun showAssist() {
        vm.operation("Assist", "prepare_session", "Native Activity", { f, run ->
            val id = "${UUID.randomUUID()}.json"; val file = File(filesDir, "assist/$id"); file.parentFile!!.mkdirs(); file.writeText(JSONObject(f).toString())
            vm.repo.store.own("Assist", id, run)
            startActivity(Intent(this, AssistActivity::class.java).putExtra("sessionId", id))
            Outcome("CREATED", "Saved private Assist configuration; launched native page", "Callbacks recorded only when invoked by framework", id)
        })
    }
}
