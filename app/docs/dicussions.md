the media preview interface needs a big analysis and revamp for optimal UI/UX, so please build the frontend correctly with the following recommendations


on Library Item Preview
1. right now I can only select one subtitle segment for a cut, but we said it should be able to select a sequence (at least I should be able say like also include the next two segments also)

2. THE SEARCH ALGORITHM, oh my GOD, please focus and build this independantly and make it the best, as the system scales we will have thousands of media files each with thousands of subtitle segments, and I want to search not only by exact word match but by fuzzy matching, semantic similarity, and others but for now atleast lets have fuzzy because people make typing errors a lot. ( and you should have a separate panel for displaying search results and all the matched items should be displayed and cliking on the segments scrolls to that item in the transcript and I can play it or whatever I want ) - add a right side panel for this, it is very important!!!

3. even as a basics the top video and bottom transcript in a single column is not working for me [ where do I see the previous cuts I have made? ] -  I should preview the cuts I have from the media (like make it like the youtube interface we talked about)- with the cuts made from the media on the right side panel (maybe a tabbed interface with the search and cuts from the media), I should be able able to see the cuts I create, delete them if I don't like them or edit them if there is a mistake


On Cuts Window
1. add filter by source media also
2. and since I am going to have lots of folders and tags lets come up with a way to condense them and search through them or something, rather than listing them all
3. just like I can filter by tags from a cut, I should also be able to filter by folders or source media from a cut (you should add buttons for those on cuts too)
4. the great search engine from previous chould also be utilized here ( but here it is used for searching accross the entire database of subtitles from all media) - this is the monster


On Studio Window
1. I like the preview popup windows, but please optimize the user exeriance, like when I load the popup videos should pause, and I can click the "ESC" button to close it, which will cause the video to resume
2. Also add more Keyboard shortcuts for more focused control, like seeking on playing video should work from any focus not just the video player, I can move up and down in the sequence of cut items of the recomposer [ maybe I want to play the next cut ], I can play in loop on a give cut item if I just want to immerse, you know, I should have buttons auto loop, I don't want to click, up up repeatedly to return to previous cut, (that is assuming you enabled the up and down shortcuts also) 
3. Add a right click functionality on the Recomposition items to enable filtering of the recommendations [ like show recommendations from the same item, or filter by tags from this item - and I would have the tags of selected cut ], also to add to the filterer, or the folder from the selected cut
4. this means you need to advance the filtering capability (it should first be a reset and add fitler tag, folder, source media type engine) -I can clear filter, or add tag items, add media items, add folders from whom segments to search from are going to be comming

and on both the Cuts and Studio pages, I would really love it if the panels of the windows can be resizable



----------------------------------------
There is this silent error I want to fix - in recomposition when cuts in sequence, when the previous and next are from different media the video player kind of jumps when loading the video (if there is anyway to smooth that out it would be perfect)
```bash
Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)
handle: <Handle _ProactorBasePipeTransport._call_connection_lost(None)>
Traceback (most recent call last):
  File "C:UserspcAppDataLocalProgramsPythonPython312Libasyncioevents.py", line 84, in _run
    self._context.run(self._callback, *self._args)
  File "C:UserspcAppDataLocalProgramsPythonPython312Libasyncioproactor_events.py", line 165, in _call_connection_lost
    self._sock.shutdown(socket.SHUT_RDWR)
ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host
```

also is there any way that we can enable multiple subtitles per media file, so that I can have multiple subtitles but they still link to the same source media, and the cuts created from them also play portions from that media,
then I also want to have a subtitle editor part where I can edit or create subtitles for the media files - this needs to be very meticoulusly thought about - it is so that I can fix subtitle errors in timing, add missing subtitles segments or remove non desired subtitle segments. I should also be cappable of doing batch operations with regex selection (you can ingore this one if it is too complex)

- then lets now try and push the faster-whisper transcription engine and yt-dlp uploads - add them to requirements and setup the required configurations, I will install them and make sure they are working

