#!/usr/bin/env python3
import asyncio
from abc import abstractmethod, ABC
from json import dump, load
from re import compile
from threading import RLock, Thread
from typing import Any, Dict, List

from boto3.session import Session
from pydot import Node

from . import LOGGER


class NodePlugin(ABC):
    def __init__(self, threaded: bool = True, refresh_interval: int = 180):
        self.threaded = threaded
        self.refresh_interval = refresh_interval
        self.__use_async = asyncio.iscoroutinefunction(self.make_node)
        self.__use_async_loader = asyncio.iscoroutinefunction(self.load)

    @abstractmethod
    async def make_node(self, data: Dict, node: Node) -> Node:
        """
        Accepts a dictionary containing the info that was used to create the node and the node itself.
        Must return a Node with the name unchanged
        """
        pass

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

    @property
    def use_async(self) -> bool:
        """
        Returns whether self.start() will run in a background thread in a loop
        """
        return self.__use_async

    @property
    def use_async_loader(self) -> bool:
        """
        Returns whether self.start() will run in a background thread in a loop
        """
        return self.__use_async_loader

    async def terminate(self) -> None:
        """Stops self.run"""

        self.__set_status("Terminating")

    @abstractmethod
    async def load(self) -> Any:
        """
        Handles any bootstrapping or dataloading that needs to be done when the plugin is
        first initialized. If self.threaded == True then it will be called on an interval set
        by self.refresh_interval
        """
        pass

    async def start(self):
        if self.threaded:
            thread = Thread(target=lambda: asyncio.run(self.__start()))
            thread.start()
        else:
            await self.__start()

    async def __start(self) -> None:
        """
        Loops over self.load() if self.treaded, otherwise runs it once
        """
        self.__set_status("Running")
        LOGGER.debug(f"Started Node plugin {self.__class__.__name__}")

        if self.use_async_loader:
            await self.load()
        else:
            await self.load()
        LOGGER.debug("Node plugin finished loading data")

        if not self.threaded:
            self.__set_status("Complete")
            return

        i = 0

        while True:
            while i <= self.refresh_interval:
                if self.status == "Terminating":
                    self.__set_status("Terminated")
                    return
                i += 0.25
                await asyncio.sleep(0.25)

            try:
                if self.use_async_loader:
                    await self.load()
                else:
                    self.load()
            except Exception as e:
                LOGGER.exception(e)
            LOGGER.info("Node plugin reload complete")
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
        LOGGER.info(f"Node plugin status changed to {self.status}")

        return self.status


