#!/usr/bin/env python3
"""
test_azure_tts.py — Independent test for Azure TTS.

Run this BEFORE starting the server to verify:
  1. Azure credentials are correct
  2. The Speech SDK is installed
  3. Audio plays through your speaker

Usage:
    python test_azure_tts.py

Environment variables needed (set in .env or export):
    AZURE_SPEECH_KEY      — Your Azure Speech subscription key
    AZURE_SPEECH_REGION   — Your Azure region (e.g. "eastus")
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()


def check_env():
    """Verify Azure credentials are set."""
    key = os.getenv("AZURE_SPEECH_KEY", "")
    region = os.getenv("AZURE_SPEECH_REGION", "")

    print("=" * 60)
    print("  Azure TTS Test")
    print("=" * 60)
    print()

    if not key:
        print("[FAIL] AZURE_SPEECH_KEY is not set.")
        print()
        print("Fix: Add to your .env file:")
        print('  AZURE_SPEECH_KEY=your_key_here')
        print('  AZURE_SPEECH_REGION=eastus')
        print()
        print("Get your key at: https://portal.azure.com → Cognitive Services → Speech Services")
        return False

    if not region:
        print("[FAIL] AZURE_SPEECH_REGION is not set.")
        print()
        print("Fix: Add to your .env file:")
        print(f'  AZURE_SPEECH_KEY={key[:4]}...{key[-4:]}')
        print('  AZURE_SPEECH_REGION=eastus')
        return False

    print(f"[OK] AZURE_SPEECH_KEY = {key[:4]}...{key[-4:]}")
    print(f"[OK] AZURE_SPEECH_REGION = {region}")
    print()
    return True


def check_sdk():
    """Verify the Azure Speech SDK is installed."""
    try:
        import azure.cognitiveservices.speech as speechsdk
        print("[OK] azure-cognitiveservices-speech is installed")
        print()
        return True
    except ImportError:
        print("[FAIL] azure-cognitiveservices-speech is NOT installed")
        print()
        print("Fix: Run this command:")
        print("  pip install azure-cognitiveservices-speech")
        print()
        return False


async def test_speak():
    """Test actual speech synthesis and playback."""
    from App.core.azure_tts import azure_tts

    print("-" * 60)
    print("  Testing Speech Output")
    print("-" * 60)
    print()

    test_messages = [
        "Hello. This is Azure Text to Speech.",
        "Person ahead, 1.2 meters.",
        "Car on your left. Caution.",
        "Path clear. You may proceed.",
    ]

    for i, msg in enumerate(test_messages, 1):
        print(f"  [{i}/{len(test_messages)}] Speaking: \"{msg}\"")
        await azure_tts.speak(msg)
        print(f"  [{i}/{len(test_messages)}] Done.")
        print()

    print("=" * 60)
    print("  All tests passed! Azure TTS is working.")
    print("  You can now start the server.")
    print("=" * 60)


def main():
    print()

    if not check_env():
        sys.exit(1)

    if not check_sdk():
        sys.exit(1)

    asyncio.run(test_speak())


if __name__ == "__main__":
    main()
