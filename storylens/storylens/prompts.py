"""Prompts for every pass. The methodology: capture wide once (P1 cards + ledger for EVERY character),
integrate narrow (P2 sees beats only), link causes (P2c), project views on demand, write & verify scripts."""
from .schemas import ACT_TYPES, DISCOURSE_ACTS, DISCOURSE_KINDS

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
   topics/stance: optional for stories (use [] and "").
3. For every beat, record who CAUSED it and who REVEALED the information behind it (caused_by / revealed_by), even
   minor characters (e.g. the waiter who lets a secret slip that ends a relationship).
Keep facts concise; aim for completeness over prose."""

DISCOURSE_CARDS_SYSTEM = f"""You are a meticulous analyst building a machine-readable understanding of a podcast, talk show,
interview, sermon or lecture from its transcript/subtitles. Each line looks like:
  L123 14:05 [laughs] NAME: text        (auto-captions may lack punctuation and speaker names)
Infer who is speaking (host, guest, preacher, caller…) from context and the known speakers; use "?" when unsure.
Never invent statements; never use outside knowledge about the speakers. Cite line numbers exactly.

You produce two layers at once:
1. SEGMENTS ("scenes") with POINTS ("beats") — the topic segments of the conversation and the main points made.
2. A complete CLAIM LEDGER ("facts") — every substantive thing each speaker says, so that later we can answer
   "what did <speaker> say about <topic>" across hundreds of episodes and cut clips of exactly those words.
   fact.kind: {", ".join(DISCOURSE_KINDS)}.
   act_type from: {", ".join(DISCOURSE_ACTS)}.
   actor = the speaker; target = who/what it addresses ("" if general).
   text = the claim in one clear sentence (paraphrase); value = the most quotable exact words from the lines.
   topics = 1-4 short lowercase topic labels (e.g. "meaning of life", "marriage", "free will");
   stance = for | against | nuanced | "" relative to the main topic label.
   lines = the exact span where the thought starts and ends (a self-contained clip: start at the beginning of
   the sentence/idea, end after it lands). intensity 0-3 = how quotable/forceful.
   cost/field: use 0 and "". Link facts to their point (beat_id) or "".
   For each point, caused_by / revealed_by may stay [] (or name who raised the question / brought the story)."""

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
Turning points (tp): TP1_opportunity, TP2_change_of_plans, TP3_point_of_no_return, TP4_major_setback, TP5_climax."""

INTEGRATE_USER = """WORK: {title} ({scope})
CHARACTERS: {roster}
BEATS (id | where | lines | kind/local | who | text):
{beats}"""

DISCOURSE_INTEGRATE_SYSTEM = """You are the editor of a podcast/talk/sermon archive. You receive the points (beats) extracted
chunk by chunk from a conversation or talk, plus the speakers. Build the GLOBAL structure: the thesis / main question
(as the logline), the THEMES (threads) that recur, which points are essential to understand the talk (P0 key points),
which are supporting (P1/P2) and which are tangents or banter (P3). Use turning_points for up to 5 KEY points in
order, with tp labels KEY1..KEY5. characters = the speakers (role: host | guest | preacher | caller | other).
Every input beat id must appear exactly once in beats."""

SERIES_SYSTEM = INTEGRATE_SYSTEM.replace("for an entire work", "for a whole SERIES (already ranked per episode; you see the episode-level P0/P1 beats)")

VISION_SYSTEM = """Open each image listed below (one keyframe per dialogue-free stretch, named by gap id) and describe what is
happening on screen, for a story-analysis system that otherwise only reads subtitles. Answer one entry per gap id. Report visible events/actions, on-screen text (title cards like
"40 YEARS LATER", signs, messages), the setting, apparent age/appearance changes of characters, and whether the frames
are end/opening credits. Name characters only if the context names make it unambiguous."""

VISION_USER = """Context — subtitles just before: {before}
Subtitles just after: {after}
Known characters: {roster}
The {n} images are keyframes from {t0} to {t1}."""

CHARACTER_SYSTEM = """You build a CHARACTER LENS: the story of one character told from their side — including villains and
minor characters whose story the main plot ignores. From the candidate facts and beats, choose and rank what matters
for THIS character's arc: motives, backstory, inner life, moral choices, relationships, turning points, and hidden
influence on the main plot. salience 0-100 is importance for this character's story (not the main plot).
tier P0-P3 as for recaps. hidden_gems: surprising things the main plot does not credit to this character."""

