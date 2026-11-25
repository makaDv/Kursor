package io.github.makadv.padlink;

import android.os.Bundle;
import android.view.KeyEvent;

import com.getcapacitor.BridgeActivity;

import io.github.makadv.padlink.nativebridge.PadLinkNativePlugin;

// Plugins (including the local padlink-native bridge) are registered automatically by `cap sync`.
public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Anti-tapjacking: ignore touches while another app draws over PadLink, so an
        // overlay cannot trick the user into typing the PC password or confirming a shutdown.
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().setFilterTouchesWhenObscured(true);
        }
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        // Optional "volume keys control the PC" mode (Tastiera > Multimedia).
        if (PadLinkNativePlugin.onVolumeKey(event.getKeyCode(), event.getAction() == KeyEvent.ACTION_DOWN)) {
            return true;
        }
        return super.dispatchKeyEvent(event);
    }
}
