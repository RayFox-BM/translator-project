import speech_recognition as sr
from translate_install import ArgosInstaller

def recognize_speech() -> str:
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Speak now...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source)
    try:
        text = recognizer.recognize_google(audio)
        print("Heard:", text)
        return text
    except sr.UnknownValueError:
        print("Could not understand audio.")
    except sr.RequestError as e:
        print("Speech service error:", e)
    return ""

def main():
    src = input("Enter source language code (e.g. en): ").strip().lower()
    tgt = input("Enter target language code (e.g. es): ").strip().lower()

    installer = ArgosInstaller(src, tgt)
    installer.install()

    while True:
        print("\nPress Enter to record or type 'quit' to exit.")
        cmd = input().strip().lower()
        if cmd == "quit":
            break

        text = recognize_speech()
        if not text:
            continue
        installer.test(text)

if __name__ == "__main__":
    main()