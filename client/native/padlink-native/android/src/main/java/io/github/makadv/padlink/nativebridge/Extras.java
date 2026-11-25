package io.github.makadv.padlink.nativebridge;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Handler;
import android.os.Looper;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/** LAN helpers: mDNS discovery of the PC and Wake-on-LAN. */
final class Extras {

    static final String SERVICE_TYPE = "_padlink._tcp.";

    static final class Found {
        final String host;
        final int port;
        final String fp;
        final String name;

        Found(String host, int port, String fp, String name) {
            this.host = host;
            this.port = port;
            this.fp = fp;
            this.name = name;
        }
    }

    private Extras() {}

    /** Browses _padlink._tcp for {@code timeoutMs}, resolving services one at a time. */
    static void discover(Context ctx, long timeoutMs, Consumer<List<Found>> done) {
        final NsdManager nsd = (NsdManager) ctx.getSystemService(Context.NSD_SERVICE);
        final Handler main = new Handler(Looper.getMainLooper());
        final List<Found> found = new ArrayList<>();
        final ArrayDeque<NsdServiceInfo> pending = new ArrayDeque<>();
        final boolean[] resolving = {false};
        final boolean[] finished = {false};

        final Runnable[] next = new Runnable[1];
        next[0] = () -> {
            if (finished[0] || resolving[0] || pending.isEmpty()) return;
            resolving[0] = true;
            NsdServiceInfo info = pending.poll();
            nsd.resolveService(info, new NsdManager.ResolveListener() {
                @Override
                public void onResolveFailed(NsdServiceInfo s, int errorCode) {
                    main.post(() -> {
                        resolving[0] = false;
                        next[0].run();
                    });
                }

                @Override
                public void onServiceResolved(NsdServiceInfo s) {
                    main.post(() -> {
                        resolving[0] = false;
                        InetAddress host = s.getHost();
                        if (host != null && host.getAddress().length == 4) {
                            Map<String, byte[]> attrs = s.getAttributes();
                            found.add(new Found(host.getHostAddress(), s.getPort(), text(attrs, "fp"), text(attrs, "name")));
                        }
                        next[0].run();
                    });
                }
            });
        };

        final NsdManager.DiscoveryListener listener = new NsdManager.DiscoveryListener() {
            @Override public void onStartDiscoveryFailed(String t, int e) { finish(); }
            @Override public void onStopDiscoveryFailed(String t, int e) {}
            @Override public void onDiscoveryStarted(String t) {}
            @Override public void onDiscoveryStopped(String t) {}
            @Override public void onServiceLost(NsdServiceInfo s) {}

            @Override
            public void onServiceFound(NsdServiceInfo s) {
                main.post(() -> {
                    pending.add(s);
                    next[0].run();
                });
            }

            private void finish() {
                main.post(() -> {
                    if (finished[0]) return;
                    finished[0] = true;
                    done.accept(found);
                });
            }
        };

        try {
            nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener);
        } catch (Exception e) {
            done.accept(found);
            return;
        }
        main.postDelayed(() -> {
            try {
                nsd.stopServiceDiscovery(listener);
            } catch (Exception ignored) {
                // already stopped
            }
            if (!finished[0]) {
                finished[0] = true;
                done.accept(found);
            }
        }, timeoutMs);
    }

    private static String text(Map<String, byte[]> attrs, String key) {
        byte[] v = attrs == null ? null : attrs.get(key);
        return v == null ? null : new String(v, StandardCharsets.UTF_8);
    }

    /** Magic packet (6x 0xFF + 16x MAC) to the LAN broadcast address, ports 9 and 7. */
    static void wakeOnLan(String mac) throws Exception {
        String hex = mac.replaceAll("[^0-9A-Fa-f]", "");
        if (hex.length() != 12) throw new IllegalArgumentException("bad mac");
        byte[] macBytes = new byte[6];
        for (int i = 0; i < 6; i++) macBytes[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
        byte[] packet = new byte[6 + 16 * 6];
        for (int i = 0; i < 6; i++) packet[i] = (byte) 0xFF;
        for (int i = 6; i < packet.length; i += 6) System.arraycopy(macBytes, 0, packet, i, 6);
        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setBroadcast(true);
            InetAddress bcast = InetAddress.getByName("255.255.255.255");
            for (int port : new int[] {9, 7}) {
                socket.send(new DatagramPacket(packet, packet.length, bcast, port));
            }
        }
    }
}
