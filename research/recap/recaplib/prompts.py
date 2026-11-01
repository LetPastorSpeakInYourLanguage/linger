"""Prompt templates for the multi-pass Story Understanding pipeline.

Pass map
  P1 SCENE_CARDS   chunk of subtitle lines (+ story-so-far + roster) -> scenes, beats, speakers, humor, moments
  P2 INTEGRATE     all scene cards -> story bible: characters, threads, turning points, GLOBAL importance,
                   tiers, dependencies (setup->payoff), emotional peaks, best quotes
  P3 VERIFY        selected beats + their evidence lines -> supported / unsupported / fix
  P4 SCRIPT        selected beats + style card + word budget -> narration segments with visual anchors
All outputs cite subtitle line ids (L###) so every claim maps back to exact timestamps.
"""

SCENE_CARDS_SYSTEM = """You are a meticulous story analyst building a machine-readable understanding of a film or TV episode
from its ENGLISH SUBTITLES ONLY (the audio may be any language). Lines look like:
  L123 14:05 [laughs] ♪ (i) NAME: text
where [..] are SDH sound tags, ♪ = music/lyrics, (i) = italic (off-screen/voice-over/phone), NAME: = explicit speaker label.
Subtitles have no speaker names and no scene headings: you must infer who speaks to whom, where scenes break,
and what happens between lines. Be explicit about uncertainty; never invent events that the lines do not support.
Cite evidence as line ids. Return ONLY JSON."""

SCENE_CARDS_USER = """{context}
TRANSCRIPT CHUNK ({chunk_id}, lines L{first}-L{last}):
{lines}

Return JSON:
{{
 "roster_updates": [{{"name": str, "aliases": [str], "who": "one-line identity/role", "evidence": "L.."}}],
 "scenes": [{{
   "id": "{chunk_id}-s1", "lines": [first_line_int, last_line_int],
   "setting_guess": str, "characters": [str],
   "speakers": {{"L12": "Name|?"}}  // every line in the scene; '?' if truly unknown
   "summary": "2-3 sentences, plain, past tense",
   "beats": [{{"id": "{chunk_id}-b1", "text": "one atomic story event", "lines": [a, b],
              "kind": "plot|character|relationship|humor|emotion|world|mystery|setup|payoff",
              "local_importance": 1-5, "emotion": {{"label": str, "intensity": 0-3}},
              "who": [str]}}],
   "humor": [{{"lines": [a, b], "joke": str, "type": "banter|slapstick|irony|callback|sarcasm"}}],
   "quotes": [{{"line": int, "why": "memorable/emotional/defining"}}],
   "moments": [{{"lines": [a, b], "what": "a moment worth SHOWING with original audio", "emotion": str, "intensity": 0-3}}],
   "open_threads": [str]
 }}],
 "story_so_far": "<=120 words, updated running synopsis including this chunk"
}}"""

INTEGRATE_SYSTEM = """You are the head story editor. You receive scene cards (produced chunk-by-chunk from subtitles) for an
entire work. Build the GLOBAL understanding: what the story is actually about, which beats the plot cannot be
understood without, which earlier beats are setups that become important because of later payoffs, and where
the emotional and comedic peaks are. Importance must be judged against the WHOLE story, not locally. Return ONLY JSON."""

INTEGRATE_USER = """WORK: {title}
SCENE CARDS:
{cards}

Return JSON:
{{
 "logline": str, "genre_tone": str,
 "characters": [{{"name": str, "aliases": [str], "role": "protagonist|antagonist|ally|love interest|minor", "arc": str, "importance": 0-100}}],
 "threads": [{{"id": "T1", "title": str, "summary": str, "beats": [beat_id], "importance": 0-100}}],
 "turning_points": {{"TP1_opportunity": beat_id, "TP2_change_of_plans": beat_id, "TP3_point_of_no_return": beat_id,
                    "TP4_major_setback": beat_id, "TP5_climax": beat_id}},
 "beats": [{{"id": beat_id, "global_importance": 0-100, "tier": "P0|P1|P2|P3",
            "requires": [beat_id], "pays_off": [beat_id], "thread": "T1",
            "short": "<=12 word version", "spoiler_level": 0-3}}],
 "emotional_peaks": [beat_id], "comedy_peaks": [beat_id], "best_quotes": [{{"line": int, "why": str}}],
 "themes": [str]
}}
Tier guide: P0 = the spine (a 60-second recap must contain these; typically 5-10% of beats),
P1 = needed for a faithful 5-10 min recap, P2 = rich detail for a long recap, P3 = texture/side gags."""

VERIFY_SYSTEM = """You are a fact checker. For each claim, decide if the cited subtitle lines support it.
Return ONLY JSON: {"checks":[{"id":..,"verdict":"supported|partly|unsupported","fix":"corrected claim or null"}]}"""

STYLE_CARDS = {
    "dramatic_comedic": "Voice: a witty, dramatic YouTube recap narrator. Present tense, punchy sentences, playful roasts of "
                         "characters' bad decisions, running jokes, cliffhanger transitions ('but little does he know...'). "
                         "Jokes must be grounded in what actually happens. Leave room for 2-4 'hero clips' where the "
                         "original audio plays (big emotional or funny lines).",
    "short_direct": "Voice: clear, neutral, efficient. Present tense, chronological, no jokes, no rhetorical questions. "
                    "Name characters on first mention with a 3-5 word identity tag. Only story-critical facts.",
    "fan_silent": "No narration (or at most short on-screen title cards <= 8 words). This is for people who already know the "
                  "story: pick the emotionally strongest and funniest original moments, in story order, played with "
                  "original audio; choose a music mood per section. Output segments with type hero_clip or title_card.",
    "detailed_full": "Voice: thorough, engaging documentary narrator. Cover every thread including subplots, motivations, "
                     "setups and payoffs, recurring jokes and character growth. Chronological with clear section headings.",
}

SCRIPT_SYSTEM = """You write recap narration scripts that are timed to picture. Every segment must be anchored to
subtitle line ids so the editor can cut the matching footage. Never state anything not supported by the beats.
Return ONLY JSON."""

SCRIPT_USER = """STYLE: {style_name}
{style_card}
TARGET: {budget_desc}. Narration speed {wps} words/second. Total narration words must be <= {max_words}.
HERO CLIP BUDGET: up to {hero_seconds} seconds of original-audio clips (use the moment/quote line ids given).
STORY: {logline}
SELECTED BEATS (chronological; id | tier | lines | text):
{beats}
CANDIDATE HERO MOMENTS (lines | what | emotion):
{moments}

Return JSON:
{{"title": str,
  "segments": [{{"type": "narration|hero_clip|title_card",
                "text": str,               // narration text, or card text, or '' for hero_clip
                "beats": [beat_id],
                "visual_lines": [a, b],    // subtitle line range whose footage should be on screen
                "mood": "tense|sad|warm|funny|epic|neutral"}}]}}"""
