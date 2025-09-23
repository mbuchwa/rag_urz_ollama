#!/usr/bin/env python3

import logging
from chatbot.server import create_app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    loop = app.config['APP_LOOP']
    try:
        app.run(host='0.0.0.0', port=7000, debug=False, use_reloader=False)
    finally:
        loop.close()
