<!-- SYSTEM -->
You are the head story editor. You receive scene cards (produced chunk-by-chunk from subtitles) for an
entire work. Build the GLOBAL understanding: what the story is actually about, which beats the plot cannot be
understood without, which earlier beats are setups that become important because of later payoffs, and where
the emotional and comedic peaks are. Importance must be judged against the WHOLE story, not locally. Return ONLY JSON.

<!-- USER -->
WORK: an unknown feature film (names changed)
SCENE CARDS:
## c01-s1 L0-L30 | Manhattan street and brownstone entry | Bram, Hollis, Opal, Otto
   An agent rushed a mother and her daughter through a huge brownstone. The mother needed to move in within two weeks to prove to her soon-to-be ex-husband she could house their daughter.
   c01-b1 [setup/4] L26-L29: Bram, newly separated, must buy a home within 14 days to prove she can provide for her daughter
   c01-b2 [world/2] L0-L18: Agents show Bram and Hollis a huge four-floor brownstone with an elevator
   humor L24-L25: the kid teaches mom to haggle
## c01-s2 L31-L44 | upper floors | Bram, Hollis, Opal
   Touring the floors, they learned the late owner was a paranoid, reclusive rich man whose heirs are suing because half of his fortune is missing.
   c01-b3 [setup/4] L33-L38: The late owner was a paranoid recluse whose missing millions have his heirs suing each other
## c01-s3 L45-L87 | master bedroom | Bram, Hollis, Opal
   Bram noticed a strange corner; the agent revealed a hidden panic room with steel walls, a separate phone line, its own air and video monitors of the whole house. Bram found it unnerving; the door's safety sensor was demonstrated.
   c01-b4 [setup/5] L50-L64: A hidden panic room is revealed: steel walls, separate phone line, own ventilation, monitors on every room
   c01-b5 [character/3] L65-L71: Bram is uneasy about the claustrophobic room
   c01-b6 [setup/4] L81-L86: The steel door has an infrared sensor that stops it closing on anything in its way
   humor L67-L70: 'Ever read any Poe?' / 'I love her album' / 'The furniture guy?'
   moment L50-L64 (awe/2): the panic room reveal
## c01-s4 L88-L108 | the new house, first night | Bram, Hollis
   On their first night, mother and daughter ordered pizza, vented about the ex-husband and his new partner, and the mother read to her daughter at bedtime.
   c01-b7 [relationship/3] L88-L102: First night in the house: Bram and Hollis bond and share bitterness about the ex-husband
   humor L99-L102: 'Fuck him.' 'Don't.' 'Fuck her too.' 'I agree. But don't.'
   moment L99-L102 (warm/1): mother-daughter venting
## c01-s5 L109-L159 | outside/inside the house at night | Rufus, Lena, Milo
   Three burglars broke in at night and discovered the mother and daughter had already moved in because of an escrow mix-up. One wanted to quit since people were involved, while the planner insisted they could finish in 45 minutes; the third, an armed stranger, alarmed the others.
   c01-b8 [plot/5] L109-L122: Three burglars break in and find the house unexpectedly occupied by a woman and a child
   c01-b9 [plot/4] L131-L140: Lena wants out because people are home; Rufus insists the job takes only 45 minutes
   c01-b10 [character/4] L128-L149: Rufus brought Milo, an unknown armed man, which alarms Lena
   humor L121-L126: 'Fourteen days, that's almost three weeks' — business-day escrow logic
   moment L114-L122 (panic/2): burglars realize people are home
## c02-s1 L160-L173 | inside the house | Rufus, Lena, Milo
   Rufus argued that keeping the family inside was not kidnapping and lured Lena back with fourteen million dollars hidden upstairs that would get him out of debt. They split up to grab the girl and the woman.
   c02-b1 [plot/5] L164-L170: Rufus reveals the prize: fourteen million dollars hidden upstairs, enough to clear Lena's debts
   c02-b2 [plot/3] L171-L173: The burglars split up to seize the woman and the girl
   humor L160-L164: 'You can't kidnap somebody in their own house' / 'third-generation idiot'
## c02-s2 L174-L196 | bedrooms, elevator, panic room | Bram, Hollis
   Bram saw the intruders on the monitors, woke Hollis and they raced for the panic room as the burglars closed in, sealing the door just in time. The room's phone was dead because Bram had never connected it.
   c02-b3 [plot/5] L174-L186: Bram spots the intruders, grabs Hollis and they barely make it into the panic room
   c02-b4 [plot/5] L187-L188: The panic room's separate phone line was never connected — they cannot call for help
   moment L176-L186 (terror/3): the race into the panic room
## c02-s3 L197-L207 | inside the panic room | Bram, Hollis
   Inside, Bram anxiously checked whether Hollis felt shaky or chilled, hinting at a medical condition.
   c02-b5 [setup/4] L197-L204: Bram checks Hollis for shakiness and chills — a hidden medical condition is planted
