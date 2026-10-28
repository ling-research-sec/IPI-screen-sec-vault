package lab.ipi.surface.modules

import android.content.ContentProviderOperation
import android.content.ContentUris
import android.net.Uri
import android.provider.ContactsContract as C
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File

/** Explicitly picked existing phone row. Kept separate from owned objects and bulk cleanup. */
class ExistingPhoneModule(private val repo: LabRepository) {
    private val stateFile = File(repo.context.filesDir, "selected-existing-phone.json")
    fun snapshot(): JSONObject? = if (stateFile.exists()) JSONObject(stateFile.readText()) else null
    private fun save(state: JSONObject) {
        val file = AtomicFile(stateFile); val stream = file.startWrite()
        try { stream.write(state.toString().toByteArray(Charsets.UTF_8)); file.finishWrite(stream) }
        catch (e: Exception) { file.failWrite(stream); throw e }
    }
    private fun read(id: Long): JSONObject {
        repo.requirePermissions("Contacts")
        val columns = arrayOf(C.Data._ID, C.Data.RAW_CONTACT_ID, C.Data.CONTACT_ID, C.Data.DATA_VERSION,
            C.Data.DISPLAY_NAME, C.CommonDataKinds.Phone.NUMBER)
        repo.context.contentResolver.query(ContentUris.withAppendedId(C.Data.CONTENT_URI, id), columns,
            "${C.Data.MIMETYPE}=?", arrayOf(C.CommonDataKinds.Phone.CONTENT_ITEM_TYPE), null).use { c ->
            require(c != null && c.moveToFirst()) { "Selected phone row no longer exists" }
            return JSONObject().put("dataId", c.getLong(0)).put("rawContactId", c.getLong(1)).put("contactId", c.getLong(2))
                .put("version", c.getLong(3)).put("displayName", c.getString(4).orEmpty()).put("number", c.getString(5).orEmpty()).put("readOnly", "UNKNOWN_PROVIDER_ENFORCED")
        }
    }
    fun select(uri: Uri): Outcome {
        require(uri.scheme == "content" && uri.authority == C.AUTHORITY) { "Use the system contacts phone picker" }
        require(uri.pathSegments.firstOrNull() == "data") { "Select a phone-number row, not an aggregate contact" }
        val row = read(ContentUris.parseId(uri))
        row.put("originalNumber", row.getString("number"))
        save(row)
        return Outcome("VERIFIED", "User-selected existing phone row loaded; no provider write", row, row.getLong("dataId").toString())
    }
    fun querySelected(): Outcome {
        val state = requireNotNull(snapshot()) { "Select an existing phone number first" }
        val row = read(state.getLong("dataId")); identity(state, row)
        return Outcome("VERIFIED", "Queried only the selected existing phone row", row, row.getLong("dataId").toString())
    }
    private fun identity(before: JSONObject, after: JSONObject) {
        require(listOf("dataId", "rawContactId", "contactId").all { before.getLong(it) == after.getLong(it) }) { "Selected contact identity changed; no write attempted" }
    }
    fun update(number: String, restore: Boolean = false): Outcome {
        val state = requireNotNull(snapshot()) { "Select an existing phone number first" }
        val id = state.getLong("dataId"); val before = read(id); identity(state, before)
        require(before.getLong("version") == state.getLong("version") && before.getString("number") == state.getString("number")) { "Phone row changed externally; saved original retained, no overwrite attempted" }
        val target = if (restore) state.getString("originalNumber") else number
        require(target.isNotBlank()) { "New phone number must not be empty" }
        if (before.getString("number") == target) return Outcome("VERIFIED", "Number already matches; no write needed", before, id.toString())
        // Persist original and intended write before touching the provider; never include this row in bulk deletion.
        state.put("pendingNumber", target); save(state)
        val uri = ContentUris.withAppendedId(C.Data.CONTENT_URI, id)
        val where = "${C.Data.RAW_CONTACT_ID}=? AND ${C.Data.CONTACT_ID}=? AND ${C.Data.MIMETYPE}=?"
        val args = arrayOf(state.getLong("rawContactId").toString(), state.getLong("contactId").toString(), C.CommonDataKinds.Phone.CONTENT_ITEM_TYPE)
        val operations = arrayListOf(
            ContentProviderOperation.newAssertQuery(uri).withSelection(where, args)
                .withValue(C.Data.DATA_VERSION, state.getLong("version")).withValue(C.CommonDataKinds.Phone.NUMBER, state.getString("number")).withExpectedCount(1).build(),
            ContentProviderOperation.newUpdate(uri).withSelection(where, args).withValue(C.CommonDataKinds.Phone.NUMBER, target).withExpectedCount(1).build())
        val result = repo.context.contentResolver.applyBatch(C.AUTHORITY, operations)
        val after = read(id); identity(state, after)
        require(after.getString("number") == target) { "Provider readback differs from requested number; inspect the saved original" }
        after.put("originalNumber", state.getString("originalNumber")); save(after)
        return Outcome("VERIFIED", "${if (restore) "restore" else "update"} existing phone row; changed=${result[1].count}; Data ID unchanged=$id", after, id.toString())
    }
}
