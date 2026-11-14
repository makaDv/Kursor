package io.github.makadv.padlink;

import android.view.KeyEvent;

import com.getcapacitor.BridgeActivity;

import io.github.makadv.kursor.nativebridge.KursorNativePlugin;

// Plugins (including the local kursor-native bridge) are registered automatically by `cap sync`.
public class MainActivity extends BridgeActivity {
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        // Optional "volume keys control the PC" mode (Tastiera > Multimedia).
        if (KursorNativePlugin.onVolumeKey(event.getKeyCode(), event.getAction() == KeyEvent.ACTION_DOWN)) {
            return true;
        }
        return super.dispatchKeyEvent(event);
    }
}
