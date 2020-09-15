import os

from aiohttp import web
from tartiflette_aiohttp import register_graphql_handlers

def run() -> None:
    """
    Entry point of the application.
    """
    web.run_app(
        register_graphql_handlers(
            app=web.Application(),
            engine_sdl=os.path.dirname(os.path.abspath(__file__)) + "/",
            engine_modules=[
                "irrd.server.graphql.query_resolvers",
            ],
            executor_http_endpoint="/graphql",
            executor_http_methods=["POST"],
            graphiql_enabled=True,
            subscription_ws_endpoint="/ws",
        ),
        host='127.0.0.1',
        port=8000,
    )

if __name__ == '__main__':
    run()
