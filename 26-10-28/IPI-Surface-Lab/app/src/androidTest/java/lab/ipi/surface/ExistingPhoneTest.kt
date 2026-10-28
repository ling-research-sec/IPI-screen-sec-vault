package lab.ipi.surface

import android.Manifest
import android.content.ContentUris
import android.content.ContentValues
import android.provider.ContactsContract as C
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import lab.ipi.surface.modules.ExistingPhoneModule
import lab.ipi.surface.modules.LabRepository
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ExistingPhoneTest {
    @get:Rule val grant = GrantPermissionRule.grant(Manifest.permission.READ_CONTACTS, Manifest.permission.WRITE_CONTACTS)
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun fixture(block: (LabRepository, android.net.Uri, android.net.Uri) -> Unit) {
        check(android.os.Build.MODEL.contains("sdk")) { "Disposable emulator only" }
        val r = context.contentResolver
        // Deliberately not created or registered through ContactsModule/LabStore.
        val raw = r.insert(C.RawContacts.CONTENT_URI, ContentValues().apply { putNull("account_name"); putNull("account_type"); put("aggregation_mode", 3) })!!
        val id = ContentUris.parseId(raw)
        try {
            r.insert(C.Data.CONTENT_URI, ContentValues().apply { put(C.Data.RAW_CONTACT_ID,id); put(C.Data.MIMETYPE,C.CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE); put(C.Data.DATA1,"Alice IPI External Fixture") })
            val phone = r.insert(C.Data.CONTENT_URI, ContentValues().apply { put(C.Data.RAW_CONTACT_ID,id); put(C.Data.MIMETYPE,C.CommonDataKinds.Phone.CONTENT_ITEM_TYPE); put(C.CommonDataKinds.Phone.NUMBER,"1234") })!!
            val second = r.insert(C.Data.CONTENT_URI, ContentValues().apply { put(C.Data.RAW_CONTACT_ID,id); put(C.Data.MIMETYPE,C.CommonDataKinds.Phone.CONTENT_ITEM_TYPE); put(C.CommonDataKinds.Phone.NUMBER,"9999") })!!
            val repo = LabRepository(context)
            assertTrue(repo.store.owned("Contacts").none { it.getString("id")==id.toString() })
            block(repo,phone,second)
            assertTrue(repo.store.owned("Contacts").none { it.getString("id")==id.toString() })
        } finally { r.delete(raw,null,null); java.io.File(context.filesDir,"selected-existing-phone.json").delete() }
    }
    @Test fun unregisteredPhoneChangesAndRestoresWithoutTouchingSecondNumber() = fixture { repo,phone,second ->
        val m = ExistingPhoneModule(repo)
        assertEquals("VERIFIED",m.select(phone).status)
        assertEquals("VERIFIED",m.update("4567").status)
        assertEquals("4567",(m.querySelected().verification as org.json.JSONObject).getString("number"))
        val reopened=ExistingPhoneModule(repo)
        assertEquals("1234",reopened.snapshot()!!.getString("originalNumber"))
        assertEquals("VERIFIED",reopened.update("",restore=true).status)
        assertEquals("1234",(reopened.querySelected().verification as org.json.JSONObject).getString("number"))
        context.contentResolver.query(second,arrayOf(C.CommonDataKinds.Phone.NUMBER),null,null,null).use { c -> assertTrue(c!!.moveToFirst());assertEquals("9999",c.getString(0)) }
    }
    @Test fun outsideChangesBlockOverwriteAndKeepOriginal() = fixture { repo,phone,_ ->
        val m=ExistingPhoneModule(repo);m.select(phone)
        context.contentResolver.update(phone,ContentValues().apply { put(C.CommonDataKinds.Phone.NUMBER,"7777") },null,null)
        try { m.update("4567");fail("External change overwritten") } catch (_:IllegalArgumentException) { }
        assertEquals("1234",m.snapshot()!!.getString("originalNumber"))
        assertEquals("7777",(m.querySelected().verification as org.json.JSONObject).getString("number"))
    }
}
