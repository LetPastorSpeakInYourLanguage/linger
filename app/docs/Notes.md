I want to create a video language dubbing utility web app - and I want you to help me refine the structure
I have multiple utilities that I want to run on a python FastAPI backend
1. SubEditing l
A: [Subtitle Utilities - from Backend]
- Video/Audio Transcriber (takes a media file and returns transcript)
- Translator - Takes transcript (segments list) in source language and returns the translations to a desired language
B: [I want to build a UI - for…]
- Proofreading transcription & translation (either separately or together) - either in chunks or one by one
2. Support Tools
A: [Support Utilities - from Backend]
- Split Audio and Accompaniments (takes audio/video [extracts audio if it is given a video]  - returns source-vocals.wav & source-accompainements.wav - separating speech parts and background audios)
- TTS: (takes transcript and a selection from 53 available languages - returns - target-speech.wav in the selected language)
- Merger: (takes optional source-accompaniments.wav  & target-speech.wav ⇒ returns target-audio.wav ) by merging them
B: [I want to build a UI - for…]
- Aligning audio/subtitles - renders audio time-line and overlays selected transcripts on-top so that we can recalibrate the positioning of subtitle segments over audio [I can also create-new segments, edit their text or delete them] - (so I can change their start and end time from the timeline - but I also need to CRUD the segments themselves) - supporter for the proofreading utility previously mentioned
- dub manager interface (this is where I)
Manage all my uploaded video/audio files 
The main files - and subsequently generated items like (source-vocals, source-accompaniments, audio-version-(incase it’s a video),...)
the subtitle transcript - uploaded for or I generated for them 
And the translations of each of those subtitles 
the audios generated for each of the translation transcriptions (target-speech.wav)
Execute
UploadMedia (With or Without Transcript, GenerateAudio, SplitAudio
GnerateTranscript, TranslateTranscript, TranscriptToSpeechGenerate
Merge TargetSpeech to SourceVideo/Audio (THIS IS THE VALUE PROPOSITION) 




--------
GEMINI

Of course. Here is a refined structure for your video language dubbing web app, focusing on a more streamlined workflow and clearer separation of concerns between your FastAPI backend and the frontend UI.
Backend API Structure (FastAPI)
Your backend should be organized around core functionalities, with distinct endpoints for each major task. This modular approach will make the API easier to build, test, and maintain.

1. Project Management API
This is the central hub for managing all assets related to a single dubbing project.
POST /projects/: Creates a new project. The request would include the initial media file (video or audio). The server will then create a unique project ID and a dedicated folder structure on the server to store all related files.
GET /projects/{project_id}: Retrieves all information about a specific project, including file paths for the original media, extracted audio, transcripts, translations, and final dubbed audio.
GET /projects/: Lists all existing projects.

2. Audio & Transcription API
This group of endpoints will handle all audio processing and speech-to-text tasks.
POST /projects/{project_id}/transcribe: Takes a project ID. It automatically finds the source audio and runs the transcription model. The output (a JSON file with subtitle segments) is saved to the project's folder.
POST /projects/{project_id}/split-audio: Takes a project ID. It finds the source audio and separates it into vocals.wav and accompaniment.wav.

3. Translation & Dubbing API
These endpoints will manage the language translation and new audio generation.
POST /projects/{project_id}/translate: The request body should contain the target_language. This endpoint reads the source transcript, translates it, and saves the new translated transcript.
POST /projects/{project_id}/generate-tts: This endpoint will take the translated transcript and generate the text-to-speech target-speech.wav. You can include parameters for voice selection in the request body.
POST /projects/{project_id}/merge-audio: This is the final step. It combines the target-speech.wav with the original accompaniment.wav to create the final dubbed audio track (dubbed-audio.wav). If it was a video project, it could also merge this new audio back into the video file.

Frontend UI Structure
The user interface should be designed to guide the user through a logical and intuitive workflow. Instead of thinking of them as separate utilities, consider a project-based dashboard.

1. The Project Dashboard
This will be the main view where users can see and manage all their dubbing projects.
Project Creation: A prominent "New Project" button that allows users to upload a video or audio file.
Project List: A gallery or list view of all existing projects. Each entry should show the project name, a thumbnail, and the status (e.g., "Transcribing," "Ready for Proofreading," "Dubbing Complete").

2. The Dubbing Studio UI
This is the core of your application where all the editing and generation happens. Clicking on a project from the dashboard would open this interface. It should be a single, integrated view.
Media Player & Timeline: A central component that displays the video or audio waveform. The subtitle segments should be visually represented on the timeline.
Subtitle Editor: A two-column text editor below the media player:
Column 1 (Source): Displays the original transcript.
Column 2 (Target): Displays the translated text.
Users can play a segment, edit the text in either column, and adjust the start/end times directly on the timeline by dragging the segment blocks. The changes are saved automatically.
Control Panel (Sidebar): A panel on the side with clear, actionable buttons:
"Generate Transcript": Becomes active after the initial upload.
"Translate": Becomes active after transcription is complete. A dropdown allows the user to select the target language.
"Generate Dubbed Audio": Becomes active after translation. This triggers the TTS and merging process.
"Download": Allows the user to download the final dubbed video/audio, the subtitle files, or the individual audio tracks.
By integrating the tools into a cohesive "Studio" environment, you move from a collection of separate utilities to a powerful, user-friendly dubbing platform. This refined structure simplifies the user journey and makes the entire process more intuitive.

—-----------------------------------
3 enhancements I need you to add
1. ProofReader View: give me another view in studio - where I see the segments in table format  of two columns (src language and target language - I can be editing source language, target language or both ) this will enable efficient proofreading for long content - in which it might not be as important to look at the video always (if it is a paginated table with the ability to set the number of rows per page - it will be perfect)
2. Manage Multiple Target Languages: I also want to be able to dub the same source into multiple target languages, so incorporate the ability to keep the state for the dubbing to be done for each of my target languages
3. Project Detail Management: give me the ability to see details of projects and manage what transcripts, generated and source files of the the source and each of initiated Target languages

—-----------------------------------

Then we can move to the 
TimingAlinger View: Waveform and Segment Start & Duration visual adjustment functionality
Also at ProofReader - we should be able to add a target language for generating translation also and not be limited to generated transcriptions (let it just be that generated target languages have a tick or symbol for visualization)
(when the user selects the target language - the generate translation button appears if it’s not translated - and on click the generation procedure is executed, if translated then the target translation is loaded for proofreading!) (persist the currently loaded target Language to database also so that state is persisted when page reloads)

—------------------------------------
- Now add 
- User Management Functionality for them to register and login to access these functionalities
- Add Self Upload Source and Target Language Transcriptions to Uploaded Source File
- Add the Ability to also Capture media from a Youtube Link not Just File uploads - (if it is a youtube link - then render the video from youtube)

(by the end of these enhancements 
- I should be able to register and login
- create a project from a youtube link also
- upload my own subtitles either at studio home or at details page for a given target language or the source ( when manually uploading additional resources - I am prompted to specify the language and the type of data like transcript with format specified, … )
- while proofreading and timing alignment keep working perfectly

—---------------------------------------

Errors and Issues to patch
- at Studio ⇒ Incorporate an Additional Step called - Merge - (this is for videos-files - which takes the output generated audio and calls the Merge api (mock in our demo case) and generates the target-dub.mp4 video)

- at Proofreader 
1. The add Language Button should only be enabled if a language is selected from the setCurrentDropDown and that language doesn’t have a translation already
2. If The Media Doesn’t already have a Source Transcript (instead of just saying generate transcript first - add a button to generate transcript right within the proofreader

- at Resource Uploader ⇒ Its not just transcripts - we can also upload target-speech.wav, source-vocals.wav, source-accompaniments.wav (ask target language if upload-type is targetLanguage transcript)


--------------------------------------------

The App for people who are always tasked to translate manuscripts from English to multiple languages - They are provided with a word document that contains a single table of two columns [the first columns contain the English texts and the second column is empty and is for filling the designated translations] - and they are told the language they should translate to.




Database Table for 
Users Data Example 
{
    "_id": "user_id_1",
    "name": "John Doe",
    "email": "translator1@example.com",
    "hashedPassword": "...", // or basic password for demo
}

Sentences Example (english is always the source bench language)
{
    "_id": "s_e9ff8328", // A hash of the source text
    "sourceText": "The quick brown fox jumps over the lazy dog.",
    "translations": {
        "am": [ // Amharic
            { "text": "ፈጣኑ ቡናማ ቀበሮ በሰነፉ ውሻ ላይ ዘለለ።", "usageCount": 15 },
            { "text": "ፈጣን ቡናማ ቀበሮ በሰነፍ ውሻ ላይ ይዘላል።", "usageCount": 2 }
        ],
        "ti": [ // Tigrinya
            { "text": "እቲ ቅልጡፍ ቡናዊ ወኻርያ ኣብ ልዕሊ እቲ ሃካይ ከልቢ ይዘልል።", "usageCount": 7 }
        ]
    }
}
Source Document Example 
{
    "_id": "doc_hist_world_01",
    "sourceName": "History of the World",
    "content": ["s_e9ff8328", "s_a1b2c3d4", ...], // Array of sentence IDs
    "uploadedBy": "user_id_1", // Ref to users collection
    "uploadedAt": "2025-06-23T12:00:00.000Z",
    "authorizedTranslators": ["user_id_1", "user_id_2"] // KEY CHANGE: Array of user IDs
}

Translation Instance Example
{
    "_id": "job_hist_world_01_am", // E.g., {sourceDocumentId}_{targetLanguage}
    "sourceDocumentId": "doc_hist_world_01", // Ref to sourceDocuments
    "targetLanguage": "am", // ISO 639-1 code
    "status": "in_progress", // 'in_progress' or 'completed'
    "ownerId": "user_id_1", // The user who initiated the job
    "contributors": ["user_id_1"], // Array of user IDs who have made edits
    "isLockedBy": null, // or "user_id_2" if being edited
    "lockExpiresAt": null, // Timestamp to prevent stale locks
    "selections": {
        "s_e9ff8328": {
            "selectedIndex": 0,
            "isConfirmed": true,
            "confirmedBy": "user_id_1" // Who clicked 'confirm'
        },
        "s_a1b2c3d4": {
            "selectedIndex": 1,
            "isConfirmed": false,
            "confirmedBy": null
        }
    }
}

Record Keeping for changes made to DB Tracking
{
    "_id": "log_id_12345",
    "timestamp": "2025-06-24T10:00:00.000Z",
    "userId": "user_id_1", // Who performed the action
    "actionType": "SAVE_CHANGES", // e.g., “UPLOAD_TRANSCRIPT” , “ADD_TRANSLATION” , “EDIT_SOURCE_SENTENCE”
    "details": {
        "translationInstanceId": "job_hist_world_01_am",
        “payload”: { "userChangedOptions": [ { "sentenceId": "s_e9ff8328", "options":  [ { "text": "ፈጣኑ ቡናማ ቀበሮ በሰነፉ ውሻ ላይ ዘለለ።", "usageCount": 15 }, { "text": "ፈጣን ቡናማ ቀበሮ በሰነፍ ውሻ ላይ ይዘላል።", "usageCount": 2 }, { "text": "ፈጣን ቡናማ ቀበሮ በሰነፍ ውሻ ላይ ይልሏል።", "usageCount": 1 } // newly added ]  }],
"userConfirmedSelections":{ "s_e9ff8328": { "selectedIndex": 2, "isConfirmed": true, "confirmedBy": "user_id_1" // Who clicked 'confirm' }, "s_a1b2c3d4": { "selectedIndex": 1, "isConfirmed": false, "confirmedBy": null } } } // this is the case where the user edited an option ad created another one to select
    }
}



(not including the user register, login features - there are 5 core activities involved)
Upload Document
Add Collaborators
New Translation Task Start (Add Translation Language)
Translation Progress Save 
Export Translated Manuscript



—------------------------------------------------------------

1. The Document Dashboard
A translator logs in and sees a dashboard of SourceDocuments. They only see documents where their user ID is present in the authorizedTranslators array.
Each document card shows the sourceName, dynamically lists the TranslationInstances currently underway for the document (e.g., "Languages: Amharic (In Progress), Spanish (Completed)"). - status coloring is acceptable, and also a “Add New Language” Button which loads a modal workflow to start a translation task for a new non-started language (see “Starting a New Translation Instance” below) 
For documents for which the currentUser is owner shown by “uploadedBy” field - he has the button to “Set Collaborators” - This loads a modal with a text input field to put their Id and click add button to add them to the list. And he can also see the list of collaborators currently active with the option to remove them
2. [interaction] Entering the Translation Studio
The translator clicks on a document card. This opens the Translation Studio.
Crucially, they have not selected a target language yet. The studio first presents them with an Empty Language Hub.
The translator clicks on a TranslationInstances badge within a Document card. This opens the Translation Studio - with the instanceId as a parameter passed to it
Here, the target language is set as TranslationInstanceId in the parameters - this loads the Language Hub with a populated Editor (see “Initial Data Loading and Population” below)
3. [page] The Language Hub (Inside the Studio)
This is the initial view within the studio for any document.
Ongoing Translations: A dropdown of languages already being translated. A translator can select one of these to open the existing TranslationInstance in the editor (see "A Note on Collaboration" below).
"Add New Language" Button: This is the button to initiate a new translation effort through a modal (see “Starting a New Translation Instance” below)
4. [modal] Starting a New Translation Instance
This follows your specified flow precisely:
The translator clicks "Add New Language" in language Hub or within a Document card at Document Dashboard.
A modal appears, listing all available languages for which a TranslationInstance does not already exist for this document.
The translator selects a language, for example, "Tigrinya" (ti).
Initial Data Setup and Creation is performed in the Backend. (see “Initial Data Loading & Population” below)
Editor is only loaded when there is a TranslationInstanceID passed as a parameter to the Language Hub page
5. [component] The Editor Interface & Experience
The editor is the pagination Enabled TanStack Table with two columns (sourceLanguage, TargetLanguage), loaded with the data from the SourceDocument [for sourceColumn], and SentenceDB target language option dropdowns with confirmed/non-confirmed selections as specified by TranslationInstance Records.
Progress Tracking: A percentage bar shows the ratio of confirmed sentences. Progress Bar: At the top, a visual bar shows (confirmed sentences / total sentences) %
Source Cell Editing: Editing the source creates a new sentence_id, triggers an on-the-fly MT fetch for that single new sentence, and updates the UI and database records. (Edit button Appears on top-right - when the user focuses on the cell) - onClick loads a dialog with a textArea with the sourceSentence Populated - if the user makes changes - a save button is enabled to trigger the database activity and Machine Translation
Target Language Cell Interaction:
On focus, over a cell in the Target language Column three top-right floating buttons appear: (Edit, Options, Confirm) 
The "Confirm" button marks that row's selection as final (isConfirmed: true).
The "Edit" button loads a modal with the source language text, and the target option populated to a text area for the user to edit - then he can save - this creates an additional translation option for the sentence_id in the current target language. Automatically the new sentence translation option is set as the selected and confirmed option (isConfirmed: true). In the TranslationInstance record.
the "Options" button appears (if alternatives exist) to switch between translation options (if only one option for the source sentence this button doesn’t appear) - [when only machine translation option is available - mostly for first time loaded sentences - only the machine generated translation are available].
Navigation & Bulk Confirmation:
Basic Paginations (Prev, Next Page, Set Rows Per Page)
Confirm Current Page: Confirms all visible rows.
Go to Next Unconfirmed: Jumps to the first page with an unconfirmed sentence.
Saving Progress: 
Save Changes Button: This stores all Option confirmations of translation options to Update at TranslationInstance and newly created options when user edits translations creating a new option to add to the current sentence_id’s current language options in Sentence DB - all these changes are pushed into backed (either by every 4 minutes callback - or user manually clicking the save changes button)
Utility Buttons: 
These are a list of Bottom-right floating buttons to facilitate translation processes 
Finalization: The "Complete Translation" button remains disabled until the progress bar is at 100%. Clicking it:
Sets the TranslationInstance status to completed.
Triggers the batch background job to increment the usageCount for all the selected translations in the main Sentences DB.
Initial Data Loading & Population
This is a critical, one-time process when a Translator opens a new language task for the first time.
Identify Missing Translations: The system takes all sentence_ids from the SourceDocument and checks the Sentences database to see which ones lack a translation for the targetLanguage.
Automated MT Fill-in: by bringing sentences missing a translation together, the system calls an external Machine Translation API (like Google Translate 5k characters per API call - batch request by newline separation of sentences is performed (sentences batched together up-to highest below 5k character chunks - then request is sent)- and results extracted for sentences by each new line).
Update Central TM: The results from the MT API are saved back into the Sentences database. They are marked as addedBy: 'mt_api' and start with a usageCount of 0.
Hydrate the Studio: The system now fetches the complete data for the studio: for every source sentence, it retrieves all available translation options in the target language. These options are sorted by usageCount in descending order, ensuring the most proven translations appear first.
Set Defaults: The TranslationInstance is created and its selections’ map is populated. By default, every sentence is assigned selectedIndex: 0 (the top-ranked translation) and isConfirmed: false. This entire data package is sent to the client-side editor. Future interactions for this session work on this local data to ensure a fast UI.
A Note on Collaboration
This model opens up questions about multiple translators working on the same TranslationInstance. Here's a simple, effective way to manage this:
Translation instance Ownership: The translator who creates a TranslationInstance is the ownerId.
Locking Mechanism: When a translator opens a TranslationInstance, the system can set a "lock" on it (e.g., isLockedBy: 'user_id'). If another translator tries to open the same TranslationInstance, they see a message: "This translation is currently being edited by [Translator Name]." - instead of loading the Editor for them.  When the first translator closes the editor (back button to dashboard), or doesn’t make save changes update within 20 minutes - the lock is expired/released. This prevents conflicting edits.
Translation facilitating Utilities
The Amharic Bible Loader and Date Converter Utility [this are loosely coupled to the languages] (I need Independent components to be build for these - and they be positioned as floating buttons at the bottom-right)
The Amharic Bible To Copy from Modal (am-54, am-05, am-NIV) versions [ with the ability to copy multi-verses [ex. John 1:1-5] - so basically you provide, version, book, chapter, and start & (optional) end verse
Date Converter Utility - Modal interaction where - you provide [year, month, day] => then you copy the alternative ethiopian Timing 
[These options are available for Translating to Target Amharic, Oromo, Tigrinya & Somali ] if the target language being translated to is not among these these options are not available - so create some kind of module addable type schema where I can just add JSON Bibles of languages to enable the bible browser utility for that language’s bible versions - so even for Oromo, Tigrinya & Somali only the JSON version bibles I add for them will be available, and for converting utility I enable it after implementing the method that takes date in english can returns date in the desired counting system - then to enable this feature for the language, I would simply enable it for that language and connect the converting method

—-- Requirements
Upload
User Uploads Source Language Document as a word file (.docx)  [THE SYSTEM THE EXTRACTS TRANSLATABLE FIRST ROW ENGLISH CONTENT FROM THE DOCUMENT]
Action: “Upload” button submits “The document” 
System must Confirm that the document MUST HAVE A TWO COLUMN TABLE WITH ONLY THE FIRST COLUMN FILLED improper uploads are rejected and user does not pass the upload phase

