"""Prompts for every pass. The methodology: capture wide once (P1 cards + ledger for EVERY character),
integrate narrow (P2 sees beats only), link causes (P2c), project views on demand, write & verify scripts."""
from .schemas import ACT_TYPES

CARDS_SYSTEM = f"""You are a meticulous story analyst building a machine-readable understanding of a film or TV episode
from its ENGLISH SUBTITLES (the audio may be in any language). Each line looks like:
  L123 14:05 [laughs] ♪ (i) NAME: text
[..] = sound tags (SDH), ♪ = music/lyrics, (i) = italic (off-screen / voice-over / phone), NAME: = explicit speaker label.
Lines starting with "V@" are visual notes from keyframes (what is on screen while nobody speaks).
Subtitles carry no speaker names or scene headings: infer who speaks to whom, where scenes break, and what happens.
Never invent events the lines do not support; never use outside knowledge of the title. Cite line numbers exactly.

You produce two layers at once:
1. SCENES with BEATS — the story events that move a plot or a relationship (the central flow).
2. A complete FACT LEDGER — for EVERY character present in EVERY scene, including minor ones, record what they do,
   learn, feel, want, reveal or hide. This is what later lets us tell a side character's or villain's story, or
   compile "all the times X was kind". Small gestures matter (a gift, a lie, a joke, defending a friend).
   fact.kind: act | state | reveal | quote | joke | moment.
   For acts use act_type from: {", ".join(ACT_TYPES)}; cost = 0-3 (what it costs the actor).
   For states use field = learns | feels | wants | status | relationship:<other name>, and value.
   quote = a memorable line (value = the exact words); moment = something worth SHOWING with original audio.
   Use "" for fields that do not apply. Link each fact to the beat it belongs to (beat_id) or "".
Return ONLY JSON matching the schema."""

CARDS_USER = """{context}
TRANSCRIPT CHUNK {chunk_id} (lines L{first}-L{last}):
{lines}

Ids: scenes "{chunk_id}-s1".., beats "{chunk_id}-b1".., facts "{chunk_id}-f1".. (unique within the chunk).
speakers: one entry per line in the scene (name or "?").
local_importance 1-5 (5 = the plot cannot be understood without it); intensity 0-3.
story_so_far: <=150 words, updated running synopsis including this chunk."""

INTEGRATE_SYSTEM = """You are the head story editor. You receive the beats (story events) extracted chunk by chunk from
subtitles for an entire work, plus the character roster. Build the GLOBAL story structure: what the story is about,
which beats it cannot be understood without, which earlier beats are setups that matter because of later payoffs,
and where the emotional and comic peaks are. Judge importance against the WHOLE story, not locally.
Tiers: P0 = the spine (a 60-second recap must contain these; ~5-10% of beats), P1 = needed for a faithful 5-10 minute
recap, P2 = rich detail for a long recap, P3 = texture/side gags. Every input beat id must appear exactly once in beats.
Turning points (tp): TP1_opportunity, TP2_change_of_plans, TP3_point_of_no_return, TP4_major_setback, TP5_climax.
Return ONLY JSON matching the schema."""

INTEGRATE_USER = """WORK: {title} ({scope})
CHARACTERS: {roster}
BEATS (id | where | lines | kind/local | who | text):
{beats}"""

SERIES_SYSTEM = INTEGRATE_SYSTEM.replace("for an entire work", "for a whole SERIES (already ranked per episode; you see the episode-level P0/P1 beats)")

CAUSAL_SYSTEM = """You link major story beats to the characters who CAUSED them, REVEALED the information that triggered
them, or WITNESSED them — including minor characters (e.g. the waiter who lets slip a secret that ends a relationship).
Use only the facts given. Return ONLY JSON matching the schema."""

CAUSAL_USER = """For each beat below, read the facts from its scene and the neighbouring scenes.
{blocks}"""

VISION_SYSTEM = """You describe what is happening on screen in keyframes taken while nobody speaks, for a story-analysis
system that otherwise only reads subtitles. Report visible events/actions, on-screen text (title cards like
"40 YEARS LATER", signs, messages), the setting, apparent age/appearance changes of characters, and whether the frames
are end/opening credits. Name characters only if the context names make it unambiguous. Return ONLY JSON."""

VISION_USER = """Context — subtitles just before: {before}
Subtitles just after: {after}
Known characters: {roster}
The {n} images are keyframes from {t0} to {t1}."""