## c02-s4 L208-L225 | intercom between room and house | Bram, Rufus, Hollis
   Over the intercom the burglars told them to leave; Bram bluffed that police were coming. A sign was held up: what they wanted was inside the room. Coached by Hollis, Bram shouted at them to get out of her house.
   c02-b6 [plot/5] L211-L214: The burglars reveal that what they want is inside the panic room itself
   c02-b7 [character/3] L209-L221: Bram bluffs about the police and, coached by Hollis, defiantly refuses to come out
   humor L218-L221: daughter coaches mom to swear: 'Say fuck.'
   moment L217-L221 (defiance/2): 'Get the fuck out of my house!'
## c02-s5 L226-L256 | house, burglars regroup | Rufus, Lena, Milo
   The burglars bickered; Lena, who spent ten years building such rooms for a living, said nobody can get in, so the woman must be forced out. They decided to seal the house so the family could not escape.
   c02-b8 [character/5] L241-L248: Lena turns out to be a builder of panic rooms who knows they cannot break in, so they must force the family out
   c02-b9 [plot/3] L249-L254: They seal the house and refuse to let Milo hover with his gun
   humor L238-L244: Milo laughs at God's sense of irony
## c02-s6 L257-L281 | panic room | Bram, Hollis
   Bram began panicking in the small space; Hollis distracted her with a joke. When the intruders sealed them in, Bram lost it and Hollis screamed at her to stay present until she recovered.
   c02-b10 [relationship/4] L259-L281: Claustrophobic Bram has a panic attack; Hollis pulls her back
   humor L263-L267: 'Why did the chicken cross the road? To prove he wasn't chicken.'
   moment L272-L281 (fear/3): Hollis screams her mother out of a panic attack
## c02-s7 L282-L304 | vents outside the room | Rufus, Lena, Milo, Bram, Hollis
   Rufus pumped gas into the room's vents to drive them out; Lena protested they would die and could not get in if the pair passed out. Rufus raged that he was coming in.
   c02-b11 [plot/5] L282-L303: Rufus pumps gas into the room to force them out, over Lena's objections
   humor L299-L303: 'how are we supposed to get into the room if they pass out?' 'Oh.'
   moment L287-L293 (terror/3): gas fills the room, they cough
## c02-s8 L305-L319 | panic room window/vents; burglars | Bram, Hollis, Rufus, Lena
   Bram flashed SOS in Morse code at a neighbor, who ignored it. Meanwhile Rufus and Lena argued over splitting the fourteen million.
   c02-b12 [plot/3] L305-L316: Bram flashes an SOS to a neighbor, but he ignores it
   c02-b13 [relationship/3] L317-L319: Rufus and Lena quarrel over shares of the money
   humor L310-L311: learned SOS from 'Titanic'
## c03-s1 L320-L330 | house | Rufus, Lena, Milo
   Arguing over shares, Rufus revealed it is his own family he is robbing — the safe was his grandfather's — and insisted they need Lena to open it as Milo threatened him.
   c03-b1 [character/4] L323-L324: Rufus is the late owner's grandson, stealing from his own family's estate
   c03-b2 [relationship/3] L325-L329: Milo threatens Lena; Rufus says they cannot open the safe without Lena
   humor L327-L329: Rufus mocks Milo's gangster talk: 'You're a bus driver... you live in Flatbush'
## c03-s2 L331-L347 | bedroom and panic room door | Bram, Hollis
   While the burglars were distracted, Bram dashed out of the panic room to her bedroom and grabbed her cell phone, making it back just in time — but there was no signal inside the room.
   c03-b3 [plot/4] L333-L343: Bram risks a dash out of the room to grab her cell phone and makes it back
   c03-b4 [plot/3] L345-L347: The cell phone gets no signal inside the steel room
   moment L336-L341 (suspense/3): 'If I can't get back, close the door' — the dash
## c03-s3 L348-L367 | panic room wall; basement | Bram, Hollis, Lena, Rufus
   Bram remembered the house's main phone line ran by the room and spliced into its wires; meanwhile the burglars realized Rufus never cut the main line. She reached 911 but was put on hold and lost the line.
   c03-b5 [plot/4] L348-L367: Bram splices into the main phone line and reaches 911, but is put on hold and cut off
   humor L363-L365: '911 emergency — please hold.'
   moment L363-L366 (despair/2): 911 puts her on hold
## c03-s4 L368-L388 | panic room | Bram, Hollis, Stephen
   They called Hollis's father, but the line was garbled; Bram insisted he would come because they still are a family. Hollis confessed she had been hiding that she was dizzy and thirsty.
   c03-b6 [plot/4] L368-L382: A garbled call reaches Hollis's father; Bram insists he will come to help
   c03-b7 [payoff/5] L383-L388: Hollis admits she is dizzy and thirsty — her blood sugar is crashing
   humor L377-L377: 'three what, three bears?'
   moment L383-L388 (fear/3): Hollis's confession