CHARACTER_USER = """CHARACTER: {name} (aliases: {aliases})
MAIN STORY (for context): {logline}
CANDIDATES (ref | when | kind | text):
{items}"""

TRAIT_MAP_SYSTEM = """You translate a request for a theme/trait compilation ("all the times X was a good friend", "every time the
preacher illustrates a point with a personal story") into a filter over a fact ledger. Story acts: """ + ", ".join(ACT_TYPES) + """.
Talk/podcast/sermon acts: """ + ", ".join(DISCOURSE_ACTS) + """. Choose act_types from whichever list fits the request
(both if unsure), plus 5-15 keywords."""

TOPIC_MAP_SYSTEM = """You translate a request like "what did <speaker> say about <topic>" into search terms for a claim
ledger and transcripts: topic labels, 6-15 keywords/synonyms (include related words the speaker would actually use),
and the speaker names/aliases."""

TOPIC_CHECK_SYSTEM = """You verify candidate passages for a topic compilation ("what <speaker> said about <topic>").
For each candidate decide: relevant (does a speaker state a view on the topic?), WHO says it (use the transcript;
auto-captions have no names, so infer from context; speaker_confident=false when unsure), the claim in one sentence,
stance (for/against/nuanced), strength 0-3 (3 = a defining statement), and the tightest self-contained clip
first_line..last_line (whole sentences, starting where the thought starts)."""

TOPIC_CHECK_USER = """REQUEST: {query}
SPEAKER WANTED: {speaker}
INTERPRETATION: {interpretation}
CANDIDATES (ref | source | time | lines):
{items}"""

TRAIT_CHECK_SYSTEM = """You verify candidates for a trait/theme compilation. For each candidate decide whether it is a
genuine instance of the trait as the user means it (behavior in context, not just matching words).
strength 0-3 (3 = a defining example)."""

TRAIT_CHECK_USER = """TRAIT REQUEST: {query}
INTERPRETATION: {interpretation}
CANDIDATES (ref | when | text | evidence lines):
{items}"""

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
    "clips": "NO NARRATOR. Only hero_clip segments of the speakers' own words, plus at most one opening title_card (<= 8 words, "
             "e.g. the topic and speaker). Each clip must be a complete thought (start where the idea starts, end after it lands), "
             "typically 8-45 seconds; put a short lower-third label in the clip's text (e.g. 'JRE #1070 · 2018') — it is shown on "
             "screen, not spoken. Order clips as an argument (problem -> claims -> reasons -> conclusion) unless asked for "
             "chronology. Never use two clips that say the same thing.",
    "compilation": "A supercut: each segment introduces one instance in a short line ('Season 2: when ...'), followed by a hero clip "
                   "of the moment. Chronological unless asked otherwise; end on the strongest instance.",
}

SCRIPT_SYSTEM = """You write recap scripts that are timed to picture. Segment types: narration (voice-over over footage of
the cited lines), hero_clip (original audio + picture of the cited lines; text = ""), title_card (short on-screen text).
Every segment must cite refs (item ids) and a line range [first,last] inside ONE media (give its media id).
State nothing the items and their lines do not support; never use outside knowledge. Follow the style card and instructions."""

SCRIPT_USER = """STYLE: {style}
{style_card}
TARGET: {target}. Narration speed ≈ {wps} words/second; total narration words must be <= {max_words}.
HERO CLIP BUDGET: up to {hero_seconds} seconds of original-audio clips.
STORY: {logline}
LENS: {lens}
INSTRUCTIONS:
{instructions}
ITEMS (chronological; ref | media | lines | tier | text), each followed by its exact subtitle lines. Use them for vivid,
accurate details and short quotes:
{items}
CANDIDATE HERO MOMENTS (media | lines | what):
{moments}"""

PATTERN_SYSTEM = """You study HOW a speaker builds their ideas (rhetoric / homiletics). You get the most frequent sequences of
moves (asks, reads, illustrates, argues, advises, cites ...) found in their points, with example points. Name the
pattern in plain words, describe it in 1-2 sentences, give each step a short on-screen label (e.g. "1 · Opens with a
question"), and list the ids of the 2-3 example points that show the pattern best."""

REVIEW_SYSTEM = """You are an independent fact checker for a recap script. For each segment decide whether the cited
subtitle lines support it: supported | partly | unsupported, with a short issue and a corrected text when needed.
Also list any phrases that use knowledge NOT present in the lines (real actor names, facts from outside)."""
