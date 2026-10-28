package lab.ipi.surface;
public class TestRecognitionService extends android.speech.RecognitionService {
    @Override public void onStartListening(android.content.Intent intent, Callback listener) { try { listener.error(7); } catch (android.os.RemoteException ignored) {} }
    @Override public void onStopListening(Callback listener) { }
    @Override public void onCancel(Callback listener) { }
}