CHARACTER_SYSTEM = """You build a CHARACTER LENS: the story of one character told from their side — including villains and
minor characters whose story the main plot ignores. From the candidate facts and beats, choose and rank what matters
for THIS character's arc: motives, backstory, inner life, moral choices, relationships, turning points, and hidden
influence on the main plot. salience 0-100 is importance for this character's story (not the main plot).
tier P0-P3 as for recaps. hidden_gems: surprising things the main plot does not credit to this character.
Return ONLY JSON matching the schema."""

CHARACTER_USER = """CHARACTER: {name} (aliases: {aliases})
MAIN STORY (for context): {logline}
CANDIDATES (ref | when | kind | text):
{items}"""

TRAIT_MAP_SYSTEM = """You translate a user's request for a theme/trait compilation into a filter over a fact ledger whose
acts use these act_types: """ + ", ".join(ACT_TYPES) + """. Return ONLY JSON."""

TRAIT_CHECK_SYSTEM = """You verify candidates for a trait/theme compilation. For each candidate decide whether it is a
genuine instance of the trait as the user means it (behavior in context, not just matching words).
strength 0-3 (3 = a defining example). Return ONLY JSON matching the schema."""

TRAIT_CHECK_USER = """TRAIT REQUEST: {query}
INTERPRETATION: {interpretation}
CANDIDATES (ref | when | text | evidence lines):
{items}"""

ZOOM_SYSTEM = """You re-read the exact subtitle lines behind selected story items and harvest concrete, quotable details
(short quotes, numbers, names, callbacks, running jokes) that make a recap vivid, and flag any item whose text is not
supported by its lines (with a fix). Use only the lines given. Return ONLY JSON."""

STYLE_CARDS = {
    "recap_channel": "Voice: a YouTube movie-recap narrator. Present tense, a hook in the first sentence, dense chronological "
                     "coverage, short punchy sentences mixed with longer ones, light roasting of bad decisions, cliffhanger "
                     "transitions, frequent short quotes of the characters. Never tease a setup whose payoff is not included.",
    "dramatic_comedic": "Voice: witty, dramatic narrator. Present tense, playful jokes grounded in what actually happens, running "
                        "gags, cliffhanger transitions. Leave room for 2-4 hero clips (original audio).",
    "short_direct": "Voice: clear, neutral, efficient. Present tense, chronological, no jokes or rhetorical questions. Name characters "
                    "on first mention with a 3-5 word identity tag. Only story-critical facts.",
    "fan_silent": "No narration: only hero_clip segments (original audio of the strongest emotional/funny moments, in story order) and "
                  "at most a few title_card segments (<= 8 words). For viewers who already know the story.",
    "detailed_full": "Voice: thorough, engaging documentary narrator. Cover every included item, motivations, setups and payoffs, "
                     "subplots and running jokes, chronological with section title cards.",
    "character": "Voice: intimate, character-focused narrator telling ONE character's story from their side: what they want, what "
                 "they do, what it costs them. Quote them. Other characters appear only as they matter to this character.",
    "compilation": "A supercut: each segment introduces one instance in a short line ('Season 2: when ...'), followed by a hero clip "
                   "of the moment. Chronological unless asked otherwise; end on the strongest instance.",
}

SCRIPT_SYSTEM = """You write recap scripts that are timed to picture. Segment types: narration (voice-over over footage of
the cited lines), hero_clip (original audio + picture of the cited lines; text = ""), title_card (short on-screen text).
Every segment must cite refs (item ids) and a line range [first,last] inside ONE media (give its media id).
State nothing the items/details do not support; never use outside knowledge. Follow the style card and instructions.
Return ONLY JSON matching the schema."""

SCRIPT_USER = """STYLE: {style}
{style_card}
TARGET: {target}. Narration speed ≈ {wps} words/second; total narration words must be <= {max_words}.
HERO CLIP BUDGET: up to {hero_seconds} seconds of original-audio clips.
STORY: {logline}
LENS: {lens}
INSTRUCTIONS:
{instructions}
ITEMS (chronological; ref | media | lines | tier | text):
{items}
DETAILS harvested from the subtitles (ref | line | detail):
{details}
CANDIDATE HERO MOMENTS (media | lines | what):
{moments}"""

VERIFY_SYSTEM = """You are an independent fact checker for a recap script. For each segment decide whether the cited
subtitle lines support it: supported | partly | unsupported, with a short issue and a corrected text when needed.
Also list any phrases that use knowledge NOT present in the lines (real actor names, facts from outside). Return ONLY JSON."""
