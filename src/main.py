# Standard Packages
import sys, json, yaml, os
from typing import Optional

# External Packages
import uvicorn
import torch
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Internal Packages
from src.search_type import asymmetric, symmetric_ledger, image_search
from src.utils.helpers import get_absolute_path, get_from_dict
from src.utils.cli import cli
from src.utils.config import SearchType, SearchModels, ProcessorConfigModel, ConversationProcessorConfigModel
from src.utils.rawconfig import FullConfig
from src.processor.conversation.gpt import converse, extract_search_type, message_to_log, message_to_prompt, understand, summarize
from src.search_filter.explicit_filter import explicit_filter
from src.search_filter.date_filter import date_filter

# Application Global State
config = FullConfig()
model = SearchModels()
processor_config = ProcessorConfigModel()
config_file = ""
verbose = 0
app = FastAPI()
web_directory = f'src/interface/web/'

app.mount("/static", StaticFiles(directory=web_directory), name="static")
app.mount("/views", StaticFiles(directory="views"), name="views")
templates = Jinja2Templates(directory="views/")

@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(web_directory + "index.html")

@app.get('/ui', response_class=HTMLResponse)
def ui(request: Request):
    return templates.TemplateResponse("config.html", context={'request': request})

@app.get('/config', response_model=FullConfig)
def config_data():
    return config

@app.post('/config')
async def config_data(updated_config: FullConfig):
    global config
    config = updated_config
    with open(config_file, 'w') as outfile:
        yaml.dump(yaml.safe_load(config.json(by_alias=True)), outfile)
        outfile.close()
    return config

@app.get('/search')
def search(q: str, n: Optional[int] = 5, t: Optional[SearchType] = None):
    if q is None or q == '':
        print(f'No query param (q) passed in API call to initiate search')
        return {}

    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    user_query = q
    results_count = n

    if (t == SearchType.Notes or t == None) and model.notes_search:
        # query notes
        hits, entries = asymmetric.query(user_query, model.notes_search, device=device, filters=[explicit_filter, date_filter])

        # collate and return results
        return asymmetric.collate_results(hits, entries, results_count)

    if (t == SearchType.Music or t == None) and model.music_search:
        # query music library
        hits, entries = asymmetric.query(user_query, model.music_search, device=device, filters=[explicit_filter, date_filter])

        # collate and return results
        return asymmetric.collate_results(hits, entries, results_count)

    if (t == SearchType.Ledger or t == None) and model.ledger_search:
        # query transactions
        hits, entries = symmetric_ledger.query(user_query, model.ledger_search, filters=[explicit_filter])

        # collate and return results
        return symmetric_ledger.collate_results(hits, entries, results_count)

    if (t == SearchType.Image or t == None) and model.image_search:
        # query transactions
        hits = image_search.query(user_query, results_count, model.image_search)
        output_directory = f'{os.getcwd()}/{web_directory}'

        # collate and return results
        return image_search.collate_results(
            hits,
            image_names=model.image_search.image_names,
            image_directory=config.content_type.image.input_directory,
            output_directory=output_directory,
            static_files_url='/static',
            count=results_count)

    else:
        return {}


@app.get('/reload')
def regenerate(t: Optional[SearchType] = None):
    global model
    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    model = initialize_search(config, regenerate=False, t=t, device=device)
    return {'status': 'ok', 'message': 'reload completed'}


@app.get('/regenerate')
def regenerate(t: Optional[SearchType] = None):
    global model
    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    model = initialize_search(config, regenerate=True, t=t, device=device)
    return {'status': 'ok', 'message': 'regeneration completed'}


@app.get('/beta/search')
def search_beta(q: str, n: Optional[int] = 1):
    # Extract Search Type using GPT
    metadata = extract_search_type(q, api_key=processor_config.conversation.openai_api_key, verbose=verbose)
    search_type = get_from_dict(metadata, "search-type")

    # Search
    search_results = search(q, n=n, t=SearchType(search_type))

    # Return response
    return {'status': 'ok', 'result': search_results, 'type': search_type}


