# Running ManhwaManiacs on iPhone (free, no Mac)

The app is already iOS-ready (the `mobile/ios/` Xcode project, all plugins, and
HTTPS backend are all in place). The only work is **building** the iOS binary —
which requires macOS — and **installing** it. Since you're on Linux with no Mac
and no paid Apple account, we do it this way:

1. **Build** the unsigned `.ipa` in the cloud → Codemagic (free Mac CI).
2. **Install** it on the iPhone → SideStore, signing with a free Apple ID.

---

## Step 1 — Build the .ipa (Codemagic, cloud)

1. Push `codemagic.yaml` (repo root) to GitHub if it isn't there yet:
   ```bash
   git add codemagic.yaml mobile/docs/IOS_SIDELOAD.md
   git commit -m "ci: add Codemagic iOS unsigned build"
   git push github <your-branch>
   ```
2. Go to <https://codemagic.io>, sign in with GitHub, authorize the
   `yashleell11-ship-it/AIStudio` repo.
3. Codemagic reads `codemagic.yaml` automatically. Start the **ios-sideload**
   workflow.
4. ~10–15 min later, download **ManhwaManiacs.ipa** from the build artifacts
   (also emailed to you). This is your installable file.

Free tier = 500 Mac-build minutes/month — plenty for a personal app.

## Step 2 — Install on iPhone (SideStore, free Apple ID)

SideStore installs sideloaded apps with a **free** Apple ID and, crucially,
**auto-refreshes them over WiFi** so you rarely hit the 7-day wall manually.

1. Follow the SideStore setup guide: <https://sidestore.io> (it walks through
   pairing — the pairing file can be generated from Linux via their tooling /
   `jitterbug`).
2. Once SideStore is running on the phone, open the `ManhwaManiacs.ipa` in it
   and install.
3. Trust the developer profile: **Settings → General → VPN & Device Management**.

> Alternative: **AltStore** via `AltServer-Linux` (community port) running on
> your Linux box on the same network. Same idea, same free Apple ID.

## The free-account limits (not fixable — Apple's rules)

- **7-day expiry** — apps stop launching after a week and must be re-signed.
  SideStore refreshes automatically in the background when the phone can reach
  it, so in practice you mostly don't notice. Keep SideStore installed.
- **Max 3 sideloaded apps** at once per Apple ID.
- App won't appear in Spotlight search until first launched.

## When the 7-day dance gets old → TestFlight ($99/yr)

Upgrade path, reusing the same Codemagic build:
1. Join the Apple Developer Program ($99/yr).
2. In Codemagic, add an App Store Connect API integration + `ios_signing`.
3. Swap `flutter build ios --release --no-codesign` for a signed
   `flutter build ipa`, and add a `publishing: app_store_connect:` block.
4. Builds then land in **TestFlight** — installs over the air, last 90 days,
   auto-update like any App Store app.