-----------------------
something we missed is that when user deletes a subtitle track, if it is the last one avaialable or if there are cuts created from it, it should be blocked, also on adding a track, I should be able to select generate with whisper transcription, also please I want you to use the whisperX library's implementation (https://github.com/m-bain/whisperx, not just faster-whisper), it is much more accurate in the timestamps, then also add the capability to export I want to see that thing work (before we move to phase 2 or next operations)


------------------------


- Multi-modal Transcription - I should be able to select which whisper model is going to be running the transcription on system, don’t always default to the small.en  
- High Priority, High Thinking: Translation and Dubbing (Cut Level, Fallback TTS Engine from Microsoft Edge Browser Scrape at My Collab) - also Add some DTW type Technology to best align dubbed audio  portion to the source vocals (Spleeter from Deezer creates vocal + accompaniments from any audio - human voice and all other voices - we replace the human voices with dubs and reattach them with accompaniments) lip sync position best way possible (so that length of dub as much as possible matches length of source language speech) - here we have translation text optimization too, but for now let's just focus on working with the the tts output audio file and how to best position it to replace the segment portion from the source media [ we silence the vocals from the original media and add bg audio, and position the dub as optimally as possible ] - you can implement the best methodology you think should be put here  
  - Also Very High Thinking Requiring task is that On Translation - translating cuts can be done (gtranslate python pip module - but people need to do through translations - and make sure meaning is carried to the other languages correctly) - also when we need to actually manage the length of translations to more accurately match the source language text length - so that they can be spoken at a similar length of time  
  - WE SHOULD BE ABLE TO ADD LANGUAGES (have default ones, and then we can even add more by language code introduction), dubbing will only be supported for those whose tts model microsoft supports and [ ASSUME WE WILL ALSO HAVE A REPO OF DUBBING EXECUTOR MODELS FOR LANGUAGES NOT SUPPORTED ] - and as we get our hands on tts models that we can run to generate dub on target languages then we can also enable dubbing for those languages  
  - But now I WANT TO STRESS THAT TRANSLATION IS A ONE TO MANY MAPPING - that is a cut can have multiple translations, one generated by gtranslate, one by user X and another by user Y - and any of these can be dubbed and the dubs used for vocal replacement   
