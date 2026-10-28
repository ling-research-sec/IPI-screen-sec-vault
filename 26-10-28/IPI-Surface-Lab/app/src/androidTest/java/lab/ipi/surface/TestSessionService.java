package lab.ipi.surface;
import android.app.assist.AssistContent;
import android.app.assist.AssistStructure;
import android.content.Context;
import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;
import android.service.voice.VoiceInteractionSessionService;
import org.json.JSONArray;
import org.json.JSONObject;
public class TestSessionService extends VoiceInteractionSessionService {
    @Override public VoiceInteractionSession onNewSession(Bundle args) { return new ReceiverSession(this); }
    static class ReceiverSession extends VoiceInteractionSession {
        ReceiverSession(Context context) { super(context); }
        @Override public android.view.View onCreateContentView() {
            android.widget.TextView text = new android.widget.TextView(getContext()); text.setText("IPI test receiver · no AI model"); return text;
        }
        void walk(AssistStructure.ViewNode node, JSONArray texts) {
            if (node.getText() != null) texts.put(node.getText().toString());
            for (int i = 0; i < node.getChildCount(); i++) walk(node.getChildAt(i), texts);
        }
        JSONObject bundleJson(Bundle bundle) throws org.json.JSONException {
            JSONObject result = new JSONObject();
            if (bundle != null) for (String key : bundle.keySet()) {
                Object value = bundle.get(key);
                result.put(key, value instanceof Bundle ? bundleJson((Bundle) value) : String.valueOf(value));
            }
            return result;
        }
        @Override public void onHandleAssist(Bundle data, AssistStructure structure, AssistContent content) {
            try {
                JSONArray texts = new JSONArray();
                if (structure != null) for (int i = 0; i < structure.getWindowNodeCount(); i++) walk(structure.getWindowNodeAt(i).getRootViewNode(), texts);
                JSONObject result = new JSONObject().put("receiver", "EMULATOR_TEST_HARNESS_NOT_AI").put("time", java.time.Instant.now().toString())
                    .put("activity", structure == null ? null : structure.getActivityComponent().flattenToShortString())
                    .put("bundle", bundleJson(data)).put("structuredData", content == null ? null : content.getStructuredData()).put("viewTexts", texts);
                if (data != null && data.getBundle("data") != null) result.put("activityBundle", data.getBundle("data").toString());
                try (java.io.FileOutputStream out = new java.io.FileOutputStream(new java.io.File(getContext().getFilesDir(), "assist-capture.json"))) { out.write(result.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
            } catch (Exception e) { android.util.Log.e("IPITestReceiver", "capture failed", e); }
        }
    }
}
