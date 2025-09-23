import asyncio
import uuid
import logging
from datetime import timedelta
import os
import json
from flask import (
    Flask,
    request,
    jsonify,
    session,
    send_from_directory,
    Response,
    stream_with_context,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from .engine import (
    async_init,
    stream_query,
    clean_sitemap_urls,
    conversation_manager,
    PERSIST_DIR,
)
from .utils import run_async

logger = logging.getLogger(__name__)


def create_app():
    # Resolve absolute path to frontend/dist
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'))
    app = Flask(__name__, static_folder=static_dir, static_url_path='')
    app.secret_key = 'your-secret-key-here'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_host=1)

    app_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(app_loop)

    urls = clean_sitemap_urls('https://www.urz.uni-heidelberg.de/sitemap.xml')
    query_engine = run_async(async_init(urls, persist_dir=PERSIST_DIR))
    app.config['QUERY_ENGINE'] = query_engine
    app.config['APP_LOOP'] = app_loop

    @app.route('/chat', methods=['POST'])
    def chat():
        data = request.json
        message = data.get('message', '')
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        qe = app.config['QUERY_ENGINE']
        loop = app.config['APP_LOOP']

        def generate():
            agen = stream_query(message, qe, session['session_id'])
            ait = agen.__aiter__()
            while True:
                try:
                    item = loop.run_until_complete(ait.__anext__())
                except StopAsyncIteration:
                    break
                if isinstance(item, str):
                    yield f"data: {json.dumps({'token': item})}\n\n"
                else:
                    payload = {'done': True}
                    think = item.get('think', '')
                    if think:
                        payload['think'] = think
                    yield f"data: {json.dumps(payload)}\n\n"

        return Response(stream_with_context(generate()), mimetype='text/event-stream')

    @app.route('/clear-chat', methods=['POST'])
    def clear_chat():
        if 'session_id' in session:
            conversation_manager.clear_conversation(session['session_id'])
        return jsonify({'status': 'success'})

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def index(path):
        file_path = os.path.join(app.static_folder, path)
        if path and os.path.exists(file_path):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, 'index.html')

    return app
