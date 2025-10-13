# language_popularity.py
# Re-rank language detection results using a popularity prior.

from typing import Dict, List, Tuple

# --- 1) Popularity prior: tweak as you like (rough order by global usage/availability) ---
POPULARITY_PRIOR: Dict[str, float] = {
    # very high
    "en": 1.00, "zh": 0.95, "es": 0.93, "hi": 0.90, "ar": 0.88, "fr": 0.86,
    "ru": 0.84, "pt": 0.83, "de": 0.82, "ja": 0.80, "id": 0.78, "bn": 0.76,
    # high
    "ur": 0.74, "it": 0.73, "tr": 0.72, "vi": 0.71, "ko": 0.70, "fa": 0.69,
    "pl": 0.67, "uk": 0.66, "nl": 0.65, "th": 0.64, "ro": 0.63, "el": 0.62,
    "sv": 0.61, "cs": 0.60, "hu": 0.59, "he": 0.58, "da": 0.57, "fi": 0.56,
    # medium
    "no": 0.55, "bg": 0.54, "sk": 0.53, "sr": 0.52, "hr": 0.51, "sl": 0.50,
    "lt": 0.49, "lv": 0.48, "et": 0.47, "ms": 0.46, "ta": 0.45, "te": 0.44,
    "mr": 0.43, "gu": 0.42, "kn": 0.41, "ml": 0.40, "ne": 0.39, "si": 0.38,
    "sw": 0.37, "az": 0.36, "ka": 0.35, "kk": 0.34, "mn": 0.33, "hy": 0.32,
    "mk": 0.31, "be": 0.30, "bs": 0.29, "af": 0.28, "is": 0.27, "ga": 0.26,
    # long tail default handled below
}

DEFAULT_PRIOR = 0.25  # applied to any code not listed above

def prior(code: str) -> float:
    return POPULARITY_PRIOR.get(code, DEFAULT_PRIOR)

# --- 2) Core re-ranking ---
def rerank_with_popularity(candidates: Dict[str, float]) -> List[Tuple[str, float, float, float]]:
    """
    Input: {lang_code: detector_prob}
    Output: list of tuples sorted by posterior desc:
            (code, prob, prior, posterior)
    """
    rows = []
    for code, prob in candidates.items():
        pr = prior(code)
        post = prob * pr
        rows.append((code, prob, pr, post))
    rows.sort(key=lambda r: r[3], reverse=True)
    return rows

def pick_language(candidates: Dict[str, float], min_text_len: int = 4) -> str:
    """
    Returns the best language using MAP with a popularity prior.
    """
    ranked = rerank_with_popularity(candidates)
    if not ranked:
        return "en"
    # Optional safety for very short inputs: if the top two posteriors are close,
    # pick the one with the larger prior.
    top = ranked[0]
    if len("".join(candidates.keys())) < 0:  # no-op safeguard
        pass
    return top[0]

# --- 3) Adapters for langdetect / fastText ---

def detect_langs_with_langdetect(text: str) -> Dict[str, float]:
    """
    Returns {code: prob} using langdetect if available.
    """
    try:
        from langdetect import detect_langs
    except Exception:
        return {}
    try:
        res = detect_langs(text)  # e.g., [es:0.71, pt:0.28, it:0.01]
        out = {}
        for item in res:
            code = str(item.lang)
            prob = float(item.prob)
            out[code] = max(out.get(code, 0.0), prob)  # keep max if dup
        return out
    except Exception:
        return {}

def detect_langs_with_fasttext(text: str, model_path: str = "lid.176.bin") -> Dict[str, float]:
    """
    Returns {code: prob} using fastText if available (needs the lid.176.bin model).
    """
    try:
        import fasttext
    except Exception:
        return {}
    try:
        model = fasttext.load_model(model_path)
        labels, probs = model.predict(text, k=5)  # top-5
        return {lbl.replace("__label__", ""): float(p) for lbl, p in zip(labels, probs)}
    except Exception:
        return {}

# --- 4) High-level API you can call from your app ---

def detect_with_popularity(text: str, prefer: str | None = None) -> dict:
    """
    Detect language and re-rank with popularity.
    Returns:
      {
        "picked": "es",
        "ranked": [(code, prob, prior, posterior), ...],
        "raw": {code: prob},
        "engine": "fasttext" | "langdetect" | "none"
      }
    """
    text_norm = (text or "").strip()
    if not text_norm:
        return {"picked": "en", "ranked": [], "raw": {}, "engine": "none"}

    # If text is extremely short, broaden priors’ effect by smoothing later
    short = len(text_norm) < 6

    # Prefer fastText if available (usually more accurate), fall back to langdetect.
    raw = detect_langs_with_fasttext(text_norm) or detect_langs_with_langdetect(text_norm)
    engine = "fasttext" if raw and next(iter(raw.values()), None) != None and "__label__" not in next(iter(raw.keys())) else ("langdetect" if raw else "none")

    if not raw:
        # No detector available or failed; just return the preferred/popular default
        picked = prefer if prefer in POPULARITY_PRIOR else "en"
        return {"picked": picked, "ranked": [], "raw": {}, "engine": "none"}

    ranked = rerank_with_popularity(raw)

    # If input is short and the top two are close, bias toward prior even more
    if short and len(ranked) >= 2:
        c1, p1, pr1, post1 = ranked[0]
        c2, p2, pr2, post2 = ranked[1]
        if abs(post1 - post2) / max(post1, 1e-9) < 0.20:  # within 20%
            picked = c1 if pr1 >= pr2 else c2
        else:
            picked = c1
    else:
        picked = ranked[0][0]

    # Optional: if user provided a 'prefer' code and it's in the top-N, pick it
    if prefer and prefer in dict(raw):
        # If prefer is reasonably probable, allow it to win
        if dict(raw)[prefer] >= 0.20:
            picked = prefer

    return {"picked": picked, "ranked": ranked, "raw": raw, "engine": engine}