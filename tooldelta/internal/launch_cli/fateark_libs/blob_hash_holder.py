from typing import Any


class FateArkBlobHashHolder:
    """BlobHashHolder-compatible facade backed by Jasmine's gRPC cache."""

    def __init__(self, core_conn: Any) -> None:
        self._core = core_conn

    def is_server(self) -> bool:
        return False

    def is_disk_holder(self) -> bool:
        return False

    def wait_login_sequence_down(self) -> None:
        return None

    def load_blob_cache(self, blob_hash: int) -> bytes:
        return self._core.load_blob_cache(blob_hash)

    def update_blob_cache(self, blob_hash: int, payload: bytes) -> bool:
        return self._core.update_blob_cache(blob_hash, payload)

    def get_client_function(self) -> "FateArkBlobHashHolder":
        return self

    def get_hash_payload(self, hashes: list[Any]) -> dict[Any, bytes]:
        result: dict[Any, bytes] = {}
        for hash_with_position in hashes:
            payload = self.load_blob_cache(hash_with_position.hash)
            if payload:
                result[hash_with_position] = payload
        return result

    def query_disk_hash_exist(self, hashes: list[Any]) -> tuple[list[Any], list[Any]]:
        hit: list[Any] = []
        miss: list[Any] = []
        for hash_with_position in hashes:
            target = hit if self.load_blob_cache(hash_with_position.hash) else miss
            target.append(hash_with_position)
        return hit, miss

    def set_holder_request(self) -> bool:
        return False

    def as_server_side(self) -> None:
        return None

