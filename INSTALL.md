# Wispr Local Alpha - Installation Guide

Welcome to the Wispr Local Alpha! This guide will help you get started with local, offline dictation.

## System Requirements

- **Operating System**: Windows 10/11 (64-bit)
- **RAM**: 8GB minimum (16GB recommended for larger models)
- **GPU (Optional but Recommended)**: NVIDIA GPU with CUDA support for faster transcription.
- **Microphone**: Any functional system microphone.

## Installation Steps

1.  **Download the Installer**: Run the `Wispr Local.msi` (or `.exe`) provided in the release.
2.  **Launch the App**: Open "Wispr Local" from your Start Menu.
3.  **Permissions**: Ensure you allow the application to access your microphone and the clipboard.
4.  **First Run**:
    - The application will start in the system tray (look for the Wispr icon).
    - On the first launch, it will download the "base" transcription model (approx. 150MB).
    - You can open the **Dashboard** by clicking the tray icon to see the download progress.

## How to Use

1.  **Dictation**: Hold the **Right Control** key (default) and start speaking.
2.  **Transcribe**: Release the key. The app will transcribe your speech and automatically type it into your active window.
3.  **Settings**: Click the tray icon and select "Show Dashboard" to change the hotkey, switch models, or enable/disable GPU acceleration.

## Troubleshooting

- **No transcription**: Ensure the correct microphone is selected in the Dashboard settings.
- **Slow performance**: Try using a smaller model (e.g., `tiny`) or enable GPU mode if you have an NVIDIA card.
- **GPU Pack**: If you have an NVIDIA GPU, go to Settings and click "Install GPU Pack" to enable high-speed transcription.

## Sending Feedback

As an Alpha tester, your feedback is invaluable! Please report any crashes or weird behavior by sending the logs found in:
`%APPDATA%\com.wispr.local\logs`
