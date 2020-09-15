from collections import OrderedDict, defaultdict
from typing import Optional, Dict

import ariadne

from irrd.rpsl.fields import RPSLFieldListMixin
from irrd.rpsl.rpsl_objects import lookup_field_names, OBJECT_CLASS_MAPPING, RPSLAsBlock
from irrd.utils.text import to_camel_case


class SchemaGenerator:
    def __init__(self):
        self._set_lookup_params()
        self._set_rpsl_object_interface_schema()
        self._set_rpsl_object_schemas()

        schema = f"""
            scalar ASN

            schema {{
              query: Query
            }}


            type Query {{
              databaseStatus(source: [String]): [DatabaseStatus]
              rpslObjects({self.lookup_params}): [RPSLObject]
              originated(origins: [Int]): [Originated]
            }}

            type DatabaseStatus {{
                source: String
                authoritative: Boolean
                object_class_filter: [String]
                rpki_rov_filter: Boolean
                scopefilter_enabled: Boolean
                local_journal_kept: Boolean
                serial_oldest_journal: Int
                serial_newest_journal: Int
                serial_last_export: Int
                serial_newest_mirror: Int
                last_update: String
                synchronised_serials: Boolean
            }}           

            type Originated {{
                origin: Int
                prefixes: [String]
            }}
        """
        schema += self.rpsl_object_interface_schema
        schema += ''.join(self.rpsl_object_schemas.values())

        self.type_defs = ariadne.gql(schema)

        self.object_types = []
        self.query_type = ariadne.QueryType()
        self.object_types.append(self.query_type)
        self.rpsl_object_type = ariadne.InterfaceType("RPSLObject")
        self.object_types.append(self.rpsl_object_type)
        # rpsl_data_type = UnionType("RPSLData")
        # object_types.append(rpsl_data_type)

        for name in self.rpsl_object_schemas.keys():
            self.object_types.append(ariadne.ObjectType(name))

        self.object_types.append(ariadne.ObjectType("Originated"))

    def _set_lookup_params(self):
        params = lookup_field_names()
        params.update({'rpslPK', 'sources', 'objectClass'})
        self.lookup_params = ', '.join([to_camel_case(p) + ': [String]' for p in params])

    def _set_rpsl_object_interface_schema(self):
        common_fields = None
        for rpsl_object_class in OBJECT_CLASS_MAPPING.values():
            if common_fields is None:
                common_fields = set(rpsl_object_class.fields.keys())
            else:
                common_fields = common_fields.intersection(set(rpsl_object_class.fields.keys()))
        common_fields = list(common_fields)
        common_fields = ['rpslPk', 'objectClass', 'rpslText', 'updated'] + common_fields
        common_field_dict = OrderedDict()
        for field in common_fields:
            try:
                # These fields are present in every object, so this is a safe check
                graphql_type = self._graphql_type_for_rpsl_field(RPSLAsBlock.fields[field])
            except KeyError:
                graphql_type = 'String'
            common_field_dict[to_camel_case(field)] = graphql_type
        schema = self._generate_schema_str('RPSLObject', 'interface', common_field_dict)
        self.rpsl_object_interface_schema = schema

    def _set_rpsl_object_schemas(self):
        self.graphql_types = defaultdict(dict)
        schemas = OrderedDict()
        for object_class, klass in OBJECT_CLASS_MAPPING.items():
            object_name = klass.__name__
            fields = OrderedDict()
            fields['rpslPk'] = 'String'
            fields['objectClass'] = 'String'
            fields['rpslText'] = 'String'
            fields['updated'] = 'String'
            for name, field in klass.fields.items():
                graphql_type = self._graphql_type_for_rpsl_field(field)
                fields[to_camel_case(name)] = graphql_type
                self.graphql_types[object_class][name] = graphql_type
            for name in klass.field_extracts:
                graphql_type = 'ASN' if name.startswith('asn') else 'String'
                fields[to_camel_case(name)] = graphql_type
            if klass.rpki_relevant:
                fields['rpkiStatus'] = 'String'

            schema = self._generate_schema_str(object_name, 'type', fields, 'RPSLObject')
            schemas[object_name] = schema
        self.rpsl_object_schemas = schemas

    def _graphql_type_for_rpsl_field(self, field) -> str:
        if RPSLFieldListMixin in field.__class__.__bases__:
            return '[String]'
        return 'String'

    def _generate_schema_str(self, name: str, graphql_type: str, fields: Dict[str, str], implements: Optional[str]=None) -> str:
        schema = f'{graphql_type} {name} '
        if implements:
            schema += f'implements {implements} '
        schema += '{\n'

        for field, field_type in fields.items():
            schema += f'  {field}: {field_type}\n'
        schema += '}\n\n'
        return schema




