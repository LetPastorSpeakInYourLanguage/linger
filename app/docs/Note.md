I have attached some of the notes I have on when I tried to build recomposer before

```
I want you to help me refine my Idea for an APP, and make it a workable concept  
—-

I am always mesmerized by how movies have these moments that just take your soul, and you just want to stay there and watch it over and over. Especially when it is the same theme from multiple movies. Like for example you want to soak into romance themes \-   
you can go to the confession scene of when harry met sally, "I don't think you're an idiot at all. I mean, there are elements of the ridiculous about you. Your mother's pretty interesting. And you really are an appallingly bad public speaker... But the thing is, um, what I'm trying to say, very inarticulately, is that, um, in fact, perhaps despite appearances, **I like you, very much. Just as you are.**"   
bridget jones, "I don't think you're an idiot at all. I mean, there are elements of the ridiculous about you. Your mother's pretty interesting. And you really are an appallingly bad public speaker... But the thing is, um, what I'm trying to say, very inarticulately, is that, um, in fact, perhaps despite appearances, **I like you, very much. Just as you are.**"   
The Notebook, "So it's not gonna be easy. It's gonna be really hard. We're gonna have to work at this every day, but I want to do that because I want you. **I want all of you, forever, you and me, every day.**

Will you do something for me, please? Just picture your life for me. Thirty years from now, forty years from now, what's it look like? If it's with him, go\! Go\! I lost you once, I think I can do it again, if I thought that's what you really wanted. But don't you take the easy way out."

Notting Hill, “"The fame thing isn't really real, you know? And don't forget—**I'm also just a girl, standing in front of a boy, asking him to love her.**"

Pride and Prejudice, “"If your feelings are still what they were last April, tell me so at once. My affections and wishes have not changed, but one word from you will silence me forever. If, however, your feelings have changed, I would have to tell you: **you have bewitched me, body and soul, and I love, I love, I love you.** I never wish to be parted from you from this day on." 

*Casablanca,* "Ilsa, I'm no good at being noble, but it doesn't take much to see that the problems of three little people don't amount to a hill of beans in this crazy world. Someday you'll understand that. Not now. Here's looking at you, kid." 


You know these kind of compilations \- I want to make an App that allows me to make this kind of compilations from the scenes I remember, and I can build out my own fantasy from all lovely scenes of movies that touched my heart, and this doesn’t need to be limited to movies, I should be able to compile concrete points from podcasts and lectures, or organize thoughts from separate media sources into my own best narrations of suspense.

What kind of app would this be and how would it work

- I want it to be a studio like operation, or something with like a youtube interface where I have all my cuts in sequence as a playlist, and I also get recommendations of cuts to add to my sequence on the left, I can play any cut by clicking on it, add it to the sequence, re-arrange the sequence, remove an item from it, and then play the entire recomposed piece of media.  
- The whole point is that 


This can be used for - 
- Creating the most emotionally impactful romantic compilations of movie scenes
- Making the best motivational speeches and compilations of movie scenes, or from podcasts and lectures
- Making horror compilations of scenes that are most impactful
- Making suspenseful compilations of scenes from movies or series  

anything that I feel like organizing or recomposing in a way I like, and since the core data is the subtitles, it means I can translate them to any language I like, and then recompose them in that language with the help of a text to speech tool - I can create their dub versions.

I also want to introduce background audio for recompositions, that can be anything from music to sound effects, I would have a collection of these background audios, just like the main media files with their subtitles (also it is to note that, users can also upload media files only then we would have a tts model like whisper [i like the whisperX github repositries implementation of the subtitle generator with accurate segment level timestamps]). so these background audio should also be length adaptable (meaning we can cut them into segments and recombine them to match the length of the recomposition) [ which is a whole different monster in itself ].

so the final result would be something like a youtube app, where I upload all my library of media files (audios or videos) with or without subtitles (it auto-generates for those that don't have subtitles), and I can create my own projects (which are basically search segments texts and add scenes from searched subtitles from my database), load a sequence of segments which would represent a scene or a part that I want as a single item (I can tag and load it to folder, categorize and everything ) for organization and easy finding in other projects. I can search for previously created cuts - that were tagged, or foldered, or categorized, say for example If I am working on something about romance - I might have a romance folder where I keep all romance related scenes and so I can open that folder and see all romance related scenes that I have previously created cuts of, and then I can add any of them I think is appropirate for this current project to my sequence (e.g. a scene of a proposal or a romantic dialogue scene, a scene where two people confess their love to each other, etc. and I can keep on adding these scenes to my sequence ) [Note : a cut is a sequence of segments that are grouped together - which communicates a single coherent thought or idea ]


although I think it is more approriate to open the loaded media and make cuts as I watch it and then use those cuts in recomposition projects.

I could also be AI Assisted to create the cuts - (which would be some scenes that the app would suggest to me ), and then I can play these segments in a sequence with background music and save it as a video or audio file (which is basically recomposed data ), or just share it with friends.

we can also have a social component where we can see what our friends have recomposed (if they share it with us ) or what other people have recomposed (if they share it publicly )

This app could be used for so many things:

- creating the most emotionally impactful romantic compilations of movie scenes
- making the best motivational speeches and compilations of movie scenes, or from podcasts and lectures
- making horror compilations of scenes that are most impactful
- making suspenseful compilations of scenes from movies or series
- even short form comedy compilations, where you edit clips from shows or movies and string them together in a funny way

There is just no end to what we can do here, it is like a studio, but for your personal use, for recomposing things in a way that makes sense to you, and helps you feel better, or be more productive, or just have fun with movies and series, podcast, etc.

I want this app to be extremely user friendly, where a user doesn't need to be technical to use it, they can just create an account, upload their media files, tag them, categorize them, and then create their own projects, load a sequence of segments which would represent a scene or a part that they want as a single item (I can tag and load it to folder, categorize and everything ), and then they can play these segments in a sequence with background music and save it as a video or audio file (which is basically recomposed data ), or just share it with friends. The only thing technical would be the fact that the backend would be running on some high performance gpu because it would be doing a lot of processing, but the frontend would be extremely simple and user friendly. And the whole point is to be able to create this, in the most efficient way possible, without any hassle.