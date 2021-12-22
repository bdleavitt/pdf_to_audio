import sys
import time
import os
import logging
import json
import uuid
import requests
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials

import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info(f'Processed a request for OCR')

    '''
    Authenticate
    Authenticates your credentials and creates a client.
    '''
    computer_vision_subscription_key = os.environ['COMPUTER_VISION_RESOURCE_KEY']
    computer_vision_endpoint = os.environ['COMPUTER_VISION_RESOURCE_ENDPOINT']
    computervision_client = ComputerVisionClient(computer_vision_endpoint, CognitiveServicesCredentials(computer_vision_subscription_key))

    try:
        req_body = req.get_json()
    except ValueError:
        pass
    else:
        source_file_name = req_body.get('source_file_name')
        source_file_language = req_body.get('source_file_language')
        url_to_process = req_body.get('source_file_url')
        target_translations = req_body.get('target_translations')

    ##################################################
    ## Do OCR on source file
    ##################################################
    logging.info(f"Doing OCR on source file {source_file_name}")
    read_response = computervision_client.read(url=url_to_process, language=source_file_language, raw=True)
    read_operation_location = read_response.headers["Operation-Location"]
    operation_id = read_operation_location.split("/")[-1]

    ## Wait for the results
    while True:
        read_result = computervision_client.get_read_result(operation_id)
        if read_result.status not in ['notStarted', 'running']:
            break
        time.sleep(1)

    doc_text_list = []

    if read_result.status == OperationStatusCodes.succeeded:
        for text_result in  read_result.analyze_result.read_results:
            for line in text_result.lines:
                doc_text_list.append(line.text)


    doc_text_combined = " ".join(doc_text_list)
       
    ###################################################
    ## Translate the text to the correct languages       
    ###################################################
    logging.info("Translating Text")
    
    translator_key = os.environ['TRANSLATOR_RESOURCE_KEY']
    translator_endpoint = os.environ['TRANSLATOR_RESOURCE_ENDPOINT']
    translator_region = os.environ['TRANSLATOR_RESOURCE_REGION']
    target_languages = [translation['language'] for translation in target_translations]
    
    path = '/translate'
    params = {
        'api-version' : '3.0',
        'from': 'en',
        'to' : target_languages
    }
    
    constructed_url = translator_endpoint + path

    logging.info(f"Calling {constructed_url}")
    
    headers = {
        'Ocp-Apim-Subscription-Key': translator_key,
        'Ocp-Apim-Subscription-Region': translator_region,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    body = [{
        'text' : doc_text_combined
    }]

    request = requests.post(constructed_url, params=params, headers=headers, json=body)
    translation_response = request.json()[0]

    ## add the translated text into the main languages dictionary
    logging.info("Adding translated text back into main dictionary")
    for index, target in enumerate(target_translations):
        for translated_text in translation_response['translations']:
            if target['language'] == translated_text['to']:
                target_translations[index]['translated_text'] = translated_text['text']

    ###################################################
    ## Generate Audio for each of the translations
    ###################################################
    logging.info("Generating audio for translated files")
    speech_key = os.environ['TEXT_TO_SPEECH_KEY']
    speech_region = os.environ['TEXT_TO_SPEECH_REGION']

    audio_download_list = []

    for translation in target_translations:
        speech_url = f'https://{speech_region}.customvoice.api.speech.microsoft.com/api/texttospeech/v3.0/longaudiosynthesis'
            
        headers = {
            'Ocp-Apim-Subscription-Key' : speech_key
        }

        synthesized_file_name = f'{source_file_name}_{translation["language"]}'

        payload = {
            'displayname' : synthesized_file_name,
            'description' : f'Generated audio for {translation["language"]} version of file: {source_file_name}.',
            'locale' : translation['speech_locale'],
            'voices' : f"[{{'voicename' : '{translation['speech_voice']}'}}]",
            'outputformat' : 'audio-16khz-32kbitrate-mono-mp3',
            'concatenateresult': True
        }
        
        files = {
            'script': (f'{synthesized_file_name}.txt', bytes(translation['translated_text'], encoding='utf-8'), 'text/plain')
        }

        response = requests.post(speech_url, data = payload, headers=headers, files=files)
        
        logging.info(response.status_code)
        logging.info(response.reason)
        logging.info(response.text)

        audio_download_list.append({
            'file' : synthesized_file_name,
            'language': translation['language'], 
            'locale' : translation['speech_locale'],
            'voice' : translation['speech_voice'],
            'reason' : response.reason,
            'message' : response.text,
            'download_link': response.headers.get('Location')
        })

    return func.HttpResponse(json.dumps(audio_download_list, sort_keys=True, indent=4, separators=(',', ': ')))