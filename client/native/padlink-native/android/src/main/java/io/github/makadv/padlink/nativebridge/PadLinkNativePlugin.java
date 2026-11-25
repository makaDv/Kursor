package io.github.makadv.padlink.nativebridge;

import android.util.Base64;

import androidx.activity.result.ActivityResult;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.journeyapps.barcodescanner.ScanIntentResult;
import com.journeyapps.barcodescanner.ScanOptions;

import java.io.IOException;
import java.security.cert.X509Certificate;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

/**
 * Native bridge used by the PadLink app (see client/src/lib/native.ts).
 *
 * All traffic to the PC goes through here instead of the WebView so the PC's
 * certificate can be pinned without installing any CA on the phone.
 */
@CapacitorPlugin(name = "PadLinkNative")
public class PadLinkNativePlugin extends Plugin {

    private static final Pattern KEY_PATTERN = Pattern.compile("^[a-z_]{1,32}$");
    private static final Pattern PIN_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{43}$");
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private static final int MAX_BODY = 1024 * 1024;
    // Same value the server allow-lists for the bundled app (security/origin.py).
    private static final String APP_ORIGIN = "https://localhost";

    private final Map<String, WebSocket> sockets = new ConcurrentHashMap<>();
    private SecureStore store;

    @Override
    public void load() {
        store = new SecureStore(getContext());
    }

    @Override
    protected void handleOnDestroy() {
        for (WebSocket ws : sockets.values()) ws.cancel();
        sockets.clear();
    }

    // ---- helpers -------------------------------------------------------------------
    private static boolean isPinMismatch(Throwable t) {
        for (int i = 0; t != null && i < 10; i++, t = t.getCause()) {
            if (t instanceof PinnedTls.PinMismatchException) return true;
        }
        return false;
    }

    private static String errorCode(Throwable t) {
        if (isPinMismatch(t)) return "pin_mismatch";
        for (int i = 0; t != null && i < 10; i++, t = t.getCause()) {
            if (t instanceof javax.net.ssl.SSLException) return "tls";
        }
        return "network";
    }

    /** Returns the pin or null; rejects the call (and returns "") if the pin is malformed. */
    private String readPin(PluginCall call) {
        String pin = call.getString("pin");
        if (pin == null || pin.isEmpty()) return null;
        if (!PIN_PATTERN.matcher(pin).matches()) {
            call.reject("invalid pin", "bad_request");
            return "";
        }
        return pin;
    }

    private static boolean httpsOnly(String url, String scheme) {
        return url != null && url.regionMatches(true, 0, scheme + "://", 0, scheme.length() + 3);
    }

    // ---- secure storage ----------------------------------------------------------------
    private String validKey(PluginCall call) {
        String key = call.getString("key");
        if (key == null || !KEY_PATTERN.matcher(key).matches()) {
            call.reject("invalid key", "bad_request");
            return null;
        }
        return key;
    }

    @PluginMethod
    public void secureGet(PluginCall call) {
        String key = validKey(call);
        if (key == null) return;
        JSObject ret = new JSObject();
        String v = store.get(key);
        ret.put("value", v);
        call.resolve(ret);
    }

    @PluginMethod
    public void secureSet(PluginCall call) {
        String key = validKey(call);
        if (key == null) return;
        String value = call.getString("value");
        if (value == null || value.length() > 4096) {
            call.reject("invalid value", "bad_request");
            return;
        }
        try {
            store.set(key, value);
            call.resolve();
        } catch (Exception e) {
            call.reject("encryption failed", "storage");
        }
    }

    @PluginMethod
    public void secureRemove(PluginCall call) {
        String key = validKey(call);
        if (key == null) return;
        store.remove(key);
        call.resolve();
    }

