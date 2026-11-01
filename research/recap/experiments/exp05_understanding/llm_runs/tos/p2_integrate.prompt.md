<!-- SYSTEM -->
You are the head story editor. You receive scene cards (produced chunk-by-chunk from subtitles) for an
entire work. Build the GLOBAL understanding: what the story is actually about, which beats the plot cannot be
understood without, which earlier beats are setups that become important because of later payoffs, and where
the emotional and comedic peaks are. Importance must be judged against the WHOLE story, not locally. Return ONLY JSON.

<!-- USER -->
WORK: Tears of Steel (short film, 12 min)
SCENE CARDS:
## c01-s1 L0-L9 | the past; a lookout/bridge where the couple argue | Celia, Thom
   Celia called Thom a jerk as he explained he wanted to go to space while she stayed with her robotics. Pressed, Thom admitted he was freaked out by her robot hand, and Celia ended the relationship. A voice announced that a robot's memory had been synced and locked.
   c01-b1 [relationship/5] L0-L2: Thom breaks up with Celia to chase his dream of going to space while she stays with her robotics
   c01-b2 [character/4] L3-L7: Thom admits the real reason: he is freaked out by Celia's robot hand and has nightmares about robotic claws
   c01-b3 [relationship/4] L8-L8: Celia ends it: 'Whatever, Thom. We're done.'
   c01-b4 [setup/3] L9-L9: A robot's memory is synced and locked at that moment of the breakup
   humor L6-L7: Thom confesses nightmares about 'giant robotic claws of death'
   moment L0-L8 (hurt/anger/2): the original breakup argument
## c01-s2 L10-L13 | unclear; long gaps suggest mostly visual scenes | ?
   Sparse lines over long silences: someone found something freaky, someone was asked why they were not 'down there', and someone admitted overhearing the couple the night before while another insisted it was not their fault.
   c01-b5 [mystery/2] L12-L13: A bystander overheard the couple's fight and insists 'it's not my fault'
## c01-s3 L14-L21 | a staging point before a military operation | Thom, Barley, Captain
   Thom was hyped up as a 'rockstar' before an operation. Barley estimated a ten-minute window and soldiers were ordered to move out.
   c01-b6 [plot/4] L16-L21: An armed team launches a time-critical operation with a window of about ten minutes
   c01-b7 [humor/2] L14-L15: Thom, clearly nervous, is reassured he is a 'rockstar'
   humor L14-L15: 'Of course you're ready, you're a rockstar' to an obviously unready Thom
   moment L19-L21 (action/2): soldiers storm out ('Move your asses! Go go go!')
## c01-s4 L22-L31 | the field, approaching 'her' | Director, Thom
   As they caught sight of 'her', the director coached Thom like an actor: she is your passion, be tender, be honest, remind her what love is.
   c01-b8 [plot/5] L24-L31: The plan relies on Thom: he is coached to approach 'her' tenderly and remind her what love is
   humor L29-L30: the director's over-the-top acting notes in the middle of a battle
   moment L25-L31 (anticipation/2): director's pep talk as Thom sees her
## c01-s5 L32-L53 | a re-staged copy of the breakup location, under attack | Director, Thom, Celia, Barley
   The team re-staged the original breakup as a film take while a 'memory overwrite' ran, with Thom repeating his old lines. With enemies two minutes away, Thom went off-script, admitting he was young and a jerk but that it was no reason to destroy the world. The take collapsed into 'Abort! Cut!' and screams.
   c01-b9 [plot/5] L32-L39: The plan revealed: they re-stage the original breakup as a film take to overwrite a memory
   c01-b10 [plot/3] L40-L42: Enemies close in with two minutes left and Thom is told to speed up
   c01-b11 [payoff/5] L43-L46: Thom goes off-script: he was young and a jerk, but that is no reason to destroy the world, revealing Celia is the threat
   c01-b12 [plot/4] L47-L53: The take falls apart into 'Abort! Cut!' and screaming chaos
   humor L34-L35: a flubbed take ('Ohp- Sorry! Sorry.') during a life-or-death re-enactment
   humor L44-L45: 'I was young... and a dick.'
   humor L42-L42: director yells 'Vivacissimo!'
   moment L43-L46 (funny/remorse/2): Thom's off-script confession
   moment L49-L53 (panic/3): abort, chaos and screams
## c01-s6 L54-L63 | face to face with Celia | Celia, Thom, Director
   Celia confronted Thom: he broke her heart and forgot her on earth, and she threatened to crush him. Thom simply said he was sorry, which the director praised as a 'good ad-lib'. Someone again insisted it was not their fault, 'this time'.
   c01-b13 [emotion/5] L54-L58: Celia reveals her motive: Thom broke her heart and forgot her on earth; she threatens to crush him
   c01-b14 [emotion/5] L59-L61: Thom sincerely apologizes; the director calls it a 'good ad-lib'
   c01-b15 [humor/2] L62-L63: Running gag: 'Not my fault! This time.'
   humor L61-L61: a heartfelt apology is judged as an acting choice
   humor L62-L63: 'Not my fault! This time.' callback to L13
   moment L54-L60 (sad/3): Celia's heartbreak and Thom's apology
## c01-s7 L64-L72 | the set during the final assault | Director, Barley, Thom, Celia, Captain
   Out of time, the battle peaked; the overwrite reached 90% while a soldier begged the captain to abort. Thom told Celia the world had changed and maybe they could too, and the memory overwrite completed.
   c01-b16 [plot/4] L64-L69: Out of time, the battle peaks as the overwrite reaches 90% and soldiers beg to abort
   c01-b17 [payoff/5] L70-L72: Thom tells Celia 'The world's changed... maybe we can too' and the memory overwrite completes
   moment L67-L69 (epic/3): battle roar and the call to abort
   moment L70-L72 (hopeful/3): Thom's final words to Celia as the overwrite completes
## c01-s8 L73-L75 | aftermath | ?
   In the aftermath someone remarked there was a lesson to learn from all this, and that it could have gone worse.
   c01-b18 [humor/3] L73-L75: Coda: 'There's a lesson to be learned from this... Could'a gone worse.'
   humor L74-L75: understatement after a world-ending battle
   moment L73-L75 (funny/2): wry closing lines

Return JSON:
{
 "logline": str, "genre_tone": str,
 "characters": [{"name": str, "aliases": [str], "role": "protagonist|antagonist|ally|love interest|minor", "arc": str, "importance": 0-100}],
 "threads": [{"id": "T1", "title": str, "summary": str, "beats": [beat_id], "importance": 0-100}],
 "turning_points": {"TP1_opportunity": beat_id, "TP2_change_of_plans": beat_id, "TP3_point_of_no_return": beat_id,
                    "TP4_major_setback": beat_id, "TP5_climax": beat_id},
 "beats": [{"id": beat_id, "global_importance": 0-100, "tier": "P0|P1|P2|P3",
            "requires": [beat_id], "pays_off": [beat_id], "thread": "T1",
            "short": "<=12 word version", "spoiler_level": 0-3}],
 "emotional_peaks": [beat_id], "comedy_peaks": [beat_id], "best_quotes": [{"line": int, "why": str}],
 "themes": [str]
}
Tier guide: P0 = the spine (a 60-second recap must contain these; typically 5-10% of beats),
P1 = needed for a faithful 5-10 min recap, P2 = rich detail for a long recap, P3 = texture/side gags.
