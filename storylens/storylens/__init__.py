"""storylens — subtitle-first story understanding and automatic recaps.

Architecture (docs/METHODOLOGY.md): capture wide once, project narrow many times.
  T0 evidence   cues, speakers, scenes, shots, keyframes            (ingest.py, media.py)
  T1 facts      every act/state/reveal/quote of every character     (understand.py: P1 cards+ledger)
  T2 structure  beats, threads, edges, turning points, characters   (understand.py: P2 integrate, P2c causal)
  T3 views      main / character / trait / thread lenses            (views.py)
  then          selection -> script -> verify -> render             (select.py, script.py, render.py)
"""
__version__ = "0.1.0"
