package lab.ipi.surface.modules

import android.app.NotificationManager
import android.app.NotificationChannel
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.Person
import lab.ipi.surface.MainActivity
import lab.ipi.surface.R
import org.json.JSONArray
import org.json.JSONObject

class NotificationsModule(private val repo: LabRepository) {
    private val manager get() = repo.context.getSystemService(NotificationManager::class.java)
    companion object { const val CHANNEL = "ipi_experiments_v1" }
    fun post(f: Map<String, String>, run: String, updateId: String? = null): Outcome {
        repo.requirePermissions("Notifications")
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "IPI 实验通知", NotificationManager.IMPORTANCE_DEFAULT))
        if (!NotificationManagerCompat.from(repo.context).areNotificationsEnabled() || manager.getNotificationChannel(CHANNEL).importance == NotificationManager.IMPORTANCE_NONE)
            return Outcome("PERMISSION_DENIED", "Notifications or experiment channel disabled", "NOT_POSTED")
        val id = if (updateId != null) { repo.store.requireOwned("Notifications", updateId); updateId.toInt() }
        else {
            val p = repo.context.getSharedPreferences("notification_ids", 0)
            val next = p.getInt("next", 1000) + 1; check(p.edit().putInt("next", next).commit()); next
        }
        val callback = Intent(repo.context, MainActivity::class.java).setAction("lab.ipi.surface.NOTIFICATION_CLICK")
            .putExtra("runId", run).putExtra("notificationId", id)
        val pending = PendingIntent.getActivity(repo.context, id, callback, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val b = NotificationCompat.Builder(repo.context, CHANNEL).setSmallIcon(R.drawable.ic_lab)
            .setContentTitle(f.orEmpty("title")).setContentText(f.orEmpty("body"))
            .setContentIntent(pending).setAutoCancel(false).addAction(R.drawable.ic_lab, "记录本地点击", pending)
        when (f["style"]) {
            "BigText" -> b.setStyle(NotificationCompat.BigTextStyle().bigText(f.orEmpty("body")))
            "Messaging" -> {
                val style = NotificationCompat.MessagingStyle(Person.Builder().setName("Researcher").build())
                    .setConversationTitle(f.orEmpty("title")).setGroupConversation(true)
                val sender = Person.Builder().setName(f["sender"].orEmpty().ifBlank { "IPI Sender" }).build()
                f.orEmpty("messages").lines().forEachIndexed { i, message -> style.addMessage(message, System.currentTimeMillis() + i, sender) }
                b.setStyle(style)
            }
        }
        // Register before notify; a post failure can then still be cleaned safely.
        repo.store.own("Notifications", id.toString(), run, JSONObject().put("fields", JSONObject(f)))
        manager.notify(id, b.build())
        return Outcome("POSTED", "NotificationManager.notify returned", "Query active notifications separately; not proof of AI reading", id.toString())
    }
    fun verify(): Outcome {
        val owned = repo.store.owned("Notifications").map { it.getString("id").toInt() }.toSet()
        val rows = JSONArray()
        manager.activeNotifications.filter { it.id in owned }.forEach { n ->
            val messages = JSONArray()
            NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(n.notification)?.messages?.forEach { message ->
                messages.put(JSONObject().put("text", message.text.toString()).put("timestamp", message.timestamp).put("sender", message.person?.name?.toString()))
            }
            rows.put(JSONObject().put("id", n.id).put("postTime", n.postTime)
                .put("title", n.notification.extras.getCharSequence("android.title")?.toString())
                .put("text", n.notification.extras.getCharSequence("android.text")?.toString())
                .put("bigText", n.notification.extras.getCharSequence("android.bigText")?.toString()).put("messages", messages))
        }
        return Outcome(if (rows.length() > 0) "VERIFIED" else "UNKNOWN", "getActiveNotifications returned ${rows.length()} owned notifications", rows)
    }
    fun delete(id: String): Outcome {
        repo.store.requireOwned("Notifications", id); manager.cancel(id.toInt())
        val exists = manager.activeNotifications.any { it.id == id.toInt() }
        if (!exists) repo.store.forget("Notifications", id)
        return Outcome(if (exists) "UNKNOWN" else "VERIFIED", "cancel returned", "active=$exists", id)
    }
}
