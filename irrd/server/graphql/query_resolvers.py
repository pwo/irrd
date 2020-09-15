import time
import traceback
from typing import Optional, Any, Dict, List

from graphql import ResolveInfo
from tartiflette import Resolver

# from irrd.conf import config_init
# from irrd.server.query_resolver import QueryResolver
# from irrd.storage.database_handler import DatabaseHandler
# from irrd.storage.preload import Preloader
#
# config_init('/Users/sasha/dev/irrd4/local_config.yaml')
# dh = DatabaseHandler(readonly=True)
# pl = Preloader(enable_queries=True)
# qr = QueryResolver('', '', pl, dh)


@Resolver("RPSLQuery.route")
async def resolve_query_route(
    parent: Optional[Any],
    args: Dict[str, Any],
    ctx: Dict[str, Any],
    info: "ResolveInfo",
) -> Optional[List[Dict[str, Any]]]:
    start = time.perf_counter()
    print(parent)
    print(args)
    print(ctx)
    print(info)
    a = []
    for i in range(10000):
        a.append({
            'prefix': '5'
        })
    print(f'Local Q time: {1000*(time.perf_counter()-start)} for {len(a)} results')
    return a
