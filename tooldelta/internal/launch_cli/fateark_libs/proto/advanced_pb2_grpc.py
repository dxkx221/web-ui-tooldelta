import grpc

from . import advanced_pb2 as advanced__pb2
from . import response_pb2 as response__pb2


class AdvancedServiceStub:
    def __init__(self, channel: grpc.Channel):
        self.LoadBlobCache = channel.unary_unary(
            "/fateark.proto.advanced.AdvancedService/LoadBlobCache",
            request_serializer=advanced__pb2.LoadBlobCacheRequest.SerializeToString,
            response_deserializer=advanced__pb2.BlobCacheResponse.FromString,
        )
        self.UpdateBlobCache = channel.unary_unary(
            "/fateark.proto.advanced.AdvancedService/UpdateBlobCache",
            request_serializer=advanced__pb2.UpdateBlobCacheRequest.SerializeToString,
            response_deserializer=response__pb2.GeneralResponse.FromString,
        )

