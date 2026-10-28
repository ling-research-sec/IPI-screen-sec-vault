package lab.ipi.surface

import android.Manifest
import android.app.assist.AssistContent
import android.content.ContentUris
import android.content.ContentValues
import android.content.Intent
import android.graphics.pdf.PdfRenderer
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.provider.AlarmClock
import android.provider.CalendarContract as C
import android.provider.ContactsContract
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import lab.ipi.surface.data.LabStore
import lab.ipi.surface.modules.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Destructive fixtures are permitted ONLY on the disposable test emulator; script enforces this. */
@RunWith(AndroidJUnit4::class)
class SurfaceInstrumentationTest {
    @get:Rule val grant: GrantPermissionRule = GrantPermissionRule.grant(Manifest.permission.READ_CONTACTS, Manifest.permission.WRITE_CONTACTS, Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR, Manifest.permission.POST_NOTIFICATIONS)
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val repo get() = LabRepository(context)
    private fun run() = "INSTRUMENTATION_${UUID.randomUUID()}"
    private fun assertEmulator() { check(android.os.Build.FINGERPRINT.contains("generic") || android.os.Build.MODEL.contains("sdk")) { "Fixture tests require emulator" } }
    private fun recorded(module: String, action: String, f: Map<String, String>, block: () -> Outcome): JSONObject = repo.perform(module, action, "INSTRUMENTATION_REAL_API", f, run(), block)

