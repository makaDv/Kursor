import AVFoundation
import UIKit

/// Full-screen QR scanner built on AVFoundation (on-device, no third-party SDK).
/// Calls `completion` exactly once: the QR text, or nil if cancelled/denied.
final class QrScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let completion: (String?) -> Void
    private let session = AVCaptureSession()
    private var preview: AVCaptureVideoPreviewLayer?
    private var finished = false

    init(completion: @escaping (String?) -> Void) {
        self.completion = completion
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black

        let hint = UILabel()
        hint.text = "Inquadra il QR mostrato da PadLink sul PC"
        hint.textColor = .white
        hint.font = .preferredFont(forTextStyle: .headline)
        hint.numberOfLines = 0
        hint.textAlignment = .center
        hint.translatesAutoresizingMaskIntoConstraints = false

        let cancel = UIButton(type: .system)
        cancel.setTitle("Annulla", for: .normal)
        cancel.titleLabel?.font = .preferredFont(forTextStyle: .title3)
        cancel.tintColor = .white
        cancel.addTarget(self, action: #selector(cancelTapped), for: .touchUpInside)
        cancel.translatesAutoresizingMaskIntoConstraints = false

        view.addSubview(hint)
        view.addSubview(cancel)
        NSLayoutConstraint.activate([
            hint.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 24),
            hint.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            hint.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            cancel.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -24),
            cancel.centerXAnchor.constraint(equalTo: view.centerXAnchor)
        ])

        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            configure()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async { granted ? self.configure() : self.finish(nil) }
            }
        default:
            hint.text = "Accesso alla fotocamera negato. Abilitalo in Impostazioni › PadLink, oppure inserisci indirizzo e PIN a mano."
        }
    }

    private func configure() {
        guard let device = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            finish(nil)
            return
        }
        session.addInput(input)
        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else {
            finish(nil)
            return
        }
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]

        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        layer.frame = view.bounds
        view.layer.insertSublayer(layer, at: 0)
        preview = layer
        DispatchQueue.global(qos: .userInitiated).async { self.session.startRunning() }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        preview?.frame = view.bounds
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput objects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard let code = objects.compactMap({ $0 as? AVMetadataMachineReadableCodeObject }).first?.stringValue else {
            return
        }
        finish(code)
    }

    @objc private func cancelTapped() {
        finish(nil)
    }

    private func finish(_ value: String?) {
        guard !finished else { return }
        finished = true
        if session.isRunning {
            DispatchQueue.global(qos: .userInitiated).async { self.session.stopRunning() }
        }
        dismiss(animated: true) { self.completion(value) }
    }
}
