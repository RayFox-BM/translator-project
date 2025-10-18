# test_speak.py
from tts import test_all_languages

if __name__ == "__main__":
    # Order here matches your numpad mapping 0..9
    order = ["en", "zh", "es", "fr", "de", "ja", "pt", "it", "ru", "ko"]
    test_all_languages(order)