import logging
from typing import Dict, List, Set, Tuple
from urllib.parse import urlsplit

from hdx.resource.changedetection.utilities import status_lookup
from hdx.utilities.dateparse import parse_date
from hdx.utilities.dictandlist import (
    dict_of_lists_add,
    list_distribute_contents,
)

logger = logging.getLogger(__name__)


class HeadResults:
    def __init__(
        self, results: Dict[str, Tuple], resources: Dict[str, Tuple]
    ) -> None:
        self.results = results
        self.resources = resources
        self._resources_to_get = {}
        self._resources_to_update = {}
        self._changes = {}
        self._netlocs = set()
        self._retrying = {}

    def process(self) -> None:
        for resource_id, result in self.results.items():
            what_changed = []
            resource = self.resources[resource_id]
            http_size, http_last_modified, etag, status = result
            if status != 200:
                if status in (403, 429):
                    # Server may not like HEAD requests or too many requests
                    self._resources_to_get[resource_id] = resource
                    status = str(status)
                    dict_of_lists_add(self._retrying, status, resource_id)
                what_changed = status_lookup.get(status, f"status {status}")
                dict_of_lists_add(self._changes, what_changed, resource_id)
                continue
            get_resource = False
            etag_unchanged = True
            if etag:
                if etag != resource[5]:
                    what_changed.append("etag")
                    etag_unchanged = False
            else:
                status = "no etag"
                what_changed.append(status)
                get_resource = True
            if http_size:
                if http_size != resource[3]:
                    status = "size"
                    what_changed.append(status)
                    if etag_unchanged:
                        get_resource = True
            else:
                what_changed.append("no size")
            if http_last_modified:
                http_last_modified = parse_date(http_last_modified)
                if http_last_modified != resource[4]:
                    status = "modified"
                    what_changed.append(status)
                    if etag_unchanged:
                        get_resource = True
            else:
                what_changed.append("no modified")
            what_changed = "|".join(what_changed)
            dict_of_lists_add(self._changes, what_changed, resource_id)
            if get_resource:
                self._resources_to_get[resource_id] = resource
                dict_of_lists_add(self._retrying, status, resource_id)
            if not etag_unchanged:
                self._resources_to_update[resource_id] = (
                    http_size,
                    http_last_modified,
                    etag,
                )

    def output(self) -> None:
        logger.info("\nChanges detected:")
        for what_changed, resource_ids in self._changes.items():
            count = len(resource_ids)
            if count < 5:
                resource_ids = ", ".join(resource_ids)
                logger.info(f"{what_changed}: {resource_ids}")
            else:
                logger.info(f"{what_changed}: {count}")
        logger.info("\nWill get these:")
        for status, resource_ids in self._retrying.items():
            count = len(resource_ids)
            if count < 5:
                resource_ids = ", ".join(resource_ids)
                logger.info(f"{status}: {resource_ids}")
            else:
                logger.info(f"{status}: {count}")

    def get_distributed_resources_to_get(self) -> List[Tuple]:
        def get_netloc(x):
            netloc = urlsplit(x[0]).netloc
            self._netlocs.add(netloc)
            return netloc

        return list_distribute_contents(
            list(self._resources_to_get.values()), get_netloc
        )

    def get_netlocs(self) -> Set[str]:
        return self._netlocs

    def get_resources_to_update(self) -> Dict[str, Tuple]:
        return self._resources_to_update