@app.get('/chat')
def chat(q: str):
    # Load Conversation History
    chat_session = processor_config.conversation.chat_session
    meta_log = processor_config.conversation.meta_log

    # Converse with OpenAI GPT
    metadata = understand(q, api_key=processor_config.conversation.openai_api_key, verbose=verbose)
    if verbose > 1:
        print(f'Understood: {get_from_dict(metadata, "intent")}')

    if get_from_dict(metadata, "intent", "memory-type") == "notes":
        query = get_from_dict(metadata, "intent", "query")
        result_list = search(query, n=1, t=SearchType.Notes)
        collated_result = "\n".join([item["Entry"] for item in result_list])
        if verbose > 1:
            print(f'Semantically Similar Notes:\n{collated_result}')
        gpt_response = summarize(collated_result, summary_type="notes", user_query=q, api_key=processor_config.conversation.openai_api_key)
    else:
        gpt_response = converse(q, chat_session, api_key=processor_config.conversation.openai_api_key)

    # Update Conversation History
    processor_config.conversation.chat_session = message_to_prompt(q, chat_session, gpt_message=gpt_response)
    processor_config.conversation.meta_log['chat'] = message_to_log(q, metadata, gpt_response, meta_log.get('chat', []))

    return {'status': 'ok', 'response': gpt_response}


def initialize_search(config: FullConfig, regenerate: bool, t: SearchType = None, device=torch.device("cpu")):
    # Initialize Org Notes Search
    if (t == SearchType.Notes or t == None) and config.content_type.org:
        # Extract Entries, Generate Notes Embeddings
        model.notes_search = asymmetric.setup(config.content_type.org, search_config=config.search_type.asymmetric, regenerate=regenerate, device=device, verbose=verbose)

    # Initialize Org Music Search
    if (t == SearchType.Music or t == None) and config.content_type.music:
        # Extract Entries, Generate Music Embeddings
        model.music_search = asymmetric.setup(config.content_type.music, search_config=config.search_type.asymmetric, regenerate=regenerate, device=device, verbose=verbose)

    # Initialize Ledger Search
    if (t == SearchType.Ledger or t == None) and config.content_type.ledger:
        # Extract Entries, Generate Ledger Embeddings
        model.ledger_search = symmetric_ledger.setup(config.content_type.ledger, search_config=config.search_type.symmetric, regenerate=regenerate, verbose=verbose)

    # Initialize Image Search
    if (t == SearchType.Image or t == None) and config.content_type.image:
        # Extract Entries, Generate Image Embeddings
        model.image_search = image_search.setup(config.content_type.image, search_config=config.search_type.image, regenerate=regenerate, verbose=verbose)

    return model


def initialize_processor(config: FullConfig):
    if not config.processor:
        return

    processor_config = ProcessorConfigModel()

    # Initialize Conversation Processor
    processor_config.conversation = ConversationProcessorConfigModel(config.processor.conversation, verbose)

    conversation_logfile = processor_config.conversation.conversation_logfile
    if processor_config.conversation.verbose:
        print('INFO:\tLoading conversation logs from disk...')

    if conversation_logfile.expanduser().absolute().is_file():
        # Load Metadata Logs from Conversation Logfile
        with open(get_absolute_path(conversation_logfile), 'r') as f:
            processor_config.conversation.meta_log = json.load(f)

        print('INFO:\tConversation logs loaded from disk.')
    else:
        # Initialize Conversation Logs
        processor_config.conversation.meta_log = {}
        processor_config.conversation.chat_session = ""

    return processor_config


@app.on_event('shutdown')
def shutdown_event():
    # No need to create empty log file
    if not processor_config.conversation.meta_log:
        return
    elif processor_config.conversation.verbose:
        print('INFO:\tSaving conversation logs to disk...')

    # Summarize Conversation Logs for this Session
    chat_session = processor_config.conversation.chat_session
    openai_api_key = processor_config.conversation.openai_api_key
    conversation_log = processor_config.conversation.meta_log
    session = {
        "summary": summarize(chat_session, summary_type="chat", api_key=openai_api_key),
        "session-start": conversation_log.get("session", [{"session-end": 0}])[-1]["session-end"],
        "session-end": len(conversation_log["chat"])
        }
    if 'session' in conversation_log:
        conversation_log['session'].append(session)
    else:
        conversation_log['session'] = [session]

    # Save Conversation Metadata Logs to Disk
    conversation_logfile = get_absolute_path(processor_config.conversation.conversation_logfile)
    with open(conversation_logfile, "w+", encoding='utf-8') as logfile:
        json.dump(conversation_log, logfile)

    print('INFO:\tConversation logs saved to disk.')


if __name__ == '__main__':
    # Load config from CLI
    args = cli(sys.argv[1:])

    # Stores the file path to the config file.
    config_file = args.config_file

    # Store the verbose flag
    verbose = args.verbose

    # Store the raw config data.
    config = args.config

    # Set device to GPU if available
    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")

    # Initialize the search model from Config
    model = initialize_search(args.config, args.regenerate, device=device)

    # Initialize Processor from Config
    processor_config = initialize_processor(args.config)

    # Start Application Server
    if args.socket:
        uvicorn.run(app, proxy_headers=True, uds=args.socket)
    else:
        uvicorn.run(app, host=args.host, port=args.port)