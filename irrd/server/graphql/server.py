import time

from ariadne import ObjectType, gql, make_executable_schema, QueryType, \
    convert_kwargs_to_snake_case, UnionType, InterfaceType
from ariadne.asgi import GraphQL

from irrd.conf import config_init
from irrd.rpsl.rpsl_objects import OBJECT_CLASS_MAPPING, lookup_field_names, RPSLAsBlock
from irrd.server.query_resolver import QueryResolver
from irrd.storage.database_handler import DatabaseHandler
from irrd.storage.preload import Preloader

config_init('/Users/sasha/dev/irrd4/local_config.yaml')
dh = DatabaseHandler(readonly=True)
pl = Preloader(enable_queries=True)
# pl._load_routes_into_memory(None)
qr = QueryResolver('', '', pl, dh)


def to_camel_case(snake_str):
    components = snake_str.split('-')
    # We capitalize the first letter of each component except the first one
    # with the 'title' method and join them together.
    return components[0] + ''.join(x.title() for x in components[1:])


rpsl_query_params = lookup_field_names()
rpsl_query_params.add('rpslPk')
rpsl_query_params_str = ', '.join([to_camel_case(p) + ': String' for p in rpsl_query_params])

rpsl_object_schemas = ''
common_fields = None
for rpsl_object_class in OBJECT_CLASS_MAPPING.values():
    if common_fields is None:
        common_fields = set(rpsl_object_class.fields.keys())
    else:
        common_fields = common_fields.intersection(set(rpsl_object_class.fields.keys()))

common_fields.update({'rpslPk', 'objectClass', 'rpslText'})
rpsl_object_schemas += f'interface RPSLObject {{\n'
for name in common_fields:
    try:
        graphql_type = RPSLAsBlock.fields[name].graphql_type
    except KeyError:
        graphql_type = 'String'
    rpsl_object_schemas += f'  {to_camel_case(name)}: {graphql_type}\n'
rpsl_object_schemas += '}\n\n'

rpsl_object_schema_names = []
common_fields = None
for rpsl_object_class in OBJECT_CLASS_MAPPING.values():
    name = rpsl_object_class.__name__
    rpsl_object_schema_names.append(name)
    rpsl_object_schemas += f'type {name} implements RPSLObject {{\n'
    rpsl_object_schemas += f'  rpslPk: String\n'
    rpsl_object_schemas += f'  objectClass: String\n'
    rpsl_object_schemas += f'  rpslText: String\n'
    for name, field in rpsl_object_class.fields.items():
        rpsl_object_schemas += f'  {to_camel_case(name)}: {field.graphql_type}\n'
    for name in rpsl_object_class.field_extracts:
        rpsl_object_schemas += f'  {to_camel_case(name)}: String\n'
    rpsl_object_schemas += '}\n\n'


# Define types using Schema Definition Language (https://graphql.org/learn/schema/)
# Wrapping string in gql function provides validation and better error traceback
schema = f"""
    schema {{
      query: Query
    }}
    
    
    type Query {{
      rpslObjects({rpsl_query_params_str}): [RPSLObject]
      originated(origins: [Int]): [Originated]
    }}
    
    type Originated {{
        origin: Int
        prefixes: [String]
    }}
""" + rpsl_object_schemas
print(schema)

type_defs = gql(schema)
object_types = []

# Map resolver functions to Query fields using QueryType
query = QueryType()
object_types.append(query)

rpsl_object_type = InterfaceType("RPSLObject")
object_types.append(rpsl_object_type)
# rpsl_data_type = UnionType("RPSLData")
# object_types.append(rpsl_data_type)


@rpsl_object_type.type_resolver
def resolve_error_type(obj, *_):
    return OBJECT_CLASS_MAPPING[obj['objectClass']].__name__


@query.field("rpslObjects")
@convert_kwargs_to_snake_case
def resolve_query_rpsl_objects(_, info, **kwargs):
    print(info)
    print(kwargs)
    attribute, value = list(kwargs.items())[0]
    for row in qr.rpsl_attribute_search(attribute.replace('_', '-'), value):
        yield(dict(
            objectClass=row['object_class'],
            rpslPk=row['rpsl_pk'],
            prefix=row['parsed_data'][row['object_class']],
            descr='\n'.join(row['parsed_data'].get('descr', [])),
            origin=row['parsed_data'].get('origin'),
            mntBy=row['parsed_data'].get('mnt-by', []),
            remarks='\n'.join(row['parsed_data'].get('remarks', [])),
            source=row['source'],
            rpkiStatus=row['rpki_status'].name,
        ))


@query.field("originated")
def resolve_query_originated(_, info, origins):
    for origin in origins:
        yield dict(origin=origin, prefixes=list(qr.routes_for_origin(f'AS{origin}')))

for name in rpsl_object_schema_names:
    object_types.append(ObjectType(name))

object_types.append(ObjectType("Originated"))

# Create executable GraphQL schema
schema = make_executable_schema(type_defs, *object_types)


# Create an ASGI app using the schema, running in debug mode
app = GraphQL(schema, debug=True)

