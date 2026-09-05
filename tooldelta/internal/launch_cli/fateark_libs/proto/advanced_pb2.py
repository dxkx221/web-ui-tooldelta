# -*- coding: utf-8 -*-
"""Minimal protobuf definitions for Jasmine's legacy AdvancedService."""

from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf.internal import builder as _builder


def _field(message, name, number, field_type):
    value = message.field.add()
    value.name = name
    value.number = number
    value.label = _descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    value.type = field_type


_file = _descriptor_pb2.FileDescriptorProto()
_file.name = "advanced.proto"
_file.package = "fateark.proto.advanced"
_file.syntax = "proto3"

_load = _file.message_type.add()
_load.name = "LoadBlobCacheRequest"
_field(_load, "hash", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_UINT64)

_response = _file.message_type.add()
_response.name = "BlobCacheResponse"
_field(_response, "status", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_INT32)
_field(_response, "payload", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_BYTES)
_field(_response, "found", 3, _descriptor_pb2.FieldDescriptorProto.TYPE_BOOL)
_field(_response, "error_msg", 4, _descriptor_pb2.FieldDescriptorProto.TYPE_STRING)

_update = _file.message_type.add()
_update.name = "UpdateBlobCacheRequest"
_field(_update, "hash", 1, _descriptor_pb2.FieldDescriptorProto.TYPE_UINT64)
_field(_update, "payload", 2, _descriptor_pb2.FieldDescriptorProto.TYPE_BYTES)

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(_file.SerializeToString())
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, __name__, globals())

