package lab.ipi.surface.modules

import android.content.ContentUris
import android.content.ContentValues
import android.content.Intent
import android.provider.CalendarContract as C
import org.json.JSONArray
import org.json.JSONObject
import java.time.ZoneId
import java.util.UUID

class CalendarModule(private val repo: LabRepository) {
    private val resolver get() = repo.context.contentResolver
    fun calendars(): Outcome {
        repo.requirePermissions("Calendar")
        val rows = JSONArray()
        // Only calendar-container metadata; never enumerate existing events or account identifiers.
        resolver.query(C.Calendars.CONTENT_URI, arrayOf(C.Calendars._ID, C.Calendars.CALENDAR_DISPLAY_NAME, C.Calendars.CALENDAR_ACCESS_LEVEL),
            "${C.Calendars.CALENDAR_ACCESS_LEVEL}>=?", arrayOf(C.Calendars.CAL_ACCESS_CONTRIBUTOR.toString()), null).use { cursor ->
            requireNotNull(cursor) { "Null calendar cursor" }
            while (cursor.moveToNext()) rows.put(JSONObject().put("id", cursor.getLong(0)).put("displayName", cursor.getString(1)).put("accessLevel", cursor.getInt(2)))
        }
        return Outcome(if (rows.length() == 0) "UNSUPPORTED" else "VERIFIED", "Writable calendar metadata; select an ID explicitly", rows)
    }
    private fun times(f: Map<String, String>): Pair<Long, Long> {
        ZoneId.of(f.orEmpty("timezone"))
        val start = f.orEmpty("start").toLong(); val end = f.orEmpty("end").toLong()
        require(end > start) { "End must be later than start (epoch milliseconds)" }; return start to end
    }
    fun create(f: Map<String, String>, run: String): Outcome {
        repo.requirePermissions("Calendar"); val (start, end) = times(f)
        val calendarId = f.orEmpty("calendarId").toLong()
        val calendarUri = ContentUris.withAppendedId(C.Calendars.CONTENT_URI, calendarId)
        resolver.query(calendarUri, arrayOf(C.Calendars.CALENDAR_ACCESS_LEVEL), null, null, null).use { c ->
            require(c != null && c.moveToFirst() && c.getInt(0) >= C.Calendars.CAL_ACCESS_CONTRIBUTOR) { "Select an existing writable calendar ID" }
        }
        val token = "ipi-surface:${UUID.randomUUID()}"
        val values = ContentValues().apply {
            put(C.Events.CALENDAR_ID, calendarId); put(C.Events.TITLE, f.orEmpty("title")); put(C.Events.DESCRIPTION, f.orEmpty("description"))
            put(C.Events.EVENT_LOCATION, f.orEmpty("location")); put(C.Events.DTSTART, start); put(C.Events.DTEND, end)
            put(C.Events.EVENT_TIMEZONE, f.orEmpty("timezone")); put(C.Events.CUSTOM_APP_PACKAGE, repo.context.packageName); put(C.Events.CUSTOM_APP_URI, token)
        }
        val uri = requireNotNull(resolver.insert(C.Events.CONTENT_URI, values)) { "Provider returned null URI" }
        val id = ContentUris.parseId(uri).toString()
        repo.store.own("Calendar", id, run, JSONObject().put("token", token).put("uri", uri.toString()).put("fields", JSONObject(f)))
        return verify(id).copy(system = "insert returned $uri")
    }
    private fun selectOwned(id: String): Pair<String, Array<String>> {
        val own = repo.store.requireOwned("Calendar", id)
        return "${C.Events._ID}=? AND ${C.Events.CUSTOM_APP_PACKAGE}=? AND ${C.Events.CUSTOM_APP_URI}=?" to arrayOf(id, repo.context.packageName, own.getJSONObject("metadata").getString("token"))
    }
    fun verify(id: String): Outcome {
        repo.requirePermissions("Calendar"); val (where, args) = selectOwned(id)
        val cols = arrayOf(C.Events._ID, C.Events.TITLE, C.Events.DESCRIPTION, C.Events.EVENT_LOCATION, C.Events.DTSTART, C.Events.DTEND, C.Events.EVENT_TIMEZONE)
        resolver.query(C.Events.CONTENT_URI, cols, where, args, null).use { c ->
            requireNotNull(c) { "Null event cursor" }
            if (!c.moveToFirst()) return Outcome("UNKNOWN", "Owned event absent or ownership fields changed", "NOT_FOUND; no unrelated events inspected", id)
            val row = JSONObject(); cols.forEachIndexed { i, key -> row.put(key, c.getString(i) ?: JSONObject.NULL) }
            return Outcome("VERIFIED", "Queried owned Event ID and ownership token", row, id)
        }
    }
    fun delete(id: String): Outcome {
        repo.requirePermissions("Calendar"); val (where, args) = selectOwned(id)
        val count = resolver.delete(C.Events.CONTENT_URI, where, args)
        val exists = resolver.query(C.Events.CONTENT_URI, arrayOf(C.Events._ID), where, args, null).use { c -> requireNotNull(c); c.moveToFirst() }
        if (!exists && count > 0) repo.store.forget("Calendar", id)
        return Outcome(if (!exists && count > 0) "VERIFIED" else "UNKNOWN", "delete=$count", "owned event remains=$exists; zero deletions require manual reconciliation", id)
    }
    fun insertIntent(f: Map<String, String>): Intent {
        val (start, end) = times(f)
        return Intent(Intent.ACTION_INSERT, C.Events.CONTENT_URI).putExtra(C.Events.TITLE, f.orEmpty("title"))
            .putExtra(C.Events.DESCRIPTION, f.orEmpty("description")).putExtra(C.Events.EVENT_LOCATION, f.orEmpty("location"))
            .putExtra(C.EXTRA_EVENT_BEGIN_TIME, start).putExtra(C.EXTRA_EVENT_END_TIME, end).putExtra(C.Events.EVENT_TIMEZONE, f.orEmpty("timezone"))
    }
    fun open(id: String): Intent { require(verify(id).status == "VERIFIED") { "Owned event not verified; no external view opened" }; return Intent(Intent.ACTION_VIEW, ContentUris.withAppendedId(C.Events.CONTENT_URI, id.toLong())) }
}