    // ---- HTTPS -----------------------------------------------------------------------------
    @PluginMethod
    public void request(final PluginCall call) {
        String url = call.getString("url");
        if (!httpsOnly(url, "https")) {
            call.reject("https only", "bad_request");
            return;
        }
        String pin = readPin(call);
        if ("".equals(pin)) return;
        String method = call.getString("method", "GET").toUpperCase();
        String body = call.getString("body");

        Request.Builder rb = new Request.Builder().url(url).header("Origin", APP_ORIGIN);
        JSObject headers = call.getObject("headers", new JSObject());
        for (Iterator<String> it = headers.keys(); it.hasNext(); ) {
            String name = it.next();
            String value = headers.optString(name, null);
            if (value != null) rb.header(name, value);
        }
        RequestBody rqBody = null;
        if (body != null || method.equals("POST") || method.equals("PUT") || method.equals("PATCH")) {
            rqBody = RequestBody.create(body == null ? "" : body, JSON);
        }
        try {
            rb.method(method, rqBody);
        } catch (IllegalArgumentException e) {
            call.reject("bad method", "bad_request");
            return;
        }

        OkHttpClient client;
        try {
            client = PinnedTls.client(pin);
        } catch (Exception e) {
            call.reject("tls init failed", "tls");
            return;
        }
        client.newCall(rb.build()).enqueue(new Callback() {
            @Override
            public void onFailure(Call c, IOException e) {
                call.reject(e.getClass().getSimpleName(), errorCode(e));
            }

            @Override
            public void onResponse(Call c, Response response) {
                try (ResponseBody rsp = response.body()) {
                    JSObject ret = new JSObject();
                    ret.put("status", response.code());
                    JSObject h = new JSObject();
                    for (String name : response.headers().names()) {
                        h.put(name.toLowerCase(), response.header(name));
                    }
                    ret.put("headers", h);
                    String text = "";
                    if (rsp != null) {
                        okio.BufferedSource src = rsp.source();
                        src.request(MAX_BODY + 1L);
                        if (src.getBuffer().size() > MAX_BODY) {
                            call.reject("response too large", "network");
                            return;
                        }
                        text = src.getBuffer().readUtf8();
                    }
                    ret.put("body", text);
                    call.resolve(ret);
                } catch (Exception e) {
                    call.reject("read failed", "network");
                }
            }
        });
    }

    /**
     * Connects once without trusting anything, to show the user the PC's CA fingerprint
     * (manual pairing without QR). Nothing but a GET /api/health is sent.
     */
    @PluginMethod
    public void probe(final PluginCall call) {
        String url = call.getString("url");
        if (!httpsOnly(url, "https")) {
            call.reject("https only", "bad_request");
            return;
        }
        final PinnedTls.Probe probe;
        try {
            probe = new PinnedTls.Probe();
        } catch (Exception e) {
            call.reject("tls init failed", "tls");
            return;
        }
        Request req = new Request.Builder().url(url.replaceAll("/+$", "") + "/api/health").get().build();
        probe.client.newCall(req).enqueue(new Callback() {
            @Override
            public void onFailure(Call c, IOException e) {
                call.reject(e.getClass().getSimpleName(), errorCode(e));
            }

            @Override
            public void onResponse(Call c, Response response) {
                response.close();
                JSObject ret = new JSObject();
                ret.put("publiclyTrusted", probe.publiclyTrusted);
                try {
                    X509Certificate root = probe.root();
                    ret.put("fingerprint", root == null ? null : PinnedTls.fingerprint(root));
                } catch (Exception e) {
                    ret.put("fingerprint", (String) null);
                }
                call.resolve(ret);
            }
        });
    }

    // ---- WebSocket -------------------------------------------------------------------------
    private void emit(String id, String type, JSObject extra) {
        JSObject ev = extra == null ? new JSObject() : extra;
        ev.put("id", id);
        ev.put("type", type);
        notifyListeners("ws", ev);
    }

    @PluginMethod
    public void wsOpen(PluginCall call) {
        String url = call.getString("url");
        if (!httpsOnly(url, "wss")) {
            call.reject("wss only", "bad_request");
            return;
        }
        String pin = readPin(call);
        if ("".equals(pin)) return;
        OkHttpClient client;
        try {
            client = PinnedTls.client(pin);
        } catch (Exception e) {
            call.reject("tls init failed", "tls");
            return;
        }
        final String id = UUID.randomUUID().toString();
        // OkHttp wants http(s) here; it upgrades to WebSocket itself.
        Request req = new Request.Builder().url("https" + url.substring(3)).header("Origin", APP_ORIGIN).build();
        WebSocket ws = client.newWebSocket(req, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                emit(id, "open", null);
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                JSObject ev = new JSObject();
                ev.put("data", text);
                emit(id, "text", ev);
            }

            @Override
            public void onMessage(WebSocket webSocket, ByteString bytes) {
                JSObject ev = new JSObject();
                ev.put("data", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP));
                emit(id, "binary", ev);
            }

