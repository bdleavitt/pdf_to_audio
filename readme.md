Takes a blob uri for a PDF and extracts, trasnlates, then creates an audio file of the content. 

Deploy to Azure functions and call using POST with the body below. 

```
{

    "source_file_name" : "you_file_name",

    "source_file_language" : "en",

    "source_file_url":"your_blob_sas_uri",

    "target_translations": [

        {"language":"es", "speech_locale": "es-MX", "speech_voice": "es-MX-DaliaNeural"},

        {"language": "fil", "speech_locale": "en-US","speech_voice": "en-US-AriaNeural"}

    ]
}
```