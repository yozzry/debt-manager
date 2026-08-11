import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    threads = int(os.environ.get('THREADS', 4))

    app.logger.info('Debt Manager starting in PRODUCTION mode')

    from waitress import serve
    app.logger.info(f'Debt Manager - Production Server | http://{host}:{port} | Threads: {threads}')
    serve(app, host=host, port=port, threads=threads, url_scheme='http')