class NullNodePlugin(NodePlugin):
    """
    Does nothing. Used as default.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, threaded=False, **kwargs)

    async def load(self):
        pass

    async def make_node(self, _, node: Node) -> Node:
        return node


class AWSNodePlugin(NodePlugin):
    def __init__(
        self,
        *args,
        dev_mode: bool = False,
        icon_dir: str = "",
        identitystore_id: str,
        sso_instance_arn: str,
        **kwargs,
    ):
        #: If True then data will be peristed to json files and read again on startup
        self.dev_mode = dev_mode
        self.boto_session = Session()
        self.sso = self.boto_session.client("sso-admin")
        self.idstore = self.boto_session.client("identitystore")
        self.org = self.boto_session.client("organizations")
        self.identitystore_id = identitystore_id
        self.sso_instance_arn = sso_instance_arn
        self.rlock = RLock()
        self.__aws_accounts = {}
        self.__aws_groups = {}
        self.__permission_sets = {}
        self.__assignments = {}
        self.group_re = compile(r"\(|\)|-|\s\:")
        self.icon_dir = icon_dir
        self.initialized = False
        super().__init__(*args, **kwargs)

    async def load(self):
        if self.dev_mode and not self.initialized:
            self.load_from_file()

        accounts = {x["Id"]: x["Name"] for x in self.org.list_accounts()["Accounts"]}
        groups = await self.get_aws_groups()
        ps = await self.get_permission_sets()

        with self.rlock:
            self.__aws_accounts = accounts
            self.__permission_sets = ps
            self.__aws_groups = groups

        assignments = {}
        for name, id in self.__aws_groups.items():
            assignments[name] = await self.get_assignments(id)

        with self.rlock:
            self.__assignments = assignments

        if self.dev_mode:
            self.persist_file()

        self.initialized = True

    def load_from_file(self):
        try:
            with open("aws_node_data.json", "r") as f:
                data = load(f)
                with self.rlock:
                    self.__aws_accounts = data["aws_accounts"]
                    self.__permission_sets = data["permission_sets"]
                    self.__aws_groups = data["aws_groups"]
                    self.__assignments = data["assignments"]
        except Exception:
            return

    def persist_file(self):
        data = {
            "aws_accounts": self.aws_accounts,
            "permission_sets": self.permission_sets,
            "aws_groups": self.aws_groups,
            "assignments": self.assignments,
        }
        with open("aws_node_data.json", "w+") as f:
            dump(data, f, indent=2)

    @property
    def aws_accounts(self):
        with self.rlock:
            return self.__aws_accounts

    @property
    def aws_groups(self):
        with self.rlock:
            return self.__aws_groups

    @property
    def permission_sets(self):
        with self.rlock:
            return self.__permission_sets

    @property
    def assignments(self):
        with self.rlock:
            return self.__assignments

    def make_aws_group_name(self, okta_group_name):
        return self.group_re.sub("_", okta_group_name)

    async def get_assignments(self, group_id):
        assignments = []
        res = self.sso.list_account_assignments_for_principal(
            InstanceArn=self.sso_instance_arn,
            PrincipalType="GROUP",
            PrincipalId=group_id,
            MaxResults=100,
        )["AccountAssignments"]

        for assignment in res:
            assignment["permissionset_name"] = self.permission_sets[
                assignment["PermissionSetArn"]
            ]
            assignment["account_name"] = self.aws_accounts[assignment["AccountId"]]
            assignments.append(assignment)

        return assignments

    async def get_permission_sets(self):
        res = self.sso.list_permission_sets(
            InstanceArn=self.sso_instance_arn, MaxResults=100
        )["PermissionSets"]
        return {x: await self.get_permissionset_name(x) for x in res}

    async def get_aws_groups(self, filters: List[Dict] = []):
        res = self.idstore.list_groups(
            IdentityStoreId=self.identitystore_id, Filters=filters, MaxResults=100
        )["Groups"]
        return {
            x["DisplayName"]: x["GroupId"]
            for x in res
            if x["DisplayName"].startswith("AWS_Role")
        }

    async def make_node(self, data, node):
        if not (data["type"] == "Okta Group" and data["name"].startswith("AWS_Role")):
            return node

        okta_group_name = data["name"]
        aws_group_name = self.make_aws_group_name(okta_group_name)
        aws_group_id = self.aws_groups.get(aws_group_name)

        if not aws_group_id:
            LOGGER.error(
                f"Could not find AWS group named {aws_group_name} for Okta group {okta_group_name}"
            )
            return node

        assignments = self.assignments[aws_group_name]

        res = {}

        for assignment in assignments:
            key = f'{assignment["account_name"]} ({assignment["AccountId"]})'
            if key not in res:
                res[key] = []
            res[key] += list(
                set(
                    [
                        x["permissionset_name"]
                        for x in assignments
                        if x["AccountId"] == assignment["AccountId"]
                    ]
                )
            )

        tooltip = "\nAWS Account/Role Assignments:\n"

        for account, pms in res.items():
            pm_string = ", ".join(pms)
            tooltip += f"{account}: {pm_string}\n"

        existing_tooltip = node.get("tooltip")

        node.set("tooltip", existing_tooltip + tooltip)

        node.set("image", f"{self.icon_dir}/aws.png")
        return node

    async def get_permissionset_name(self, arn: str):
        return self.sso.describe_permission_set(
            InstanceArn=self.sso_instance_arn, PermissionSetArn=arn
        )["PermissionSet"]["Name"]