            @Override
            public void onClosing(WebSocket webSocket, int code, String reason) {
                webSocket.close(code == 1005 ? 1000 : code, null);
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                if (sockets.remove(id) == null) return;
                JSObject ev = new JSObject();
                ev.put("code", code);
                ev.put("reason", reason);
                emit(id, "close", ev);
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                if (sockets.remove(id) == null) return;
                JSObject ev = new JSObject();
                ev.put("code", 1006);
                ev.put("reason", errorCode(t));
                emit(id, "close", ev);
            }
        });
        sockets.put(id, ws);
        JSObject ret = new JSObject();
        ret.put("id", id);
        call.resolve(ret);
    }

    @PluginMethod
    public void wsSend(PluginCall call) {
        WebSocket ws = sockets.get(call.getString("id", ""));
        String data = call.getString("data");
        JSObject ret = new JSObject();
        boolean ok = ws != null && data != null && ws.send(data);
        ret.put("ok", ok);
        ret.put("buffered", ws == null ? 0 : ws.queueSize());
        call.resolve(ret);
    }

    @PluginMethod
    public void wsClose(PluginCall call) {
        WebSocket ws = sockets.get(call.getString("id", ""));
        if (ws != null) {
            int code = call.getInt("code", 1000);
            if (!ws.close(code, call.getString("reason"))) ws.cancel();
        }
        call.resolve();
    }

    // ---- biometric unlock ------------------------------------------------------------------
    private static final int AUTHENTICATORS =
        androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
            | androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL;

    /**
     * FLAG_SECURE on/off: while on, Android blocks screenshots, screen recording and the
     * preview in "recent apps". Used on the password/PIN screens and the PC screen view.
     */
    @PluginMethod
    public void setSecure(PluginCall call) {
        final boolean on = Boolean.TRUE.equals(call.getBoolean("enabled", false));
        getActivity().runOnUiThread(() -> {
            if (on) {
                getActivity().getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE);
            } else {
                getActivity().getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE);
            }
            call.resolve();
        });
    }

    @PluginMethod
    public void biometricAvailable(PluginCall call) {
        int r = androidx.biometric.BiometricManager.from(getContext()).canAuthenticate(AUTHENTICATORS);
        JSObject ret = new JSObject();
        ret.put("available", r == androidx.biometric.BiometricManager.BIOMETRIC_SUCCESS);
        call.resolve(ret);
    }

    @PluginMethod
    public void biometricAuth(final PluginCall call) {
        final String reason = call.getString("reason", "Sblocca PadLink");
        getActivity().runOnUiThread(() -> {
            try {
                androidx.biometric.BiometricPrompt prompt = new androidx.biometric.BiometricPrompt(
                    (androidx.fragment.app.FragmentActivity) getActivity(),
                    androidx.core.content.ContextCompat.getMainExecutor(getContext()),
                    new androidx.biometric.BiometricPrompt.AuthenticationCallback() {
                        @Override
                        public void onAuthenticationSucceeded(androidx.biometric.BiometricPrompt.AuthenticationResult r) {
                            JSObject ret = new JSObject();
                            ret.put("ok", true);
                            call.resolve(ret);
                        }

                        @Override
                        public void onAuthenticationError(int code, CharSequence msg) {
                            JSObject ret = new JSObject();
                            ret.put("ok", false);
                            ret.put("error", String.valueOf(msg));
                            call.resolve(ret);
                        }
                    });
                prompt.authenticate(new androidx.biometric.BiometricPrompt.PromptInfo.Builder()
                    .setTitle("PadLink")
                    .setSubtitle(reason)
                    .setAllowedAuthenticators(AUTHENTICATORS)
                    .build());
            } catch (Exception e) {
                call.reject("biometric unavailable", "unavailable");
            }
        });
    }

    // ---- LAN discovery / Wake-on-LAN ---------------------------------------------------------
    @PluginMethod
    public void discover(final PluginCall call) {
        long timeout = Math.max(500, Math.min(10_000, call.getInt("timeout", 3000)));
        Extras.discover(getContext(), timeout, found -> {
            com.getcapacitor.JSArray arr = new com.getcapacitor.JSArray();
            for (Extras.Found f : found) {
                JSObject o = new JSObject();
                o.put("host", f.host);
                o.put("port", f.port);
                o.put("fp", f.fp);
                o.put("name", f.name);
                arr.put(o);
            }
            JSObject ret = new JSObject();
            ret.put("pcs", arr);
            call.resolve(ret);
        });
    }

    @PluginMethod
    public void wakeOnLan(final PluginCall call) {
        final String mac = call.getString("mac");
        new Thread(() -> {
            try {
                Extras.wakeOnLan(mac == null ? "" : mac);
                call.resolve();
            } catch (Exception e) {
                call.reject("wake-on-lan failed", "network");
            }
        }).start();
    }

    // ---- store review --------------------------------------------------------------------------
    @PluginMethod
    public void requestReview(final PluginCall call) {
        final com.google.android.play.core.review.ReviewManager manager =
            com.google.android.play.core.review.ReviewManagerFactory.create(getContext());
        manager.requestReviewFlow().addOnCompleteListener(task -> {
            if (!task.isSuccessful()) {
                call.resolve();
                return;
            }
            manager.launchReviewFlow(getActivity(), task.getResult()).addOnCompleteListener(t -> call.resolve());
        });
    }

    // ---- hardware volume keys as PC volume (opt-in, only while the app is in front) ---------------
    private static volatile PadLinkNativePlugin instance;
    private static volatile boolean captureVolume = false;

    @PluginMethod
    public void setVolumeKeyCapture(PluginCall call) {
        instance = this;
        captureVolume = Boolean.TRUE.equals(call.getBoolean("enabled", false));
        call.resolve();
    }

    /** Called by MainActivity.dispatchKeyEvent; returns true if the key was consumed. */
    public static boolean onVolumeKey(int keyCode, boolean down) {
        PadLinkNativePlugin p = instance;
        if (!captureVolume || p == null) return false;
        if (keyCode != android.view.KeyEvent.KEYCODE_VOLUME_UP && keyCode != android.view.KeyEvent.KEYCODE_VOLUME_DOWN) {
            return false;
        }
        if (down) {
            JSObject ev = new JSObject();
            ev.put("key", keyCode == android.view.KeyEvent.KEYCODE_VOLUME_UP ? "up" : "down");
            p.notifyListeners("volumeKey", ev);
        }
        return true;
    }

    // ---- launcher shortcuts (padlink://tab/<name>) ------------------------------------------------
    private static String tabFrom(android.content.Intent intent) {
        if (intent == null || intent.getData() == null) return null;
        android.net.Uri u = intent.getData();
        if (!"padlink".equals(u.getScheme()) || !"tab".equals(u.getHost())) return null;
        String tab = u.getLastPathSegment();
        return tab != null && tab.matches("^[a-z]{1,16}$") ? tab : null;
    }

    @PluginMethod
    public void getLaunchTab(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("tab", tabFrom(getActivity().getIntent()));
        call.resolve(ret);
    }

    @Override
    protected void handleOnNewIntent(android.content.Intent intent) {
        super.handleOnNewIntent(intent);
        String tab = tabFrom(intent);
        if (tab != null) {
            JSObject ev = new JSObject();
            ev.put("tab", tab);
            notifyListeners("launchTab", ev);
        }
    }

    // ---- QR scanner ------------------------------------------------------------------------
    @PluginMethod
    public void scanQr(PluginCall call) {
        ScanOptions opts = new ScanOptions()
            .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            .setPrompt("Inquadra il QR mostrato da PadLink sul PC")
            .setBeepEnabled(false)
            .setOrientationLocked(false);
        startActivityForResult(call, opts.createScanIntent(getActivity()), "onScanResult");
    }

    @ActivityCallback
    private void onScanResult(PluginCall call, ActivityResult result) {
        if (call == null) return;
        ScanIntentResult r = ScanIntentResult.parseActivityResult(result.getResultCode(), result.getData());
        JSObject ret = new JSObject();
        String contents = r.getContents();
        ret.put("value", contents);
        call.resolve(ret);
    }
}
