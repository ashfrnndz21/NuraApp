# iOS

Swift 6, SwiftUI, iOS 17 minimum. Project generated with XcodeGen from `project.yml` (commit the yml, not the xcodeproj). Builds and tests need Xcode on macOS.

- MVVM with `@Observable` stores. Networking with async/await and ETag delta sync. SwiftData for the offline cache.
- Design tokens in `DesignSystem/Tokens.swift` from `docs/design-system.md`. Two densities: `.patient` and `.caregiver`, chosen from the profile setting and the key.
- Feed: `FeedPagerView` with `.scrollTargetBehavior(.paging)` and `containerRelativeFrame(.vertical)`; `FeedStore` streams now → today → gate → story → learning with a cursor.
- Audio: pre-rendered voice via `AVPlayer`; `AVSpeechSynthesizer` fallback for en, ms, zh. Never autoplay the next card.
- Widgets in `NuraWidgets/`: medium (Now with Taken), Lock Screen (emergency card). Live Activity for visit day in T2.
- Share Extension `NuraShare/` posts photos, PDFs and screenshots to the ingestion API for the selected profile.
- Every patient-facing string lives in `Resources/Localizable.xcstrings` with a `patient` comment tag so the plain-words check can find it.
