#!/usr/bin/env python3
import asyncio
from abc import ABC, abstractmethod
from json import dump, load, JSONDecodeError
from threading import Thread
from typing import Any, Dict, List

from okta.client import Client as OktaClient

from . import LOGGER


class OktaCache(ABC):
    """
    Base Class for building caching classes. It implements the bare bones needed to create a pluggable caching system
    """

    def __init__(
        self,
        *,
        refresh_interval: int = 300,
        persist: bool = True,
        threaded: bool = True,
    ):
        #: Whether or not to start a refresh look in another thread
        self.threaded = threaded

        self.__set_status("Waiting to start")
        #: Whether or not to call self.persist_cache on every update and at termination
        self.persist: bool = persist
        #: How long to wait between iterations of fetching new data
        self.refresh_interval = refresh_interval

        self.__use_async_group_cache = asyncio.iscoroutinefunction(
            self.load_group_cache
        )
        self.__use_async_rule_cache = asyncio.iscoroutinefunction(self.load_rule_cache)

        if self.__use_async_rule_cache != self.__use_async_group_cache:
            raise TypeError(
                "You all chache loaders must be async or non async. You cannot mix and match"
            )
        self.log_configuration()

        self.rules = []
        self.groups = {}

    @property
    def status(self) -> str:
        """
        Returns one of the following:
            * Waiting to start
            * Running
            * Terminating
            * Terminated
            * Complete
        """
        return self.__status

    def log_configuration(self) -> None:
        """Log some useful info about our configuration"""

        msg = f"Loaded cache class {self.__class__.__name__}"
        if self.persist:
            msg += " with persistance enabled."
        else:
            msg += " without persistance"

        LOGGER.info(msg)
        LOGGER.info(f"Cache refresh set to {self.refresh_interval} seconds")

        if self.use_async:
            LOGGER.info(f"Using Async handlers for caching")

    @property
    def use_async(self) -> bool:
        """
        Returns whether self.group_loader and self.rule_loader are async or not
        """
        return self.__use_async_group_cache

    @property
    def use_async_persist(self) -> bool:
        """
        Returns whether or not self.persist_cache is async
        """
        return asyncio.iscoroutinefunction(self.persist_cache)

    async def terminate(self) -> None:
        """Stops self.run"""

        self.__set_status("Terminating")

    async def __persist_cache(self) -> None:
        if self.use_async_persist:
            await self.persist_cache()
        else:
            self.persist_cache()

    async def start(self):
        if self.threaded:
            thread = Thread(target=lambda: asyncio.run(self.__start()))
            thread.start()
        else:
            await self.__start()

    async def __start(self) -> None:
        """
        Loops over self.group_loader() and self.rule_loader() at self.refresh_interval until
        self.terminate() is called
        """
        self.__set_status("Running")

        await self.__load_group_cache()
        await self.__load_rule_cache()

        if not self.threaded:
            self.__set_status("Complete")
            return

        i = 0

        while True:
            while i <= self.refresh_interval:
                if self.status in ("Terminating", "Complete"):
                    if self.persist:
                        await self.__persist_cache()
                    self.__set_status("Terminated")
                    return
                i += 0.25
                await asyncio.sleep(0.25)
            try:
                await self.__load_group_cache()
            except Exception as e:
                LOGGER.exception(e)

            if self.status in ("Terminated", "Complete"):
                return

            try:
                await self.__load_rule_cache()
            except Exception as e:
                LOGGER.exception(e)

            LOGGER.debug("Cache reloaded")

            if self.persist:
                await self.__persist_cache()

            i = 0

    def __set_status(self, status):
        allowed_statuses = [
            "Waiting to start",
            "Running",
            "Terminating",
            "Terminated",
            "Complete",
        ]
        if status not in allowed_statuses:
            raise ValueError(f"Status must be one of {','.join(allowed_statuses)}.")

        self.__status = status
        LOGGER.info(f"Cache status changed to {self.status}")

        return self.status

    async def __load_group_cache(self) -> None:
        if self.use_async:
            self.groups = await self.load_group_cache()
        else:
            self.groups = self.load_group_cache()

    async def __load_rule_cache(self) -> None:
        if self.use_async:
            self.rules = await self.load_rule_cache()
        else:
            self.rules = self.load_rule_cache()

    @abstractmethod
    def load_group_cache(self) -> None:
        """
        Abstract method that child classes must implement. It must receive no arguments and
        should update self.groups with fresh data.
        """
        pass

    @abstractmethod
    def load_rule_cache(self) -> None:
        """
        Abstract method that child classes must implement. It must receive no arguments and
        should update self.rules with fresh data.
        """

        pass

    async def persist_cache(self) -> None:
        """
        Abstract method that child classes should implement if they desire to persist data externally
        between refresh intervals and/or after the cache has terminated.
        """
        pass


class OktaApiCache(OktaCache):
    """
    Provides a base class for caches that will fetch their data from the Okta API.
    """

    def __init__(
        self,
        *,
        okta_client: OktaClient,
        **kwargs: Dict[str, Any],
    ):
        #: A client, from the okta.client in the okta python library, used to make API calls to Okta
        self.okta_client: OktaClient = okta_client
        super().__init__(**kwargs)

    async def load_rule_cache(self) -> List[Dict[str, Any]]:
        """
        Loads all group rules via the Okta API.
        """
        res = await self._do_query(self.okta_client.list_group_rules)
        rules = [x.as_dict() for x in res]
        return rules

    async def load_group_cache(self) -> Dict[str, Any]:
        """
        Loads all groups via the Okta API.
        """
        res = await self._do_query(self.okta_client.list_groups)
        groups = {x.id: x.as_dict() for x in res}
        return groups

    async def _do_query(self, action, params={}):
        """
        Handles executing CRUD and aggregating results from pagination
        using the Okta API client.
        """
        items = []
        res, pager, _ = await action(params)
        items += res

        if pager.has_next():
            groups, _ = await pager.next()
            items += groups

        while pager.has_next():
            groups, _ = await pager.next()
            items += groups

        return items


class OktaFileCache(OktaApiCache):
    """
    Provides basic caching and persistance using JSON files on disk.
    """

    def __init__(
        self,
        *args,
        groups_file: str = "groups.json",
        rules_file: str = "rules.json",
        **kwargs: Dict[str, Any],
    ):
        #: The file that rule data will be peristed to
        self.rules_file: str = rules_file

        #: The file that group data will be persisted to
        self.groups_file: str = groups_file

        super().__init__(*args, **kwargs)

        try:
            with open(self.groups_file, "r") as f:
                self.groups = load(f)
        except JSONDecodeError as e:
            LOGGER.exception(e)
        except FileNotFoundError:
            with open(self.groups_file, "w+") as f:
                dump({}, f)

        try:
            with open(self.rules_file, "r") as f:
                self.rules = load(f)
        except JSONDecodeError as e:
            LOGGER.exception(e)
        except FileNotFoundError:
            with open(self.groups_file, "w+") as f:
                dump([], f)

    def persist_cache(self) -> None:
        """
        Writes group and rule data to disk in JSON files
        """
        with open(self.groups_file, "w+") as f:
            dump(self.groups, f)

        with open(self.rules_file, "w+") as f:
            dump(self.rules, f)
