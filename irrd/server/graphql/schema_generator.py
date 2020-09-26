from collections import OrderedDict, defaultdict
from typing import Optional, Dict, Tuple

import ariadne

from irrd.rpki.status import RPKIStatus
from irrd.rpsl.fields import RPSLFieldListMixin
from irrd.rpsl.rpsl_objects import lookup_field_names, OBJECT_CLASS_MAPPING, RPSLAsBlock, \
    RPSLAutNum, RPSLInetRtr, RPSLPerson, RPSLRole
from irrd.scopefilter.status import ScopeFilterStatus
from irrd.utils.text import to_camel_case


class SchemaGenerator:
    def __init__(self):
        self._set_rpsl_query_fields()
        self._set_rpsl_object_interface_schema()
        self._set_rpsl_contact_schema()
        self._set_rpsl_object_schemas()
        self._set_enums()

        schema = self.enums
        schema += """
            scalar ASN
            scalar IP

            schema {
              query: Query
            }

            type Query {
              rpslObjects(""" + self.rpsl_query_fields + """): [RPSLObject!]
              databaseStatus(sources: [String!]): [DatabaseStatus]
              asnPrefixes(asns: [Int!]!, sources: [String!]): [ASNPrefixes]
              asSetPrefixes(setNames: [String!]!, sources: [String!], ipVersion: Int, sqlTrace: Boolean): [AsSetPrefixes!]
              recursiveSetMembers(setNames: [String!]!, sources: [String!], sqlTrace: Boolean): [SetMembers!]
            }

            type DatabaseStatus {
                source: String!
                authoritative: Boolean!
                object_class_filter: [String!]
                rpki_rov_filter: Boolean!
                scopefilter_enabled: Boolean!
                local_journal_kept: Boolean!
                serial_oldest_journal: Int
                serial_newest_journal: Int
                serial_last_export: Int
                serial_newest_mirror: Int
                last_update: String
                synchronised_serials: Boolean!
            }

            type RPSLJournalEntry {
                rpslPk: String!
                source: String!
                serialNrtm: Int!
                operation: String!
                origin: String
                objectClass: String!
                objectText: String!
                timestamp: String!
            }

            type ASNPrefixes {
                asn: Int!
                prefixes: [IP!]
            }

            type AsSetPrefixes {
                rpslPk: String!
                prefixes: [IP!]
            }

            type SetMembers {
                rpslPk: String!
                members: [String!]
            }
        """
        schema += self.rpsl_object_interface_schema
        schema += self.rpsl_contact_schema
        schema += ''.join(self.rpsl_object_schemas.values())
        schema += 'union RPSLContactUnion = RPSLPerson | RPSLRole'
        print(schema)

        self.type_defs = ariadne.gql(schema)

        self.object_types = []
        self.query_type = ariadne.QueryType()
        self.object_types.append(self.query_type)
        self.rpsl_object_type = ariadne.InterfaceType("RPSLObject")
        self.object_types.append(self.rpsl_object_type)
        self.rpsl_contact_union_type = ariadne.UnionType("RPSLContactUnion")
        self.object_types.append(self.rpsl_contact_union_type)
        self.asn_scalar_type = ariadne.ScalarType("ASN")
        self.object_types.append(self.asn_scalar_type)
        self.ip_scalar_type = ariadne.ScalarType("IP")
        self.object_types.append(self.ip_scalar_type)

        for name in self.rpsl_object_schemas.keys():
            self.object_types.append(ariadne.ObjectType(name))

        self.object_types.append(ariadne.ObjectType("ASNPrefixes"))
        self.object_types.append(ariadne.ObjectType("AsSetPrefixes"))
        self.object_types.append(ariadne.ObjectType("SetMembers"))
        self.object_types.append(ariadne.EnumType("RPKIStatus", RPKIStatus))
        self.object_types.append(ariadne.EnumType("ScopeFilterStatus", ScopeFilterStatus))

    def _set_rpsl_query_fields(self):
        string_list_fields = {'rpsl_pk', 'sources', 'object_class'}.union(lookup_field_names())
        params = [to_camel_case(p) + ': [String!]' for p in string_list_fields]
        params += [
            'ipExact: IP',
            'ipLessSpecific: IP',
            'ipLessSpecificOneLevel: IP',
            'ipMoreSpecific: IP',
            'asns: [ASN!]',
            'rpkiStatus: [RPKIStatus!]',
            'scopeFilterStatus: [ScopeFilterStatus!]',
            'textSearch: String',
            'sqlTrace: Boolean',
        ]
        self.rpsl_query_fields = ', '.join(params)

    def _set_enums(self):
        self.enums = ''
        for enum in [RPKIStatus, ScopeFilterStatus]:
            self.enums += f'enum {enum.__name__} {{\n'
            for value in enum:
                self.enums += f'    {value.name}\n'
            self.enums += '}\n\n'

    def _set_rpsl_object_interface_schema(self):
        common_fields = None
        for rpsl_object_class in OBJECT_CLASS_MAPPING.values():
            if common_fields is None:
                common_fields = set(rpsl_object_class.fields.keys())
            else:
                common_fields = common_fields.intersection(set(rpsl_object_class.fields.keys()))
        common_fields = list(common_fields)
        common_fields = ['rpslPk', 'objectClass', 'objectText', 'updated'] + common_fields
        common_field_dict = OrderedDict()
        for field_name in common_fields:
            try:
                # These fields are present in every object, so this is a safe check
                rpsl_field = RPSLAsBlock.fields[field_name]
                graphql_type = self._graphql_type_for_rpsl_field(rpsl_field)

                reference_name, reference_type = self._grapql_type_for_reference_field(field_name, rpsl_field)
                if reference_name and reference_type:
                    common_field_dict[reference_name] = reference_type
            except KeyError:
                graphql_type = 'String'
            common_field_dict[to_camel_case(field_name)] = graphql_type
        common_field_dict['journal'] = '[RPSLJournalEntry]'
        schema = self._generate_schema_str('RPSLObject', 'interface', common_field_dict)
        self.rpsl_object_interface_schema = schema

    def _set_rpsl_contact_schema(self):
        common_fields = set(RPSLPerson.fields.keys()).intersection(set(RPSLRole.fields.keys()))
        common_fields = common_fields.union({'rpslPk', 'objectClass', 'objectText', 'updated'})
        common_field_dict = OrderedDict()
        for field_name in common_fields:
            try:
                # These fields are present in both objects, so this is a safe check
                rpsl_field = RPSLPerson.fields[field_name]
                graphql_type = self._graphql_type_for_rpsl_field(rpsl_field)

                reference_name, reference_type = self._grapql_type_for_reference_field(field_name, rpsl_field)
                if reference_name and reference_type:
                    common_field_dict[reference_name] = reference_type
            except KeyError:
                graphql_type = 'String'
            common_field_dict[to_camel_case(field_name)] = graphql_type
        schema = self._generate_schema_str('RPSLContact', 'interface', common_field_dict)
        self.rpsl_contact_schema = schema

    def _set_rpsl_object_schemas(self):
        self.graphql_types = defaultdict(dict)
        schemas = OrderedDict()
        for object_class, klass in OBJECT_CLASS_MAPPING.items():
            object_name = klass.__name__
            graphql_fields = OrderedDict()
            graphql_fields['rpslPk'] = 'String'
            graphql_fields['objectClass'] = 'String'
            graphql_fields['objectText'] = 'String'
            graphql_fields['updated'] = 'String'
            graphql_fields['journal'] = '[RPSLJournalEntry]'
            for name, field in klass.fields.items():
                graphql_type = self._graphql_type_for_rpsl_field(field)
                graphql_fields[to_camel_case(name)] = graphql_type
                self.graphql_types[to_camel_case(object_name)][name] = graphql_type

                reference_name, reference_type = self._grapql_type_for_reference_field(name, field)
                if reference_name and reference_type:
                    graphql_fields[reference_name] = reference_type
                    self.graphql_types[object_name][reference_name] = reference_type

            for name in klass.field_extracts:
                if name.startswith('asn'):
                    graphql_type = 'ASN'
                elif name == 'prefix':
                    graphql_type = 'IP'
                elif name == 'prefix_length':
                    graphql_type = 'Int'
                else:
                    graphql_type = 'String'
                graphql_fields[to_camel_case(name)] = graphql_type
            if klass.rpki_relevant:
                graphql_fields['rpkiStatus'] = 'String'
            implements = 'RPSLContact & RPSLObject' if klass in [RPSLPerson, RPSLRole] else 'RPSLObject'
            schema = self._generate_schema_str(object_name, 'type', graphql_fields, implements)
            schemas[object_name] = schema
        self.rpsl_object_schemas = schemas

    def _graphql_type_for_rpsl_field(self, field) -> str:
        if RPSLFieldListMixin in field.__class__.__bases__ or field.multiple:
            return '[String!]'
        return 'String'

    def _grapql_type_for_reference_field(self, field_name: str, rpsl_field) -> Tuple[Optional[str], Optional[str]]:
        if getattr(rpsl_field, 'referring', None):
            rpsl_field.resolve_references()
            graphql_name = to_camel_case(field_name) + 'Objs'
            grapql_referring = set(rpsl_field.referring_object_classes)
            if RPSLAutNum in grapql_referring:
                grapql_referring.remove(RPSLAutNum)
            if RPSLInetRtr in grapql_referring:
                grapql_referring.remove(RPSLInetRtr)
            if grapql_referring == {RPSLPerson, RPSLRole}:
                graphql_type = '[RPSLContactUnion!]'
            else:
                graphql_type = '[' + grapql_referring.pop().__name__ + '!]'
            return graphql_name, graphql_type
        return None, None

    def _generate_schema_str(self, name: str, graphql_type: str, fields: Dict[str, str], implements: Optional[str]=None) -> str:
        schema = f'{graphql_type} {name} '
        if implements:
            schema += f'implements {implements} '
        schema += '{\n'

        for field, field_type in fields.items():
            schema += f'  {field}: {field_type}\n'
        schema += '}\n\n'
        return schema
