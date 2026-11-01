"""Strict JSON schemas for every LLM pass (all keys required, no extra keys) — used for structured outputs
and to validate folder/agent answers. Empty string / empty list = 'not applicable'."""
S, I, B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}


def obj(**props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


SPAN = arr(I)  # [first_line, last_line]

ACT_TYPES = ["helps", "comforts", "defends", "protects", "rescues", "sacrifices", "gifts", "advises", "encourages", "thanks",
             "apologizes", "forgives", "confesses", "reveals", "discovers", "decides", "plans", "refuses", "quits", "leaves",
             "returns", "jokes", "teases", "mocks", "flirts", "kisses", "rejects", "breaks_up", "argues", "accuses",
             "lies", "deceives", "betrays", "steals", "threatens", "attacks", "kills", "other"]
FACT_KINDS = ["act", "state", "reveal", "quote", "joke", "moment"]
DISCOURSE_ACTS = ["asserts", "argues", "illustrates", "cites", "asks", "answers", "advises", "agrees", "disagrees", "confesses",
                  "jokes", "prays", "reads", "quotes", "predicts", "other"]
DISCOURSE_KINDS = ["claim", "argument", "story", "question", "answer", "reference", "advice", "quote", "joke", "moment"]

CARDS = obj(
    roster_updates=arr(obj(name=S, aliases=arr(S), who=S)),
    scenes=arr(obj(
        id=S, lines=SPAN, setting=S, characters=arr(S),
        speakers=arr(obj(line=I, name=S)),
        summary=S,
        beats=arr(obj(id=S, text=S, lines=SPAN, kind=S, local_importance=I, emotion=S, intensity=I, who=arr(S))),
        facts=arr(obj(id=S, kind=S, actor=S, act_type=S, target=S, cost=I, field=S, value=S, text=S, lines=SPAN,
                      intensity=I, beat_id=S, topics=arr(S), stance=S)),
    )),
    story_so_far=S,
)

INTEGRATE = obj(
    logline=S, genre_tone=S,
    characters=arr(obj(name=S, aliases=arr(S), role=S, arc=S, importance=I)),
    threads=arr(obj(id=S, title=S, summary=S, importance=I, beats=arr(S))),
    turning_points=arr(obj(tp=S, beat_id=S)),
    beats=arr(obj(id=S, global_importance=I, tier=S, requires=arr(S), pays_off=arr(S), thread=S, short=S, spoiler_level=I)),
    themes=arr(S),
)

CAUSAL = obj(links=arr(obj(beat_id=S, caused_by=arr(S), revealed_by=arr(S), witnessed_by=arr(S), evidence_facts=arr(S))))

VISION = obj(events=arr(obj(text=S, kind=S, who=arr(S))), onscreen_text=S, setting=S, is_credits=B)

CHARACTER_VIEW = obj(
    summary=S, arc=S, hidden_gems=arr(S),
    items=arr(obj(ref=S, salience=I, tier=S, role=S, why=S)),
)

TRAIT_MAP = obj(description=S, act_types=arr(S), keywords=arr(S), actor_required=B)

TRAIT_CHECK = obj(checks=arr(obj(ref=S, match=B, strength=I, why=S)))

TOPIC_MAP = obj(description=S, topics=arr(S), keywords=arr(S), speakers=arr(S))

TOPIC_CHECK = obj(checks=arr(obj(ref=S, relevant=B, speaker=S, speaker_confident=B, claim=S, stance=S, strength=I, first_line=I, last_line=I)))

ZOOM = obj(details=arr(obj(ref=S, detail=S, line=I)), corrections=arr(obj(ref=S, issue=S, fix=S)))

SCRIPT = obj(
    title=S,
    segments=arr(obj(type=S, text=S, refs=arr(S), media=S, lines=SPAN, mood=S)),
)

VERIFY = obj(checks=arr(obj(index=I, verdict=S, issue=S, fix=S)), leakage=arr(S))