## c03-s5 L389-L426 | cross-cutting: burglars / panic room | Rufus, Lena, Milo, Bram, Hollis
   Bram realized Hollis, a diabetic, needed sugar or her Glucagon shot, which was in the fridge in Hollis's room outside. Meanwhile Rufus gave up and tried to quit with a payout, but Milo declared nobody leaves and he would open the safe.
   c03-b8 [plot/5] L394-L422: Hollis is diabetic; her emergency Glucagon injection is outside the room, in her bedroom fridge
   c03-b9 [plot/4] L405-L418: Rufus tries to quit; Milo declares nobody leaves
   humor L397-L398: 'I'm dizzy, not deaf.' 'Still a smart ass, excellent sign.'
   moment L419-L426 (tender/2): mother and daughter calm each other about the attack
## c03-s6 L427-L462 | house | Milo, Rufus, Lena
   When Rufus tried to walk out, Milo violently stopped him, apparently shooting him, then held Lena at gunpoint and forced him to come up with a way into the room.
   c03-b10 [plot/5] L427-L447: Milo violently stops Rufus from leaving (apparently shooting him) and seizes control
   c03-b11 [plot/4] L448-L462: At gunpoint, Lena is forced to find a way into the room
   moment L433-L447 (shock/3): Milo turns on Rufus
## c03-s7 L463-L479 | house, in view of the room's monitors | Stephen, Milo, Lena, Bram, Hollis
   Hollis's father arrived and was captured; the burglars beat him in front of the monitors to make Bram open the door. Hollis screamed for her daddy, Bram refused, Lena protested, and Hollis began to slip into a diabetic attack.
   c03-b12 [plot/5] L463-L472: The father arrives and is captured; the burglars beat him on camera to force the door open
   c03-b13 [plot/5] L473-L473: Hollis goes into a diabetic attack and begs her mother for the injection
   moment L467-L473 (horror/3): father beaten; Hollis screams 'DADDY!'
## c04-s1 L480-L509 | inside the panic room (burglars now inside with Hollis); Bram outside on the intercom | Bram, Hollis, Lena, Milo
   The positions had flipped: the burglars were now inside the panic room with Hollis while Bram, outside, screamed that her daughter needed her medicine. Learning that without the injection Hollis could fall into a coma and die, Lena decided to give her the shot himself despite Milo.
   c04-b1 [plot/5] L480-L487: Positions flip: the burglars are locked in the panic room with Hollis while Bram is outside with the medicine
   c04-b2 [character/5] L503-L509: Told Hollis could fall into a coma and die, Lena insists on giving her the injection
   moment L503-L505 (tense/3): 'Coma. Die.' / 'I'll give her the shot.'
## c04-s2 L510-L529 | panic room | Lena, Hollis, Milo
   Lena gave Hollis the shot while confessing he was a desperate gambler who had lost his house, car and wife; Hollis recovered, and Milo sneered that he had only saved her for ten minutes.
   c04-b3 [character/5] L510-L528: Lena injects Hollis and saves her, confessing that gambling debts drove him to crime
   c04-b4 [plot/4] L529-L529: Milo: 'You saved her life for ten minutes' — he means to kill her
   humor L512-L512: 'TV don't lie, right?'
   moment L519-L527 (melancholy/2): Lena's bad-cards confession while saving the girl
## c04-s3 L530-L575 | front door; monitors | Bram, Police officers, Milo, Lena
   Police arrived after the father's call. Watched on the monitors by the burglars holding her daughter, Bram convinced the officers nothing was wrong with an embarrassing lie about a drunk call to her ex, and they left.
   c04-b5 [plot/5] L530-L575: Police arrive, but with her daughter held hostage Bram lies and sends them away
   humor L571-L575: the 'three things I'll do for you' cover story
   moment L553-L567 (tense/3): officer offers a secret signal; Bram declines
## c04-s4 L576-L593 | panic room | Milo, Lena
   Milo announced the witnesses must die — the kid now, the other two later — and Lena refused; the safe was finally being opened.
   c04-b6 [plot/5] L576-L588: Milo plans to kill all three witnesses; Lena refuses
   c04-b7 [plot/4] L589-L593: The safe is opened
## c04-s5 L594-L608 | house, chaotic final fight | Bram, Milo, Lena, Hollis
   In the chaotic finale someone broke through a wall from the neighbor's house; Bram turned the burglars' own gun on them, and Lena grabbed the money and ran as Milo shouted after him. (Physical action is largely absent from the dialogue; details are inferred.)
   c04-b8 [plot/5] L594-L604: Final showdown: Bram gets hold of the gun and fights back
   c04-b9 [plot/4] L605-L608: Lena grabs the money and flees
   humor L597-L599: 'WHO BREAKS IN THROUGH THE NEIGHBOR'S HOUSE?!'
   moment L600-L606 (chaos/3): screaming climax
## c04-s6 L609-L610 | outside | Police officers, Lena
   Police ordered someone, apparently the fleeing Lena, to put their hands up.
   c04-b10 [payoff/4] L609-L610: Police order the fleeing burglar to put his hands up
## c04-s7 L611-L613 | later, a park bench | Bram, Hollis
   Later, mother and daughter browsed real-estate listings and wondered where they would live now.
   c04-b11 [payoff/4] L611-L613: Epilogue: safe, mother and daughter look for a new place to live
   humor L613-L613: house-hunting again after the house from hell
   moment L611-L613 (warm/1): calm epilogue

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
