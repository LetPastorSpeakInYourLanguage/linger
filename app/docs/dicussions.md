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
  File "C:\Users\pc\AppData\Local\Programs\Python\Python312\Lib\asyncio\events.py", line 84, in _run
    self._context.run(self._callback, *self._args)
  File "C:\Users\pc\AppData\Local\Programs\Python\Python312\Lib\asyncio\proactor_events.py", line 165, in _call_connection_lost
    self._sock.shutdown(socket.SHUT_RDWR)
ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host
```

also is there any way that we can enable multiple subtitles per media file, so that I can have multiple subtitles but they still link to the same source media, and the cuts created from them also play portions from that media,
then I also want to have a subtitle editor part where I can edit or create subtitles for the media files - this needs to be very meticoulusly thought about - it is so that I can fix subtitle errors in timing, add missing subtitles segments or remove non desired subtitle segments. I should also be cappable of doing batch operations with regex selection (you can ingore this one if it is too complex)

- then lets now try and push the faster-whisper transcription engine and yt-dlp uploads - add them to requirements and setup the required configurations, I will install them and make sure they are working

-----------------------
something we missed is that when user deletes a subtitle track, if it is the last one avaialable or if there are cuts created from it, it should be blocked, also on adding a track, I should be able to select generate with whisper transcription, also please I want you to use the whisperX library's implementation (https://github.com/m-bain/whisperx, not just faster-whisper), it is much more accurate in the timestamps, then also add the capability to export I want to see that thing work (before we move to phase 2 or next operations)


------------------------
- model selection thingy
- 