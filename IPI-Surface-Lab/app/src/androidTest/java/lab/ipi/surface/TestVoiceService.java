package lab.ipi.surface;
public class TestVoiceService extends android.service.voice.VoiceInteractionService {
    static TestVoiceService active;
    @Override public void onReady() { super.onReady(); active = this; }
    @Override public void onShutdown() { active = null; super.onShutdown(); }
}
