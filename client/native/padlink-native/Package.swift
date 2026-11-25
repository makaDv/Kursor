// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PadLinkNative",
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "PadLinkNative", targets: ["PadLinkNativePlugin"])
    ],
    dependencies: [
        .package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", from: "8.0.0")
    ],
    targets: [
        .target(
            name: "PadLinkNativePlugin",
            dependencies: [
                .product(name: "Capacitor", package: "capacitor-swift-pm"),
                .product(name: "Cordova", package: "capacitor-swift-pm")
            ],
            path: "ios/Sources/PadLinkNativePlugin",
            resources: [.copy("PrivacyInfo.xcprivacy")])
    ]
)
