package lab.ipi.surface;
public class TestShowReceiver extends android.content.BroadcastReceiver {
    @Override public void onReceive(android.content.Context context, android.content.Intent intent) {
        if (TestVoiceService.active != null) TestVoiceService.active.showSession(new android.os.Bundle(), android.service.voice.VoiceInteractionSession.SHOW_WITH_ASSIST);
    }
}
