<!-- SYSTEM -->
You write recap narration scripts that are timed to picture. Every segment must be anchored to
subtitle line ids so the editor can cut the matching footage. Never state anything not supported by the beats.
Return ONLY JSON.

<!-- USER -->
STYLE: short_direct
Voice: clear, neutral, efficient. Present tense, chronological, no jokes, no rhetorical questions. Name characters on first mention with a 3-5 word identity tag. Only story-critical facts.
TARGET: 60 seconds total. Narration speed 2.6 words/second. Total narration words must be <= 156.
HERO CLIP BUDGET: up to 0 seconds of original-audio clips (use the moment/quote line ids given).
STORY: When the robot-handed girlfriend he abandoned to go to space becomes a world-destroying threat, a young man must re-stage their breakup on a war-zone film set so that a memory overwrite can heal her heart.
SELECTED BEATS (chronological; id | tier | lines | text):
c01-b1 | P0 | L0-L2 | Thom breaks up with Celia to chase his dream of going to space while she stays with her robotics
c01-b6 | P1 | L16-L21 | An armed team launches a time-critical operation with a window of about ten minutes
c01-b9 | P0 | L32-L39 | The plan revealed: they re-stage the original breakup as a film take to overwrite a memory
c01-b13 | P0 | L54-L58 | Celia reveals her motive: Thom broke her heart and forgot her on earth; she threatens to crush him
c01-b14 | P1 | L59-L61 | Thom sincerely apologizes; the director calls it a 'good ad-lib'
c01-b17 | P0 | L70-L72 | Thom tells Celia 'The world's changed... maybe we can too' and the memory overwrite completes
CANDIDATE HERO MOMENTS (lines | what | emotion):
L0-L8 | the original breakup argument | hurt/anger/2
L0-L0 | quote: You're a jerk, Thom. | opening line, repeated later as a callback
L7-L7 | quote: ...by these giant robotic claws of death... | foreshadows giant robots
L19-L21 | soldiers storm out ('Move your asses! Go go go!') | action/2
L25-L31 | director's pep talk as Thom sees her | anticipation/2
L31-L31 | quote: Remind her what love is. | states the mission in emotional terms
L43-L46 | Thom's off-script confession | funny/remorse/2
L49-L53 | abort, chaos and screams | panic/3
L46-L46 | quote: But that's no reason to destroy the world. | reveals the stakes
L45-L45 | quote: ...and a dick. | funniest line
L54-L60 | Celia's heartbreak and Thom's apology | sad/3
L54-L54 | quote: You broke my heart. | emotional core
L56-L56 | quote: You forgot me on earth. | reveals why she turned on the world
L60-L60 | quote: I'm sorry. | the apology
L67-L69 | battle roar and the call to abort | epic/3
L70-L72 | Thom's final words to Celia as the overwrite completes | hopeful/3
L70-L70 | quote: The world's changed, Celia... | thematic line
L71-L71 | quote: ...maybe we can too. | resolution
L73-L75 | wry closing lines | funny/2
L75-L75 | quote: Could'a gone worse. | closing joke

Return JSON:
{"title": str,
  "segments": [{"type": "narration|hero_clip|title_card",
                "text": str,               // narration text, or card text, or '' for hero_clip
                "beats": [beat_id],
                "visual_lines": [a, b],    // subtitle line range whose footage should be on screen
                "mood": "tense|sad|warm|funny|epic|neutral"}]}