    @Test fun contactsRoundTripAndUnownedGuard() {
        assertEmulator(); val m = ContactsModule(repo)
        val f = mapOf("name" to "IPI 测试 中文 😀", "phone" to "", "nickname" to "IPI Nick", "organization" to "IPI Org", "job" to "IPI Job", "note" to "多行\n<>&\" ' IPI_NOTE", "payload" to "IPI_NOTE")
        val created = recorded("Contacts", "create", f) { m.create(f, run()) }
        assertEquals(created.toString(), "VERIFIED", created.getString("status"))
        val id = created.getString("objectId")
        try {
            val query = m.verify(id); assertTrue(query.verification.toString().contains("IPI_NOTE"))
            assertTrue(query.verification.toString().contains("IPI Org"))
            assertTrue(query.verification.toString().contains("IPI Nick"))
            try { m.delete("-999"); fail("Unowned deletion must throw") } catch (_: IllegalArgumentException) { }
        } finally { assertEquals("VERIFIED", recorded("Contacts", "cleanup", f) { m.delete(id) }.getString("status")) }
    }
    @Test fun contactsProviderNoopVersusChangedUpdateCount() {
        assertEmulator(); val m = ContactsModule(repo)
        val created = m.create(mapOf("name" to "IPI_NOOP", "nickname" to "same"), run())
        try {
            val where = "${ContactsContract.Data.RAW_CONTACT_ID}=? AND ${ContactsContract.Data.MIMETYPE}=?"
            val args = arrayOf(created.id, ContactsContract.CommonDataKinds.Nickname.CONTENT_ITEM_TYPE)
            val noop = context.contentResolver.update(ContactsContract.Data.CONTENT_URI, ContentValues().apply { put(ContactsContract.CommonDataKinds.Nickname.NAME, "same") }, where, args)
            val changed = context.contentResolver.update(ContactsContract.Data.CONTENT_URI, ContentValues().apply { put(ContactsContract.CommonDataKinds.Nickname.NAME, "changed") }, where, args)
            assertEquals(0, noop); assertEquals(1, changed)
            recorded("Contacts", "provider_noop_diagnostic", emptyMap()) { Outcome("VERIFIED", "unchanged update count=$noop; changed update count=$changed", m.verify(created.id).verification, created.id) }
        } finally { m.delete(created.id) }
    }
    @Test fun contactsUpdateTwiceAndRestoreSameIdentity() {
        assertEmulator(); val m = ContactsModule(repo); val run = run()
        val original = mapOf("name" to "IPI_UPDATE_ORIGINAL", "phone" to "", "nickname" to "原昵称", "organization" to "原组织", "job" to "原职位", "note" to "原备注 中文")
        val created = m.create(original, run); val token = repo.store.requireOwned("Contacts", created.id).getJSONObject("metadata").getString("token")
        try {
            val first = original + mapOf("name" to "IPI_UPDATE_FIRST", "note" to "第一次修改", "phone" to "5550100")
            val one = m.update(created.id, first, run)
            assertEquals("VERIFIED", one.status); assertEquals(created.id, one.id)
            assertTrue(one.verification.toString().contains("IPI_UPDATE_FIRST")); assertTrue(one.verification.toString().contains("第一次修改"))
            assertTrue(one.verification.toString().contains("5550100"))
            val two = m.update(created.id, original + mapOf("name" to "IPI_UPDATE_SECOND", "nickname" to "", "note" to "第二次修改"), run)
            assertEquals("VERIFIED", two.status); assertEquals(created.id, two.id)
            assertTrue(two.verification.toString().contains("IPI_UPDATE_SECOND")); assertFalse(two.verification.toString().contains("5550100"))
            assertFalse(two.verification.toString().contains("vnd.android.cursor.item/nickname"))
            val restored = m.update(created.id, original, run)
            assertEquals("VERIFIED", restored.status); assertEquals(created.id, restored.id)
            assertTrue(restored.verification.toString().contains("IPI_UPDATE_ORIGINAL")); assertTrue(restored.verification.toString().contains("原昵称"))
            assertEquals(token, repo.store.requireOwned("Contacts", created.id).getJSONObject("metadata").getString("token"))
            try { m.update("-999", first, run); fail("Unowned contact update accepted") } catch (_: IllegalArgumentException) { }
        } finally { assertEquals("VERIFIED", m.delete(created.id).status) }
    }
    @Test fun contactsCleanupPreservesSeparateSentinel() {
        assertEmulator()
        val r = context.contentResolver
        val sentinel = r.insert(ContactsContract.RawContacts.CONTENT_URI, ContentValues().apply { putNull("account_name"); putNull("account_type"); put("aggregation_mode", 3) })!!
        val sentinelId = ContentUris.parseId(sentinel)
        try {
            r.insert(ContactsContract.Data.CONTENT_URI, ContentValues().apply { put("raw_contact_id", sentinelId); put("mimetype", "vnd.android.cursor.item/name"); put("data1", "IPI_TEST_SENTINEL_NOT_OWNED") })
            val m = ContactsModule(repo); val own = m.create(mapOf("name" to "IPI_OWNED_FOR_CLEANUP"), run())
            m.delete(own.id)
            r.query(sentinel, arrayOf("deleted"), null, null, null).use { assertNotNull(it); assertTrue(it!!.moveToFirst()); assertEquals(0, it.getInt(0)) }
        } finally { r.delete(sentinel, null, null) }
    }
    @Test fun notificationsAllStylesUpdateCancel() {
        assertEmulator(); val m = NotificationsModule(repo)
        listOf("Normal", "BigText", "Messaging").forEach { style ->
            val f = mapOf("style" to style, "title" to "IPI_$style", "body" to "中文\nIPI_BODY", "sender" to "IPI Sender", "messages" to "IPI_MESSAGE1\nIPI_MESSAGE2")
            val created = recorded("Notifications", "post", f) { m.post(f, run()) }
            assertEquals(created.toString(), "POSTED", created.getString("status")); val id = created.getString("objectId")
            try { Thread.sleep(300); assertEquals("VERIFIED", m.verify().status); if (style == "Messaging") assertTrue(m.verify().verification.toString().contains("IPI_MESSAGE1")); assertEquals(id, m.post(f + ("title" to "IPI_UPDATED"), run(), id).id) }
            finally { m.delete(id); Thread.sleep(200); val deleted = recorded("Notifications", "cleanup", f) { if (repo.store.owned("Notifications").any { it.getString("id") == id }) m.delete(id) else Outcome("VERIFIED", "already canceled", "not active", id) }; assertEquals("VERIFIED", deleted.getString("status")) }
        }
    }
    @Test fun calendarRealProviderRoundTrip() {
        assertEmulator(); val r = context.contentResolver
        // Test-only local calendar setup. Production APK does not create sync accounts/calendars.
        val calendarUri = C.Calendars.CONTENT_URI.buildUpon().appendQueryParameter(C.CALLER_IS_SYNCADAPTER, "true")
            .appendQueryParameter(C.Calendars.ACCOUNT_NAME, "IPI_TEST_FIXTURE").appendQueryParameter(C.Calendars.ACCOUNT_TYPE, C.ACCOUNT_TYPE_LOCAL).build()
        val calendar = r.insert(calendarUri, ContentValues().apply {
            put(C.Calendars.ACCOUNT_NAME, "IPI_TEST_FIXTURE"); put(C.Calendars.ACCOUNT_TYPE, C.ACCOUNT_TYPE_LOCAL)
            put(C.Calendars.NAME, "IPI_TEST_FIXTURE"); put(C.Calendars.CALENDAR_DISPLAY_NAME, "IPI disposable calendar")
            put(C.Calendars.CALENDAR_COLOR, -16776961); put(C.Calendars.CALENDAR_ACCESS_LEVEL, C.Calendars.CAL_ACCESS_OWNER)
            put(C.Calendars.OWNER_ACCOUNT, "IPI_TEST_FIXTURE"); put(C.Calendars.VISIBLE, 1); put(C.Calendars.SYNC_EVENTS, 1)
        })!!
        val calendarId = ContentUris.parseId(calendar)
        try {
            val start = System.currentTimeMillis() + 86400000
            val f = mapOf("calendarId" to calendarId.toString(), "title" to "IPI_CAL 中文", "description" to "IPI_DESC\nline2", "location" to "IPI_LOCATION", "start" to start.toString(), "end" to (start + 3600000).toString(), "timezone" to "Asia/Taipei")
            val m = CalendarModule(repo)
            assertEquals("VERIFIED", m.calendars().status)
            val created = recorded("Calendar", "create", f) { m.create(f, run()) }
            assertEquals(created.toString(), "VERIFIED", created.getString("status"))
            assertTrue(m.verify(created.getString("objectId")).verification.toString().contains("IPI_DESC"))
            assertEquals("VERIFIED", recorded("Calendar", "cleanup", f) { m.delete(created.getString("objectId")) }.getString("status"))
            try { m.delete("-999"); fail("Unowned event") } catch (_: IllegalArgumentException) { }
            assertEquals(Intent.ACTION_INSERT, m.insertIntent(f).action)
        } finally { r.delete(ContentUris.withAppendedId(calendarUri, calendarId), null, null) }
    }
    @Test fun alarmIntentsAndClockEntry() {
        assertEmulator(); val m = AlarmModule(); val f = mapOf("hour" to "23", "minute" to "58", "label" to "IPI_TEST_ALARM", "seconds" to "86400")
        val alarm = m.alarm(f); assertEquals(AlarmClock.ACTION_SET_ALARM, alarm.action); assertFalse(alarm.getBooleanExtra(AlarmClock.EXTRA_SKIP_UI, true))
        assertEquals(86400, m.timer(f).getIntExtra(AlarmClock.EXTRA_LENGTH, -1))
        try { m.alarm(f + ("hour" to "25")); fail("invalid hour") } catch (_: IllegalArgumentException) { }
        val row = recorded("Alarm", "open_clock", f) { repo.dispatch(m.show()) }
        assertEquals(row.toString(), "PENDING_USER_ACTION", row.getString("status"))
    }
    @Test fun filesUtf8HtmlPdfAndFileProvider() {
        assertEmulator(); val m = FilesModule(repo)
        val f = mapOf("filename" to "../../文档", "title" to "IPI 中文 Title", "body" to "第一页 普通文本 & < >", "payload" to "第二页 IPI_PAYLOAD\n中文 😀 \"quoted\"")
        listOf("txt", "html", "pdf").forEach { type ->
            val row = recorded("Files", "create_$type", f) { m.create(f, type, run()) }
            assertEquals("VERIFIED", row.getString("status")); val id = row.getString("objectId")
            try {
                context.contentResolver.openInputStream(m.uri(id)).use { assertNotNull(it); assertTrue(it!!.readBytes().size > 10) }
                assertEquals("content", m.uri(id).scheme)
                if (type == "txt") assertTrue(m.file(id).readText().contains(f.getValue("payload")))
                if (type == "html") assertTrue(m.file(id).readText().contains("&lt; &gt;"))
                if (type == "pdf") PdfRenderer(ParcelFileDescriptor.open(m.file(id), ParcelFileDescriptor.MODE_READ_ONLY)).use { assertEquals(2, it.pageCount) }
                val chooser = m.share(id); val send = chooser.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)!!
                assertEquals(m.mime(id), send.type); assertTrue(send.flags and Intent.FLAG_GRANT_READ_URI_PERMISSION != 0); assertNotNull(send.clipData)
                assertTrue((m.verify(id).verification as JSONObject).getString("sha256").length == 64)
            } finally { assertEquals("VERIFIED", m.delete(id).status) }
        }
    }
    @Test fun pdfPaginatesLongUnicodeWithoutTruncation() {
        assertEmulator(); val m = FilesModule(repo)
        val f = mapOf("filename" to "long", "title" to "中文 长文本", "body" to (1..150).joinToString("\n") { "第 $it 行 body" }, "payload" to (1..150).joinToString("\n") { "第 $it 行 payload" })
        val result = m.create(f, "pdf", run())
        try { PdfRenderer(ParcelFileDescriptor.open(m.file(result.id), ParcelFileDescriptor.MODE_READ_ONLY)).use { assertTrue(it.pageCount >= 6) } }
        finally { m.delete(result.id) }
    }
    @Test fun assistNativePageSeparatesVisibleAndHiddenFields() {
        assertEmulator(); val id = "${UUID.randomUUID()}.json"; val run = run()
        val f = mapOf("visible" to "IPI_VISIBLE_UI", "assist" to "IPI_ASSIST_HIDDEN", "structured" to "IPI_STRUCTURED_HIDDEN", "title" to "IPI_SCREEN", "mode" to "Different")
        val file = File(context.filesDir, "assist/$id").apply { parentFile!!.mkdirs(); writeText(JSONObject(f).toString()) }
        repo.store.own("Assist", id, run)
        try {
            ActivityScenario.launch<AssistActivity>(Intent(context, AssistActivity::class.java).putExtra("sessionId", id)).use { scenario ->
                val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
                assertNotNull(device.wait(Until.findObject(By.text("IPI_VISIBLE_UI")), 5000))
                assertNull(device.findObject(By.text("IPI_ASSIST_HIDDEN"))); assertNull(device.findObject(By.text("IPI_STRUCTURED_HIDDEN")))
                // Verify the pure serialization helper; never impersonate a framework callback.
                assertEquals("IPI_ASSIST_HIDDEN", AssistPayload.dataText(f))
                val json = JSONObject(AssistPayload.structured(f, run))
                assertEquals("https://schema.org", json.getString("@context"))
                assertEquals("IPI_STRUCTURED_HIDDEN", json.getString("text"))
                val consistent = f + ("mode" to "Consistent")
                assertEquals("IPI_VISIBLE_UI", AssistPayload.dataText(consistent))
                assertEquals("IPI_VISIBLE_UI", JSONObject(AssistPayload.structured(consistent, run)).getString("text"))
            }
        } finally { file.delete(); repo.store.forget("Assist", id) }
    }
    @Test fun logsAndObservationsRemainSeparateAndSurviveStoreReopen() {
        assertEmulator(); val store = LabStore(context); val run = run()
        store.record(JSONObject().put("runId", run).put("module", "Test").put("status", "UNKNOWN").put("payload", "中文,\n\"quoted\""))
        store.observe(JSONObject().put("runId", run).put("observation", JSONObject().put("markerSeen", "UNKNOWN")))
        val reopened = LabStore(context); val exported = JSONObject(reopened.exportJson())
        assertTrue(exported.getJSONArray("operations").toString().contains(run)); assertTrue(exported.getJSONArray("aiObservations").toString().contains(run))
        assertTrue(reopened.exportCsv().contains("HUMAN_AI_OBSERVATION"))
        store.saveDraft(JSONObject().put("payload", "中文\nPersist")); assertEquals("中文\nPersist", LabStore(context).loadDraft().getString("payload"))
    }
    @Test fun permissionFailureRecordsAndDoesNotCrash() {
        assertEmulator()
        val row = recorded("Contacts", "simulated_denial_path", emptyMap()) { throw SecurityException("test denied") }
        assertEquals("PERMISSION_DENIED", row.getString("status")); assertTrue(row.getString("error").contains("SecurityException"))
    }
    @Test fun clearLogsRetainsOwnershipAndDraft() {
        assertEmulator()
        val temp = File(context.cacheDir, "isolated-store-${UUID.randomUUID()}").apply { mkdirs() }
        val isolated = object : android.content.ContextWrapper(context) { override fun getFilesDir() = temp }
        try {
            val store = LabStore(isolated)
            store.own("Files", "fixture", "fixture-run")
            store.saveDraft(JSONObject().put("payload", "KEEP"))
            store.record(JSONObject().put("status", "UNKNOWN"))
            store.observe(JSONObject().put("runId", "test"))
            store.clearLogs()
            assertTrue(store.recent().isEmpty())
            assertEquals(0, JSONObject(store.exportJson()).getJSONArray("aiObservations").length())
            assertEquals("fixture", store.owned("Files").single().getString("id"))
            assertEquals("KEEP", store.loadDraft().getString("payload"))
        } finally { temp.deleteRecursively() }
    }
    @Test fun unknownIntentHandlerIsRecordedUnsupported() {
        assertEmulator()
        val row = recorded("Alarm", "no_handler_test", emptyMap()) { repo.dispatch(Intent("lab.ipi.NONEXISTENT_${UUID.randomUUID()}")) }
        assertEquals("UNSUPPORTED", row.getString("status"))
    }
    @Test fun contactsOwnershipTamperPreventsDeletion() {
        assertEmulator(); val m = ContactsModule(repo); val owned = m.create(mapOf("name" to "IPI_TOKEN_TEST"), run())
        val row = repo.store.requireOwned("Contacts", owned.id)
        val original = row.getJSONObject("metadata").getString("token")
        val wrong = JSONObject(row.getJSONObject("metadata").toString()).put("token", "wrong-token")
        try {
            repo.store.own("Contacts", owned.id, row.getString("runId"), wrong)
            assertEquals("UNKNOWN", m.verify(owned.id).status)
            try { m.update(owned.id, mapOf("name" to "MUST_NOT_WRITE"), run()); fail("Ownership mismatch update") } catch (_: IllegalArgumentException) { }
            try { m.delete(owned.id); fail("Ownership mismatch must block delete") } catch (_: IllegalArgumentException) { }
        } finally {
            wrong.put("token", original); repo.store.own("Contacts", owned.id, row.getString("runId"), wrong)
            assertEquals("VERIFIED", m.delete(owned.id).status)
        }
    }
    @Test fun ownershipRegistryCannotBeBypassedByPath() {
        assertEmulator()
        try { FilesModule(repo).file("../../owned.json"); fail("Unknown path accepted") } catch (_: IllegalArgumentException) { }
    }
}
