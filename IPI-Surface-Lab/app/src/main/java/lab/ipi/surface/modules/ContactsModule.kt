package lab.ipi.surface.modules

import android.content.ContentProviderOperation
import android.content.ContentUris
import android.content.ContentValues
import android.content.Intent
import android.provider.ContactsContract as C
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

class ContactsModule(private val repo: LabRepository) {
    private val resolver get() = repo.context.contentResolver
    companion object { const val OWNER_MIME = "vnd.android.cursor.item/vnd.lab.ipi.surface.owner" }
    fun create(f: Map<String, String>, run: String): Outcome {
        repo.requirePermissions("Contacts")
        require(!f["name"].isNullOrBlank()) { "Name is required" }
        val token = UUID.randomUUID().toString()
        val ops = arrayListOf(ContentProviderOperation.newInsert(C.RawContacts.CONTENT_URI)
            .withValue(C.RawContacts.ACCOUNT_TYPE, null).withValue(C.RawContacts.ACCOUNT_NAME, null)
            .withValue(C.RawContacts.AGGREGATION_MODE, C.RawContacts.AGGREGATION_MODE_DISABLED).build())
        fun data(mime: String, vararg values: Pair<String, String>) {
            val b = ContentProviderOperation.newInsert(C.Data.CONTENT_URI).withValueBackReference(C.Data.RAW_CONTACT_ID, 0).withValue(C.Data.MIMETYPE, mime)
            values.forEach { b.withValue(it.first, it.second) }; ops.add(b.build())
        }
        data(C.CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE, C.CommonDataKinds.StructuredName.DISPLAY_NAME to f.getValue("name"))
        if (!f["phone"].isNullOrBlank()) data(C.CommonDataKinds.Phone.CONTENT_ITEM_TYPE, C.CommonDataKinds.Phone.NUMBER to f.getValue("phone"), C.CommonDataKinds.Phone.TYPE to C.CommonDataKinds.Phone.TYPE_OTHER.toString())
        if (!f["nickname"].isNullOrBlank()) data(C.CommonDataKinds.Nickname.CONTENT_ITEM_TYPE, C.CommonDataKinds.Nickname.NAME to f.getValue("nickname"))
        data(C.CommonDataKinds.Organization.CONTENT_ITEM_TYPE, C.CommonDataKinds.Organization.COMPANY to f.orEmpty("organization"), C.CommonDataKinds.Organization.TITLE to f.orEmpty("job"))
        data(C.CommonDataKinds.Note.CONTENT_ITEM_TYPE, C.CommonDataKinds.Note.NOTE to f.orEmpty("note"))
        data(OWNER_MIME, C.Data.DATA1 to token)
        val results = resolver.applyBatch(C.AUTHORITY, ops)
        val uri = requireNotNull(results.first().uri) { "Provider did not return RawContact URI" }
        val id = ContentUris.parseId(uri).toString()
        repo.store.own("Contacts", id, run, JSONObject().put("token", token).put("uri", uri.toString()).put("fields", JSONObject(f)))
        val verified = verify(id)
        return verified.copy(system = "applyBatch returned ${results.size} results; rawContactUri=$uri")
    }
    /** Update an existing owned RawContact in place; never recreate its identity. */
    fun update(id: String, f: Map<String, String>, run: String): Outcome {
        repo.requirePermissions("Contacts")
        require(!f["name"].isNullOrBlank()) { "Name is required" }
        val own = repo.store.requireOwned("Contacts", id)
        require(hasOwner(id)) { "Ownership marker mismatch; no update attempted" }
        val token = own.getJSONObject("metadata").getString("token")
        val ops = arrayListOf(ContentProviderOperation.newAssertQuery(C.Data.CONTENT_URI)
            .withSelection("${C.Data.RAW_CONTACT_ID}=? AND ${C.Data.MIMETYPE}=? AND ${C.Data.DATA1}=?", arrayOf(id, OWNER_MIME, token))
            .withExpectedCount(1).build())
        fun field(mime: String, values: ContentValues?) {
            val ids = mutableListOf<Long>()
            val keys = values?.keySet()?.toList().orEmpty()
            var unchanged = false
            resolver.query(C.Data.CONTENT_URI, (listOf(C.Data._ID) + keys).toTypedArray(), "${C.Data.RAW_CONTACT_ID}=? AND ${C.Data.MIMETYPE}=?", arrayOf(id, mime), null).use { c ->
                requireNotNull(c) { "Null owned-data cursor" }
                while (c.moveToNext()) {
                    ids.add(c.getLong(0))
                    unchanged = values != null && keys.all { key -> c.getString(c.getColumnIndexOrThrow(key)) == values.getAsString(key) }
                }
            }
            require(ids.size <= 1) { "Multiple rows for $mime; review this test contact manually" }
            // ContactsProvider can return 0 for an unchanged Data row. Avoid asserting a change for a no-op.
            if (ids.isNotEmpty() && unchanged) return
            if (ids.isEmpty()) {
                if (values != null) ops.add(ContentProviderOperation.newInsert(C.Data.CONTENT_URI)
                    .withValue(C.Data.RAW_CONTACT_ID, id.toLong()).withValue(C.Data.MIMETYPE, mime).withValues(values).build())
            } else {
                val operation = if (values == null) ContentProviderOperation.newDelete(C.Data.CONTENT_URI)
                    else ContentProviderOperation.newUpdate(C.Data.CONTENT_URI).withValues(values)
                ops.add(operation.withSelection("${C.Data._ID}=? AND ${C.Data.RAW_CONTACT_ID}=? AND ${C.Data.MIMETYPE}=?", arrayOf(ids.single().toString(), id, mime))
                    .withExpectedCount(1).build())
            }
        }
        field(C.CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE, ContentValues().apply {
            put(C.CommonDataKinds.StructuredName.DISPLAY_NAME, f.getValue("name"))
            put(C.CommonDataKinds.StructuredName.GIVEN_NAME, f.getValue("name"))
            putNull(C.CommonDataKinds.StructuredName.FAMILY_NAME); putNull(C.CommonDataKinds.StructuredName.MIDDLE_NAME)
            putNull(C.CommonDataKinds.StructuredName.PREFIX); putNull(C.CommonDataKinds.StructuredName.SUFFIX)
        })
        field(C.CommonDataKinds.Phone.CONTENT_ITEM_TYPE, if (f.orEmpty("phone").isBlank()) null else ContentValues().apply {
            put(C.CommonDataKinds.Phone.NUMBER, f.getValue("phone")); put(C.CommonDataKinds.Phone.TYPE, C.CommonDataKinds.Phone.TYPE_OTHER)
        })
        field(C.CommonDataKinds.Nickname.CONTENT_ITEM_TYPE, if (f.orEmpty("nickname").isBlank()) null else ContentValues().apply { put(C.CommonDataKinds.Nickname.NAME, f.getValue("nickname")) })
        field(C.CommonDataKinds.Organization.CONTENT_ITEM_TYPE, if (f.orEmpty("organization").isBlank() && f.orEmpty("job").isBlank()) null else ContentValues().apply {
            put(C.CommonDataKinds.Organization.COMPANY, f.orEmpty("organization")); put(C.CommonDataKinds.Organization.TITLE, f.orEmpty("job"))
        })
        field(C.CommonDataKinds.Note.CONTENT_ITEM_TYPE, if (f.orEmpty("note").isBlank()) null else ContentValues().apply { put(C.CommonDataKinds.Note.NOTE, f.getValue("note")) })
        val results = resolver.applyBatch(C.AUTHORITY, ops)
        val metadata = JSONObject(own.getJSONObject("metadata").toString()).put("fields", JSONObject(f)).put("lastModifiedRun", run)
        repo.store.own("Contacts", id, own.getString("runId"), metadata)
        return verify(id).copy(system = "applyBatch update returned ${results.size} results; RawContact ID unchanged=$id; counts=${results.map { it.count }}")
    }
    private fun hasOwner(id: String): Boolean {
        val token = repo.store.requireOwned("Contacts", id).getJSONObject("metadata").getString("token")
        resolver.query(C.Data.CONTENT_URI, arrayOf(C.Data._ID), "${C.Data.RAW_CONTACT_ID}=? AND ${C.Data.MIMETYPE}=? AND ${C.Data.DATA1}=?", arrayOf(id, OWNER_MIME, token), null).use { return it != null && it.moveToFirst() }
    }
    fun verify(id: String): Outcome {
        repo.requirePermissions("Contacts"); repo.store.requireOwned("Contacts", id)
        if (!hasOwner(id)) return Outcome("UNKNOWN", "Owned marker absent; no unrelated rows read", "NOT_FOUND_OR_CHANGED; deletion disabled", id)
        val rows = JSONArray()
        resolver.query(C.Data.CONTENT_URI, arrayOf(C.Data.MIMETYPE, C.Data.DATA1, C.Data.DATA2, C.Data.DATA3, C.Data.DATA4), "${C.Data.RAW_CONTACT_ID}=?", arrayOf(id), null).use { cursor ->
            requireNotNull(cursor) { "Provider returned null cursor" }
            while (cursor.moveToNext()) { val row = JSONObject(); cursor.columnNames.forEachIndexed { i, column -> row.put(column, cursor.getString(i) ?: JSONObject.NULL) }; rows.put(row) }
        }
        return Outcome("VERIFIED", "Queried only owned RawContact data", rows, id)
    }
    fun delete(id: String): Outcome {
        repo.requirePermissions("Contacts"); require(hasOwner(id)) { "Ownership marker mismatch; no deletion attempted" }
        val uri = ContentUris.withAppendedId(C.RawContacts.CONTENT_URI, id.toLong())
        val count = resolver.delete(uri, null, null)
        val remaining = resolver.query(uri, arrayOf(C.RawContacts.DELETED), null, null, null).use { c ->
            requireNotNull(c) { "Null cursor after delete" }; c.moveToFirst() && c.getInt(0) == 0
        }
        if (!remaining) repo.store.forget("Contacts", id)
        return Outcome(if (!remaining) "VERIFIED" else "UNKNOWN", "delete=$count", "owned raw contact active=$remaining", id)
    }
    fun insertIntent(f: Map<String, String>): Intent {
        val extras = arrayListOf<ContentValues>()
        extras.add(ContentValues().apply { put(C.Data.MIMETYPE, C.CommonDataKinds.Nickname.CONTENT_ITEM_TYPE); put(C.CommonDataKinds.Nickname.NAME, f.orEmpty("nickname")) })
        return Intent(Intent.ACTION_INSERT).setDataAndType(C.RawContacts.CONTENT_URI, C.RawContacts.CONTENT_TYPE)
            .putExtra(C.Intents.Insert.NAME, f.orEmpty("name")).putExtra(C.Intents.Insert.PHONE, f.orEmpty("phone"))
            .putExtra(C.Intents.Insert.COMPANY, f.orEmpty("organization")).putExtra(C.Intents.Insert.JOB_TITLE, f.orEmpty("job"))
            .putExtra(C.Intents.Insert.NOTES, f.orEmpty("note")).putParcelableArrayListExtra(C.Intents.Insert.DATA, extras)
    }
    fun open(id: String): Intent {
        repo.requirePermissions("Contacts"); require(hasOwner(id))
        val raw = ContentUris.withAppendedId(C.RawContacts.CONTENT_URI, id.toLong())
        val lookup = requireNotNull(C.RawContacts.getContactLookupUri(resolver, raw))
        return Intent(Intent.ACTION_VIEW, lookup)
    }
}
internal fun Map<String, String>.orEmpty(key: String) = this[key] ?: ""
