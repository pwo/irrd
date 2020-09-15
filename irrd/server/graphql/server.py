import time

from ariadne import ObjectType, QueryType, gql, make_executable_schema
from ariadne.asgi import GraphQL

from irrd.conf import config_init
from irrd.server.query_resolver import QueryResolver
from irrd.storage.database_handler import DatabaseHandler
from irrd.storage.preload import Preloader

config_init('/Users/sasha/dev/irrd4/local_config.yaml')
dh = DatabaseHandler(readonly=True)
pl = Preloader(enable_queries=True)
qr = QueryResolver('', '', pl, dh)

# Define types using Schema Definition Language (https://graphql.org/learn/schema/)
# Wrapping string in gql function provides validation and better error traceback
type_defs = gql("""
    schema {
      query: RPSLQuery
    }
    

    
    type RPSLQuery {
      route(origin: Int): [RPSLRoute]
    }
    
    type RPSLRoute {
      prefix: String
      origin: String
      descr: String
      remarks: String
      mntBy: [String]
      source: String
      rpkiStatus: String
    }
""")

# Map resolver functions to Query fields using QueryType
rpsl_query = ObjectType("RPSLQuery")


@rpsl_query.field("route")
def resolve_query_route(_, info, origin):
    for row in qr.rpsl_attribute_search('origin', f'AS{origin}'):
        yield(dict(
            prefix=row['parsed_data'][row['object_class']],
            descr='\n'.join(row['parsed_data'].get('descr', [])),
            origin=row['parsed_data']['origin'],
            mntBy=row['parsed_data'].get('mnt-by', []),
            remarks='\n'.join(row['parsed_data'].get('remarks', [])),
            source=row['source'],
            rpkiStatus=row['rpki_status'].name,
        ))
        yield(dict(
            prefix=row['parsed_data'][row['object_class']],
            descr='\n'.join(row['parsed_data'].get('descr', [])),
            origin=row['parsed_data']['origin'],
            mntBy=row['parsed_data'].get('mnt-by', []),
            remarks='\n'.join(row['parsed_data'].get('remarks', [])),
            source=row['source'],
            rpkiStatus=row['rpki_status'].name,
        ))


# Map resolver functions to custom type fields using ObjectType
rpsl_route = ObjectType("RPSLRoute")

# Create executable GraphQL schema
schema = make_executable_schema(type_defs, rpsl_query, rpsl_route)

# Create an ASGI app using the schema, running in debug mode
app = GraphQL(schema, debug=True)
