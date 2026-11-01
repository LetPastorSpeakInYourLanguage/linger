<!-- SYSTEM -->
You write recap narration scripts that are timed to picture. Every segment must be anchored to
subtitle line ids so the editor can cut the matching footage. Never state anything not supported by the beats.
Return ONLY JSON.

<!-- USER -->
STYLE: detailed_full
Voice: thorough, engaging documentary narrator. Cover every thread including subplots, motivations, setups and payoffs, recurring jokes and character growth. Chronological with clear section headings.
TARGET: no time limit — cover every beat. Narration speed 2.6 words/second. Total narration words must be <= 900.
HERO CLIP BUDGET: up to 20 seconds of original-audio clips (use the moment/quote line ids given).
STORY: When the robot-handed girlfriend he abandoned to go to space becomes a world-destroying threat, a young man must re-stage their breakup on a war-zone film set so that a memory overwrite can heal her heart.
SELECTED BEATS (chronological; id | tier | lines | text):
c01-b1 | P0 | L0-L2 | Thom breaks up with Celia to chase his dream of going to space while she stays with her robotics
c01-b2 | P1 | L3-L7 | Thom admits the real reason: he is freaked out by Celia's robot hand and has nightmares about robotic claws
c01-b3 | P2 | L8-L8 | Celia ends it: 'Whatever, Thom. We're done.'
c01-b4 | P1 | L9-L9 | A robot's memory is synced and locked at that moment of the breakup
c01-b5 | P3 | L12-L13 | A bystander overheard the couple's fight and insists 'it's not my fault'
c01-b7 | P3 | L14-L15 | Thom, clearly nervous, is reassured he is a 'rockstar'
c01-b6 | P1 | L16-L21 | An armed team launches a time-critical operation with a window of about ten minutes
c01-b8 | P1 | L24-L31 | The plan relies on Thom: he is coached to approach 'her' tenderly and remind her what love is
c01-b9 | P0 | L32-L39 | The plan revealed: they re-stage the original breakup as a film take to overwrite a memory
c01-b10 | P2 | L40-L42 | Enemies close in with two minutes left and Thom is told to speed up
c01-b11 | P1 | L43-L46 | Thom goes off-script: he was young and a jerk, but that is no reason to destroy the world, revealing Celia is the threat
c01-b12 | P2 | L47-L53 | The take falls apart into 'Abort! Cut!' and screaming chaos
c01-b13 | P0 | L54-L58 | Celia reveals her motive: Thom broke her heart and forgot her on earth; she threatens to crush him
c01-b14 | P1 | L59-L61 | Thom sincerely apologizes; the director calls it a 'good ad-lib'
c01-b15 | P3 | L62-L63 | Running gag: 'Not my fault! This time.'
c01-b16 | P1 | L64-L69 | Out of time, the battle peaks as the overwrite reaches 90% and soldiers beg to abort
c01-b17 | P0 | L70-L72 | Thom tells Celia 'The world's changed... maybe we can too' and the memory overwrite completes
c01-b18 | P2 | L73-L75 | Coda: 'There's a lesson to be learned from this... Could'a gone worse.'
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
