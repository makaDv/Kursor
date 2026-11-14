package io.github.makadv.kursor.nativebridge;

import android.util.Base64;

import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Collections;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

import okhttp3.ConnectionSpec;
import okhttp3.OkHttpClient;

/**
 * TLS trust for connections to the user's PC.
 *
 * With a pin (SHA-256 of the PC's local CA certificate, delivered by the pairing
 * QR code or confirmed by the user through the verification code) the chain is
 * validated with that CA as the ONLY trust anchor: system and user-installed CAs
 * are ignored, so no other certificate authority can intercept the connection.
 * Hostname verification is not needed with a pin (see build()); with system trust it stays on.
 *
 * Without a pin (e.g. a Cloudflare tunnel with a public certificate) the normal
 * system trust store is used. Cleartext HTTP is never allowed.
 */
final class PinnedTls {

    static final class PinMismatchException extends CertificateException {
        PinMismatchException() {
            super("pin_mismatch");
        }
    }

    private static final Map<String, OkHttpClient> CLIENTS = new ConcurrentHashMap<>();
    private static final String SYSTEM = "<system>";

    private PinnedTls() {}

    static String fingerprint(X509Certificate cert) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(cert.getEncoded());
        return Base64.encodeToString(digest, Base64.URL_SAFE | Base64.NO_PADDING | Base64.NO_WRAP);
    }

    static X509TrustManager systemTrust() throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init((KeyStore) null);
        return firstX509(tmf.getTrustManagers());
    }

    private static X509TrustManager firstX509(TrustManager[] managers) {
        for (TrustManager tm : managers) {
            if (tm instanceof X509TrustManager) return (X509TrustManager) tm;
        }
        throw new IllegalStateException("no X509TrustManager");
    }

    /** Accepts a chain only if it validates against the pinned certificate as the sole anchor. */
    static X509TrustManager pinnedTrust(final String pin) {
        return new X509TrustManager() {
            @Override
            public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
                throw new CertificateException("client certificates not supported");
            }

            @Override
            public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
                if (chain == null || chain.length == 0) throw new PinMismatchException();
                X509Certificate anchor = null;
                try {
                    for (X509Certificate c : chain) {
                        if (MessageDigest.isEqual(fingerprint(c).getBytes(), pin.getBytes())) {
                            anchor = c;
                            break;
                        }
                    }
                } catch (Exception e) {
                    throw new CertificateException(e);
                }
                if (anchor == null || anchor.getBasicConstraints() < 0) throw new PinMismatchException();
                try {
                    KeyStore ks = KeyStore.getInstance(KeyStore.getDefaultType());
                    ks.load(null, null);
                    ks.setCertificateEntry("kursor-pc", anchor);
                    TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
                    tmf.init(ks);
                    firstX509(tmf.getTrustManagers()).checkServerTrusted(chain, authType);
                } catch (CertificateException e) {
                    throw e;
                } catch (Exception e) {
                    throw new CertificateException(e);
                }
            }

            @Override
            public X509Certificate[] getAcceptedIssuers() {
                return new X509Certificate[0];
            }
        };
    }

    private static OkHttpClient build(X509TrustManager tm, boolean pinned) throws Exception {
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, new TrustManager[] {tm}, null);
        OkHttpClient.Builder b = new OkHttpClient.Builder();
        if (pinned) {
            // The pinned CA is private to this one PC (and name-constrained): it IS the identity.
            // Skipping the hostname check lets the app follow the PC to a new DHCP address
            // (found again via mDNS) before the PC has re-issued its certificate.
            b.hostnameVerifier((host, session) -> true);
        }
        return b
            .sslSocketFactory(ctx.getSocketFactory(), tm)
            .connectionSpecs(Collections.singletonList(ConnectionSpec.MODERN_TLS))
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .build();
    }

    /** Shared client per pin (connection pooling); {@code pin == null} means system trust. */
    static OkHttpClient client(String pin) throws Exception {
        String key = pin == null ? SYSTEM : pin;
        OkHttpClient c = CLIENTS.get(key);
        if (c != null) return c;
        c = build(pin == null ? systemTrust() : pinnedTrust(pin), pin != null);
        CLIENTS.put(key, c);
        return c;
    }

    /**
     * Probe-only client: records the presented chain and accepts it, so the app can show
     * the CA fingerprint as a verification code. Used for a single GET /api/health; no
     * credentials or user data are ever sent over a probed connection.
     */
    static final class Probe {
        volatile X509Certificate[] chain;
        volatile boolean publiclyTrusted;
        final OkHttpClient client;

        Probe() throws Exception {
            final X509TrustManager system = systemTrust();
            X509TrustManager capture = new X509TrustManager() {
                @Override
                public void checkClientTrusted(X509Certificate[] c, String a) throws CertificateException {
                    throw new CertificateException("unsupported");
                }

                @Override
                public void checkServerTrusted(X509Certificate[] c, String a) {
                    chain = c == null ? null : Arrays.copyOf(c, c.length);
                    try {
                        system.checkServerTrusted(c, a);
                        publiclyTrusted = true;
                    } catch (Exception ignored) {
                        publiclyTrusted = false;
                    }
                }

                @Override
                public X509Certificate[] getAcceptedIssuers() {
                    return new X509Certificate[0];
                }
            };
            SSLContext ctx = SSLContext.getInstance("TLS");
            ctx.init(null, new TrustManager[] {capture}, null);
            client = new OkHttpClient.Builder()
                .sslSocketFactory(ctx.getSocketFactory(), capture)
                .hostnameVerifier((h, s) -> true)
                .connectionSpecs(Collections.singletonList(ConnectionSpec.MODERN_TLS))
                .followRedirects(false)
                .followSslRedirects(false)
                .connectTimeout(8, TimeUnit.SECONDS)
                .readTimeout(8, TimeUnit.SECONDS)
                .build();
        }

        /** The self-signed root of the presented chain (the PC's local CA), or null. */
        X509Certificate root() {
            X509Certificate[] c = chain;
            if (c == null || c.length == 0) return null;
            for (X509Certificate cert : c) {
                if (cert.getBasicConstraints() >= 0
                    && cert.getSubjectX500Principal().equals(cert.getIssuerX500Principal())) {
                    return cert;
                }
            }
            return null;
        }
    }
}
