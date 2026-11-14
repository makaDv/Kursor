package io.github.makadv.kursor;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.regex.Pattern;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Minimal secure key/value store for the refresh token.
 *
 * Values are encrypted with AES-256-GCM using a non-exportable key that lives in
 * the Android Keystore (hardware-backed where available). Only the ciphertext
 * reaches SharedPreferences, and app backup is disabled in the manifest.
 */
@CapacitorPlugin(name = "SecureStore")
public class SecureStorePlugin extends Plugin {

    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String KEY_ALIAS = "kursor_secure_store_v1";
    private static final String PREFS = "kursor_secure_store";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final Pattern KEY_PATTERN = Pattern.compile("^[a-z_]{1,32}$");

    private SharedPreferences prefs() {
        return getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private SecretKey getOrCreateKey() throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        KeyStore.Entry entry = ks.getEntry(KEY_ALIAS, null);
        if (entry instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(
            new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        );
        return generator.generateKey();
    }

    private String validKey(PluginCall call) {
        String key = call.getString("key");
        if (key == null || !KEY_PATTERN.matcher(key).matches()) {
            call.reject("invalid key");
            return null;
        }
        return key;
    }

    @PluginMethod
    public void set(PluginCall call) {
        String key = validKey(call);
        if (key == null) return;
        String value = call.getString("value");
        if (value == null || value.length() > 4096) {
            call.reject("invalid value");
            return;
        }
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
            byte[] ct = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
            String stored = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" + Base64.encodeToString(ct, Base64.NO_WRAP);
            prefs().edit().putString(key, stored).apply();
            call.resolve();
        } catch (Exception e) {
            call.reject("encryption failed");
        }
    }

    @PluginMethod
    public void get(PluginCall call) {
        String key = validKey(call);
        if (key == null) return;
        JSObject ret = new JSObject();
        String stored = prefs().getString(key, null);
        if (stored == null) {
            ret.put("value", (String) null);
            call.resolve(ret);
            return;
        }
        try {
            String[] parts = stored.split(":", 2);
            byte[] iv = Base64.decode(parts[0], Base64.NO_WRAP);
            byte[] ct = Base64.decode(parts[1], Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
            ret.put("value", new String(cipher.doFinal(ct), StandardCharsets.UTF_8));
        } catch (Exception e) {
            // Key invalidated or data tampered with: drop it, user pairs again.
            prefs().edit().remove(key).apply();
            ret.put("value", (String) null);
        }
        call.resolve(ret);
    }

    @PluginMethod
    public void remove(PluginCall call) {
        String key = validKey(call);
        if (key == null) return;
        prefs().edit().remove(key).apply();
        call.resolve();
    }
}