- High Priority, High Thinking: Variable Length Background Audio Separate Technology and then Add Tracking + Spleeter from Deezer for Remove BG Audio (Spleeter creates vocal + accompaniments - human voice and all other voices) before Merge Bg Audio  
- Also a custom way to add text overlay ass .ass subtitles that we will imprint on recompositions ( again this is language specifiable and all it's motions is controlled by .ass logic which we should have a high config editing for, just like a legit video overlay editing feature ), as a separate video track to overlay, just like background audio
- Community Sharing of Recompositions (upvote, downvote,) & Versioning creating an duplicate editable version of other creator Recompositions  
- Differed, High Thinking (Powerful separate Module for monstrous backend operations - a poor person’s budgeting solutions for storage and compute) (or maybe just add Options to Integrate https://www.vidking.net/#documentation - which offers lots of movies as iframe integratable api endpoints - please explore that option also - or disconnect the media files from actuall stored media and everytime we open the apps instance the unlinked media must be associated with a valid source for the app to work - please research on these try to integrate as much options as possible): Scaling Storage & Compute to Google:   
  - If we can attach the system to some sort of framework of stored media on multiple Google drive Folders - where in each I have some sort of Standard Folders for (source_media, exports, …) and I can save my loaded videos either manual on there or upload them via the system - I would specify where the target of an upload would be, and also on export I would specify where the target of an export would be; I can introduce new Drive folders via adding their link into my system for horizontal scaling of storage  
  - Also as a completely separate module - we should differ running background tasks to a separated background module’s operations - so every op is not automatically run on my local pc which is running the web app - but if I want to I could also start the background tasks server (which would query - IT SHOULD BE A PASSIVE SERVER, THAT RUNS TASK ON SERVER START AND EXECUTE ORDER, until this background server is running all heavy compute background operations are on - waiting for bg-server to start status, and when server starts - it initiates queue and runs all pending operations in order)   
  - THIS IS IMPORTANT ONLY IF WE CAN DIFFER STORAGE TO G-DRIVE, if we have all media in everywhere accessible G-Drive folders then we can PUT this executer module on a Google Colab Notebook and run it on the T4 GPU’s and save the results on the Google Drive itself if it is a file or on DB  
  - this allows the app to not be single pc storage and compute limited - so please research if there is any way to link to different kinds of storage sources (like if I can make the videos load from Google Drive - as a shared file and it will be best if the system can utilize them from there and run compute and build operations on them)  
- High Priority, High Thinking: The Social Media Merge: Not only do I want to export to specific files on my PC, I should also be capable to link the system to auto upload to social media platforms like all the major platforms should be connected and I can just directly push to them from my recomposer system,and once pushed they can serve as storages even (and we can also attach links to the posted recompositions) - so that people can go and view them on the social media platforms - like n8n autonomous workflows that post social media content  
- High Priority, High Thinking: AI Support Integration - vector and semantic similarity search, auto cut creation from subtitle transcripts of a video and adding to appropriate folders, giving them tags and then also suggested prompt based compilation of recomposition from well organized cuts and adding appropriate bg-audios - and general help in creating useful recompositions  
- Full End to End testing of All Features from Uploaded to Community and all Social Media Pushed Recomposition Content

You have Delivered the MVP, but now I want to know how we are moving forward, remember I still have a lot of integrations to be added to this application, what are in plan for the complete build - above I have listed things that are my important (you probably also got them from the notes we started with,) can you please re-evaluate how far we have come and if we are actually on track to make all this updates, and what things are possible from my list, and first build me a feature list with epics and milestones (as use-cases) and the complete plan with todos on how to get to the complete system and then we will follow that plan thoroughly


-----------
codex tried to build the remaining phases of on your plan earlier

@app/docs/codex.md  /code-review  I had codex try and build until phase two of our plan @app/docs/ROADMAP.md  - please look through what changes it has make and fix those that are not inline with the idea we are working towards (and also I don't think the vocals + accompaninemt splitting of source media voices is working) - the exports are just the target language voice added on the source media full audio, there is no removal of the vocal parts of the source media in the source language so that we replace it with the target language's voice only

also I want to be able to use multiple voices to actually make a different between the different speakers as their voice is translated - atleast male and female voices should be translated respectfully (I have attached the complete logic for implementing this kind of structure to reference from in @app/temp - from my previous attempts to build this app) [ atleast gender based differentiation should be available - their gender can be infered and adjusted by user at recomposition export it if the processes is damaging to how we started ]

and please lets also make the source media decoupled, so that anyone with access to the system, who might not have access to the media files in their local pc, can link to it via, link or add a reference from their own pc local storage and the videos would just work, you'ld just need to verify a sha256 matching to confirm that they have located the exact same source media (if it is from a file)

also as very high difficulty additions don't forget we need
- a complete dynamic length backgrond audio studio where we store bg-audio's and then also apply algorithms to actually cut them in the right places and extend them to each other to make the same audio be of any length that we want so that we can add bg-audio spanning any length of cuts, like I can say for this 12 cut sequence use these 3 bg-audios in this order and cuts of those will be accurate length matched to the recomposition

- and the .ass based (or if you have a better recommendation I am up for it), overlay text display method on which we can show, captions, any other text, or anything we want visual wise on the video overlay

- this all means that there will be multiple parrallel tracks on the recomposition studio (overlays, main videos, bg-audios), ...


so please review where we are, the code codex built, where we are planning to go, things we need to adjust and the feasible way forward


also please remember - we are working towards 