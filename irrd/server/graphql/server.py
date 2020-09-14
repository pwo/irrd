import functools

import graphene

from irrd.conf import config_init
from irrd.rpki.status import RPKIStatus
from irrd.server.query_resolver import QueryResolver
from irrd.storage.database_handler import DatabaseHandler
from irrd.storage.preload import Preloader

import time

class RPSLRoute(graphene.ObjectType):
    prefix = graphene.String()
    origin = graphene.String()
    descr = graphene.String()
    remarks = graphene.String()
    mnt_by = graphene.List(graphene.String)
    source = graphene.String()
    rpki_status = graphene.Field(graphene.Enum.from_enum(RPKIStatus))

config_init('/Users/sasha/dev/irrd4/local_config.yaml')
dh = DatabaseHandler(readonly=True)
pl = Preloader(enable_queries=True)
qr = QueryResolver('', '', pl, dh)

class RPSLQuery(graphene.ObjectType):
    # this defines a Field `hello` in our Schema with a single Argument `name`
    route = graphene.List(of_type=RPSLRoute, origin=graphene.Int())

    # our Resolver method takes the GraphQL context (root, info) as well as
    # Argument (name) for the Field and returns data for the query Response
    def resolve_route(root, info, origin):
        start = time.perf_counter()
        a = []
        # for row in qr.rpsl_attribute_search('origin', f'AS{origin}'):
        #     a.append( RPSLRoute(
        #         prefix=row['parsed_data'][row['object_class']],
        #         descr='\n'.join(row['parsed_data'].get('descr', [])),
        #         origin=row['parsed_data']['origin'],
        #         mnt_by=row['parsed_data'].get('mnt-by', []),
        #         remarks='\n'.join(row['parsed_data'].get('remarks', [])),
        #         source=row['source'],
        #         rpki_status=row['rpki_status'],
        #     ))
        for i in range(10000):
            a.append( RPSLRoute(
            ))
        print(f'Local Q time: {1000*(time.perf_counter()-start)} for {len(a)} results')
        return a

# class RPSLObjects(graphene.ObjectType):
#     objects = graphene.List(RPSLRoute)

schema = graphene.Schema(RPSLQuery)

# we can query for our field (with the default argument)
# query_string = '{ hello }'
# result = schema.execute(query_string)
# print(result.data['hello'])
# "Hello stranger!"

# or passing the argument in the query
# query_with_argument = '{ hello(name: "GraphQL") }'
# result = schema.execute(query_with_argument)
# print(result.data['hello'])
# "Hello GraphQL!"


from flask import Flask
from flask_graphql import GraphQLView

app = Flask(__name__)
app.debug = True

app.add_url_rule(
    '/graphql',
    view_func=GraphQLView.as_view(
        'graphql',
        schema=schema,
        graphiql=True
    )
)

if __name__ == '__main__':
    app.run()
