package lab.ipi.surface.modules

import android.content.ClipData
import android.content.Intent
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.core.content.FileProvider
import lab.ipi.surface.data.TextCodec
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID

class FilesModule(private val repo: LabRepository) {
    private val dir = File(repo.context.filesDir, "documents").apply { mkdirs() }
    fun file(id: String): File {
        repo.store.requireOwned("Files", id)
        val f = File(dir, id); require(f.canonicalFile.parentFile == dir.canonicalFile) { "Path outside managed directory" }; return f
    }
    fun uri(id: String): Uri = FileProvider.getUriForFile(repo.context, "${repo.context.packageName}.files", file(id))
    fun mime(id: String) = when (id.substringAfterLast('.')) { "pdf" -> "application/pdf"; "html" -> "text/html"; else -> "text/plain" }
    fun create(f: Map<String, String>, kind: String, run: String): Outcome {
        require(kind in listOf("txt", "html", "pdf"))
        val id = "${UUID.randomUUID()}_${TextCodec.filename(f.orEmpty("filename"))}.$kind"
        val file = File(dir, id)
        val title = f.orEmpty("title"); val body = f.orEmpty("body"); val payload = f.orEmpty("payload")
        try {
            when (kind) {
                "txt" -> file.writeText("$title\n\n$body\n\n--- Payload ---\n$payload", Charsets.UTF_8)
                "html" -> file.writeText("<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\"><title>${TextCodec.html(title)}</title></head><body><h1>${TextCodec.html(title)}</h1><pre>${TextCodec.html(body)}</pre><hr><h2>Payload</h2><pre>${TextCodec.html(payload)}</pre></body></html>", Charsets.UTF_8)
                "pdf" -> pdf(file, title, body, payload)
            }
            repo.store.own("Files", id, run, JSONObject().put("kind", kind).put("fields", JSONObject(f)))
        } catch (e: Exception) { file.delete(); throw e }
        return verify(id).copy(system = "Wrote UTF-8 $kind / PDF document")
    }
    private fun pdf(file: File, title: String, body: String, payload: String) {
        val doc = PdfDocument()
        try {
            var pageIndex = 0
            fun section(heading: String, text: String) {
                val paint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 14f }
                val layout = StaticLayout.Builder.obtain("$heading\n\n$text", 0, ("$heading\n\n$text").length, paint, 499)
                    .setAlignment(Layout.Alignment.ALIGN_NORMAL).setIncludePad(true).setLineSpacing(3f, 1f).build()
                var firstLine = 0
                do {
                    val top = layout.getLineTop(firstLine); var last = firstLine
                    while (last < layout.lineCount && layout.getLineBottom(last) - top <= 720) last++
                    if (last == firstLine) last++
                    val height = layout.getLineTop(last) - top
                    val page = doc.startPage(PdfDocument.PageInfo.Builder(595, 842, ++pageIndex).create())
                    page.canvas.save(); page.canvas.translate(48f, 48f); page.canvas.clipRect(0, 0, 499, height)
                    page.canvas.translate(0f, -top.toFloat()); layout.draw(page.canvas); page.canvas.restore()
                    page.canvas.drawText("IPI Surface Lab / $pageIndex", 48f, 810f, paint)
                    doc.finishPage(page); firstLine = last
                } while (firstLine < layout.lineCount)
            }
            section(title, body); section("Payload", payload)
            FileOutputStream(file).use { doc.writeTo(it) }
        } finally { doc.close() }
    }
    fun verify(id: String): Outcome {
        val f = file(id); if (!f.isFile) return Outcome("UNKNOWN", "File missing", "NOT_FOUND", id)
        val digest = MessageDigest.getInstance("SHA-256"); f.inputStream().use { input -> val buffer = ByteArray(8192); var n = input.read(buffer); while (n >= 0) { digest.update(buffer, 0, n); n = input.read(buffer) } }
        val hash = digest.digest().joinToString("") { "%02x".format(it) }
        return Outcome("VERIFIED", "Reopened local file and hashed bytes", JSONObject().put("uri", uri(id).toString()).put("path", f.absolutePath).put("bytes", f.length()).put("sha256", hash).put("mime", mime(id)), id)
    }
    fun share(id: String): Intent {
        val uri = uri(id)
        val send = Intent(Intent.ACTION_SEND).setType(mime(id)).putExtra(Intent.EXTRA_STREAM, uri)
            .apply { clipData = ClipData.newRawUri("IPI file", uri) }.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        return Intent.createChooser(send, "分享实验文件（不代表模型已读取）").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    fun open(id: String) = Intent(Intent.ACTION_VIEW).setDataAndType(uri(id), mime(id))
        .apply { clipData = ClipData.newRawUri("IPI file", uri(id)) }.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    fun delete(id: String): Outcome {
        val f = file(id); val result = !f.exists() || f.delete(); val exists = f.exists()
        if (!exists) repo.store.forget("Files", id)
        return Outcome(if (result && !exists) "VERIFIED" else "FAILED", "delete=$result", "exists=$exists", id)
    }
}
