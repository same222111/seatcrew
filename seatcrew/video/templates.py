"""The three starter templates. Each is a style preset the WRITER, SCRIPT CHECK, VOICE and EDITOR read."""
TEMPLATES = {
    "emotional_story": dict(
        label="Emotional story", wpm=140, shots=(5, 8), shot_sec=(3.0, 7.0), total_sec=(20, 75), camera="push_in",
        cameras=["push_in", "pan_right", "pull_out", "pan_up", "push_in", "pan_left"], transition="crossfade", transition_sec=0.8,
        bgm_gain_db=-17, max_words_per_sentence=18,
        arc=["hook: a small, concrete moment", "the person and what they want", "the obstacle", "the turn", "the change", "a quiet closing line"],
        visual_style="cinematic, natural light, shallow depth of field, film grain, warm tones, 35mm"),
    "knowledge_explainer": dict(
        label="Knowledge explainer", wpm=165, shots=(5, 9), shot_sec=(2.5, 6.0), total_sec=(20, 90), camera="pan_right",
        cameras=["push_in", "pan_right", "pan_left", "pan_up", "pull_out"], transition="crossfade", transition_sec=0.4,
        bgm_gain_db=-20, max_words_per_sentence=16,
        arc=["hook: a surprising question", "the short answer", "how it works, step 1", "step 2", "a concrete example", "one-line recap"],
        visual_style="clean editorial illustration or crisp documentary photo, high detail, clear subject, uncluttered background"),
    "product_promo": dict(
        label="Product promo", wpm=170, shots=(4, 7), shot_sec=(2.0, 5.0), total_sec=(12, 45), camera="push_in",
        cameras=["push_in", "pan_left", "push_in", "pull_out", "pan_right"], transition="crossfade", transition_sec=0.3,
        bgm_gain_db=-15, max_words_per_sentence=12,
        arc=["hook: the problem in one line", "meet the product", "key benefit 1", "key benefit 2", "proof / detail", "call to action"],
        visual_style="premium product photography, studio lighting, sharp focus, minimal set, high-end commercial look"),
}
